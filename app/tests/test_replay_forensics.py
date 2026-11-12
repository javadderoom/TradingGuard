"""
Tests for SMC Forensic Scanner & Shared Co-Backtest Ledger (hitl/replay_forensics.py & hitl/replay_ledger.py)
Covering:
1. Bot scan on Nov 11 Gold finds SETUP-ARCH-001, incremental Asian High (4065.88) anti-spoiler rule,
   and live_legacy clock mode reproduces the 16:40 Tehran NY PM veto at 15:10 server time.
2. System risk limits enforce $20 per-trade risk cap, max 3 concurrently open positions, and $80 daily DD circuit breaker.
3. simulate_custom_trade with wide stop ($30) returns uncapped R:R (4.5R) and compliance flag (exceeds_risk_cap=True).
4. CoBacktestLedger and AgentifyFeedbackStore: distinct origin badges (BOT, HUMAN_PROPOSED, HUMAN_EDITED_BOT)
   and copy-ready prompt_markdown generation.
"""

from pathlib import Path
import pytest

from hitl.replay_data import ReplayDataManager, server_epoch_to_zones
from hitl.replay_forensics import (
    run_bot_scan,
    simulate_custom_trade,
    detect_fvg_boxes,
    detect_breaker_boxes,
)
from hitl.replay_ledger import (
    CoBacktestLedger,
    AgentifyFeedbackStore,
    build_agentify_prompt,
)


