"""
TradingGuard HITL - Nasdaq 100 (NQ) Multidimensional Parameter & Execution Sensitivity Matrix
Evaluates parameter stability across:
1. Target R:R Realism Cap: 2.0R, 2.5R, 3.0R, 3.5R, 4.0R
2. Breakeven Ratchet Threshold: 1.0R, 1.2R, 1.5R, 1.8R, None
3. Inactivity Limit Order TTL: 30m, 45m, 60m, 75m, 90m
4. Broker Execution Slippage: 0.0 pt, 0.5 pt, 1.0 pt, 1.5 pt, 2.0 pt
"""

import sys
import os
import json
import time
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.fast_screener import screen_ict_session
from hitl.setup_registry import setup_registry
from hitl.backtest.evaluator import evaluate_council_decision

CACHE_DIR = BASE_DIR / 'backtest_results' / 'cache'
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'nq_sensitivity_matrix'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_LONDON = ZoneInfo("Europe/London")
TZ_UTC = ZoneInfo("UTC")


def classify_nq_session(dt_utc: datetime.datetime) -> Tuple[str, str]:
    dt_ny = dt_utc.astimezone(TZ_NEW_YORK)
    dt_lon = dt_utc.astimezone(TZ_LONDON)
    dt_tehran = dt_utc.astimezone(TZ_TEHRAN)

    ny_time = dt_ny.time()
    lon_time = dt_lon.time()

    if dt_utc.weekday() in (5, 6):
        return "Weekend", "Weekend"

    if datetime.time(8, 0) <= lon_time < datetime.time(10, 30):
        return "London_Open", "London_Open"
    elif datetime.time(8, 0) <= ny_time < datetime.time(9, 30):
        return "NY_Pre_Market", "NY_Pre_Market"
    return "Other", "Other"


