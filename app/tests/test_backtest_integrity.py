"""
TradingGuard Anti-Cheat Pytest Suite - Backtesting Integrity & Causality Verification
Verifies:
1. Future-Scramble Invariance (Zero-Lookahead Mathematical Proof)
2. Intrabar Conflict & Fill-Bar SL Blow-Through Resolution (Pessimistic Mandate)
3. Risk/Reward Symmetry & Honest Over-Risk Rejection
4. AST Custom-Simulator Linter (Enforces Single Simulator Mandate)
5. Causal Data Slicer Bar-Close Visibility & T-1 D1 Indexing
6. Chronological Portfolio Event Queue Drawdown & Concurrency Gating
"""

import ast
import os
import unittest
from pathlib import Path
from typing import Any, Dict, List
import pytest

from hitl.backtest.causal_feed import (
    CausalDataFeed,
    PortfolioEventQueue,
    get_causal_slice,
    get_causal_d1_slice,
    convert_epoch_to_session_context,
)
from hitl.backtest.evaluator import evaluate_council_decision
from hitl.backtest.fast_screener import screen_ict_session


class TestBacktestIntegrity(unittest.TestCase):
    """Unittest harness for Backtest Integrity verification."""

    def test_future_scramble_invariance(self):
        test_future_scramble_invariance()

    def test_intrabar_conflict_and_fill_bar_blow_through(self):
        test_intrabar_conflict_and_fill_bar_blow_through()

    def test_risk_reward_symmetry_and_over_risk_rejection(self):
        test_risk_reward_symmetry_and_over_risk_rejection()

    def test_ast_custom_simulator_linter(self):
        test_ast_custom_simulator_linter()

    def test_causal_data_slicer_bar_close_visibility(self):
        test_causal_data_slicer_bar_close_visibility()

    def test_chronological_portfolio_event_queue(self):
        test_chronological_portfolio_event_queue()



def test_future_scramble_invariance():
    """
    Zero-Lookahead Mathematical Proof:
    Mutating all future bars after decision timestamp T with +1000% spikes and -90% crashes
    must produce 100% byte-for-byte identical signals, entries, SLs, and TPs at T.
    """
    base_ts = 1772618400  # 2026-03-05 10:00:00 UTC (EET 12:00)
    # Generate 100 clean 5M bars
    bars_5m = []
    p = 2000.0
    for i in range(100):
        t = base_ts + i * 300
        bars_5m.append({
            "time": t,
            "open": p,
            "high": p + 2.0,
            "low": p - 2.0,
            "close": p + 0.5,
            "tick_volume": 100
        })
        p += 0.5

    # Generate 40 clean 1H bars
    bars_1h = []
    p_h = 2000.0
    for i in range(40):
        t = base_ts + i * 3600
        bars_1h.append({
            "time": t,
            "open": p_h,
            "high": p_h + 8.0,
            "low": p_h - 8.0,
            "close": p_h + 2.0,
            "tick_volume": 1000
        })
        p_h += 2.0

    # Generate 10 clean D1 bars
    bars_1d = []
    p_d = 1950.0
    for i in range(10):
        t = base_ts + i * 86400
        bars_1d.append({
            "time": t,
            "open": p_d,
            "high": p_d + 30.0,
            "low": p_d - 10.0,
            "close": p_d + 15.0,
            "tick_volume": 10000
        })
        p_d += 10.0

    # Baseline evaluation at bar 80
    decision_ts = bars_5m[80]["time"] + 300  # Exactly when bar 80 closes
    slice_5m_clean = get_causal_slice(bars_5m, decision_ts, tf_seconds=300)
    slice_1h_clean = get_causal_slice(bars_1h, decision_ts, tf_seconds=3600)
    slice_1d_clean = get_causal_d1_slice(bars_1d, decision_ts)

    res_clean = screen_ict_session(
        slice_5m_clean,
        slice_1h_clean,
        "XAUUSD",
        11,
        bars_1d=slice_1d_clean,
        closed_bars_only=True
    )

    # Future-Scramble: Create copy of data with extreme fantasy spikes after decision_ts
    scrambled_5m = [dict(b) for b in bars_5m]
    for b in scrambled_5m:
        if b["time"] >= decision_ts:
            b["open"] *= 10.0
            b["high"] *= 15.0
            b["low"] *= 0.1
            b["close"] *= 12.0

    scrambled_1h = [dict(b) for b in bars_1h]
    for b in scrambled_1h:
        if b["time"] >= decision_ts:
            b["open"] *= 10.0
            b["high"] *= 15.0
            b["low"] *= 0.1
            b["close"] *= 12.0

    scrambled_1d = [dict(b) for b in bars_1d]
    for b in scrambled_1d:
        if b["time"] + 86400 > decision_ts:
            b["open"] *= 10.0
            b["high"] *= 15.0
            b["low"] *= 0.1
            b["close"] *= 12.0

    # Slice the scrambled data causally at decision_ts
    slice_5m_scrambled = get_causal_slice(scrambled_5m, decision_ts, tf_seconds=300)
    slice_1h_scrambled = get_causal_slice(scrambled_1h, decision_ts, tf_seconds=3600)
    slice_1d_scrambled = get_causal_d1_slice(scrambled_1d, decision_ts)

    res_scrambled = screen_ict_session(
        slice_5m_scrambled,
        slice_1h_scrambled,
        "XAUUSD",
        11,
        bars_1d=slice_1d_scrambled,
        closed_bars_only=True
    )

    # Invariance Assertion: Byte-for-byte identical output
    assert res_clean["has_setup"] == res_scrambled["has_setup"]
    assert res_clean["setup_type"] == res_scrambled["setup_type"]
    assert res_clean["signal_bar_time"] == res_scrambled["signal_bar_time"]
    assert res_clean.get("entry") == res_scrambled.get("entry")
    assert res_clean.get("sl") == res_scrambled.get("sl")
    assert res_clean.get("tp") == res_scrambled.get("tp")


