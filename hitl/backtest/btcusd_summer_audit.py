"""
TradingGuard HITL - Bitcoin (BTCUSD) Out-Of-Sample Summer Audit (July 1 - August 31, 2026)
Zero-Council Pure Algorithmic Pipeline | 62 Days Continuous 24/7 MT5 Microstructure (17,857 M5 Bars, 89,235 M1 Bars)
Validates:
1. Stability of Curated Archetype-Session Match (Config 4) out-of-sample
2. Decommissioning confirmation for ARCH-009 & ARCH-010
3. Persistence of Toxic Sessions (NY Late PM, Asian Early, London Continuation)
4. Dynamic Seasonal Session Clock (Summer DST: London Open 10:30 Tehran, NY Open 15:30 Tehran)
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
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'btcusd_summer_audit'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_LONDON = ZoneInfo("Europe/London")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_UTC = datetime.timezone.utc


def get_dynamic_crypto_session(dt_utc: datetime.datetime) -> tuple:
    """
    Returns (session_name, session_key) factoring in DST shifts.
    """
    d = dt_utc.date()
    lon_open = datetime.datetime(d.year, d.month, d.day, 8, 0, tzinfo=TZ_LONDON).astimezone(TZ_UTC)
    ny_open = datetime.datetime(d.year, d.month, d.day, 8, 0, tzinfo=TZ_NEW_YORK).astimezone(TZ_UTC)
    ny_sb_start = datetime.datetime(d.year, d.month, d.day, 10, 0, tzinfo=TZ_NEW_YORK).astimezone(TZ_UTC)
    ny_sb_end = datetime.datetime(d.year, d.month, d.day, 11, 0, tzinfo=TZ_NEW_YORK).astimezone(TZ_UTC)
    ny_late_start = datetime.datetime(d.year, d.month, d.day, 11, 30, tzinfo=TZ_NEW_YORK).astimezone(TZ_UTC)
    ny_late_end = datetime.datetime(d.year, d.month, d.day, 15, 0, tzinfo=TZ_NEW_YORK).astimezone(TZ_UTC)

    lon_cont_start = lon_open + datetime.timedelta(hours=2, minutes=30)
    
    asian_early_start = dt_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    asian_early_end = dt_utc.replace(hour=4, minute=0, second=0, microsecond=0)

    if asian_early_start <= dt_utc < asian_early_end:
        return "Asian_Early (00:00-04:00 UTC | 03:30-07:30 Tehran)", "Asian_Early"
    elif asian_early_end <= dt_utc < lon_open:
        lon_str = lon_open.astimezone(TZ_TEHRAN).strftime("%H:%M")
        return f"Asian_Late (04:00-{lon_open.strftime('%H:%M')} UTC | 07:30-{lon_str} Tehran)", "Asian_Late"
    elif lon_open <= dt_utc < lon_cont_start:
        return f"London_Open ({lon_open.strftime('%H:%M')} UTC | {lon_open.astimezone(TZ_TEHRAN).strftime('%H:%M')} Tehran)", "London_Open"
    elif lon_cont_start <= dt_utc < ny_open:
        return f"London_Continuation ({lon_cont_start.strftime('%H:%M')}-{ny_open.strftime('%H:%M')} UTC)", "London_Continuation"
    elif ny_open <= dt_utc < ny_sb_start:
        return f"NY_Open ({ny_open.strftime('%H:%M')} UTC | {ny_open.astimezone(TZ_TEHRAN).strftime('%H:%M')} Tehran)", "NY_Open"
    elif ny_sb_start <= dt_utc <= ny_sb_end:
        return f"NY_Silver_Bullet ({ny_sb_start.strftime('%H:%M')}-{ny_sb_end.strftime('%H:%M')} UTC)", "NY_Silver_Bullet"
    elif ny_late_start <= dt_utc < ny_late_end:
        return f"NY_Late_PM ({ny_late_start.strftime('%H:%M')}-{ny_late_end.strftime('%H:%M')} UTC)", "NY_Late_PM"
    else:
        return f"Pacific_Off_Hours ({ny_late_end.strftime('%H:%M')}-24:00 UTC)", "Pacific_Off_Hours"


def run_btcusd_summer_audit():
    print("=" * 90)
    print("🚀 TRADINGGUARD - BITCOIN (BTCUSD) OUT-OF-SAMPLE SUMMER AUDIT (JUL 1 - AUG 31, 2026)")
    print("Zero-Council Pure Algorithmic Pipeline | 62 Days Continuous 24/7 MT5 Microstructure")
    print("=" * 90)

    # 1. Load Parquet Data
    m5_path = CACHE_DIR / 'BTCUSD_M5_SUMMER_2026.parquet'
    m1_path = CACHE_DIR / 'BTCUSD_M1_SUMMER_2026.parquet'
    h1_path = CACHE_DIR / 'BTCUSD_H1_SUMMER_2026.parquet'
    d1_path = CACHE_DIR / 'BTCUSD_D1_SUMMER_2026.parquet'

    if not (m5_path.exists() and m1_path.exists()):
        print(f"Cache missing! Run cache_btcusd_summer_data.py first.")
        return

    print("Loading cached market data...")
    df_m5 = pd.read_parquet(m5_path)
    df_m1 = pd.read_parquet(m1_path)
    df_h1 = pd.read_parquet(h1_path) if h1_path.exists() else None
    df_d1 = pd.read_parquet(d1_path) if d1_path.exists() else None

    # Filter strictly to July 1 to August 31, 2026 (keep warmup bars prior to July 1)
    t_july1_epoch = int(datetime.datetime(2026, 7, 1, 0, 0, tzinfo=TZ_UTC).timestamp())
    t_aug31_epoch = int(datetime.datetime(2026, 8, 31, 23, 59, 59, tzinfo=TZ_UTC).timestamp())

    bars_m5_all = df_m5.to_dict('records')
    bars_m1_all = df_m1.to_dict('records')
    bars_h1_all = df_h1.to_dict('records') if df_h1 is not None else []
    bars_d1_all = df_d1.to_dict('records') if df_d1 is not None else []

    print(f"Loaded: {len(bars_m5_all):,} M5 bars | {len(bars_m1_all):,} M1 bars | {len(bars_h1_all):,} H1 bars | {len(bars_d1_all):,} D1 bars")

    # Build M1 index map by epoch timestamp for O(1) lookup
    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1_all)}

    # Find the index of July 1 in M5
    start_m5_idx = None
    for idx, b in enumerate(bars_m5_all):
        if b['time'] >= t_july1_epoch:
            start_m5_idx = idx
            break

    if start_m5_idx is None or start_m5_idx < 120:
        start_m5_idx = 120

    total_m5 = len(bars_m5_all)
    trades = []
    active_trade_until = 0

    t0_sim = time.time()
    print(f"\nRunning chronological bar-by-bar simulation across Summer M5 bars (starting index {start_m5_idx:,} of {total_m5:,})...")

    eval_count = 0
    for i in range(start_m5_idx, total_m5):
        curr_bar = bars_m5_all[i]
        curr_epoch = curr_bar['time']

        if curr_epoch > t_aug31_epoch:
            break

        if curr_epoch < active_trade_until:
            continue

        bar_dt_utc = datetime.datetime.fromtimestamp(curr_epoch, tz=TZ_UTC)
        bar_dt_tehran = bar_dt_utc.astimezone(TZ_TEHRAN)

        # Slice 120 M5 bars up to curr_epoch
        m5_slice = bars_m5_all[i - 119 : i + 1]

        # Slice H1 and D1 bars up to curr_epoch
        h1_slice = [b for b in bars_h1_all if b['time'] <= curr_epoch][-100:]
        d1_slice = [b for b in bars_d1_all if b['time'] <= curr_epoch][-30:]

        eval_count += 1
        if eval_count % 3000 == 0:
            print(f"  Processed {eval_count:,} M5 bars | Current time: {bar_dt_utc.strftime('%Y-%m-%d %H:%M')} UTC | Candidate signals: {len(trades)}")

        # Run algorithmic screener
        res = screen_ict_session(
            bars_5m=m5_slice,
            bars_1h=h1_slice,
            symbol="BTCUSD",
            session_hour=bar_dt_utc.hour,
            bars_1m=None,
            bars_1d=d1_slice,
            closed_bars_only=True
        )
        if not res.get("has_setup") or res.get("setup_type") == "NONE":
            continue

        setup_type = res.get("setup_type", "NONE")
        arch_id = res.get("archetype_id", "NONE")
        entry_p = res.get("entry_ref")
        sl_p = res.get("sl_ref")

        if not (entry_p and sl_p):
            continue

        risk_pts = abs(entry_p - sl_p)
        if risk_pts < 80.0 or risk_pts > 1200.0:
            continue

        is_buy = "BULLISH" in setup_type or "LONG" in setup_type
        direction = "BUY" if is_buy else "SELL"
        target_rr = res.get("recommended_target_rr", 3.5)
        be_rr = res.get("recommended_be_rr", 1.8)
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

        sess_name, sess_key = get_dynamic_crypto_session(bar_dt_utc)
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

        if status in ("WIN", "LOSS", "BREAKEVEN"):
            active_trade_until = curr_epoch + (exit_min * 60)
        elif status == "EXPIRED":
            active_trade_until = curr_epoch + (75 * 60)

    elapsed_sim = time.time() - t0_sim
    print(f"\nSimulation completed in {elapsed_sim:.2f}s! Total signals evaluated: {len(trades)}")

    df_trades = pd.DataFrame(trades)
    df_trades.to_parquet(OUTPUT_DIR / "btcusd_summer_trades.parquet")
    df_trades.to_csv(OUTPUT_DIR / "btcusd_summer_trades.csv", index=False)

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

    raw_summary = compute_metrics(df_trades, "Raw Unfiltered Baseline (Summer)")

    # Session breakdown
    session_rows = []
    for sess, group in df_trades.groupby('session_key'):
        session_rows.append(compute_metrics(group, sess))
    df_sessions = pd.DataFrame(session_rows).sort_values('Net_R', ascending=False)

    # Hourly breakdown
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

    # Archetype breakdown
    arch_rows = []
    for arch, group in df_trades.groupby('archetype_id'):
        arch_rows.append(compute_metrics(group, arch))
    df_archetypes = pd.DataFrame(arch_rows).sort_values('Net_R', ascending=False)

    # Day of week
    day_rows = []
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for day in day_order:
        group = df_trades[df_trades['day_name'] == day]
        day_rows.append(compute_metrics(group, day))
    df_days = pd.DataFrame(day_rows)

    weekend_metrics = compute_metrics(df_trades[df_trades['is_weekend'] == True], "Weekend (Sat-Sun)")
    weekday_metrics = compute_metrics(df_trades[df_trades['is_weekend'] == False], "Weekday (Mon-Fri)")
    df_weekend = pd.DataFrame([weekday_metrics, weekend_metrics])

    # Direction & Phase
    dir_rows = [compute_metrics(df_trades[df_trades['direction'] == d], d) for d in ['BUY', 'SELL']]
    phase_rows = [compute_metrics(df_trades[df_trades['phase'] == p], p) for p in df_trades['phase'].unique() if p]

    # Evaluate the 8 optimization configurations on Summer data
    opt_rows = []
    opt_rows.append(compute_metrics(df_trades, "0. Raw Baseline (Summer)"))

    # Config 1: Decommission ARCH-009 & ARCH-010
    f1 = df_trades[~df_trades['archetype_id'].isin(['SETUP-ARCH-009', 'SETUP-ARCH-010'])]
    opt_rows.append(compute_metrics(f1, "1. Decommission ARCH-009 & ARCH-010"))

    # Config 2: Config 1 + Ban 3 Toxic Sessions (NY_Late_PM, Asian_Early, London_Continuation)
    f2 = df_trades[
        (~df_trades['archetype_id'].isin(['SETUP-ARCH-009', 'SETUP-ARCH-010'])) &
        (~df_trades['session_key'].isin(['NY_Late_PM', 'Asian_Early', 'London_Continuation']))
    ]
    opt_rows.append(compute_metrics(f2, "2. Config 1 + Ban 3 Toxic Sessions"))

    # Config 3: Curated Archetype-Session Match
    c1 = (df_trades['archetype_id'] == 'SETUP-ARCH-001') & (df_trades['session_key'].isin(['Asian_Early', 'Asian_Late', 'NY_Open', 'NY_Silver_Bullet']))
    c2 = (df_trades['archetype_id'] == 'SETUP-ARCH-002') & (df_trades['session_key'].isin(['London_Open', 'NY_Silver_Bullet']))
    c3 = (df_trades['archetype_id'] == 'SETUP-ARCH-004') & (df_trades['session_key'].isin(['Asian_Late', 'NY_Open']))
    c4 = (df_trades['archetype_id'] == 'SETUP-ARCH-011') & (df_trades['session_key'].isin(['London_Continuation', 'Asian_Late']))
    f3 = df_trades[c1 | c2 | c3 | c4]
    opt_rows.append(compute_metrics(f3, "3. Curated Archetype-Session Match"))

    # Config 4: Config 3 Weekday Only (Mon-Fri)
    f4 = df_trades[(c1 | c2 | c3 | c4) & (df_trades['is_weekend'] == False)]
    opt_rows.append(compute_metrics(f4, "4. Config 3 Weekday Only (Mon-Fri)"))

    df_opt = pd.DataFrame(opt_rows)

    print("\n" + "=" * 90)
    print("📊 BITCOIN SUMMER AUDIT - STRATEGY OPTIMIZATION MATRIX (JUL 1 - AUG 31, 2026)")
    print("=" * 90)
    print(df_opt[['Name', 'Fills', 'Wins', 'Losses', 'BE', 'WR%', 'Net_R', 'Net_PnL', 'PF']].to_string(index=False))

    print("\n" + "=" * 90)
    print("📊 ARCHETYPE BREAKDOWN (SUMMER 2026)")
    print("=" * 90)
    print(df_archetypes[['Name', 'Signals', 'Fills', 'Wins', 'Losses', 'BE', 'WR%', 'Net_R', 'PF']].to_string(index=False))

    print("\n" + "=" * 90)
    print("📊 SESSION BREAKDOWN (SUMMER 2026)")
    print("=" * 90)
    print(df_sessions[['Name', 'Signals', 'Fills', 'Wins', 'Losses', 'BE', 'WR%', 'Net_R', 'PF']].to_string(index=False))

    print("\n" + "=" * 90)
    print("📊 WEEKEND VS WEEKDAY (SUMMER 2026)")
    print("=" * 90)
    print(df_weekend[['Name', 'Signals', 'Fills', 'Wins', 'Losses', 'BE', 'WR%', 'Net_R', 'PF']].to_string(index=False))

    # Save complete JSON summary
    summary_data = {
        "raw_summary": raw_summary,
        "curated_summary": compute_metrics(f4, "Calibrated Curated Bitcoin Portfolio (Summer)"),
        "optimization_matrix": opt_rows,
        "sessions": session_rows,
        "archetypes": arch_rows,
        "hourly": hourly_rows,
        "days": day_rows,
        "weekend_vs_weekday": [weekday_metrics, weekend_metrics],
        "direction": dir_rows,
        "phase": phase_rows
    }
    with open(OUTPUT_DIR / "btcusd_summer_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    print(f"\nAll summer audit results saved to {OUTPUT_DIR}/")


if __name__ == '__main__':
    run_btcusd_summer_audit()
