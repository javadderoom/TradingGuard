from typing import List, Dict, Any
from hitl.backtest.evaluator import evaluate_council_decision


def test_default_max_risk_remains_12():
    bars = [
        {"time": 60, "open": 4000.0, "high": 4001.0, "low": 3999.0, "close": 4000.0},
        {"time": 120, "open": 3999.0, "high": 4000.0, "low": 3970.0, "close": 3975.0},
    ]
    res = evaluate_council_decision(
        {"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3975.0, "tp": 4050.0, "lot": 0.01},
        bars,
        symbol="XAUUSD_o",
        spread_pts=0.2,
        commission_usd=0.0,
        target_rr_cap=None,
    )
    assert res["status"] == "LOSS"
    assert res["realized_pnl_usd"] == -12.0


def test_20_dollar_risk_cap_and_uncapped_human_rr():
    bars_loss = [
        {"time": 60, "open": 4000.0, "high": 4001.0, "low": 3999.0, "close": 4000.0},
        {"time": 120, "open": 3999.0, "high": 4000.0, "low": 3965.0, "close": 3968.0},
    ]
    res_20 = evaluate_council_decision(
        {"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3975.0, "tp": 4050.0, "lot": 0.01},
        bars_loss,
        symbol="XAUUSD_o",
        spread_pts=0.2,
        commission_usd=0.0,
        target_rr_cap=None,
        max_risk_usd=20.0,
    )
    assert res_20["status"] == "LOSS"
    assert res_20["realized_pnl_usd"] == -20.0

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
