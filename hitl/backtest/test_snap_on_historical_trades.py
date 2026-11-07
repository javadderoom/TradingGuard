"""
TradingGuard HITL - SubQ Snap Evaluation on Real Historical Setups
Runs SubQ Snap on real historical setups from orders_schedule.csv to test model classifications and probabilities.
"""

import sys
import json
import time
import datetime
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.data_feed import _convert_records
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.mtf_structure import analyze_mtf_state
from hitl.snap_decision_engine import snap_engine
from hitl.backtest.evaluator import evaluate_council_decision

CANDIDATES = [
    {"dt_str": "2026-02-02 14:00:00", "symbol": "XAUUSD_o", "type": "SELL_LIMIT", "entry": 4777.81, "sl": 4783.81, "tp": 4756.81},
    {"dt_str": "2026-02-03 10:00:00", "symbol": "XAUUSD_o", "type": "SELL_LIMIT", "entry": 4925.36, "sl": 4931.36, "tp": 4904.36},
    {"dt_str": "2026-02-18 14:00:00", "symbol": "XAUUSD_o", "type": "BUY_LIMIT",  "entry": 4911.48, "sl": 4905.48, "tp": 4932.48},
    {"dt_str": "2026-02-24 14:00:00", "symbol": "XAUUSD_o", "type": "SELL_LIMIT", "entry": 5171.00, "sl": 5179.00, "tp": 5143.00},
]


def test_snap_candidates():
    terminal_path = r"C:\Program Files\LiteFinance MT5 Terminal\terminal64.exe"
    if not mt5.initialize(path=terminal_path):
        print("[Error] Failed to initialize MT5")
        return

    print("==========================================================================================")
    print("🔬 TESTING SUBQ SNAP DECISION ENGINE ON REAL HISTORICAL TRADE CANDIDATES")
    print("==========================================================================================")

    for cand in CANDIDATES:
        dt = datetime.datetime.strptime(cand["dt_str"], "%Y-%m-%d %H:%M:%S")
        sym = cand["symbol"]
        clean_sym = "XAUUSD" if "XAU" in sym else "GBPUSD"
        target_dir = cand["type"]

        print(f"\n>>> CANDIDATE: {sym} at {dt} (Historical Order Type: {target_dir})")

        # Fetch bars up to dt
        bars_5m = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M5, dt, 120))
        bars_1h = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_H1, dt, 120))
        bars_1d = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_D1, dt, 60))

        if not bars_5m or not bars_1h:
            print("  Missing bars, skipping.")
            continue

        mtf_state = analyze_mtf_state(bars_1d, bars_1h, bars_5m, symbol=clean_sym)
        curr_b = bars_5m[-1]
        quote = {
            "bid": curr_b['close'],
            "ask": curr_b['close'] + 0.20,
            "spread": 0.20
        }

        mock_setup = {
            "archetype_id": "HISTORICAL_RETEST",
            "setup_type": "PRO_TREND_LIQUIDITY_EXPANSION",
            "direction": "SHORT" if "SELL" in target_dir else "LONG",
            "entry_price": cand["entry"],
            "sl_price": cand["sl"],
            "target_price": cand["tp"]
        }

        # Evaluate through SubQ Snap
        t0 = time.perf_counter()
        snap_res = snap_engine.evaluate_candidate(
            symbol=clean_sym,
            session_label=f"Session_{dt.strftime('%Y%m%d_%H%M')}",
            screener_setup=mock_setup,
            mtf_state=mtf_state,
            current_quote=quote
        )
        latency = (time.perf_counter() - t0) * 1000.0

        decision = snap_res.get("decision", "STAND_ASIDE")
        conf = snap_res.get("confidence", 0.0)
        probs = snap_res.get("probabilities", {})
        driver = snap_res.get("primary_driver", "NONE")
        tier = snap_res.get("conviction_tier", "NONE")

        print(f"  [SubQ Snap ({latency:.0f}ms)] Decision: {decision} (Conf: {conf:.2f}, Tier: {tier})")
        print(f"      Probabilities: BUY={probs.get('BUY_LIMIT', 0.0):.2f} | SELL={probs.get('SELL_LIMIT', 0.0):.2f} | STAND={probs.get('STAND_ASIDE', 0.0):.2f}")
        print(f"      Primary Driver: {driver}")

        # Check forward execution on M1
        fwd_rates = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, dt + datetime.timedelta(minutes=240), 240)
        fwd_m1 = _convert_records(fwd_rates)
        fwd_m1_valid = [b for b in fwd_m1 if b['time'] >= int(dt.timestamp())]

        plan = {
            "symbol": clean_sym,
            "decision": cand["type"],
            "entry": cand["entry"],
            "sl": cand["sl"],
            "tp": cand["tp"],
            "lot": 0.01,
            "risk_usd": abs(cand["entry"] - cand["sl"]),
            "rr": 3.5
        }
        sim_res = evaluate_council_decision(plan, fwd_m1_valid, clean_sym)
        print(f"      Forward Execution: {sim_res.get('status')} | Realized PnL: ${sim_res.get('realized_pnl_usd', 0.0):+.2f}")


if __name__ == "__main__":
    test_snap_candidates()
