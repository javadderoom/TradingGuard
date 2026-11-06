"""
TradingGuard HITL - Multimodal Vision Backtest Runner for Nov 05 & Nov 06, 2026
Renders high-fidelity 4-timeframe TradingView charts (1D, 1H, 15M, 5M) for every key session,
extracts structural SMC landmarks, screens setups, and evaluates forward broker execution.
"""

import sys
import shutil
import datetime
from pathlib import Path
from typing import Dict, Any, List

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.chart_renderer import render_candlestick_chart
from hitl.backtest.data_feed import _convert_records
from hitl.tools.smc_tools import get_smc_landmarks, format_smc_tools_block
from hitl.backtest.hybrid_telemetry import extract_hybrid_telemetry
from hitl.backtest.evaluator import evaluate_council_decision

OUTPUT_DIR = BASE_DIR / "analysis_assets" / "vision_backtest"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACT_DIR = Path(r"C:\Users\Javad\.gemini\antigravity\brain\9458aaca-f0fa-43e6-95ae-d440f3eb9e63")

SESSIONS = [
    {
        "id": "NOV05-LON",
        "date_str": "2026-11-05",
        "session_name": "Nov 05 (Thu) London Open",
        "broker_dt": datetime.datetime(2026, 11, 5, 10, 0),
        "tehran_str": "11:30 Tehran",
        "utc_str": "08:00 UTC",
        "catalyst": "European Morning Liquidity & London Judas Opening"
    },
    {
        "id": "NOV05-NYO",
        "date_str": "2026-11-05",
        "session_name": "Nov 05 (Thu) NY Open",
        "broker_dt": datetime.datetime(2026, 11, 5, 15, 0),
        "tehran_str": "16:30 Tehran",
        "utc_str": "13:00 UTC",
        "catalyst": "US Initial Jobless Claims & NY AM Trend Expansion"
    },
    {
        "id": "NOV05-NYSB",
        "date_str": "2026-11-05",
        "session_name": "Nov 05 (Thu) NY Silver Bullet",
        "broker_dt": datetime.datetime(2026, 11, 5, 17, 0),
        "tehran_str": "18:30 Tehran",
        "utc_str": "15:00 UTC",
        "catalyst": "NY Silver Bullet (10:00-11:00 EST Institutional Delivery)"
    },
    {
        "id": "NOV06-LON",
        "date_str": "2026-11-06",
        "session_name": "Nov 06 (Fri) London Open",
        "broker_dt": datetime.datetime(2026, 11, 6, 10, 0),
        "tehran_str": "11:30 Tehran",
        "utc_str": "08:00 UTC",
        "catalyst": "London Opening Range vs Asian Accumulation"
    },
    {
        "id": "NOV06-NYO",
        "date_str": "2026-11-06",
        "session_name": "Nov 06 (Fri) NY Open (NFP Release)",
        "broker_dt": datetime.datetime(2026, 11, 6, 15, 0),
        "tehran_str": "16:30 Tehran",
        "utc_str": "13:00 UTC",
        "catalyst": "US Non-Farm Payrolls (NFP) & Unemployment Rate"
    },
    {
        "id": "NOV06-NYSB",
        "date_str": "2026-11-06",
        "session_name": "Nov 06 (Fri) NY Silver Bullet (Post-NFP)",
        "broker_dt": datetime.datetime(2026, 11, 6, 17, 0),
        "tehran_str": "18:30 Tehran",
        "utc_str": "15:00 UTC",
        "catalyst": "Post-NFP Clean Out & Institutional Re-distribution"
    }
]


