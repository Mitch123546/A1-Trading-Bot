from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest

from app.strategy import Bar


class AlpacaPaperBroker:
    """Narrow broker adapter with an intentionally hard-coded paper environment."""

    def __init__(self, api_key: str, secret_key: str):
        self.trading = TradingClient(api_key, secret_key, paper=True)
        self.data = StockHistoricalDataClient(api_key, secret_key)

    def account(self) -> dict[str, Any]:
        account = self.trading.get_account()
        return {
            "id": str(account.id),
            "status": str(account.status),
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "portfolio_value": float(account.portfolio_value),
            "trading_blocked": bool(account.trading_blocked),
            "pattern_day_trader": bool(account.pattern_day_trader),
        }

    def clock(self) -> dict[str, Any]:
        clock = self.trading.get_clock()
        return {
            "is_open": bool(clock.is_open),
            "timestamp": clock.timestamp,
            "next_open": clock.next_open,
            "next_close": clock.next_close,
        }

    def positions(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": position.symbol,
                "qty": float(position.qty),
                "avg_entry_price": float(position.avg_entry_price),
                "market_value": float(position.market_value),
                "current_price": float(position.current_price),
                "unrealized_pl": float(position.unrealized_pl),
                "unrealized_plpc": float(position.unrealized_plpc),
                "side": str(position.side),
            }
            for position in self.trading.get_all_positions()
        ]

    def orders(self, limit: int = 50) -> list[dict[str, Any]]:
        request = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=limit, nested=True)
        orders = self.trading.get_orders(filter=request)
        return [
            {
                "id": str(order.id),
                "symbol": order.symbol,
                "side": str(order.side),
                "status": str(order.status),
                "type": str(order.type),
                "qty": float(order.qty) if order.qty is not None else None,
                "notional": float(order.notional) if order.notional is not None else None,
                "filled_qty": float(order.filled_qty or 0),
                "filled_avg_price": (
                    float(order.filled_avg_price) if order.filled_avg_price is not None else None
                ),
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
            }
            for order in orders
        ]

    def hourly_bars(self, symbols: list[str], days: int = 90) -> dict[str, list[Bar]]:
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Hour,
            start=datetime.now(UTC) - timedelta(days=days),
            end=datetime.now(UTC),
            feed=DataFeed.IEX,
        )
        bar_set = self.data.get_stock_bars(request)
        result: dict[str, list[Bar]] = {}
        for symbol in symbols:
            result[symbol] = [
                Bar(
                    timestamp=item.timestamp,
                    open=float(item.open),
                    high=float(item.high),
                    low=float(item.low),
                    close=float(item.close),
                    volume=float(item.volume),
                )
                for item in bar_set.data.get(symbol, [])
            ]
        return result

    def submit_buy(self, symbol: str, notional: float) -> dict[str, Any]:
        request = MarketOrderRequest(
            symbol=symbol,
            notional=round(notional, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            extended_hours=False,
            client_order_id=f"a1-baseline-{uuid4().hex[:20]}",
        )
        order = self.trading.submit_order(order_data=request)
        return {"id": str(order.id), "status": str(order.status), "symbol": symbol}

    def close_position(self, symbol: str) -> dict[str, Any]:
        order = self.trading.close_position(symbol)
        return {"id": str(order.id), "status": str(order.status), "symbol": symbol}

    def cancel_all_orders(self) -> None:
        self.trading.cancel_orders()
