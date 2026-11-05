from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Signal:
    symbol: str
    action: Literal["BUY", "SELL", "HOLD"]
    score: float
    price: float
    stop_price: float | None
    target_price: float | None
    explanation: str


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    window = changes[-period:]
    average_gain = sum(max(change, 0) for change in window) / period
    average_loss = sum(max(-change, 0) for change in window) / period
    if average_loss == 0:
        return 100.0
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def atr(bars: list[Bar], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    ranges: list[float] = []
    for index in range(1, len(bars)):
        current = bars[index]
        previous_close = bars[index - 1].close
        ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous_close),
                abs(current.low - previous_close),
            )
        )
    window = ranges[-period:]
    return sum(window) / len(window)


class TrendMomentumStrategy:
    """Explainable swing-trading baseline evaluated on hourly bars."""

    minimum_bars = 60

    def evaluate(
        self,
        symbol: str,
        bars: list[Bar],
        stop_atr_multiple: float = 2.0,
        target_atr_multiple: float = 3.0,
    ) -> Signal:
        if len(bars) < self.minimum_bars:
            price = bars[-1].close if bars else 0.0
            return Signal(symbol, "HOLD", 0, price, None, None, "Not enough hourly history")

        closes = [bar.close for bar in bars]
        volumes = [bar.volume for bar in bars]
        fast = ema(closes, 20)[-1]
        slow = ema(closes, 50)[-1]
        current_rsi = rsi(closes)
        current_atr = atr(bars)
        price = closes[-1]
        momentum = price / closes[-6] - 1
        average_volume = sum(volumes[-20:]) / 20
        volume_ratio = volumes[-1] / average_volume if average_volume else 0
        trend_gap = (fast / slow - 1) if slow else 0

        entry_rules = {
            "uptrend": fast > slow,
            "above fast average": price > fast,
            "healthy momentum": momentum > 0,
            "RSI between 50 and 70": 50 <= current_rsi <= 70,
            "adequate volume": volume_ratio >= 0.70,
        }
        score = max(
            0,
            min(
                100,
                50
                + trend_gap * 1000
                + momentum * 500
                + (10 - abs(60 - current_rsi))
                + min(volume_ratio, 2) * 5,
            ),
        )

        if all(entry_rules.values()) and current_atr > 0:
            stop = max(0.01, price - stop_atr_multiple * current_atr)
            target = price + target_atr_multiple * current_atr
            explanation = (
                f"Hourly uptrend confirmed; RSI {current_rsi:.1f}, "
                f"5-hour momentum {momentum:.1%}, volume {volume_ratio:.1f}x average."
            )
            return Signal(symbol, "BUY", round(score, 2), price, stop, target, explanation)

        exit_reasons: list[str] = []
        if fast < slow:
            exit_reasons.append("20-hour EMA fell below 50-hour EMA")
        if current_rsi < 42:
            exit_reasons.append(f"RSI weakened to {current_rsi:.1f}")
        if price < fast * 0.985:
            exit_reasons.append("price is materially below the fast average")
        if exit_reasons:
            return Signal(
                symbol, "SELL", round(score, 2), price, None, None, "; ".join(exit_reasons)
            )

        missing = ", ".join(name for name, passed in entry_rules.items() if not passed)
        return Signal(
            symbol,
            "HOLD",
            round(score, 2),
            price,
            None,
            None,
            f"No entry: {missing}.",
        )
