"""
TradingGuard HITL - Extended 3.2-Month Nasdaq 100 (NQ) Comprehensive Audit
Spans continuous MT5 broker data from August 1 to November 6, 2026 (20,652 M5 bars, 96,352 M1 bars).
Audits both:
1. Extended Raw Baseline (24h, all 6 archetypes)
2. Extended Curated Institutional Portfolio (London Open + NY Pre-Market, toxic setups banned)
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
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'nq_extended_3month_audit'
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
        return "Weekend_Off_Hours", "Weekend"

    if datetime.time(9, 30) <= ny_time < datetime.time(10, 0):
        return f"NYSE_Cash_Open (09:30-10:00 NY | {dt_tehran.strftime('%H:%M')} Tehran)", "NYSE_Cash_Open"
    elif datetime.time(10, 0) <= ny_time < datetime.time(11, 0):
        return f"NY_Silver_Bullet (10:00-11:00 NY | {dt_tehran.strftime('%H:%M')} Tehran)", "NY_Silver_Bullet"
    elif datetime.time(8, 0) <= ny_time < datetime.time(9, 30):
        return f"NY_Pre_Market (08:00-09:30 NY | {dt_tehran.strftime('%H:%M')} Tehran)", "NY_Pre_Market"
    elif datetime.time(11, 0) <= ny_time < datetime.time(16, 0):
        return f"NY_Regular_PM (11:00-16:00 NY | {dt_tehran.strftime('%H:%M')} Tehran)", "NY_Regular_PM"
    elif datetime.time(8, 0) <= lon_time < datetime.time(10, 30):
        return f"London_Open (08:00-10:30 Lon | {dt_tehran.strftime('%H:%M')} Tehran)", "London_Open"
    elif datetime.time(10, 30) <= lon_time < datetime.time(13, 0):
        return f"London_Continuation (10:30-13:00 Lon | {dt_tehran.strftime('%H:%M')} Tehran)", "London_Cont"
    elif datetime.time(0, 0) <= dt_utc.time() < datetime.time(7, 0):
        return f"Asian_Overnight (00:00-07:00 UTC | {dt_tehran.strftime('%H:%M')} Tehran)", "Asian_Overnight"
    else:
        return f"Pacific_Off_Hours ({dt_utc.strftime('%H:%M')} UTC | {dt_tehran.strftime('%H:%M')} Tehran)", "Pacific_Off_Hours"


def run_extended_nq_audit():
    print("=" * 95)
    print("🚀 TRADINGGUARD - EXTENDED 3.2-MONTH NASDAQ 100 (NQ) COMPREHENSIVE AUDIT")
    print("Aug 1 to Nov 6, 2026 MT5 Broker Microstructure | 20,652 M5 Bars | 96,352 M1 Bars")
    print("=" * 95)

    m5_path = CACHE_DIR / 'NQ_M5_EXTENDED_2026.parquet'
    m1_path = CACHE_DIR / 'NQ_M1_EXTENDED_2026.parquet'
    h1_path = CACHE_DIR / 'NQ_H1_EXTENDED_2026.parquet'
    d1_path = CACHE_DIR / 'NQ_D1_EXTENDED_2026.parquet'

    df_m5 = pd.read_parquet(m5_path)
    df_m1 = pd.read_parquet(m1_path)
    df_h1 = pd.read_parquet(h1_path) if h1_path.exists() else None
    df_d1 = pd.read_parquet(d1_path) if d1_path.exists() else None

    bars_m5_all = df_m5.to_dict('records')
    bars_m1_all = df_m1.to_dict('records')
    bars_h1_all = df_h1.to_dict('records') if df_h1 is not None else []
    bars_d1_all = df_d1.to_dict('records') if df_d1 is not None else []

    print(f"Loaded Extended Cache: {len(bars_m5_all):,} M5 bars | {len(bars_m1_all):,} M1 bars | {len(bars_h1_all):,} H1 bars")

    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1_all)}

    warmup_bars = 120
    total_m5 = len(bars_m5_all)

    # --- 1. RUN RAW BASELINE SIMULATION ---
    print(f"\n1. Running Extended Raw Baseline Simulation across {total_m5 - warmup_bars:,} M5 bars...")
    trades_raw = []
    active_until_raw = 0
    t0 = time.time()

    for i in range(warmup_bars, total_m5):
        curr_bar = bars_m5_all[i]
        curr_epoch = curr_bar['time']

        if curr_epoch < active_until_raw:
            continue

        bar_dt_utc = datetime.datetime.fromtimestamp(curr_epoch, tz=TZ_UTC)
        bar_dt_tehran = bar_dt_utc.astimezone(TZ_TEHRAN)
        bar_dt_ny = bar_dt_utc.astimezone(TZ_NEW_YORK)

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
        target_rr = res.get("recommended_target_rr", 3.0)
        be_rr = res.get("recommended_be_rr", 1.5)
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
        fill_min = eval_res.get("fill_minute")

        sess_name, sess_key = classify_nq_session(bar_dt_utc)
        day_name = bar_dt_utc.strftime("%A")

        trade_record = {
            "epoch": curr_epoch,
            "time_utc": str(bar_dt_utc),
            "time_ny": str(bar_dt_ny),
            "time_tehran": str(bar_dt_tehran),
            "date": bar_dt_utc.strftime("%Y-%m-%d"),
            "month": bar_dt_utc.strftime("%B"),
            "session_name": sess_name,
            "session_key": sess_key,
            "day_name": day_name,
            "archetype_id": arch_id,
            "setup_type": setup_type,
            "direction": direction,
            "entry": entry_p,
            "sl": sl_p,
            "tp": tp_p,
            "risk_pts": risk_pts,
            "status": status,
            "realized_pnl_usd": pnl,
            "rr_realized": rr,
            "fill_minute": fill_min,
            "exit_minute": exit_min
        }
        trades_raw.append(trade_record)

        if status in ("WIN", "LOSS", "BREAKEVEN"):
            active_until_raw = curr_epoch + (exit_min * 60)
        elif status == "EXPIRED":
            active_until_raw = curr_epoch + (60 * 60)

    print(f"Raw simulation finished in {time.time()-t0:.2f}s! Signals: {len(trades_raw)}")
    df_raw = pd.DataFrame(trades_raw)
    df_raw.to_parquet(OUTPUT_DIR / "nq_extended_raw_trades.parquet")

    # --- 2. RUN CURATED INSTITUTIONAL POLICY SIMULATION ---
    print(f"\n2. Running Extended Curated Institutional Policy Simulation...")
    trades_curated = []
    active_until_curated = 0
    t1 = time.time()

    for i in range(warmup_bars, total_m5):
        curr_bar = bars_m5_all[i]
        curr_epoch = curr_bar['time']

        if curr_epoch < active_until_curated:
            continue

        bar_dt_utc = datetime.datetime.fromtimestamp(curr_epoch, tz=TZ_UTC)
        sess_name, sess_key = classify_nq_session(bar_dt_utc)

        # Curated Institutional Windows: London Open (08:00-10:30 Lon) & NY Pre-Market (08:00-09:30 NY)
        if sess_key not in ("London_Open", "NY_Pre_Market"):
            continue

        bar_dt_tehran = bar_dt_utc.astimezone(TZ_TEHRAN)
        bar_dt_ny = bar_dt_utc.astimezone(TZ_NEW_YORK)

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

        # Decommission toxic archetypes
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
        target_rr = res.get("recommended_target_rr", 3.0)
        be_rr = res.get("recommended_be_rr", 1.5)
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
        fill_min = eval_res.get("fill_minute")

        day_name = bar_dt_utc.strftime("%A")

        trade_record = {
            "epoch": curr_epoch,
            "time_utc": str(bar_dt_utc),
            "time_ny": str(bar_dt_ny),
            "time_tehran": str(bar_dt_tehran),
            "date": bar_dt_utc.strftime("%Y-%m-%d"),
            "month": bar_dt_utc.strftime("%B"),
            "session_name": sess_name,
            "session_key": sess_key,
            "day_name": day_name,
            "archetype_id": arch_id,
            "setup_type": setup_type,
            "direction": direction,
            "entry": entry_p,
            "sl": sl_p,
            "tp": tp_p,
            "risk_pts": risk_pts,
            "status": status,
            "realized_pnl_usd": pnl,
            "rr_realized": rr,
            "fill_minute": fill_min,
            "exit_minute": exit_min
        }
        trades_curated.append(trade_record)

        if status in ("WIN", "LOSS", "BREAKEVEN"):
            active_until_curated = curr_epoch + (exit_min * 60)
        elif status == "EXPIRED":
            active_until_curated = curr_epoch + (60 * 60)

    print(f"Curated simulation finished in {time.time()-t1:.2f}s! Signals: {len(trades_curated)}")
    df_curated = pd.DataFrame(trades_curated)
    df_curated.to_parquet(OUTPUT_DIR / "nq_extended_curated_trades.parquet")

    # Metrics helper
    def get_stats(df_sub):
        fills = df_sub[df_sub['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
        n = len(fills)
        wins = len(df_sub[df_sub['status'] == 'WIN'])
        losses = len(df_sub[df_sub['status'] == 'LOSS'])
        be = len(df_sub[df_sub['status'] == 'BREAKEVEN'])
        exp = len(df_sub[df_sub['status'] == 'EXPIRED'])
        wr = (wins / n * 100) if n > 0 else 0.0
        net_r = df_sub['rr_realized'].sum()
        net_pnl = df_sub['realized_pnl_usd'].sum()
        gp = df_sub[df_sub['realized_pnl_usd'] > 0]['realized_pnl_usd'].sum()
        gl = abs(df_sub[df_sub['realized_pnl_usd'] < 0]['realized_pnl_usd'].sum())
        pf = (gp / gl) if gl > 0 else (99.0 if gp > 0 else 0.0)
        return {
            "Signals": len(df_sub), "Fills": n, "Wins": wins, "Losses": losses, "BE": be, "Exp": exp,
            "WR%": round(wr, 1), "Net_R": round(net_r, 2), "Net_PnL": round(net_pnl, 2), "PF": round(pf, 2)
        }

    raw_stats = get_stats(df_raw)
    cur_stats = get_stats(df_curated)

    print("\n" + "=" * 95)
    print("📊 EXTENDED 3.2-MONTH RESULTS (AUGUST 1 TO NOVEMBER 6, 2026)")
    print("=" * 95)
    print("RAW BASELINE :", raw_stats)
    print("CURATED CORE :", cur_stats)

    # Monthly breakdown for curated portfolio
    print("\n--- CURATED PORTFOLIO MONTHLY PERFORMANCE ---")
    monthly_rows = []
    month_order = ["August", "September", "October", "November"]
    for m in month_order:
        sub = df_curated[df_curated['month'] == m]
        if not sub.empty:
            s = get_stats(sub)
            s["Month"] = m
            monthly_rows.append(s)
            print(f"  {m:10s} | Fills: {s['Fills']:2d} | W: {s['Wins']:2d} | L: {s['Losses']:2d} | BE: {s['BE']:2d} | WR: {s['WR%']:5.1f}% | Net R: {s['Net_R']:+6.2f}R | Net PnL: ${s['Net_PnL']:+6.2f} | PF: {s['PF']:.2f}")

    # Archetype breakdown for curated portfolio
    print("\n--- CURATED PORTFOLIO ARCHETYPE BREAKDOWN ---")
    for arch, g in df_curated.groupby('archetype_id'):
        s = get_stats(g)
        print(f"  {arch:15s} | Fills: {s['Fills']:2d} | W: {s['Wins']:2d} | L: {s['Losses']:2d} | BE: {s['BE']:2d} | WR: {s['WR%']:5.1f}% | Net R: {s['Net_R']:+6.2f}R | Net PnL: ${s['Net_PnL']:+6.2f} | PF: {s['PF']:.2f}")

    summary_export = {
        "raw_stats": raw_stats,
        "curated_stats": cur_stats,
        "monthly": monthly_rows
    }
    with open(OUTPUT_DIR / "nq_extended_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_export, f, indent=2)

    print(f"\n✅ Extended Audit Complete! Results saved to {OUTPUT_DIR}")


if __name__ == '__main__':
    run_extended_nq_audit()
