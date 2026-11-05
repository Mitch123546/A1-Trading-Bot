import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.alpaca_adapter import AlpacaPaperBroker
from app.backtest import run_backtest
from app.config import Settings
from app.database import Database, dump_public_settings, utc_now
from app.notifications import DiscordNotifier
from app.risk import check_circuit_breakers, size_position, virtual_equity
from app.strategy import TrendMomentumStrategy

logger = logging.getLogger(__name__)
NEW_YORK = ZoneInfo("America/New_York")


class TradingEngine:
    def __init__(self, config: Settings, database: Database):
        self.config = config
        self.database = database
        self.strategy = TrendMomentumStrategy()
        self.notifier = DiscordNotifier(config)
        self._broker_instance: AlpacaPaperBroker | None = None
        self._cycle_lock = threading.Lock()

    @property
    def broker(self) -> AlpacaPaperBroker:
        if not self.config.credentials_configured:
            raise RuntimeError("Alpaca paper credentials are not configured in .env")
        if self._broker_instance is None:
            self._broker_instance = AlpacaPaperBroker(
                self.config.alpaca_api_key.get_secret_value(),
                self.config.alpaca_secret_key.get_secret_value(),
            )
        return self._broker_instance

    def test_connection(self) -> dict[str, Any]:
        account = self.broker.account()
        clock = self.broker.clock()
        return {
            "connected": True,
            "environment": "paper",
            "account_status": account["status"],
            "equity": account["equity"],
            "market_open": clock["is_open"],
        }

    def start(self) -> dict[str, Any]:
        if not self.config.secure_configuration:
            raise RuntimeError("Change DASHBOARD_PASSWORD and SESSION_SECRET in .env first")
        connection = self.test_connection()
        self.database.update_state(
            paused=False, emergency_stop=False, halt_reason=None, last_error=None
        )
        self.database.add_event("CONTROL", "Paper bot started")
        self.notifier.send(
            "Paper bot started", "The baseline strategy is now monitoring the market."
        )
        return connection

    def pause(self) -> None:
        self.database.update_state(paused=True)
        self.database.add_event(
            "CONTROL", "Paper bot paused; existing positions were left unchanged"
        )
        self.notifier.send("Paper bot paused", "No new automated orders will be submitted.")

    def emergency_stop(self) -> None:
        self.database.update_state(
            paused=True, emergency_stop=True, halt_reason="Manual emergency stop"
        )
        try:
            if self.config.credentials_configured:
                self.broker.cancel_all_orders()
        finally:
            self.database.add_event(
                "EMERGENCY", "Emergency stop engaged and all open orders canceled"
            )
            self.notifier.send(
                "Emergency stop",
                "Trading is halted and open orders were canceled. Positions were not liquidated.",
                urgent=True,
            )

    def resume_after_emergency(self) -> None:
        self.test_connection()
        self.database.update_state(
            paused=False, emergency_stop=False, halt_reason=None, last_error=None
        )
        self.database.add_event("CONTROL", "Emergency stop manually cleared; paper bot resumed")

    def scheduled_cycle(self) -> None:
        state = self.database.get_state()
        if state["paused"] or state["emergency_stop"]:
            return
        last_cycle = state.get("last_cycle_at")
        interval = self.database.get_settings().evaluation_minutes
        if last_cycle:
            elapsed = datetime.now(UTC) - datetime.fromisoformat(last_cycle)
            if elapsed < timedelta(minutes=interval):
                return
        self.run_cycle()

    def run_cycle(self) -> dict[str, Any]:
        if not self._cycle_lock.acquire(blocking=False):
            return {"skipped": True, "reason": "A cycle is already running"}
        try:
            return self._run_cycle()
        except Exception as exc:
            logger.exception("Trading cycle failed")
            message = f"{type(exc).__name__}: {exc}"
            self.database.update_state(paused=True, last_error=message)
            self.database.add_event("ERROR", f"Trading paused after an error: {message}")
            self.notifier.send("Trading cycle failed", message, urgent=True)
            raise
        finally:
            self._cycle_lock.release()

    def _run_cycle(self) -> dict[str, Any]:
        state = self.database.get_state()
        if state["paused"] or state["emergency_stop"]:
            return {"skipped": True, "reason": "Bot is paused"}

        clock = self.broker.clock()
        if not clock["is_open"]:
            self.database.update_state(last_cycle_at=utc_now(), last_error=None)
            return {"skipped": True, "reason": "Regular market is closed"}

        settings = self.database.get_settings()
        account = self.broker.account()
        equity = account["equity"]
        now_ny = datetime.now(NEW_YORK)
        day_key = now_ny.date().isoformat()

        baseline = state.get("baseline_account_equity")
        if baseline is None:
            baseline = equity
            self.database.update_state(baseline_account_equity=baseline)
        day_start = state.get("day_start_account_equity")
        if day_start is None or state.get("day_key") != day_key:
            day_start = equity
            self.database.update_state(day_start_account_equity=equity, day_key=day_key)

        virtual = virtual_equity(equity, baseline, settings.capital_cap)
        peak = max(state.get("peak_virtual_equity") or settings.capital_cap, virtual)
        self.database.update_state(peak_virtual_equity=peak)
        self.database.add_equity_snapshot(equity, virtual, account["cash"], account["buying_power"])

        risk = check_circuit_breakers(
            account_equity=equity,
            day_start_account_equity=day_start,
            virtual_equity_value=virtual,
            peak_virtual_equity=peak,
            capital_cap=settings.capital_cap,
            max_daily_loss_pct=settings.max_daily_loss_pct,
            max_drawdown_pct=settings.max_drawdown_pct,
        )
        if not risk.allowed:
            self.database.update_state(
                paused=True, emergency_stop=True, halt_reason=risk.reason, last_cycle_at=utc_now()
            )
            self.broker.cancel_all_orders()
            self.database.add_event("RISK_HALT", risk.reason or "Risk limit reached")
            self.notifier.send("Risk circuit breaker", risk.reason or "Risk halt", urgent=True)
            return {"halted": True, "reason": risk.reason}

        broker_positions = {item["symbol"]: item for item in self.broker.positions()}
        managed = self.database.managed_positions()
        symbols = list(dict.fromkeys(settings.watchlist + list(broker_positions)))
        bars_by_symbol = self.broker.hourly_bars(symbols)
        signals = []
        for symbol in symbols:
            signal = self.strategy.evaluate(
                symbol,
                bars_by_symbol.get(symbol, []),
                settings.stop_atr_multiple,
                settings.target_atr_multiple,
            )
            self.database.add_signal(signal)
            signals.append(signal)

        submitted: list[dict[str, Any]] = []
        for signal in signals:
            if signal.symbol not in broker_positions or signal.symbol not in managed:
                continue
            details = managed[signal.symbol]
            price = signal.price
            opened_at = datetime.fromisoformat(details["opened_at"])
            held_long_enough = datetime.now(UTC) - opened_at >= timedelta(
                hours=settings.min_hold_hours
            )
            reason = None
            if price <= details["stop_price"]:
                reason = f"software stop at ${details['stop_price']:.2f}"
            elif price >= details["target_price"]:
                reason = f"profit target at ${details['target_price']:.2f}"
            elif signal.action == "SELL" and held_long_enough:
                reason = signal.explanation
            if reason:
                order = self.broker.close_position(signal.symbol)
                self.database.remove_managed_position(signal.symbol)
                self.database.add_event(
                    "ORDER_SUBMITTED",
                    f"Sell submitted: {reason}",
                    symbol=signal.symbol,
                    side="SELL",
                    quantity=broker_positions[signal.symbol]["qty"],
                    price=price,
                    broker_order_id=order["id"],
                )
                submitted.append(order)
                self.notifier.send("Paper sell submitted", f"{signal.symbol}: {reason}")

        occupied = set(broker_positions) | set(managed)
        slots = max(0, settings.max_positions - len(occupied))
        time_to_close = clock["next_close"] - clock["timestamp"]
        may_open = time_to_close >= timedelta(minutes=30)
        if may_open and slots:
            candidates = sorted(
                (
                    signal
                    for signal in signals
                    if signal.action == "BUY" and signal.symbol not in occupied
                ),
                key=lambda item: item.score,
                reverse=True,
            )
            available_cash = min(account["cash"], max(0, virtual))
            for signal in candidates[:slots]:
                notional = size_position(
                    virtual_equity_value=virtual,
                    price=signal.price,
                    stop_price=signal.stop_price or signal.price,
                    max_position_pct=settings.max_position_pct,
                    risk_per_trade_pct=settings.risk_per_trade_pct,
                )
                notional = min(notional, available_cash)
                if notional < 10:
                    continue
                order = self.broker.submit_buy(signal.symbol, notional)
                self.database.manage_position(
                    signal.symbol,
                    signal.price,
                    signal.stop_price or signal.price,
                    signal.target_price or signal.price,
                )
                self.database.add_event(
                    "ORDER_SUBMITTED",
                    signal.explanation,
                    symbol=signal.symbol,
                    side="BUY",
                    notional=notional,
                    price=signal.price,
                    broker_order_id=order["id"],
                )
                submitted.append(order)
                available_cash -= notional
                self.notifier.send(
                    "Paper buy submitted",
                    f"{signal.symbol}: ${notional:.2f}. {signal.explanation}",
                )

        self.database.update_state(last_cycle_at=utc_now(), last_error=None)
        return {
            "completed": True,
            "signals_checked": len(signals),
            "orders_submitted": len(submitted),
            "virtual_equity": round(virtual, 2),
        }

    def dashboard_snapshot(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "environment": "PAPER ONLY",
            "state": self.database.get_state(),
            "settings": dump_public_settings(self.database.get_settings()),
            "credentials_configured": self.config.credentials_configured,
            "secure_configuration": self.config.secure_configuration,
            "equity_history": list(reversed(self.database.recent_rows("equity_snapshots", 200))),
            "signals": self.database.recent_rows("signals", 50),
            "events": self.database.recent_rows("trade_events", 100),
            "account": None,
            "positions": [],
            "orders": [],
            "market": None,
        }
        if self.config.credentials_configured:
            try:
                result["account"] = self.broker.account()
                result["positions"] = self.broker.positions()
                result["orders"] = self.broker.orders(30)
                result["market"] = self.broker.clock()
            except Exception as exc:
                result["connection_error"] = f"{type(exc).__name__}: {exc}"
        return result

    def backtest(self) -> dict[str, Any]:
        settings = self.database.get_settings()
        bars = self.broker.hourly_bars(settings.watchlist, days=180)
        result = run_backtest(bars, settings)
        self.database.add_event(
            "BACKTEST",
            f"Backtest completed: {result['return_pct']:.2f}% return, "
            f"{result['max_drawdown_pct']:.2f}% max drawdown",
        )
        return result