def run_vision_backtest():
    terminal_path = r"C:\Program Files\LiteFinance MT5 Terminal\terminal64.exe"
    if not mt5.initialize(path=terminal_path):
        print("Failed to initialize MT5 terminal")
        return

    print("=" * 90)
    print("👁️ TRADINGGUARD - MULTIMODAL VISION BACKTEST (NOV 05 & NOV 06, 2026)")
    print("High-Fidelity MTF Chart Rendering + SMC Landmarks + Visual Council Inspection")
    print("=" * 90)

    symbols = ["XAUUSD_o", "GBPUSD_o"]
    session_results = []

    for sess in SESSIONS:
        sess_id = sess["id"]
        sess_title = sess["session_name"]
        broker_t = sess["broker_dt"]
        print(f"\n" + "-" * 80)
        print(f"📍 SESSION: {sess_title} [{sess['tehran_str']} | {sess['utc_str']}]")
        print(f"   Catalyst: {sess['catalyst']}")
        print("-" * 80)

        for sym in symbols:
            clean_sym = "XAUUSD" if "XAU" in sym else "GBPUSD"
            is_xau = "XAU" in sym

            # 1. Fetch MTF Bars strictly up to broker_t
            r_1d = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_D1, broker_t, 60))
            r_1h = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_H1, broker_t, 60))
            r_15m = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M15, broker_t, 60))
            r_5m = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M5, broker_t, 60))

            if not (r_1d and r_1h and r_15m and r_5m):
                print(f"⚠️ {clean_sym}: Missing MTF bars at {broker_t}")
                continue

            # Verify no lookahead
            t_epoch = int(broker_t.timestamp())
            if r_5m[-1]['time'] > t_epoch:
                r_5m = [b for b in r_5m if b['time'] <= t_epoch]
                r_15m = [b for b in r_15m if b['time'] <= t_epoch]
                r_1h = [b for b in r_1h if b['time'] <= t_epoch]

            latest_close = r_5m[-1]['close']
            price_fmt = f"{latest_close:.2f}" if is_xau else f"{latest_close:.5f}"

            # 2. Render 4 Institutional MTF Charts
            p_1d = OUTPUT_DIR / f"{sess_id}_{clean_sym}_1D.png"
            p_1h = OUTPUT_DIR / f"{sess_id}_{clean_sym}_1H.png"
            p_15m = OUTPUT_DIR / f"{sess_id}_{clean_sym}_15M.png"
            p_5m = OUTPUT_DIR / f"{sess_id}_{clean_sym}_5M.png"

            render_candlestick_chart(r_1d, clean_sym, "1D", p_1d)
            render_candlestick_chart(r_1h, clean_sym, "1H", p_1h)
            render_candlestick_chart(r_15m, clean_sym, "15M", p_15m)
            render_candlestick_chart(r_5m, clean_sym, "5M", p_5m)

            # Copy to artifact directory for markdown display
            if ARTIFACT_DIR.exists():
                for p in [p_1d, p_1h, p_15m, p_5m]:
                    shutil.copy2(p, ARTIFACT_DIR / p.name)

            # 3. Extract SMC Landmarks
            landmarks = get_smc_landmarks(
                r_1d, r_1h, r_15m, r_5m,
                symbol=clean_sym,
                current_bid=latest_close,
                current_ask=latest_close + (0.20 if is_xau else 0.00006),
                broker_time=broker_t
            )

            # 4. Fetch Forward M1 Bars for outcome evaluation
            forward_bars = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, broker_t + datetime.timedelta(hours=8), 480))
            forward_window = [b for b in forward_bars if b['time'] > t_epoch][:480]

            print(f"  📊 {clean_sym} @ {price_fmt} | Rendered 4 MTF Charts (1D, 1H, 15M, 5M)")
            print(f"     SMC Status: Bias={landmarks.get('htf_bias')} | Active FVGs: {len(landmarks.get('active_fvgs', []))} | Forward M1: {len(forward_window)} bars")

            session_results.append({
                "session": sess,
                "symbol": clean_sym,
                "latest_close": latest_close,
                "price_fmt": price_fmt,
                "landmarks": landmarks,
                "chart_paths": [p_1d.name, p_1h.name, p_15m.name, p_5m.name],
                "forward_bars": forward_window,
                "r_5m": r_5m,
                "r_15m": r_15m,
                "r_1h": r_1h,
                "r_1d": r_1d
            })

    mt5.shutdown()
    print("\n" + "=" * 90)
    print(f"✅ Vision Rendering Complete: {len(session_results)} asset sessions rendered & ready for visual review.")
    print("=" * 90)
    return session_results


if __name__ == "__main__":
    run_vision_backtest()