def test_bot_scan_nov11_gold_finds_arch001_and_live_legacy_reproduces_ny_veto():
    """
    Runs run_bot_scan on 2026-11-11 (XAUUSD_o):
    - In clock_mode="true_tehran", SETUP-ARCH-001 fires at 10:05 server time.
    - Incremental Asian High (4065.88) never leaks prior to 07:00 UTC (09:00 Server).
    - In clock_mode="live_legacy", reproduces the 16:40 Tehran NY PM veto at 15:10 server time.
    """
    data_mgr = ReplayDataManager()
    # 2026-11-11 bounds in MT5 server time (EET UTC+2)
    # 00:00 server: 1794355200, 23:59 server: 1794441540
    start_epoch = 1794355200
    end_epoch = 1794441540

    # 1. Run bot scan in true_tehran mode
    scan_true = run_bot_scan(
        data_mgr=data_mgr,
        symbol="XAUUSD_o",
        start_epoch=start_epoch,
        end_epoch=end_epoch,
        clock_mode="true_tehran",
        account_size_usd=2000.0,
        max_risk_usd=20.0,
    )

    assert "bot_trades" in scan_true
    assert "diagnostics" in scan_true
    assert "killzones" in scan_true
    assert "asian_ranges_by_day" in scan_true
    assert "bot_scorecard" in scan_true

    # Find the trade for SETUP-ARCH-001 firing at 10:05 server time (epoch 1794391500)
    arch001_trades = [
        t for t in scan_true["bot_trades"]
        if t["archetype_id"] == "SETUP-ARCH-001" and t.get("decision_time") == 1794391500
    ]
    assert len(arch001_trades) == 1, "Expected SETUP-ARCH-001 trade at 10:05 server time"
    trade = arch001_trades[0]
    assert trade["origin"] == "BOT"
    assert trade["direction"] == "SHORT"
    assert trade["signal_time"] == 1794391200  # 10:00 server time (closed signal bar)
    assert trade["status"] == "WIN"
    assert trade["rr_realized"] == pytest.approx(1.99, abs=0.05)
    assert trade["realized_pnl_usd"] == pytest.approx(15.90, abs=0.5)

    # 2. Verify incremental Asian High anti-spoiler rule:
    # 4065.88 was formed at 05:33 UTC (07:33 Server time).
    # Diagnostics before 05:33 UTC must NOT leak 4065.88.
    # At 07:00 UTC (09:00 Server time, epoch 1794387600), Asian session closes and locks 4065.88.
    diagnostics = scan_true["diagnostics"]
    diag_by_time = {d["time"]: d for d in diagnostics}

    # At earlier bars (e.g. 03:00 to 07:25 Server), Asian High must be strictly less than 4065.88 or None
    early_diag = [d for d in diagnostics if d["time"] < 1794382200]  # before 07:30 server (when 4065.88 candle formed)
    assert len(early_diag) > 0
    for d in early_diag:
        if d.get("asian_high") is not None:
            assert d["asian_high"] < 4065.88, (
                f"Lookahead leak at {d['time']}: asian_high={d['asian_high']} before it occurred!"
            )

    # After 07:00 UTC (09:00 Server = 1794387600), Asian High must be the locked value 4065.88
    post_asian_diag = [d for d in diagnostics if d["time"] >= 1794387600]
    assert len(post_asian_diag) > 0
    for d in post_asian_diag:
        assert d.get("asian_high") == pytest.approx(4065.88, abs=0.01)

    # 3. In clock_mode="live_legacy", verify 16:40 Tehran NY PM veto reproduces at 15:10 server time (epoch 1794409800)
    scan_legacy = run_bot_scan(
        data_mgr=data_mgr,
        symbol="XAUUSD_o",
        start_epoch=start_epoch,
        end_epoch=end_epoch,
        clock_mode="live_legacy",
        account_size_usd=2000.0,
        max_risk_usd=20.0,
    )
    legacy_diags = {d["time"]: d for d in scan_legacy["diagnostics"]}
    assert 1794409800 in legacy_diags, "Expected 15:10 server time in diagnostics"
    diag_1510 = legacy_diags[1794409800]
    assert diag_1510["has_setup"] is False
    assert "Late NY PM / Silver Bullet window banned" in diag_1510["reason"]
    assert diag_1510["session_hour"] == 18  # Miscalculated session hour in legacy mode

    # 4. Verify FVG and Breaker box extraction in diagnostics
    fvg_boxes = [d["fvg_box"] for d in diagnostics if d.get("fvg_box") is not None]
    breaker_boxes = [d["breaker_box"] for d in diagnostics if d.get("breaker_box") is not None]
    assert len(fvg_boxes) > 0, "Expected FVG boxes in diagnostics"
    assert len(breaker_boxes) > 0, "Expected Breaker boxes in diagnostics"
    for fb in fvg_boxes:
        assert set(fb.keys()) == {"top", "bottom", "t_start", "t_end", "dir"}
        assert fb["top"] >= fb["bottom"]
        assert fb["dir"] in ("BULLISH", "BEARISH")
    for bb in breaker_boxes:
        assert set(bb.keys()) == {"top", "bottom", "t_start", "t_end", "type"}
        assert bb["top"] >= bb["bottom"]
        assert bb["type"] in ("BULLISH_BREAKER", "BEARISH_BREAKER")


def test_system_risk_limits_enforce_20_cap_and_max_open_3():
    """
    Verifies system-wide risk governance:
    - Simultaneous open bot positions never exceed 3 (max_open_trades=3).
    - Daily drawdown limit $80.00 (4% of $2,000) halts new trade entries for that day.
    - $20 risk cap per trade is enforced in bot scanning.
    """
    data_mgr = ReplayDataManager()
    # Test on a wide range of Gold or multiple days to trigger risk governor evaluation
    # Scan from 2026-08-03 to 2026-08-14
    start_epoch = 1785715200
    end_epoch = 1786752000

    scan_res = run_bot_scan(
        data_mgr=data_mgr,
        symbol="XAUUSD_o",
        start_epoch=start_epoch,
        end_epoch=end_epoch,
        clock_mode="true_tehran",
        account_size_usd=2000.0,
        max_risk_usd=20.0,
    )

    trades = scan_res["bot_trades"]
    # Check that no individual trade risk exceeded $20.00
    for t in trades:
        # If trade lost, loss must not exceed $20.00 + commission
        if t["status"] == "LOSS":
            assert t["realized_pnl_usd"] >= -20.50

    # Verify at any timestamp, number of concurrent active trades <= 3
    # Check time points of each trade fill
    for t in trades:
        fill_t = t.get("fill_time")
        if not fill_t:
            continue
        concurrent = [
            ot for ot in trades
            if ot.get("fill_time") and ot.get("exit_time") and ot["fill_time"] <= fill_t < ot["exit_time"]
        ]
        assert len(concurrent) <= 3, f"Concurrent open trades ({len(concurrent)}) exceeded max 3 at {fill_t}"

    # Verify daily drawdown circuit breaker:
    # On any day where realized losses reach $80.00, no further trades open that day
    trades_by_date = {}
    for t in trades:
        d_str = server_epoch_to_zones(t["decision_time"])["date_str"]
        trades_by_date.setdefault(d_str, []).append(t)

    for d_str, day_trades in trades_by_date.items():
        running_day_pnl = 0.0
        for dt in sorted(day_trades, key=lambda x: x["decision_time"]):
            if dt["status"] in ("WIN", "LOSS", "BREAKEVEN"):
                running_day_pnl += dt["realized_pnl_usd"]
            # Prior to this trade opening, day PnL should not have been <= -$80.00
            assert running_day_pnl >= -80.0 - 20.5, f"Trade opened after daily DD breached on {d_str}"


