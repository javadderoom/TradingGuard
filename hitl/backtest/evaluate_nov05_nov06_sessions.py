"""
TradingGuard HITL - Quantitative Screener & Forward Evaluator for Nov 05 & Nov 06, 2026
Screens setups across all 12 sessions, tests against ratified archetypes, and evaluates forward execution.
"""

import sys
import datetime
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.data_feed import _convert_records
from hitl.setup_registry import setup_registry
from hitl.backtest.master_production_portfolio_audit import simulate_production_execution

SESSIONS = [
    {"id": "NOV05-LON", "name": "Nov 05 (Thu) London Open", "hour": 10, "label": "London_Open", "dt": datetime.datetime(2026, 11, 5, 10, 0)},
    {"id": "NOV05-NYO", "name": "Nov 05 (Thu) NY Open", "hour": 15, "label": "NY_Open", "dt": datetime.datetime(2026, 11, 5, 15, 0)},
    {"id": "NOV05-NYSB", "name": "Nov 05 (Thu) NY Silver Bullet", "hour": 17, "label": "NY_Silver_Bullet", "dt": datetime.datetime(2026, 11, 5, 17, 0)},
    {"id": "NOV06-LON", "name": "Nov 06 (Fri) London Open", "hour": 10, "label": "London_Open", "dt": datetime.datetime(2026, 11, 6, 10, 0)},
    {"id": "NOV06-NYO", "name": "Nov 06 (Fri) NY Open (NFP)", "hour": 15, "label": "NY_Open", "dt": datetime.datetime(2026, 11, 6, 15, 0)},
    {"id": "NOV06-NYSB", "name": "Nov 06 (Fri) NY Silver Bullet", "hour": 17, "label": "NY_Silver_Bullet", "dt": datetime.datetime(2026, 11, 6, 17, 0)}
]


def audit_sessions():
    terminal_path = r"C:\Program Files\LiteFinance MT5 Terminal\terminal64.exe"
    if not mt5.initialize(path=terminal_path):
        print("Failed to initialize MT5")
        return

    results = []
    symbols = ["XAUUSD_o", "GBPUSD_o"]

    for sess in SESSIONS:
        dt = sess["dt"]
        sess_name = sess["name"]
        sess_hour = sess["hour"]
        sess_label = sess["label"]

        print(f"\n========================================================")
        print(f"🔍 EVALUATING: {sess_name} (Broker Time: {dt})")
        print(f"========================================================")

        for sym in symbols:
            clean_sym = "XAUUSD" if "XAU" in sym else "GBPUSD"
            is_fx = "GBP" in sym

            # Gather historical bars ending at dt
            bars_5m = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M5, dt, 120))
            bars_1h = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_H1, dt, 120))
            bars_1d = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_D1, dt, 60))
            bars_15m = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M15, dt, 120))

            if not (bars_5m and bars_1h and bars_1d):
                print(f"  [{clean_sym}] Incomplete rates")
                continue

            # Run Screener
            res = screen_ict_session(
                bars_5m=bars_5m,
                bars_1h=bars_1h,
                symbol=sym,
                session_hour=sess_hour,
                bars_1m=None,
                bars_1d=bars_1d
            )

            has_setup = res.get("has_setup") and res.get("setup_type") != "NONE"
            arch_id = res.get("archetype_id", "NONE")
            setup_type = res.get("setup_type", "NONE")

            print(f"  [{clean_sym}] Setup Detected: {has_setup} | Type: {setup_type} | Archetype: {arch_id}")

            if has_setup:
                # Check Ratification
                is_ratified = setup_registry.is_archetype_ratified(arch_id)
                print(f"     Ratification: {is_ratified}")
                
                # Forward M1 evaluation
                t_epoch = int(dt.timestamp())
                forward_bars = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, dt + datetime.timedelta(hours=8), 480))
                forward_window = [b for b in forward_bars if b['time'] > t_epoch][:480]

                m15_map = {b['time']: b for b in bars_15m}

                sim = simulate_production_execution(
                    setup=res,
                    forward_m1=forward_window,
                    bars_m15_map=m15_map,
                    symbol=sym,
                    session_label=sess_label
                )

                if sim:
                    print(f"     Outcome: {sim['status']} | Net R: {sim['net_r']:+.2f}R | MFE: {sim['max_mfe_r']}R | MAE: {sim['max_mae_r']}R | Held: {sim['held_minutes']}m")
                else:
                    print("     Execution simulation returned None")
            else:
                sim = None

            results.append({
                "session_id": sess["id"],
                "session_name": sess_name,
                "symbol": clean_sym,
                "close_at_t": bars_5m[-1]["close"],
                "has_setup": has_setup,
                "setup_type": setup_type,
                "archetype_id": arch_id,
                "entry": res.get("entry_ref", res.get("entry_price")),
                "sl": res.get("sl_ref", res.get("stop_loss")),
                "sim": sim
            })

    mt5.shutdown()

    print("\n" + "=" * 90)
    print("🏆 SUMMARY OF EXECUTED SETUPS (NOV 05 & NOV 06, 2026)")
    print("=" * 90)
    for r in results:
        if r["has_setup"] and r["sim"]:
            s = r["sim"]
            print(f"• {r['session_name']} | {r['symbol']} | {r['setup_type']}")
            print(f"  Entry: {r['entry']} | SL: {r['sl']} | Target RR: {s['target_rr']}R")
            print(f"  Result: {s['status']} ({s['net_r']:+.2f}R) | MFE: {s['max_mfe_r']}R | MAE: {s['max_mae_r']}R | Held: {s['held_minutes']} min\n")

    return results


if __name__ == "__main__":
    audit_sessions()
