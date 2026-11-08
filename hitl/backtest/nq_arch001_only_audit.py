"""
TradingGuard HITL - Nasdaq 100 (NQ) Purified Execution Audit (ARCH-004 & ARCH-010 Decommissioned)
Evaluates NQ strictly on SETUP-ARCH-001 (Major Liquidity Sweeps + MSS Displacement) across the full 5.2-month dataset (June 1 - Nov 6, 2026: 32,974 M5 bars, 157,960 M1 bars).
Verifies the clean win rate and profit factor after eliminating low-conviction FVG noise.
"""

import sys
import os
import json
import time
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Tuple, Dict, Any, List
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
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'nq_arch001_only_audit'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_LONDON = ZoneInfo("Europe/London")
TZ_UTC = ZoneInfo("UTC")


def classify_session(dt_utc: datetime.datetime) -> Tuple[str, str]:
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
    elif datetime.time(9, 30) <= ny_time < datetime.time(10, 0):
        return "NYSE_Cash_Open", "NYSE_Cash_Open"
    elif datetime.time(10, 0) <= ny_time < datetime.time(11, 0):
        return "NY_Silver_Bullet", "NY_Silver_Bullet"
    elif datetime.time(11, 0) <= ny_time < datetime.time(16, 0):
        return "NY_Regular_PM", "NY_Regular_PM"
    elif datetime.time(0, 0) <= dt_utc.time() < datetime.time(7, 0):
        return "Asian_Overnight", "Asian_Overnight"
    else:
        return "Pacific_Off_Hours", "Pacific_Off_Hours"