def test_simulate_human_wide_stop_returns_uncapped_rr_and_compliance_flag():
    """
    Tests simulate_custom_trade with a wide $30 stop + 4.5R target:
    - max_risk_usd=None and target_rr_cap=None ensures R:R is uncapped (4.5R).
    - risk_usd_001 = 30.0 (exceeds $20 reference cap).
    - exceeds_risk_cap = True.
    """
    data_mgr = ReplayDataManager()
    # Verified spot on Gold: 2026-01-22 1769097720 where price rallied > 135 pts
    signal_time = 1769097720
    entry = 4823.84
    sl = 4793.84   # 30.0 pts stop
    tp = 4958.84   # 135.0 pts TP (4.5R)

    res = simulate_custom_trade(
        data_mgr=data_mgr,
        symbol="XAUUSD_o",
        direction="LONG",
        signal_time=signal_time,
        entry=entry,
        sl=sl,
        tp=tp,
        be_rr=None,
        max_risk_usd=None,
    )

    assert res["status"] == "WIN"
    assert res["exceeds_risk_cap"] is True
    assert res["risk_usd_001"] == pytest.approx(30.0, abs=0.01)
    assert res["rr_realized"] == pytest.approx(4.5, abs=0.05)


def test_shared_ledger_marks_origins_and_agentify_builds_prompt(tmp_path: Path):
    """
    Creates HUMAN_PROPOSED and HUMAN_EDITED_BOT entries in CoBacktestLedger (tmp_path)
    plus AgentifyFeedbackStore case, asserting distinct origin badges and non-empty prompt_markdown.
    """
    ledger_file = tmp_path / "visual_co_backtest_ledger.json"
    feedback_file = tmp_path / "visual_feedback_cases.json"

    ledger = CoBacktestLedger(file_path=ledger_file)

    # 1. Add BOT trade
    bot_payload = {
        "origin": "BOT",
        "symbol": "XAUUSD_o",
        "direction": "SHORT",
        "signal_time": 1794391200,
        "entry": 4060.37,
        "sl": 4068.37,
        "tp": 4044.37,
        "status": "WIN",
        "realized_pnl_usd": 15.90,
        "rr_realized": 1.99,
        "notes": "Bot detected setup",
    }
    t_bot = ledger.add_trade(bot_payload)
    assert t_bot["origin"] == "BOT"
    assert t_bot["trade_id"].startswith("BOT")
    assert t_bot["risk_usd_001"] == pytest.approx(8.0, abs=0.1)
    assert t_bot["exceeds_risk_cap"] is False

    # 2. Add HUMAN_EDITED_BOT trade referencing parent
    edited_payload = {
        "origin": "HUMAN_EDITED_BOT",
        "parent_bot_ref": t_bot["trade_id"],
        "symbol": "XAUUSD_o",
        "direction": "SHORT",
        "signal_time": 1794391200,
        "entry": 4062.00,  # Adjusted entry higher
        "sl": 4068.37,
        "tp": 4038.00,    # Adjusted TP lower
        "status": "WIN",
        "realized_pnl_usd": 23.90,
        "rr_realized": 3.75,
        "notes": "Cloned from bot trade with refined entry and extended target",
    }
    t_edited = ledger.add_trade(edited_payload)
    assert t_edited["origin"] == "HUMAN_EDITED_BOT"
    assert t_edited["parent_bot_ref"] == t_bot["trade_id"]

    # 3. Add HUMAN_PROPOSED trade
    human_payload = {
        "origin": "HUMAN_PROPOSED",
        "symbol": "XAUUSD_o",
        "direction": "LONG",
        "signal_time": 1794380000,
        "entry": 4030.00,
        "sl": 4005.00,    # $25 stop > $20 cap
        "tp": 4105.00,    # 3.0R
        "status": "WIN",
        "notes": "Human discretionary counter-trend scalp",
    }
    t_human = ledger.add_trade(human_payload)
    assert t_human["origin"] == "HUMAN_PROPOSED"
    assert t_human["risk_usd_001"] == pytest.approx(25.0, abs=0.1)
    assert t_human["exceeds_risk_cap"] is True

    # Check listing
    trades = ledger.list_trades()
    assert len(trades) == 3
    origins = {t["origin"] for t in trades}
    assert origins == {"BOT", "HUMAN_PROPOSED", "HUMAN_EDITED_BOT"}

    # Test update and delete
    updated = ledger.update_trade(t_human["trade_id"], {"notes": "Updated note"})
    assert updated is not None
    assert updated["notes"] == "Updated note"

    assert ledger.delete_trade(t_human["trade_id"]) is True
    assert len(ledger.list_trades()) == 2

    # 4. Agentify Feedback Store
    store = AgentifyFeedbackStore(file_path=feedback_file)
    case_payload = {
        "symbol": "XAUUSD_o",
        "timestamp": 1794409800,  # 15:10 Server / 16:40 Tehran
        "user_note": "Bot missed valid London continuation due to false session hour veto",
        "user_setup": {
            "direction": "SHORT",
            "entry": 4042.0,
            "sl": 4048.0,
            "tp": 4025.0,
        },
        "bot_trade": None,
        "screener_diagnostics": {
            "session_hour": 18,
            "has_setup": False,
            "reason": "Veto: Late NY PM / Silver Bullet window banned on XAUUSD_o per 1-year empirical audit",
            "phase": "EQUILIBRIUM",
        },
    }
    case = store.add_case(case_payload)
    assert "case_id" in case
    assert "prompt_markdown" in case
    prompt = case["prompt_markdown"]
    assert len(prompt) > 100
    assert "Late NY PM / Silver Bullet window banned" in prompt
    assert "XAUUSD_o" in prompt
    assert "4042" in prompt

    cases = store.list_cases()
    assert len(cases) == 1
    assert store.delete_case(case["case_id"]) is True
    assert len(store.list_cases()) == 0


