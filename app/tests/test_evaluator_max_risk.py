import pytest
from hitl.backtest.evaluator import evaluate_council_decision


def test_default_max_risk_honest_rejection_and_clamping():
    bars = [
        {"time": 60, "open": 4000.0, "high": 4001.0, "low": 3999.0, "close": 4000.0},
        {"time": 120, "open": 3999.0, "high": 4000.0, "low": 3970.0, "close": 3975.0},
    ]
    # By default, reject_over_risk=True rejects orders exceeding $12 cap on 0.01 lot
    res_reject = evaluate_council_decision(
        {"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3975.0, "tp": 4050.0, "lot": 0.01},
        bars,
        symbol="XAUUSD_o",
        spread_pts=0.2,
        commission_usd=0.0,
        target_rr_cap=None,
    )
    assert res_reject["status"] == "REJECTED_RISK_CAP"
    assert res_reject["realized_pnl_usd"] == 0.0

    # With reject_over_risk=False, clamps loss to max_risk_usd
    res_clamp = evaluate_council_decision(
        {"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3975.0, "tp": 4050.0, "lot": 0.01},
        bars,
        symbol="XAUUSD_o",
        spread_pts=0.2,
        commission_usd=0.0,
        target_rr_cap=None,
        reject_over_risk=False,
    )
    assert res_clamp["status"] == "LOSS"
    assert res_clamp["realized_pnl_usd"] == -12.0


def test_20_dollar_risk_cap_and_uncapped_human_rr():
    bars_loss = [
        {"time": 60, "open": 4000.0, "high": 4001.0, "low": 3999.0, "close": 4000.0},
        {"time": 120, "open": 3999.0, "high": 4000.0, "low": 3965.0, "close": 3968.0},
    ]
    # $25 risk with max_risk_usd=20.0 and reject_over_risk=False clamps to -20.0
    res_20 = evaluate_council_decision(
        {"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3975.0, "tp": 4050.0, "lot": 0.01},
        bars_loss,
        symbol="XAUUSD_o",
        spread_pts=0.2,
        commission_usd=0.0,
        target_rr_cap=None,
        max_risk_usd=20.0,
        reject_over_risk=False,
    )
    assert res_20["status"] == "LOSS"
    assert res_20["realized_pnl_usd"] == -20.0

    # With reject_over_risk=True, it rejects
    res_20_rej = evaluate_council_decision(
        {"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3975.0, "tp": 4050.0, "lot": 0.01},
        bars_loss,
        symbol="XAUUSD_o",
        spread_pts=0.2,
        commission_usd=0.0,
        target_rr_cap=None,
        max_risk_usd=20.0,
        reject_over_risk=True,
    )
    assert res_20_rej["status"] == "REJECTED_RISK_CAP"

    bars_win = [
        {"time": 60, "open": 4000.0, "high": 4001.0, "low": 3999.0, "close": 4000.0},
        {"time": 120, "open": 4000.0, "high": 4135.0, "low": 3999.0, "close": 4130.0},
    ]
    res_uncapped = evaluate_council_decision(
        {"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3970.0, "tp": 4135.0, "lot": 0.01},
        bars_win,
        symbol="XAUUSD_o",
        spread_pts=0.2,
        commission_usd=0.0,
        target_rr_cap=None,
        max_risk_usd=None,
    )
    assert res_uncapped["status"] == "WIN"
    assert res_uncapped["rr_realized"] == 4.5


def test_sell_order_max_risk_cap_and_uncapped():
    bars_loss = [
        {"time": 60, "open": 4000.0, "high": 4001.0, "low": 3999.0, "close": 4000.0},
        {"time": 120, "open": 4001.0, "high": 4030.0, "low": 4000.0, "close": 4028.0},
    ]
    res_20 = evaluate_council_decision(
        {"decision": "SELL_LIMIT", "entry": 4000.0, "sl": 4025.0, "tp": 3950.0, "lot": 0.01},
        bars_loss,
        symbol="XAUUSD_o",
        spread_pts=0.2,
        commission_usd=0.0,
        target_rr_cap=None,
        max_risk_usd=20.0,
        reject_over_risk=False,
    )
    assert res_20["status"] == "LOSS"
    assert res_20["realized_pnl_usd"] == -20.0

    res_uncapped = evaluate_council_decision(
        {"decision": "SELL_LIMIT", "entry": 4000.0, "sl": 4025.0, "tp": 3950.0, "lot": 0.01},
        bars_loss,
        symbol="XAUUSD_o",
        spread_pts=0.2,
        commission_usd=0.0,
        target_rr_cap=None,
        max_risk_usd=None,
    )
    assert res_uncapped["status"] == "LOSS"
    assert res_uncapped["realized_pnl_usd"] == -25.0


def test_non_positive_max_risk_usd_raises_value_error():
    bars = [
        {"time": 60, "open": 4000.0, "high": 4001.0, "low": 3999.0, "close": 4000.0},
    ]
    with pytest.raises(ValueError, match="max_risk_usd must be positive when specified"):
        evaluate_council_decision(
            {"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3975.0, "tp": 4050.0, "lot": 0.01},
            bars,
            symbol="XAUUSD_o",
            max_risk_usd=0.0,
        )

    with pytest.raises(ValueError, match="max_risk_usd must be positive when specified"):
        evaluate_council_decision(
            {"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3975.0, "tp": 4050.0, "lot": 0.01},
            bars,
            symbol="XAUUSD_o",
            max_risk_usd=-5.0,
        )
