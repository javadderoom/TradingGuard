"""
TradingGuard HITL - SubQ Snap vs Screener Verification Runner (Nov 05 & Nov 06, 2026)
Runs SubQ Snap side-by-side on all 12 sessions across Nov 05 & Nov 06, evaluating:
1. Pre-screener setup detection
2. SubQ Snap decision classification, probabilities, and latency
3. Forward M1 broker execution outcome via the canonical evaluator
"""

import sys
import json
import time
import datetime
from pathlib import Path

# Force UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.data_feed import _convert_records
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.mtf_structure import analyze_mtf_state
from hitl.setup_registry import setup_registry
from hitl.snap_decision_engine import snap_engine
from hitl.tools.smc_tools import build_validated_order_plan
from hitl.backtest.evaluator import evaluate_council_decision

SESSIONS = [
    {"id": "NOV05-LON", "name": "Nov 05 (Thu) London Open", "hour": 10, "dt": datetime.datetime(2026, 11, 5, 10, 0)},
    {"id": "NOV05-NYO", "name": "Nov 05 (Thu) NY Open", "hour": 15, "dt": datetime.datetime(2026, 11, 5, 15, 0)},
    {"id": "NOV05-NYSB", "name": "Nov 05 (Thu) NY Silver Bullet", "hour": 17, "dt": datetime.datetime(2026, 11, 5, 17, 0)},
    {"id": "NOV06-LON", "name": "Nov 06 (Fri) London Open", "hour": 10, "dt": datetime.datetime(2026, 11, 6, 10, 0)},
    {"id": "NOV06-NYO", "name": "Nov 06 (Fri) NY Open (NFP)", "hour": 15, "dt": datetime.datetime(2026, 11, 6, 15, 0)},
    {"id": "NOV06-NYSB", "name": "Nov 06 (Fri) NY Silver Bullet", "hour": 17, "dt": datetime.datetime(2026, 11, 6, 17, 0)}
]