def run_nq_purified_audit():
    print("=" * 95)
    print("🚀 TRADINGGUARD - NASDAQ 100 (NQ) PURIFIED EXECUTION AUDIT (ARCH-001 ONLY)")
    print("Full 5.2 Months (June 1 - Nov 6, 2026) | 32,974 M5 Bars | 157,960 M1 Bars")
    print("=" * 95)

    # Load Summer & Autumn Datasets
    df_m5_sum = pd.read_parquet(CACHE_DIR / 'NQ_M5_SUMMER_2026.parquet')
    df_m1_sum = pd.read_parquet(CACHE_DIR / 'NQ_M1_SUMMER_2026.parquet')
    df_h1_sum = pd.read_parquet(CACHE_DIR / 'NQ_H1_SUMMER_2026.parquet')
    df_d1_sum = pd.read_parquet(CACHE_DIR / 'NQ_D1_SUMMER_2026.parquet')

    df_m5_aut = pd.read_parquet(CACHE_DIR / 'NQ_M5_EXTENDED_2026.parquet')
    df_m1_aut = pd.read_parquet(CACHE_DIR / 'NQ_M1_EXTENDED_2026.parquet')
    df_h1_aut = pd.read_parquet(CACHE_DIR / 'NQ_H1_EXTENDED_2026.parquet')
    df_d1_aut = pd.read_parquet(CACHE_DIR / 'NQ_D1_EXTENDED_2026.parquet')

    # Merge into unified continuous data
    df_m5_all = pd.concat([df_m5_sum, df_m5_aut]).drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)
    df_m1_all = pd.concat([df_m1_sum, df_m1_aut]).drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)
    df_h1_all = pd.concat([df_h1_sum, df_h1_aut]).drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)
    df_d1_all = pd.concat([df_d1_sum, df_d1_aut]).drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)

    bars_m5_all = df_m5_all.to_dict('records')
    bars_m1_all = df_m1_all.to_dict('records')
    bars_h1_all = df_h1_all.to_dict('records')
    bars_d1_all = df_d1_all.to_dict('records')

    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1_all)}
    warmup_bars = 120
    total_m5 = len(bars_m5_all)

    # Evaluate across Target 3.0R and 3.5R
    for target_rr in [3.0, 3.5]:
        trades = []
        active_until = 0
        t0 = time.time()

        for i in range(warmup_bars, total_m5):
            curr_bar = bars_m5_all[i]
            curr_epoch = curr_bar['time']

            if curr_epoch < active_until:
                continue

            bar_dt_utc = datetime.datetime.fromtimestamp(curr_epoch, tz=TZ_UTC)
            sess_name, sess_key = classify_session(bar_dt_utc)

            # Purified Policy: London Open & NY Pre-Market
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
            
            # Strict gate: ONLY SETUP-ARCH-001 (004 and 010 removed)
            if arch_id != "SETUP-ARCH-001":
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
            be_rr = 1.5
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
                slippage_pts=0.0,
                ttl_minutes=60
            )

            status = eval_res["status"]
            pnl = eval_res["realized_pnl_usd"]
            rr = eval_res.get("rr_realized", 0.0)
            exit_min = eval_res.get("exit_minute") or 60

            trades.append({
                "epoch": curr_epoch,
                "date": bar_dt_utc.strftime("%Y-%m-%d"),
                "month": bar_dt_utc.strftime("%Y-%m"),
                "session_key": sess_key,
                "archetype_id": arch_id,
                "direction": direction,
                "risk_pts": risk_pts,
                "status": status,
                "realized_pnl_usd": pnl,
                "rr_realized": rr
            })

            if status in ("WIN", "LOSS", "BREAKEVEN"):
                active_until = curr_epoch + (exit_min * 60)
            elif status == "EXPIRED":
                active_until = curr_epoch + (60 * 60)

        df_trades = pd.DataFrame(trades)
        tag = f"target_{str(target_rr).replace('.', '')}"
        df_trades.to_parquet(OUTPUT_DIR / f"nq_arch001_{tag}_trades.parquet")
        df_trades.to_csv(OUTPUT_DIR / f"nq_arch001_{tag}_trades.csv", index=False)

        def calc_stats(df_sub):
            fills = df_sub[df_sub['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
            n = len(fills)
            wins = len(df_sub[df_sub['status'] == 'WIN'])
            losses = len(df_sub[df_sub['status'] == 'LOSS'])
            be = len(df_sub[df_sub['status'] == 'BREAKEVEN'])
            exp = len(df_sub[df_sub['status'] == 'EXPIRED'])
            wr = (wins / n * 100) if n > 0 else 0.0
            net_r = df_sub['rr_realized'].sum() if len(df_sub) > 0 else 0.0
            net_pnl = df_sub['realized_pnl_usd'].sum() if len(df_sub) > 0 else 0.0
            gp = df_sub[df_sub['realized_pnl_usd'] > 0]['realized_pnl_usd'].sum() if len(df_sub) > 0 else 0.0
            gl = abs(df_sub[df_sub['realized_pnl_usd'] < 0]['realized_pnl_usd'].sum()) if len(df_sub) > 0 else 0.0
            pf = (gp / gl) if gl > 0 else (99.0 if gp > 0 else 0.0)
            return {
                "Signals": len(df_sub), "Fills": n, "Wins": wins, "Losses": losses, "BE": be, "Exp": exp,
                "WR%": round(wr, 1), "Net_R": round(net_r, 2), "Net_PnL": round(net_pnl, 2), "PF": round(pf, 2)
            }

        s = calc_stats(df_trades)
        print(f"\n--- NQ ARCH-001 ONLY (Target {target_rr}R) ---")
        print(s)

        print(f"\n--- Month-by-Month Breakdown (Target {target_rr}R) ---")
        for m, g in df_trades.groupby('month'):
            sm = calc_stats(g)
            print(f"  {m} | Fills: {sm['Fills']:2d} | W: {sm['Wins']:2d} | L: {sm['Losses']:2d} | BE: {sm['BE']:2d} | WR: {sm['WR%']:5.1f}% | Net R: {sm['Net_R']:+6.2f}R | Net PnL: ${sm['Net_PnL']:+6.2f} | PF: {sm['PF']:.2f}")

    print(f"\n✅ Purified Audit complete! Results saved to {OUTPUT_DIR}")


if __name__ == '__main__':
    run_nq_purified_audit()
