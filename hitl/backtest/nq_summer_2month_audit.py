"""
TradingGuard HITL - Nasdaq 100 (NQ) Independent 2-Month Summer 2026 Audit
Evaluates institutional SMC screening across continuous MT5 broker data (June 1 to July 31, 2026: 12,322 M5 bars, 61,608 M1 bars).
Tests out-of-sample stability in a completely independent market regime prior to Autumn 2026.
Also combines Summer + Autumn into a unified 5.2-month institutional performance benchmark.
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
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'nq_summer_2month_audit'
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
        return f"London_Open ({dt_lon.strftime('%H:%M')} Lon | {dt_tehran.strftime('%H:%M')} Tehran)", "London_Open"
    elif datetime.time(8, 0) <= ny_time < datetime.time(9, 30):
        return f"NY_Pre_Market ({dt_ny.strftime('%H:%M')} NY | {dt_tehran.strftime('%H:%M')} Tehran)", "NY_Pre_Market"
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


def run_nq_summer_audit():
    print("=" * 95)
    print("🚀 TRADINGGUARD - NASDAQ 100 (NQ) INDEPENDENT 2-MONTH SUMMER AUDIT")
    print("June 1 to July 31, 2026 MT5 Broker Microstructure | 12,322 M5 Bars | 61,608 M1 Bars")
    print("=" * 95)

    df_m5 = pd.read_parquet(CACHE_DIR / 'NQ_M5_SUMMER_2026.parquet')
    df_m1 = pd.read_parquet(CACHE_DIR / 'NQ_M1_SUMMER_2026.parquet')
    df_h1 = pd.read_parquet(CACHE_DIR / 'NQ_H1_SUMMER_2026.parquet')
    df_d1 = pd.read_parquet(CACHE_DIR / 'NQ_D1_SUMMER_2026.parquet')

    bars_m5_all = df_m5.to_dict('records')
    bars_m1_all = df_m1.to_dict('records')
    bars_h1_all = df_h1.to_dict('records')
    bars_d1_all = df_d1.to_dict('records')

    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1_all)}
    
    # Filter evaluation strictly to June 1 to July 31, 2026 (epoch >= 1780275600)
    summer_start_epoch = int(datetime.datetime(2026, 6, 1, 0, 0, tzinfo=TZ_UTC).timestamp())
    summer_end_epoch = int(datetime.datetime(2026, 8, 1, 0, 0, tzinfo=TZ_UTC).timestamp())
    
    eval_m5_indices = [idx for idx, b in enumerate(bars_m5_all) if summer_start_epoch <= b['time'] < summer_end_epoch]
    print(f"Loaded {len(bars_m5_all)} total M5 bars. Active Summer evaluation slice: {len(eval_m5_indices)} bars.")

    def run_simulation(sim_name: str, target_rr: float = 3.5, be_rr: float = 1.5, curated_only: bool = True):
        trades = []
        active_until = 0
        t0 = time.time()

        for idx in eval_m5_indices:
            curr_bar = bars_m5_all[idx]
            curr_epoch = curr_bar['time']

            if curr_epoch < active_until:
                continue

            bar_dt_utc = datetime.datetime.fromtimestamp(curr_epoch, tz=TZ_UTC)
            sess_name, sess_key = classify_session(bar_dt_utc)

            if curated_only and sess_key not in ("London_Open", "NY_Pre_Market"):
                continue

            bar_dt_tehran = bar_dt_utc.astimezone(TZ_TEHRAN)

            bars_5m_slice = bars_m5_all[max(0, idx-120) : idx+1]
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
            
            if curated_only:
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

        df_res = pd.DataFrame(trades)
        print(f"Simulation '{sim_name}' finished in {time.time()-t0:.2f}s! Signals: {len(trades)}")
        return df_res

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

    # 1. Run Raw Baseline for Summer (June - July)
    print("\n1. Running Summer 2026 Raw Baseline Simulation...")
    df_summer_raw = run_simulation("NQ_Summer_Raw", target_rr=3.0, be_rr=1.5, curated_only=False)
    df_summer_raw.to_parquet(OUTPUT_DIR / "nq_summer_raw_trades.parquet")

    # 2. Run Curated Institutional Core (Target 3.0R)
    print("\n2. Running Summer 2026 Curated Core (Target 3.0R)...")
    df_summer_cur_30 = run_simulation("NQ_Summer_Curated_30", target_rr=3.0, be_rr=1.5, curated_only=True)
    df_summer_cur_30.to_parquet(OUTPUT_DIR / "nq_summer_curated_30_trades.parquet")

    # 3. Run Curated Institutional Core (Target 3.5R)
    print("\n3. Running Summer 2026 Curated Core (Target 3.5R)...")
    df_summer_cur_35 = run_simulation("NQ_Summer_Curated_35", target_rr=3.5, be_rr=1.5, curated_only=True)
    df_summer_cur_35.to_parquet(OUTPUT_DIR / "nq_summer_curated_35_trades.parquet")

    # 4. Run Curated Institutional Core (Target 4.0R)
    print("\n4. Running Summer 2026 Curated Core (Target 4.0R)...")
    df_summer_cur_40 = run_simulation("NQ_Summer_Curated_40", target_rr=4.0, be_rr=1.5, curated_only=True)
    df_summer_cur_40.to_parquet(OUTPUT_DIR / "nq_summer_curated_40_trades.parquet")

    s_raw = calc_stats(df_summer_raw)
    s_cur_30 = calc_stats(df_summer_cur_30)
    s_cur_35 = calc_stats(df_summer_cur_35)
    s_cur_40 = calc_stats(df_summer_cur_40)

    print("\n" + "=" * 95)
    print("📊 NASDAQ 100 (NQ) INDEPENDENT SUMMER 2-MONTH BENCHMARK (JUNE 1 - JULY 31, 2026)")
    print("=" * 95)
    print("SUMMER RAW BASELINE   :", s_raw)
    print("SUMMER CURATED (3.0R) :", s_cur_30)
    print("SUMMER CURATED (3.5R) :", s_cur_35)
    print("SUMMER CURATED (4.0R) :", s_cur_40)

    print("\n--- SUMMER CURATED (3.5R) MONTHLY BREAKDOWN ---")
    for m, g in df_summer_cur_35.groupby('month'):
        s = calc_stats(g)
        print(f"  Month: {m} | Fills: {s['Fills']:2d} | W: {s['Wins']:2d} | L: {s['Losses']:2d} | BE: {s['BE']:2d} | WR: {s['WR%']:5.1f}% | Net R: {s['Net_R']:+6.2f}R | Net PnL: ${s['Net_PnL']:+6.2f} | PF: {s['PF']:.2f}")

    print("\n--- SUMMER CURATED (3.5R) BY ARCHETYPE ---")
    for arch, g in df_summer_cur_35.groupby('archetype_id'):
        s = calc_stats(g)
        print(f"  {arch:15s} | Fills: {s['Fills']:2d} | W: {s['Wins']:2d} | L: {s['Losses']:2d} | BE: {s['BE']:2d} | WR: {s['WR%']:5.1f}% | Net R: {s['Net_R']:+6.2f}R | Net PnL: ${s['Net_PnL']:+6.2f} | PF: {s['PF']:.2f}")

    print("\n--- SUMMER CURATED (3.5R) BY SESSION ---")
    for sess, g in df_summer_cur_35.groupby('session_key'):
        s = calc_stats(g)
        print(f"  {sess:15s} | Fills: {s['Fills']:2d} | W: {s['Wins']:2d} | L: {s['Losses']:2d} | BE: {s['BE']:2d} | WR: {s['WR%']:5.1f}% | Net R: {s['Net_R']:+6.2f}R | Net PnL: ${s['Net_PnL']:+6.2f} | PF: {s['PF']:.2f}")

    # 5. UNIFIED 5.2-MONTH CONTINUOUS INSTITUTIONAL AGGREGATE (JUNE 1 - NOV 6, 2026)
    # Load Autumn Extended Curated trades
    print("\n" + "=" * 95)
    print("🌐 UNIFIED 5.2-MONTH CONTINUOUS INSTITUTIONAL AUDIT (JUNE 1 - NOV 6, 2026)")
    print("=" * 95)
    
    # We can run the 3.5R policy across the Autumn data to combine cleanly
    df_autumn_cur = pd.read_parquet(OUTPUT_DIR.parent / 'unified_portfolio_audit' / 'trades_nq.parquet')
    
    # Concatenate Summer + Autumn
    df_unified = pd.concat([df_summer_cur_35, df_autumn_cur]).drop_duplicates(subset=['epoch']).sort_values('epoch').reset_index(drop=True)
    df_unified.to_parquet(OUTPUT_DIR / "nq_unified_5_month_trades.parquet")
    df_unified.to_csv(OUTPUT_DIR / "nq_unified_5_month_trades.csv", index=False)

    s_unified = calc_stats(df_unified)
    print("UNIFIED 5.2-MONTH NQ (Target 3.5R):", s_unified)

    print("\n--- UNIFIED 5.2-MONTH PROGRESSION (CALENDAR MONTH BY MONTH) ---")
    df_unified['month'] = pd.to_datetime(df_unified['date']).dt.strftime('%Y-%m')
    for m, g in df_unified.groupby('month'):
        s = calc_stats(g)
        print(f"  Month: {m} | Fills: {s['Fills']:2d} | W: {s['Wins']:2d} | L: {s['Losses']:2d} | BE: {s['BE']:2d} | WR: {s['WR%']:5.1f}% | Net R: {s['Net_R']:+6.2f}R | Net PnL: ${s['Net_PnL']:+6.2f} | PF: {s['PF']:.2f}")

    summary = {
        "summer_raw_stats": s_raw,
        "summer_curated_30": s_cur_30,
        "summer_curated_35": s_cur_35,
        "summer_curated_40": s_cur_40,
        "unified_5month_stats": s_unified
    }

    with open(OUTPUT_DIR / "nq_summer_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n✅ NQ Summer 2-Month Audit complete! Saved to {OUTPUT_DIR}")


if __name__ == '__main__':
    run_nq_summer_audit()
