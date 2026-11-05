from app.risk import check_circuit_breakers, size_position, virtual_equity


def test_virtual_allocation_uses_account_profit_and_loss():
    assert virtual_equity(99_950, 100_000, 2_000) == 1_950
    assert virtual_equity(100_075, 100_000, 2_000) == 2_075


def test_daily_loss_halts_against_capital_cap():
    decision = check_circuit_breakers(
        account_equity=99_939,
        day_start_account_equity=100_000,
        virtual_equity_value=1_939,
        peak_virtual_equity=2_000,
        capital_cap=2_000,
        max_daily_loss_pct=0.03,
        max_drawdown_pct=0.10,
    )
    assert not decision.allowed
    assert "Daily" in decision.reason


def test_position_sizing_uses_smaller_risk_or_concentration_limit():
    notional = size_position(
        virtual_equity_value=2_000,
        price=100,
        stop_price=95,
        max_position_pct=0.20,
        risk_per_trade_pct=0.01,
    )
    assert notional == 400