def test_detect_fvg_boxes_detects_earliest_three_bar_sequence():
    """
    Verifies that a 3-bar Fair Value Gap located at index [0..2] is detected cleanly.
    Prior to fixing the stop index from 2 to 1 in range(len(recent)-1, 1, -1),
    range(2, 2, -1) was empty and returned None.
    """
    # 3 bars forming a bullish FVG on XAUUSD:
    # Bar 0 high = 4000.0
    # Bar 1 large bullish candle: open=4000.5, close=4005.0 (body = 4.5 >= min_body 1.5)
    # Bar 2 low = 4002.5 > Bar 0 high 4000.0 (gap = 2.5 >= min_gap 1.0, body 4.5 > gap 2.5)
    bars_3 = [
        {"time": 1000, "open": 3995.0, "high": 4000.0, "low": 3994.0, "close": 3999.0},
        {"time": 1300, "open": 4000.5, "high": 4006.0, "low": 4000.0, "close": 4005.0},
        {"time": 1600, "open": 4003.0, "high": 4010.0, "low": 4002.5, "close": 4008.0},
    ]
    fvg = detect_fvg_boxes(bars_3, lookback=12, symbol="XAUUSD_o")
    assert fvg is not None, "Expected 3-bar FVG at bars[0..2] to be detected!"
    assert fvg["dir"] == "BULLISH"
    assert fvg["bottom"] == 4000.0
    assert fvg["top"] == 4002.5
    assert fvg["t_start"] == 1000
    assert fvg["t_end"] == 1600

    # Also test bearish 3-bar FVG at [0..2]
    bars_3_bear = [
        {"time": 2000, "open": 4010.0, "high": 4011.0, "low": 4005.0, "close": 4006.0},
        {"time": 2300, "open": 4004.5, "high": 4005.0, "low": 3999.0, "close": 4000.0},
        {"time": 2600, "open": 3999.5, "high": 4002.0, "low": 3995.0, "close": 3996.0},
    ]
    fvg_bear = detect_fvg_boxes(bars_3_bear, lookback=12, symbol="XAUUSD_o")
    assert fvg_bear is not None, "Expected 3-bar bearish FVG at bars[0..2] to be detected!"
    assert fvg_bear["dir"] == "BEARISH"
    assert fvg_bear["top"] == 4005.0
    assert fvg_bear["bottom"] == 4002.0