def run_nq_sensitivity_analysis():
    print("=" * 95)
    print("🔬 TRADINGGUARD - NASDAQ 100 (NQ) MULTIDIMENSIONAL SENSITIVITY MATRIX")
    print("Aug 1 to Nov 6, 2026 | 20,652 M5 Bars | 96,352 M1 Bars")
    print("=" * 95)

    df_m5 = pd.read_parquet(CACHE_DIR / 'NQ_M5_EXTENDED_2026.parquet')
    df_m1 = pd.read_parquet(CACHE_DIR / 'NQ_M1_EXTENDED_2026.parquet')
    df_h1 = pd.read_parquet(CACHE_DIR / 'NQ_H1_EXTENDED_2026.parquet')
    df_d1 = pd.read_parquet(CACHE_DIR / 'NQ_D1_EXTENDED_2026.parquet')

    bars_m5_all = df_m5.to_dict('records')
    bars_m1_all = df_m1.to_dict('records')
    bars_h1_all = df_h1.to_dict('records')
    bars_d1_all = df_d1.to_dict('records')

    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1_all)}
    warmup_bars = 120
    total_m5 = len(bars_m5_all)

    # First, collect candidate trade setups from closed M5 bars (London Open & NY Pre-Market)
    print("Scanning M5 bars for institutional candidate signals...")
    candidate_signals = []

    for i in range(warmup_bars, total_m5):
        curr_bar = bars_m5_all[i]
        curr_epoch = curr_bar['time']

        bar_dt_utc = datetime.datetime.fromtimestamp(curr_epoch, tz=TZ_UTC)
        sess_name, sess_key = classify_nq_session(bar_dt_utc)
        if sess_key not in ("London_Open", "NY_Pre_Market"):
            continue

        bar_dt_tehran = bar_dt_utc.astimezone(TZ_TEHRAN)

        bars_5m_slice = bars_m5_all[i-120:i+1]
        bars_1h_slice = [b for b in bars_h1_all if b['time'] <= curr_epoch][-120:]
        bars_1d_slice = [b for b in bars_d1_all if b['time'] <= curr_epoch][-60:]

        if len(bars_1h_slice) < 10:
            continue

        res = screen_ict_session(
            bars_5m=bars_5m_slice,
            bars_1h=bars_1h_slice,
            symbol="NQ",
            session_hour=bar_dt_tehran.hour,
            bars_1m=None,
            bars_1d=bars_1d_slice,
            closed_bars_only=True
        )

        if not res.get("has_setup") or res.get("setup_type") == "NONE":
            continue

        arch_id = res.get("archetype_id", "NONE")
        if arch_id in ("SETUP-ARCH-002", "SETUP-ARCH-009"):
            continue

        if sess_key == "London_Open" and arch_id not in ("SETUP-ARCH-004", "SETUP-ARCH-010"):
            continue
        elif sess_key == "NY_Pre_Market" and arch_id not in ("SETUP-ARCH-001", "SETUP-ARCH-010"):
            continue

        setup_type = res.get("setup_type", "NONE")
        entry_p = res.get("entry_ref")
        sl_p = res.get("sl_ref")

        if not (entry_p and sl_p):
            continue

        risk_pts = abs(entry_p - sl_p)
        if risk_pts < 15.0 or risk_pts > 120.0:
            continue

        is_buy = "BULLISH" in setup_type or "LONG" in setup_type
        direction = "BUY" if is_buy else "SELL"

        candidate_signals.append({
            "epoch": curr_epoch,
            "session_key": sess_key,
            "archetype_id": arch_id,
            "direction": direction,
            "entry_p": entry_p,
            "sl_p": sl_p,
            "risk_pts": risk_pts
        })

    print(f"Discovered {len(candidate_signals)} candidate signals. Now running sensitivity permutations...")

    def simulate_permutation(target_rr, be_rr, ttl_min, slippage_pts):
        active_until = 0
        trades = []

        for sig in candidate_signals:
            curr_epoch = sig["epoch"]
            if curr_epoch < active_until:
                continue

            entry_p = sig["entry_p"]
            sl_p = sig["sl_p"]
            risk_pts = sig["risk_pts"]
            direction = sig["direction"]
            is_buy = direction == "BUY"

            tp_p = entry_p + (target_rr * risk_pts) if is_buy else entry_p - (target_rr * risk_pts)

            next_m1_epoch = curr_epoch + 300
            m1_start_idx = m1_time_map.get(next_m1_epoch)
            if m1_start_idx is None:
                forward_m1 = [b for b in bars_m1_all if b['time'] >= next_m1_epoch][:480]
            else:
                forward_m1 = bars_m1_all[m1_start_idx : m1_start_idx + 480]

            if not forward_m1:
                continue

            decision_dict = {
                "decision": direction,
                "entry": round(entry_p, 1),
                "sl": round(sl_p, 1),
                "tp": round(tp_p, 1),
                "lot": 0.01
            }

            eval_res = evaluate_council_decision(
                decision_dict=decision_dict,
                forward_m1_bars=forward_m1,
                symbol="NQ",
                spread_pts=1.0,
                breakeven_rr=be_rr,
                target_rr_cap=target_rr,
                commission_usd=0.10,
                slippage_pts=slippage_pts,
                ttl_minutes=ttl_min
            )

            status = eval_res["status"]
            pnl = eval_res["realized_pnl_usd"]
            rr = eval_res.get("rr_realized", 0.0)
            exit_min = eval_res.get("exit_minute") or ttl_min

            trades.append({
                "status": status,
                "pnl": pnl,
                "rr": rr
            })

            if status in ("WIN", "LOSS", "BREAKEVEN"):
                active_until = curr_epoch + (exit_min * 60)
            elif status == "EXPIRED":
                active_until = curr_epoch + (ttl_min * 60)

        df_t = pd.DataFrame(trades)
        fills = df_t[df_t['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
        n = len(fills)
        wins = len(df_t[df_t['status'] == 'WIN'])
        losses = len(df_t[df_t['status'] == 'LOSS'])
        bes = len(df_t[df_t['status'] == 'BREAKEVEN'])
        wr = (wins / n * 100) if n > 0 else 0.0
        net_r = df_t['rr'].sum() if len(df_t) > 0 else 0.0
        net_pnl = df_t['pnl'].sum() if len(df_t) > 0 else 0.0
        gp = df_t[df_t['pnl'] > 0]['pnl'].sum() if len(df_t) > 0 else 0.0
        gl = abs(df_t[df_t['pnl'] < 0]['pnl'].sum()) if len(df_t) > 0 else 0.0
        pf = (gp / gl) if gl > 0 else (99.0 if gp > 0 else 0.0)

        return {
            "Fills": n, "Wins": wins, "Losses": losses, "BE": bes,
            "WR%": round(wr, 1), "Net_R": round(net_r, 2), "Net_PnL": round(net_pnl, 2), "PF": round(pf, 2)
        }

    # 1. Target R:R Sweep (with baseline BE 1.5R, TTL 60m, Slippage 0.0)
    print("\n--- 1. TARGET R:R SENSITIVITY SWEEP ---")
    target_results = []
    for tr in [2.0, 2.5, 3.0, 3.5, 4.0]:
        res = simulate_permutation(target_rr=tr, be_rr=1.5, ttl_min=60, slippage_pts=0.0)
        res["Target_RR"] = f"{tr:.1f}R"
        target_results.append(res)
        print(f"  Target {tr:.1f}R | Fills: {res['Fills']:3d} | W: {res['Wins']:2d} | L: {res['Losses']:2d} | BE: {res['BE']:2d} | WR: {res['WR%']:5.1f}% | Net R: {res['Net_R']:+6.2f}R | Net PnL: ${res['Net_PnL']:+6.2f} | PF: {res['PF']:.2f}")

    # 2. Breakeven Ratchet Sweep (with Target 3.0R, TTL 60m, Slippage 0.0)
    print("\n--- 2. BREAKEVEN RATCHET SENSITIVITY SWEEP ---")
    be_results = []
    for be in [1.0, 1.2, 1.5, 1.8, None]:
        res = simulate_permutation(target_rr=3.0, be_rr=be, ttl_min=60, slippage_pts=0.0)
        res["BE_RR"] = f"{be:.1f}R" if be else "None"
        be_results.append(res)
        be_label = f"{be:.1f}R" if be else "None"
        print(f"  BE Ratchet {be_label:5s} | Fills: {res['Fills']:3d} | W: {res['Wins']:2d} | L: {res['Losses']:2d} | BE: {res['BE']:2d} | WR: {res['WR%']:5.1f}% | Net R: {res['Net_R']:+6.2f}R | Net PnL: ${res['Net_PnL']:+6.2f} | PF: {res['PF']:.2f}")

    # 3. Inactivity TTL Sweep (with Target 3.0R, BE 1.5R, Slippage 0.0)
    print("\n--- 3. INACTIVITY ORDER TTL SWEEP ---")
    ttl_results = []
    for ttl in [30, 45, 60, 75, 90]:
        res = simulate_permutation(target_rr=3.0, be_rr=1.5, ttl_min=ttl, slippage_pts=0.0)
        res["TTL_Min"] = f"{ttl}m"
        ttl_results.append(res)
        print(f"  TTL {ttl:2d} min   | Fills: {res['Fills']:3d} | W: {res['Wins']:2d} | L: {res['Losses']:2d} | BE: {res['BE']:2d} | WR: {res['WR%']:5.1f}% | Net R: {res['Net_R']:+6.2f}R | Net PnL: ${res['Net_PnL']:+6.2f} | PF: {res['PF']:.2f}")

    # 4. Slippage Stress Testing (with Target 3.0R, BE 1.5R, TTL 60m)
    print("\n--- 4. BROKER SLIPPAGE STRESS TEST ---")
    slip_results = []
    for slip in [0.0, 0.5, 1.0, 1.5, 2.0]:
        res = simulate_permutation(target_rr=3.0, be_rr=1.5, ttl_min=60, slippage_pts=slip)
        res["Slippage_Pts"] = f"{slip:.1f} pt"
        slip_results.append(res)
        print(f"  Slippage {slip:.1f} pt | Fills: {res['Fills']:3d} | W: {res['Wins']:2d} | L: {res['Losses']:2d} | BE: {res['BE']:2d} | WR: {res['WR%']:5.1f}% | Net R: {res['Net_R']:+6.2f}R | Net PnL: ${res['Net_PnL']:+6.2f} | PF: {res['PF']:.2f}")

    sensitivity_export = {
        "target_rr_sweep": target_results,
        "breakeven_sweep": be_results,
        "ttl_sweep": ttl_results,
        "slippage_stress": slip_results
    }
    with open(OUTPUT_DIR / "nq_sensitivity_results.json", "w", encoding="utf-8") as f:
        json.dump(sensitivity_export, f, indent=2)

    print(f"\n✅ Sensitivity Analysis complete! Results saved to {OUTPUT_DIR}")


if __name__ == '__main__':
    run_nq_sensitivity_analysis()
