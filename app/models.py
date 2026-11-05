from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DEFAULT_WATCHLIST = [
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "XLK",
    "XLF",
    "XLV",
    "XLI",
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
]


class TradingSettings(BaseModel):
    watchlist: list[str] = Field(default_factory=lambda: DEFAULT_WATCHLIST.copy())
    capital_cap: float = Field(2000, ge=100, le=1_000_000)
    evaluation_minutes: int = Field(15, ge=5, le=240)
    max_positions: int = Field(4, ge=1, le=20)
    max_position_pct: float = Field(0.20, ge=0.02, le=0.50)
    risk_per_trade_pct: float = Field(0.01, ge=0.001, le=0.05)
    max_daily_loss_pct: float = Field(0.03, ge=0.005, le=0.10)
    max_drawdown_pct: float = Field(0.10, ge=0.02, le=0.30)
    stop_atr_multiple: float = Field(2.0, ge=0.5, le=5)
    target_atr_multiple: float = Field(3.0, ge=1, le=10)
    min_hold_hours: int = Field(20, ge=0, le=720)
    slippage_bps: float = Field(2.0, ge=0, le=100)

    @field_validator("watchlist")
    @classmethod
    def clean_watchlist(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(item.strip().upper() for item in values if item.strip()))
        if not cleaned:
            raise ValueError("Watchlist must contain at least one symbol")
        if len(cleaned) > 50:
            raise ValueError("Watchlist is limited to 50 symbols")
        if any(not symbol.replace(".", "").isalnum() for symbol in cleaned):
            raise ValueError("Watchlist contains an invalid symbol")
        return cleaned


class LoginRequest(BaseModel):
    password: str


class ConfirmRequest(BaseModel):
    confirmation: str = ""


class BotState(BaseModel):
    paused: bool
    emergency_stop: bool
    last_cycle_at: datetime | None = None
    last_error: str | None = None
    halt_reason: str | None = None


class SignalRecord(BaseModel):
    symbol: str
    action: Literal["BUY", "SELL", "HOLD"]
    score: float
    price: float
    stop_price: float | None = None
    target_price: float | None = None
    explanation: str
    created_at: datetime