def run_snap_audit():
    terminal_path = r"C:\Program Files\LiteFinance MT5 Terminal\terminal64.exe"
    if not mt5.initialize(path=terminal_path):
        print("[Error] Failed to initialize MT5")
        return

    print("==========================================================================================")
    print("🚀 SUBQ SNAP DECISION ENGINE — NOV 05 & NOV 06 HISTORICAL VERIFICATION")
    print("==========================================================================================")

    symbols = ["XAUUSD_o", "GBPUSD_o"]
    audit_results = []

    for sess in SESSIONS:
        dt = sess["dt"]
        sess_name = sess["name"]
        sess_hour = sess["hour"]

        print(f"\n>>> SESSION: {sess_name} (Broker Time: {dt})")

        for sym in symbols:
            clean_sym = "XAUUSD" if "XAU" in sym else "GBPUSD"
            is_fx = "GBP" in sym

            # Gather historical bars ending at dt
            bars_5m = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M5, dt, 120))
            bars_1h = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_H1, dt, 120))
            bars_1d = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_D1, dt, 60))

            if not bars_5m or not bars_1h:
                print(f"  [{clean_sym}] Missing bars")
                continue

            # 1. Run Quantitative Screener
            screen_res = screen_ict_session(
                bars_5m=bars_5m,
                bars_1h=bars_1h,
                symbol=clean_sym,
                session_hour=sess_hour,
                bars_1d=bars_1d
            )

            has_setup = screen_res.get("has_setup", False)
            arch_id = screen_res.get("archetype_id", "NONE")
            setup_type = screen_res.get("setup_type", "NONE")

            if not has_setup:
                print(f"  [{clean_sym}] Screener: No Setup ({screen_res.get('reason', 'N/A')[:60]})")
                continue

            is_ratified = setup_registry.is_archetype_ratified(arch_id)
            print(f"  [{clean_sym}] Screener: DETECTED {arch_id} ({setup_type}) | Ratified: {is_ratified}")

            if not is_ratified:
                print(f"  [{clean_sym}] Setup unratified per registry. Standing aside.")
                continue

            # 2. Extract MTF state and Current Quote
            mtf_state = analyze_mtf_state(bars_1d, bars_1h, bars_5m, symbol=clean_sym)
            curr_b = bars_5m[-1]
            quote = {
                "bid": curr_b['close'],
                "ask": curr_b['close'] + (0.00015 if is_fx else 0.20),
                "spread": 0.00015 if is_fx else 0.20
            }

            # 3. Query SubQ Snap Decision Engine
            print(f"  [{clean_sym}] Invoking SubQ Snap Decision Model...")
            t0 = time.perf_counter()
            snap_res = snap_engine.evaluate_candidate(
                symbol=clean_sym,
                session_label=sess_name,
                screener_setup=screen_res,
                mtf_state=mtf_state,
                current_quote=quote
            )
            elapsed = (time.perf_counter() - t0) * 1000.0

            decision = snap_res.get("decision", "STAND_ASIDE")
            confidence = snap_res.get("confidence", 0.0)
            probs = snap_res.get("probabilities", {})
            driver = snap_res.get("primary_driver", "NONE")
            conviction = snap_res.get("conviction_tier", "NONE")

            print(f"  [{clean_sym}] SubQ Snap Result ({elapsed:.0f}ms): {decision} (Confidence: {confidence:.2f}, Tier: {conviction}, Driver: {driver})")
            print(f"       Probabilities: BUY={probs.get('BUY_LIMIT', 0.0):.2f} | SELL={probs.get('SELL_LIMIT', 0.0):.2f} | STAND={probs.get('STAND_ASIDE', 0.0):.2f}")

            # 4. Forward Execution Simulation if Approved
            exec_outcome = "STAND_ASIDE"
            pnl_usd = 0.0
            rr_realized = 0.0

            if decision in ("BUY_LIMIT", "SELL_LIMIT"):
                landmarks = {
                    "fvg": {
                        "proximal_edge": screen_res.get("entry_price", curr_b['close']),
                        "distal_edge": screen_res.get("sl_price", curr_b['close'])
                    },
                    "market_structure": {
                        "last_mss_level": curr_b['close'],
                        "invalidation_level": screen_res.get("sl_price", curr_b['close'])
                    },
                    "current_quote": quote
                }
                order_plan, plan_err = build_validated_order_plan(
                    decision=decision,
                    poi_selection="PROXIMAL_EDGE",
                    landmarks=landmarks,
                    symbol=clean_sym
                )

                if order_plan:
                    # Gather forward M1 bars for 240 mins
                    fwd_rates = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, dt + datetime.timedelta(minutes=240), 240)
                    fwd_m1 = _convert_records(fwd_rates)
                    # Slice starting at or after dt
                    fwd_m1_valid = [b for b in fwd_m1 if b['time'] >= int(dt.timestamp())]

                    if fwd_m1_valid:
                        sim_res = evaluate_council_decision(
                            plan=order_plan,
                            forward_m1_bars=fwd_m1_valid,
                            symbol=clean_sym
                        )
                        exec_outcome = sim_res.get("status", "UNKNOWN")
                        pnl_usd = sim_res.get("realized_pnl_usd", 0.0)
                        rr_realized = sim_res.get("rr_realized", 0.0)
                        print(f"       Execution Outcome: {exec_outcome} | PnL: ${pnl_usd:+.2f} | R: {rr_realized:+.2f}R")
                else:
                    print(f"       Plan Validation Rejected: {plan_err}")

            audit_results.append({
                "session": sess_name,
                "symbol": clean_sym,
                "screener_arch": arch_id,
                "screener_dir": screen_res.get("direction"),
                "snap_decision": decision,
                "snap_confidence": confidence,
                "snap_latency_ms": elapsed,
                "snap_driver": driver,
                "execution_status": exec_outcome,
                "realized_pnl_usd": pnl_usd,
                "realized_rr": rr_realized
            })

    # Summary
    print("\n==========================================================================================")
    print("📊 SUBQ SNAP EXECUTIVE AUDIT SUMMARY (NOV 05 & NOV 06)")
    print("==========================================================================================")
    for r in audit_results:
        print(f"• {r['session']} | {r['symbol']} | Screener: {r['screener_arch']} ({r['screener_dir']}) ➔ Snap: {r['snap_decision']} ({r['snap_confidence']:.2f}) in {r['snap_latency_ms']:.0f}ms ➔ Outcome: {r['execution_status']} ({r['realized_rr']:+.2f}R, ${r['realized_pnl_usd']:+.2f})")


if __name__ == "__main__":
    run_snap_audit()
