"""
TradingGuard HITL - Long-Term Multi-Month Quantitative Audit for Bitcoin (BTCUSD)
Evaluates algorithmic SMC screening across continuous 24/7 broker bars (Sep 1 to Nov 8, 2026: 69 days, 99k M1 bars).
Audits performance by:
1. Session Window (Asian Early/Late, London Open/Cont, NY Open, NY Silver Bullet, NY Late PM, Pacific)
2. 24-Hour Clock (00 to 23 UTC / Tehran time)
3. Setup Archetype (SETUP-ARCH-001 through SETUP-ARCH-014)
4. Day of Week & Weekday vs Weekend (Mon-Fri vs Sat-Sun)
5. Direction (Long vs Short) & HTF Phase (PRO_EXPANSION vs HTF_RETRACEMENT)
Discovers the optimal institutional sweet spot and identifies toxic drag.
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
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'btcusd_long_term_audit'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_UTC = ZoneInfo("UTC")

def get_session_name(utc_hour: int, utc_minute: int) -> str:
    """
    Classifies the exact institutional session window for Crypto 24/7 markets.
    """
    total_minutes = utc_hour * 60 + utc_minute
    if 0 <= total_minutes < 240:
        return "Asian_Early (00:00-04:00 UTC | 03:30-07:30 Tehran)"
    elif 240 <= total_minutes < 480:
        return "Asian_Late (04:00-08:00 UTC | 07:30-11:30 Tehran)"
    elif 480 <= total_minutes < 630:
        return "London_Open (08:00-10:30 UTC | 11:30-14:00 Tehran)"
    elif 630 <= total_minutes < 780:
        return "London_Continuation (10:30-13:00 UTC | 14:00-16:30 Tehran)"
    elif 780 <= total_minutes < 900:
        return "NY_Open (13:00-15:00 UTC | 16:30-18:30 Tehran)"
    elif 900 <= total_minutes < 990:
        return "NY_Silver_Bullet (15:00-16:30 UTC | 18:30-20:00 Tehran)"
    elif 990 <= total_minutes < 1200:
        return "NY_Late_PM (16:30-20:00 UTC | 20:00-23:30 Tehran)"
    else:
        return "Pacific_Off_Hours (20:00-24:00 UTC | 23:30-03:30 Tehran)"

def get_short_session_key(session_name: str) -> str:
    return session_name.split()[0]

def run_btcusd_audit():
    print("=" * 90)
    print("🚀 TRADINGGUARD - BITCOIN (BTCUSD) LONG-TERM MULTI-MONTH QUANTITATIVE AUDIT")
    print("Zero-Council Pure Algorithmic Pipeline | 69 Days Continuous 24/7 MT5 Microstructure")
    print("=" * 90)

    # 1. Load Parquet Data
    m5_path = CACHE_DIR / 'BTCUSD_M5_2026.parquet'
    m1_path = CACHE_DIR / 'BTCUSD_M1_2026.parquet'
    h1_path = CACHE_DIR / 'BTCUSD_H1_2026.parquet'
    d1_path = CACHE_DIR / 'BTCUSD_D1_2026.parquet'

    if not (m5_path.exists() and m1_path.exists()):
        print(f"Cache missing! Run cache_btcusd_data.py first.")
        return

    print("Loading cached market data...")
    df_m5 = pd.read_parquet(m5_path)
    df_m1 = pd.read_parquet(m1_path)
    df_h1 = pd.read_parquet(h1_path) if h1_path.exists() else None
    df_d1 = pd.read_parquet(d1_path) if d1_path.exists() else None

    # Convert to list of dicts for fast slicing
    bars_m5_all = df_m5.to_dict('records')
    bars_m1_all = df_m1.to_dict('records')
    bars_h1_all = df_h1.to_dict('records') if df_h1 is not None else []
    bars_d1_all = df_d1.to_dict('records') if df_d1 is not None else []

    print(f"Loaded: {len(bars_m5_all):,} M5 bars | {len(bars_m1_all):,} M1 bars | {len(bars_h1_all):,} H1 bars | {len(bars_d1_all):,} D1 bars")

    # Build M1 index map by epoch timestamp for O(1) lookup
    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1_all)}

    # Scan start index (require 120 prior M5 bars for warmup)
    warmup_bars = 120
    total_m5 = len(bars_m5_all)

    trades = []
    active_trade_until = 0  # Epoch timestamp when position closes / expires

    t0_sim = time.time()
    print(f"\nRunning chronological bar-by-bar simulation across {total_m5 - warmup_bars:,} M5 bars...")

    for i in range(warmup_bars, total_m5):
        curr_bar = bars_m5_all[i]
        curr_epoch = curr_bar['time']

        # Skip if a position or pending limit order is actively open
        if curr_epoch < active_trade_until:
            continue

        bar_dt_utc = datetime.datetime.fromtimestamp(curr_epoch, tz=TZ_UTC)
        bar_dt_tehran = bar_dt_utc.astimezone(TZ_TEHRAN)

        # Slice 120 M5 bars up to curr_epoch
        bars_5m_slice = bars_m5_all[i-120:i+1]

        # Slice H1 and D1 bars up to curr_epoch
        bars_1h_slice = [b for b in bars_h1_all if b['time'] <= curr_epoch][-120:]
        bars_1d_slice = [b for b in bars_d1_all if b['time'] <= curr_epoch][-60:]

        if len(bars_1h_slice) < 10:
            continue

        res = screen_ict_session(
            bars_5m=bars_5m_slice,
            bars_1h=bars_1h_slice,
            symbol="BTCUSD",
            session_hour=bar_dt_utc.hour,
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
        if risk_pts < 80.0 or risk_pts > 1200.0:
            # Skip micro noise (<$0.80) or extreme out-of-cap risk (>$12.00)
            continue

        is_buy = "BULLISH" in setup_type or "LONG" in setup_type
        direction = "BUY" if is_buy else "SELL"
        target_rr = res.get("recommended_target_rr", 3.5)
        be_rr = res.get("recommended_be_rr", 1.8)
        tp_p = entry_p + (target_rr * risk_pts) if is_buy else entry_p - (target_rr * risk_pts)

        # Locate forward M1 bars
        # The signal bar closes at curr_epoch. Limit order begins on next minute.
        next_m1_epoch = curr_epoch + 300  # 5 min after current bar start
        m1_start_idx = m1_time_map.get(next_m1_epoch)
        if m1_start_idx is None:
            # Try finding nearest subsequent M1 bar
            forward_m1 = [b for b in bars_m1_all if b['time'] >= next_m1_epoch][:480]
        else:
            forward_m1 = bars_m1_all[m1_start_idx : m1_start_idx + 480]

        if not forward_m1:
            continue

        decision_dict = {
            "decision": direction,
            "entry": round(entry_p, 2),
            "sl": round(sl_p, 2),
            "tp": round(tp_p, 2),
            "lot": 0.01
        }

        eval_res = evaluate_council_decision(
            decision_dict=decision_dict,
            forward_m1_bars=forward_m1,
            symbol="BTCUSD",
            spread_pts=1.50,
            breakeven_rr=be_rr,
            target_rr_cap=target_rr,
            commission_usd=0.10,
            slippage_pts=0.0,
            ttl_minutes=75
        )

        status = eval_res["status"]
        pnl = eval_res["realized_pnl_usd"]
        rr = eval_res.get("rr_realized", 0.0)
        exit_min = eval_res.get("exit_minute") or 75
        fill_min = eval_res.get("fill_minute")

        # Session and Day Metadata
        sess_name = get_session_name(bar_dt_utc.hour, bar_dt_utc.minute)
        sess_key = get_short_session_key(sess_name)
        day_name = bar_dt_utc.strftime("%A")
        is_weekend = bar_dt_utc.weekday() in (5, 6)

        trade_record = {
            "epoch": curr_epoch,
            "time_utc": str(bar_dt_utc),
            "time_tehran": str(bar_dt_tehran),
            "date": bar_dt_utc.strftime("%Y-%m-%d"),
            "hour_utc": bar_dt_utc.hour,
            "hour_tehran": bar_dt_tehran.hour,
            "session_name": sess_name,
            "session_key": sess_key,
            "day_name": day_name,
            "is_weekend": is_weekend,
            "archetype_id": arch_id,
            "setup_type": setup_type,
            "phase": res.get("phase", "UNKNOWN"),
            "direction": direction,
            "entry": entry_p,
            "sl": sl_p,
            "tp": tp_p,
            "risk_pts": risk_pts,
            "risk_usd": risk_pts * 0.01,
            "status": status,
            "realized_pnl_usd": pnl,
            "rr_realized": rr,
            "fill_minute": fill_min,
            "exit_minute": exit_min,
            "notes": eval_res.get("notes", "")
        }
        trades.append(trade_record)

        # Update position tracker
        if status in ("WIN", "LOSS", "BREAKEVEN"):
            active_trade_until = curr_epoch + (exit_min * 60)
        elif status == "EXPIRED":
            active_trade_until = curr_epoch + (75 * 60)

    elapsed_sim = time.time() - t0_sim
    print(f"Simulation completed in {elapsed_sim:.2f}s! Total signals evaluated: {len(trades)}")

    # Convert trades to DataFrame
    df_trades = pd.DataFrame(trades)
    df_trades.to_parquet(OUTPUT_DIR / "btcusd_long_term_trades.parquet")
    df_trades.to_csv(OUTPUT_DIR / "btcusd_long_term_trades.csv", index=False)

    # 2. Performance Aggregation Functions
    def compute_metrics(subset: pd.DataFrame, label: str = "Group") -> dict:
        total = len(subset)
        if total == 0:
            return {"Name": label, "Signals": 0, "Fills": 0, "Wins": 0, "Losses": 0, "BE": 0, "Exp": 0, "WR%": 0.0, "Net_R": 0.0, "Net_PnL": 0.0, "PF": 0.0, "Expectancy_R": 0.0}

        fills = subset[subset['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
        n_fills = len(fills)
        wins = subset[subset['status'] == 'WIN']
        losses = subset[subset['status'] == 'LOSS']
        bes = subset[subset['status'] == 'BREAKEVEN']
        exp = subset[subset['status'] == 'EXPIRED']

        n_wins = len(wins)
        n_losses = len(losses)
        n_be = len(bes)
        n_exp = len(exp)

        wr = (n_wins / n_fills * 100) if n_fills > 0 else 0.0
        net_pnl = subset['realized_pnl_usd'].sum()
        net_r = subset['rr_realized'].dropna().sum()

        gross_win_usd = wins['realized_pnl_usd'].sum()
        gross_loss_usd = abs(losses['realized_pnl_usd'].sum())
        pf = (gross_win_usd / gross_loss_usd) if gross_loss_usd > 0 else (99.0 if gross_win_usd > 0 else 0.0)

        exp_r = (net_r / n_fills) if n_fills > 0 else 0.0

        return {
            "Name": label,
            "Signals": total,
            "Fills": n_fills,
            "Wins": n_wins,
            "Losses": n_losses,
            "BE": n_be,
            "Exp": n_exp,
            "WR%": round(wr, 1),
            "Net_R": round(net_r, 2),
            "Net_PnL": round(net_pnl, 2),
            "PF": round(pf, 2),
            "Expectancy_R": round(exp_r, 2)
        }

    # 3. Overall Raw Baseline
    raw_summary = compute_metrics(df_trades, "Raw Unfiltered Baseline")

    # 4. Dimension 1: Session Breakdown
    session_rows = []
    for sess, group in df_trades.groupby('session_name'):
        session_rows.append(compute_metrics(group, sess))
    df_sessions = pd.DataFrame(session_rows).sort_values('Net_R', ascending=False)

    # 5. Dimension 2: Hourly Clock Breakdown (UTC and Tehran)
    hourly_rows = []
    for h, group in df_trades.groupby('hour_utc'):
        tehran_h = (h + 3) % 24
        tehran_str = f"{tehran_h:02d}:30"
        label = f"{h:02d}:00 UTC ({tehran_str} Tehran)"
        m = compute_metrics(group, label)
        m["Hour_UTC"] = h
        m["Hour_Tehran"] = tehran_str
        hourly_rows.append(m)
    df_hourly = pd.DataFrame(hourly_rows).sort_values('Hour_UTC')

    # 6. Dimension 3: Setup Archetype Breakdown
    arch_rows = []
    for arch, group in df_trades.groupby('archetype_id'):
        arch_rows.append(compute_metrics(group, arch))
    df_archetypes = pd.DataFrame(arch_rows).sort_values('Net_R', ascending=False)

    # 7. Dimension 4: Day of Week & Weekend vs Weekday
    day_rows = []
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for day in day_order:
        group = df_trades[df_trades['day_name'] == day]
        day_rows.append(compute_metrics(group, day))
    df_days = pd.DataFrame(day_rows)

    weekend_metrics = compute_metrics(df_trades[df_trades['is_weekend'] == True], "Weekend (Sat-Sun)")
    weekday_metrics = compute_metrics(df_trades[df_trades['is_weekend'] == False], "Weekday (Mon-Fri)")
    df_weekend = pd.DataFrame([weekday_metrics, weekend_metrics])

    # 8. Dimension 5: Direction & HTF Phase Breakdown
    dir_rows = []
    for d, group in df_trades.groupby('direction'):
        dir_rows.append(compute_metrics(group, d))
    df_direction = pd.DataFrame(dir_rows)

    phase_rows = []
    for ph, group in df_trades.groupby('phase'):
        phase_rows.append(compute_metrics(group, ph))
    df_phase = pd.DataFrame(phase_rows)

    # 9. Strategy Optimization: Identify Toxic Drag vs Alpha Generators
    # Toxic Sessions: Sessions with Net_R <= 0 or PF < 1.0
    toxic_sessions = df_sessions[df_sessions['Net_R'] < 0]['Name'].tolist()
    profitable_sessions = df_sessions[df_sessions['Net_R'] > 0]['Name'].tolist()

    # Toxic Archetypes: Archetypes with Net_R <= 0 or PF < 1.0
    toxic_archetypes = df_archetypes[df_archetypes['Net_R'] < 0]['Name'].tolist()
    profitable_archetypes = df_archetypes[df_archetypes['Net_R'] > 0]['Name'].tolist()

    # Calibrated Curated Portfolio: Filter out toxic sessions AND toxic archetypes
    # Also check weekend filter
    curated_mask = (
        (~df_trades['session_name'].isin(toxic_sessions)) &
        (~df_trades['archetype_id'].isin(toxic_archetypes))
    )
    df_curated = df_trades[curated_mask]
    curated_summary = compute_metrics(df_curated, "Calibrated Curated Bitcoin Portfolio")

    # If weekend is also toxic, create Weekday Calibrated Portfolio
    weekday_curated_mask = curated_mask & (df_trades['is_weekend'] == False)
    df_weekday_curated = df_trades[weekday_curated_mask]
    weekday_curated_summary = compute_metrics(df_weekday_curated, "Weekday-Only Calibrated Portfolio")

    # 10. Print Comprehensive Report
    print("\n" + "=" * 90)
    print("📊 1. OVERALL RAW BASELINE (ALL HOURS, ALL SETUPS, NO FILTERS)")
    print("=" * 90)
    print(pd.DataFrame([raw_summary]).to_string(index=False))

    print("\n" + "=" * 90)
    print("🕒 2. PERFORMANCE BY INSTITUTIONAL SESSION WINDOW")
    print("=" * 90)
    print(df_sessions.to_string(index=False))

    print("\n" + "=" * 90)
    print("🎯 3. PERFORMANCE BY SETUP ARCHETYPE")
    print("=" * 90)
    print(df_archetypes.to_string(index=False))

    print("\n" + "=" * 90)
    print("📅 4. PERFORMANCE BY DAY OF WEEK & WEEKDAY VS WEEKEND")
    print("=" * 90)
    print(df_days.to_string(index=False))
    print("-" * 90)
    print(df_weekend.to_string(index=False))

    print("\n" + "=" * 90)
    print("🧭 5. PERFORMANCE BY DIRECTION & HTF PHASE")
    print("=" * 90)
    print(df_direction.to_string(index=False))
    print("-" * 90)
    print(df_phase.to_string(index=False))

    print("\n" + "=" * 90)
    print("🏆 6. RAW BASELINE VS. CALIBRATED CURATED PORTFOLIO")
    print("=" * 90)
    comp_df = pd.DataFrame([raw_summary, curated_summary, weekday_curated_summary])
    print(comp_df.to_string(index=False))

    # Save summary JSON
    summary_data = {
        "raw_summary": raw_summary,
        "curated_summary": curated_summary,
        "weekday_curated_summary": weekday_curated_summary,
        "sessions": df_sessions.to_dict('records'),
        "archetypes": df_archetypes.to_dict('records'),
        "hourly": df_hourly.to_dict('records'),
        "days": df_days.to_dict('records'),
        "weekend_vs_weekday": df_weekend.to_dict('records'),
        "direction": df_direction.to_dict('records'),
        "phase": df_phase.to_dict('records'),
        "toxic_sessions": toxic_sessions,
        "profitable_sessions": profitable_sessions,
        "toxic_archetypes": toxic_archetypes,
        "profitable_archetypes": profitable_archetypes
    }
    with open(OUTPUT_DIR / "btcusd_long_term_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    print(f"\nAll data, trades, and summary matrices successfully saved to: {OUTPUT_DIR}")
    return summary_data

if __name__ == "__main__":
    run_btcusd_audit()
