from datetime import UTC, datetime, timedelta

from app.strategy import Bar, TrendMomentumStrategy, atr, ema, rsi


def make_trending_bars(count: int = 90) -> list[Bar]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = []
    price = 100.0
    for index in range(count):
        price += 0.4 if index % 2 == 0 else -0.2
        bars.append(
            Bar(
                timestamp=start + timedelta(hours=index),
                open=price - 0.15,
                high=price + 0.6,
                low=price - 0.6,
                close=price,
                volume=1_000_000,
            )
        )
    return bars


def test_indicators_are_well_formed():
    values = [float(value) for value in range(1, 80)]
    assert len(ema(values, 20)) == len(values)
    assert rsi(values) == 100
    assert atr(make_trending_bars()) > 0


def test_strategy_identifies_healthy_uptrend():
    signal = TrendMomentumStrategy().evaluate("TEST", make_trending_bars())
    assert signal.action == "BUY"
    assert signal.stop_price < signal.price < signal.target_price
    assert "uptrend" in signal.explanation


def test_strategy_waits_for_enough_history():
    signal = TrendMomentumStrategy().evaluate("TEST", make_trending_bars(20))
    assert signal.action == "HOLD"
    assert signal.score == 0