def test_intrabar_conflict_and_fill_bar_blow_through():
    """
    TradingGuard Pessimistic Mandate:
    When an order fills at M1 bar idx, and that exact same bar touches Stop Loss,
    it must register as LOSS immediately, granting ZERO minutes of SL immunity.
    """
    decision = {
        "decision": "BUY",
        "entry": 2000.0,
        "sl": 1995.0,
        "tp": 2015.0,
        "lot": 0.01
    }

    # Bar 0: Touches entry (1998 <= 2000) AND blows through SL (1993 <= 1995) within the same minute
    violent_fill_bar = {
        "time": 1772618400,
        "open": 2002.0,
        "high": 2003.0,
        "low": 1992.0,   # Touches both Entry and SL!
        "close": 1993.0,
        "spread": 22
    }

    # Subsequent bars that would have hit TP if immunity was granted
    subsequent_tp_bars = [
        {"time": 1772618460, "open": 1994.0, "high": 2020.0, "low": 1994.0, "close": 2018.0, "spread": 22}
    ]

    forward_bars = [violent_fill_bar] + subsequent_tp_bars
    res = evaluate_council_decision(decision, forward_bars, symbol="XAUUSD")

    assert res["status"] == "LOSS", f"Expected LOSS on same-bar blow-through, got {res['status']}"
    assert res["fill_minute"] == 0
    assert res["exit_minute"] == 0
    assert res["realized_pnl_usd"] < 0.0
    assert "same-bar blow-through" in res["notes"]


def test_risk_reward_symmetry_and_over_risk_rejection():
    """
    Risk/Reward Symmetry:
    An order with a wide stop (> $12.00 at 0.01 lot) must return REJECTED_RISK_CAP
    with 0.0 PnL, never paying a $70 win while clamping losses to $12.
    """
    # 25-point Gold stop = $25.00 risk on 0.01 lot (exceeds $12.00 cap)
    wide_stop_decision = {
        "decision": "BUY",
        "entry": 2000.0,
        "sl": 1975.0,   # $25.00 risk
        "tp": 2075.0,   # $75.00 target
        "lot": 0.01
    }

    # Bar goes straight to TP
    winning_bars = [
        {"time": 1772618400, "open": 2000.0, "high": 2080.0, "low": 1999.0, "close": 2076.0, "spread": 22}
    ]

    # With reject_over_risk=True (Default Canonical Mode):
    res_rejected = evaluate_council_decision(
        wide_stop_decision,
        winning_bars,
        symbol="XAUUSD",
        max_risk_usd=12.0,
        reject_over_risk=True
    )
    assert res_rejected["status"] == "REJECTED_RISK_CAP"
    assert res_rejected["realized_pnl_usd"] == 0.0
    assert "exceeds $12.00 ceiling" in res_rejected["notes"]


def test_ast_custom_simulator_linter():
    """
    Single Simulator Mandate:
    Scans all Python files in hitl/backtest/.
    Fails if any active/unmarked file contains an ad-hoc simulation loop
    (checking hit_sl or hit_tp) instead of routing through evaluator.py.
    Legacy files must be explicitly marked with DEPRECATED_UNVERIFIABLE.
    """
    backtest_dir = Path("hitl/backtest")
    assert backtest_dir.exists(), "hitl/backtest directory not found"

    violations = []
    for py_file in backtest_dir.glob("*.py"):
        if py_file.name == "evaluator.py":
            continue

        code = py_file.read_text(encoding="utf-8", errors="ignore")
        if "DEPRECATED_UNVERIFIABLE" in code:
            continue

        # Parse AST to inspect for trade simulation loops
        try:
            tree = ast.parse(code, filename=str(py_file))
        except SyntaxError:
            continue

        has_custom_sim = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in ("hit_sl", "hit_tp"):
                has_custom_sim = True
                break

        if has_custom_sim:
            violations.append(py_file.name)

    assert not violations, (
        f"Custom trade simulator loop detected in non-deprecated files: {violations}. "
        "All backtest simulations must route through hitl/backtest/evaluator.py "
        "or be marked # STATUS: DEPRECATED_UNVERIFIABLE."
    )


