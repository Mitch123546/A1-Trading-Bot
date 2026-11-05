from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.models import TradingSettings
from app.risk import size_position
from app.strategy import Bar, TrendMomentumStrategy


@dataclass
class SimulatedPosition:
    quantity: float
    entry_price: float
    stop_price: float
    target_price: float
    opened_at: Any


def run_backtest(bars_by_symbol: dict[str, list[Bar]], settings: TradingSettings) -> dict[str, Any]:
    """Simple event-driven portfolio test with configurable slippage and no look-ahead."""
    strategy = TrendMomentumStrategy()
    by_time: dict[Any, list[tuple[str, int]]] = {}
    for symbol, bars in bars_by_symbol.items():
        for index, bar in enumerate(bars):
            by_time.setdefault(bar.timestamp, []).append((symbol, index))

    cash = settings.capital_cap
    positions: dict[str, SimulatedPosition] = {}
    latest_prices: dict[str, float] = {}
    equity_curve: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    slip = settings.slippage_bps / 10_000

    for timestamp in sorted(by_time):
        candidates = []
        for symbol, index in by_time[timestamp]:
            history = bars_by_symbol[symbol][: index + 1]
            bar = history[-1]
            latest_prices[symbol] = bar.close
            signal = strategy.evaluate(
                symbol, history, settings.stop_atr_multiple, settings.target_atr_multiple
            )

            position = positions.get(symbol)
            if position:
                held_long_enough = timestamp - position.opened_at >= timedelta(
                    hours=settings.min_hold_hours
                )
                reason = None
                exit_price = bar.close
                if bar.low <= position.stop_price:
                    reason, exit_price = "stop", position.stop_price
                elif bar.high >= position.target_price:
                    reason, exit_price = "target", position.target_price
                elif signal.action == "SELL" and held_long_enough:
                    reason = "signal"
                if reason:
                    fill = exit_price * (1 - slip)
                    proceeds = fill * position.quantity
                    cash += proceeds
                    pnl = proceeds - position.entry_price * position.quantity
                    trades.append(
                        {
                            "symbol": symbol,
                            "side": "SELL",
                            "price": round(fill, 4),
                            "pnl": round(pnl, 2),
                            "reason": reason,
                            "timestamp": timestamp.isoformat(),
                        }
                    )
                    del positions[symbol]
            elif signal.action == "BUY":
                candidates.append(signal)

        marked_equity = cash + sum(
            position.quantity * latest_prices.get(symbol, position.entry_price)
            for symbol, position in positions.items()
        )
        for signal in sorted(candidates, key=lambda item: item.score, reverse=True):
            if len(positions) >= settings.max_positions or signal.symbol in positions:
                continue
            notional = size_position(
                virtual_equity_value=marked_equity,
                price=signal.price,
                stop_price=signal.stop_price or signal.price,
                max_position_pct=settings.max_position_pct,
                risk_per_trade_pct=settings.risk_per_trade_pct,
            )
            notional = min(notional, cash)
            if notional < 10:
                continue
            fill = signal.price * (1 + slip)
            quantity = notional / fill
            cash -= quantity * fill
            positions[signal.symbol] = SimulatedPosition(
                quantity, fill, signal.stop_price or fill, signal.target_price or fill, timestamp
            )
            trades.append(
                {
                    "symbol": signal.symbol,
                    "side": "BUY",
                    "price": round(fill, 4),
                    "pnl": None,
                    "reason": "signal",
                    "timestamp": timestamp.isoformat(),
                }
            )

        equity = cash + sum(
            position.quantity * latest_prices.get(symbol, position.entry_price)
            for symbol, position in positions.items()
        )
        if not equity_curve or timestamp.date() != equity_curve[-1]["date"]:
            equity_curve.append({"date": timestamp.date(), "equity": round(equity, 2)})
        else:
            equity_curve[-1]["equity"] = round(equity, 2)

    final_equity = cash + sum(
        position.quantity * latest_prices.get(symbol, position.entry_price)
        for symbol, position in positions.items()
    )
    closed = [trade for trade in trades if trade["side"] == "SELL"]
    winners = [trade for trade in closed if (trade["pnl"] or 0) > 0]
    peak = settings.capital_cap
    max_drawdown = 0.0
    for point in equity_curve:
        peak = max(peak, point["equity"])
        max_drawdown = max(max_drawdown, 1 - point["equity"] / peak)

    return {
        "starting_equity": settings.capital_cap,
        "ending_equity": round(final_equity, 2),
        "return_pct": round((final_equity / settings.capital_cap - 1) * 100, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "closed_trades": len(closed),
        "win_rate_pct": round(len(winners) / len(closed) * 100, 2) if closed else 0,
        "slippage_bps": settings.slippage_bps,
        "commission_assumption": 0,
        "equity_curve": [
            {"date": point["date"].isoformat(), "equity": point["equity"]} for point in equity_curve
        ],
        "recent_trades": trades[-100:],
        "disclaimer": "Historical simulation using IEX data; it does not predict future results.",
    }