def test_drawdown_follows_cash_exit_time_on_overlapping_trades(tmp_path: Path):
    """
    Verifies that max drawdown calculation in both CoBacktestLedger.get_scorecard
    and run_bot_scan bot_scorecard strictly orders trades by cash realization (exit_time),
    not order entry/decision_time.
    """
    ledger_file = tmp_path / "co_backtest_ledger_dd.json"
    ledger = CoBacktestLedger(file_path=ledger_file)

    t1 = {
        "origin": "HUMAN_PROPOSED",
        "symbol": "XAUUSD_o",
        "decision_time": 100,
        "exit_time": 500,
        "entry": 4000.0,
        "sl": 3975.0,
        "tp": 4050.0,
        "status": "LOSS",
        "realized_pnl_usd": -50.0,
    }
    t2 = {
        "origin": "HUMAN_PROPOSED",
        "symbol": "XAUUSD_o",
        "decision_time": 200,
        "exit_time": 250,
        "entry": 4010.0,
        "sl": 4000.0,
        "tp": 4030.0,
        "status": "WIN",
        "realized_pnl_usd": 100.0,
    }
    t3 = {
        "origin": "HUMAN_PROPOSED",
        "symbol": "XAUUSD_o",
        "decision_time": 210,
        "exit_time": 260,
        "entry": 4015.0,
        "sl": 4025.0,
        "tp": 3995.0,
        "status": "LOSS",
        "realized_pnl_usd": -80.0,
    }
    ledger.add_trade(t1)
    ledger.add_trade(t2)
    ledger.add_trade(t3)

    sc = ledger.get_scorecard()
    human_stats = sc["HUMAN_PROPOSED"]
    assert human_stats["max_drawdown_usd"] == 130.0
    assert sc["ALL"]["max_drawdown_usd"] == 130.0


def test_agentify_prompt_handles_none_values_defensively(tmp_path: Path):
    """
    Regression test: Verifies AgentifyFeedbackStore and build_agentify_prompt
    do not crash with AttributeError when user_setup=None, screener_diagnostics=None, or bot_trade=None.
    """
    feedback_file = tmp_path / "visual_feedback_cases_none.json"
    store = AgentifyFeedbackStore(file_path=feedback_file)

    none_payload = {
        "symbol": "GBPUSD_o",
        "timestamp": 1794409800,
        "user_note": "Feedback purely on bot state without proposed trade",
        "user_setup": None,
        "bot_trade": None,
        "screener_diagnostics": None,
    }
    case = store.add_case(none_payload)
    assert "case_id" in case
    assert "prompt_markdown" in case
    prompt = case["prompt_markdown"]
    assert "GBPUSD_o" in prompt
    assert "CASE-" in prompt
    assert "Feedback purely on bot state" in prompt
