from dataclasses import dataclass


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str | None = None


def virtual_equity(
    account_equity: float, baseline_account_equity: float, capital_cap: float
) -> float:
    """Track bot performance against a capped allocation, even in a $100k paper account."""
    return capital_cap + (account_equity - baseline_account_equity)


def check_circuit_breakers(
    *,
    account_equity: float,
    day_start_account_equity: float,
    virtual_equity_value: float,
    peak_virtual_equity: float,
    capital_cap: float,
    max_daily_loss_pct: float,
    max_drawdown_pct: float,
) -> RiskDecision:
    daily_loss = day_start_account_equity - account_equity
    if daily_loss >= capital_cap * max_daily_loss_pct:
        return RiskDecision(False, f"Daily loss limit reached (${daily_loss:.2f})")
    drawdown = 1 - virtual_equity_value / peak_virtual_equity if peak_virtual_equity > 0 else 0
    if drawdown >= max_drawdown_pct:
        return RiskDecision(False, f"Maximum drawdown reached ({drawdown:.1%})")
    if virtual_equity_value <= capital_cap * 0.50:
        return RiskDecision(False, "Virtual allocation has lost 50%")
    return RiskDecision(True)


def size_position(
    *,
    virtual_equity_value: float,
    price: float,
    stop_price: float,
    max_position_pct: float,
    risk_per_trade_pct: float,
) -> float:
    if price <= 0 or stop_price >= price:
        return 0
    risk_budget = virtual_equity_value * risk_per_trade_pct
    stop_fraction = (price - stop_price) / price
    risk_sized_notional = risk_budget / stop_fraction
    concentration_cap = virtual_equity_value * max_position_pct
    return round(max(0, min(risk_sized_notional, concentration_cap)), 2)