def test_causal_data_slicer_bar_close_visibility():
    """
    Strict Bar-Close Visibility:
    Verifies that get_causal_slice excludes forming bars and get_causal_d1_slice
    guarantees slice[-1] is strictly Prior Day (T-1).
    """
    # 5M bar opens at 1000, closes at 1300
    m5_bar = {"time": 1000, "open": 100, "high": 102, "low": 98, "close": 101}

    # At t=1299: forming -> MUST NOT be visible
    assert len(get_causal_slice([m5_bar], decision_ts=1299, tf_seconds=300)) == 0

    # At t=1300: just closed -> MUST be visible
    slice_closed = get_causal_slice([m5_bar], decision_ts=1300, tf_seconds=300)
    assert len(slice_closed) == 1
    assert slice_closed[0]["time"] == 1000

    # D1 bar opens at 1772582400 (00:00:00 UTC), closes at 1772668800 (24:00:00 UTC)
    d1_bar = {"time": 1772582400, "open": 2000, "high": 2020, "low": 1990, "close": 2010}

    # At midday (1772625600): forming -> MUST NOT be in causal D1 slice
    assert len(get_causal_d1_slice([d1_bar], decision_ts=1772625600)) == 0

    # At day close + 1s: completed -> visible as Prior Day
    d1_slice = get_causal_d1_slice([d1_bar], decision_ts=1772668801)
    assert len(d1_slice) == 1
    assert d1_slice[-1]["time"] == 1772582400


def test_chronological_portfolio_event_queue():
    """
    Verifies that PortfolioEventQueue:
    1. Only counts trades as active while filled and not yet exited.
    2. Realized daily PnL updates ONLY after an order's exit timestamp has elapsed.
    3. Triggers circuit breaker and concurrency gating accurately.
    """
    queue = PortfolioEventQueue(max_concurrent=2, max_daily_dd_usd=34.0)

    # Trade 1: fills at 1000, exits at 1500 with -$20.00 loss
    queue.record_trade(
        trade_id="T1",
        symbol="XAUUSD",
        placed_ts=900,
        fill_ts=1000,
        exit_ts=1500,
        status="LOSS",
        risk_usd=12.0,
        realized_pnl_usd=-20.0,
        date_str="2026-03-05"
    )

    # Trade 2: fills at 1200, exits at 1800 with -$15.00 loss
    queue.record_trade(
        trade_id="T2",
        symbol="GBPUSD",
        placed_ts=1100,
        fill_ts=1200,
        exit_ts=1800,
        status="LOSS",
        risk_usd=12.0,
        realized_pnl_usd=-15.0,
        date_str="2026-03-05"
    )

    # At T=1100: Trade 1 is open (T2 has not filled yet)
    open_1100 = queue.get_open_trades_at(1100)
    assert len(open_1100) == 1
    assert open_1100[0]["trade_id"] == "T1"
    # Realized PnL is still $0.00 because neither trade has exited
    assert queue.get_realized_daily_pnl_usd(1100, "2026-03-05") == 0.0

    # At T=1300: Both T1 and T2 are open -> max concurrent reached (2/2)
    open_1300 = queue.get_open_trades_at(1300)
    assert len(open_1300) == 2
    can_open, reason = queue.can_open_trade(1300, new_risk_usd=12.0, date_str="2026-03-05")
    assert not can_open
    assert "Max concurrent trades reached" in reason

    # At T=1600: T1 has exited (-$20 realized), T2 is still open
    assert queue.get_realized_daily_pnl_usd(1600, "2026-03-05") == -20.0
    open_1600 = queue.get_open_trades_at(1600)
    assert len(open_1600) == 1
    assert open_1600[0]["trade_id"] == "T2"

    # At T=1900: Both trades have exited -> cumulative realized loss = -$35.00
    assert queue.get_realized_daily_pnl_usd(1900, "2026-03-05") == -35.0
    # Circuit breaker breached (-$35 <= -$34 ceiling)
    can_open_cb, reason_cb = queue.can_open_trade(1900, new_risk_usd=12.0, date_str="2026-03-05")
    assert not can_open_cb
    assert "Daily circuit breaker breached" in reason_cb
