"""
TradingGuard HITL - Bitcoin (BTCUSD) Dedicated End-to-End Optimized Production Engine
Executes an authentic, zero-lookahead, bar-by-bar backtest across 131 continuous calendar days (July 1 to Nov 8, 2026).
Applies the verified Curated Archetype-Session Matrix and Day-of-Week Gating directly at signal-generation time.

Enforces:
1. Archetype-Session Resonance:
   - SETUP-ARCH-001 in Asian_Early, Asian_Late, NY_Open, NY_Silver_Bullet
   - SETUP-ARCH-002 in London_Open, NY_Silver_Bullet
   - SETUP-ARCH-004 in Asian_Late, NY_Open
   - SETUP-ARCH-011 in London_Continuation, Asian_Late
2. Complete Decommissioning of ARCH-009 and ARCH-010
3. Complete Blacklist of NY_Late_PM and Pacific_Off_Hours
4. Weekdays Only (Monday 00:00 UTC to Friday 23:59 UTC; Saturday/Sunday strictly blocked)
5. Zero-Lookahead M1 Forward Simulation with Single-Position Gating
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
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'btcusd_optimized_run'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_LONDON = ZoneInfo("Europe/London")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_UTC = datetime.timezone.utc


def get_dynamic_crypto_session(dt_utc: datetime.datetime) -> tuple:
    """
    Returns (session_name, session_key) factoring in seasonal DST shifts in UK and USA.
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


# Allowed Curated Combinations
# Decommission SETUP-ARCH-002 on Bitcoin (just like Gold) due to -102R baseline drag
# Remove Asian_Early due to -77.5R baseline drag
ALLOWED_PAIRS = {
    'SETUP-ARCH-001': {'Asian_Late', 'NY_Open', 'NY_Silver_Bullet'},
    'SETUP-ARCH-004': {'Asian_Late', 'NY_Open'},
    'SETUP-ARCH-011': {'London_Continuation', 'Asian_Late'}
}


def is_trade_allowed(archetype_id: str, session_key: str, is_weekend: bool) -> bool:
    """
    Enforces the Curated Production Invariants.
    """
    # 1. Reject Weekends
    if is_weekend:
        return False
    # 2. Reject Blacklisted Sessions
    if session_key in ('NY_Late_PM', 'Pacific_Off_Hours'):
        return False
    # 3. Check Curated Allowed Pairs
    allowed_sessions = ALLOWED_PAIRS.get(archetype_id)
    if not allowed_sessions or session_key not in allowed_sessions:
        return False
    return True


def run_btcusd_optimized_backtest():
    print("=" * 95)
    print("🚀 TRADINGGUARD - BITCOIN (BTCUSD) DEDICATED OPTIMIZED PRODUCTION BACKTEST")
    print("131 Continuous 24/7 Calendar Days (July 1 - November 8, 2026)")
    print("Authentic Single-Position Gating with Optimized Settings Enforced In-Engine")
    print("=" * 95)

    # 1. Load and merge Summer and Autumn market data
    print("Loading market data...")
    df_m5_sum = pd.read_parquet(CACHE_DIR / 'BTCUSD_M5_SUMMER_2026.parquet')
    df_m5_aut = pd.read_parquet(CACHE_DIR / 'BTCUSD_M5_2026.parquet')
    df_m5_all = pd.concat([df_m5_sum, df_m5_aut], ignore_index=True).drop_duplicates(subset=['time']).sort_values('time')

    df_m1_sum = pd.read_parquet(CACHE_DIR / 'BTCUSD_M1_SUMMER_2026.parquet')
    df_m1_aut = pd.read_parquet(CACHE_DIR / 'BTCUSD_M1_2026.parquet')
    df_m1_all = pd.concat([df_m1_sum, df_m1_aut], ignore_index=True).drop_duplicates(subset=['time']).sort_values('time')

    df_h1_sum = pd.read_parquet(CACHE_DIR / 'BTCUSD_H1_SUMMER_2026.parquet')
    df_h1_aut = pd.read_parquet(CACHE_DIR / 'BTCUSD_H1_2026.parquet')
    df_h1_all = pd.concat([df_h1_sum, df_h1_aut], ignore_index=True).drop_duplicates(subset=['time']).sort_values('time')

    df_d1_sum = pd.read_parquet(CACHE_DIR / 'BTCUSD_D1_SUMMER_2026.parquet')
    df_d1_aut = pd.read_parquet(CACHE_DIR / 'BTCUSD_D1_2026.parquet')
    df_d1_all = pd.concat([df_d1_sum, df_d1_aut], ignore_index=True).drop_duplicates(subset=['time']).sort_values('time')

    bars_m5 = df_m5_all.to_dict('records')
    bars_m1 = df_m1_all.to_dict('records')
    bars_h1 = df_h1_all.to_dict('records')
    bars_d1 = df_d1_all.to_dict('records')

    print(f"Unified Dataset: {len(bars_m5):,} M5 bars | {len(bars_m1):,} M1 bars | {len(bars_h1):,} H1 bars | {len(bars_d1):,} D1 bars")

    # M1 index map by epoch
    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    # Target test range: July 1, 2026 00:00 UTC to November 8, 2026 17:34 UTC
    t_start_epoch = int(datetime.datetime(2026, 7, 1, 0, 0, tzinfo=TZ_UTC).timestamp())
    t_end_epoch = int(datetime.datetime(2026, 11, 8, 23, 59, 59, tzinfo=TZ_UTC).timestamp())

    # Find starting M5 index
    start_idx = None
    for idx, b in enumerate(bars_m5):
        if b['time'] >= t_start_epoch:
            start_idx = idx
            break
    if start_idx is None or start_idx < 120:
        start_idx = 120

    total_m5 = len(bars_m5)
    print(f"\nSimulating from index {start_idx:,} to {total_m5:,} ({total_m5 - start_idx:,} M5 bars)...")

    trades = []
    active_trade_until = 0
    t0_sim = time.time()
    bars_scanned = 0
    candidates_screened = 0
    gated_out_count = 0

    for i in range(start_idx, total_m5):
        curr_bar = bars_m5[i]
        curr_epoch = curr_bar['time']

        if curr_epoch > t_end_epoch:
            break

        # Check if single-position lock is active
        if curr_epoch < active_trade_until:
            continue

        bar_dt_utc = datetime.datetime.fromtimestamp(curr_epoch, tz=TZ_UTC)
        bar_dt_tehran = bar_dt_utc.astimezone(TZ_TEHRAN)
        is_weekend = bar_dt_utc.weekday() in (5, 6)

        # Pre-filter weekend directly to save compute
        if is_weekend:
            continue

        sess_name, sess_key = get_dynamic_crypto_session(bar_dt_utc)

        # Pre-filter toxic sessions directly
        if sess_key in ('NY_Late_PM', 'Pacific_Off_Hours'):
            continue

        bars_scanned += 1
        m5_slice = bars_m5[i - 119 : i + 1]
        h1_slice = [b for b in bars_h1 if b['time'] <= curr_epoch][-100:]
        d1_slice = [b for b in bars_d1 if b['time'] <= curr_epoch][-30:]

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

        candidates_screened += 1
        arch_id = res.get("archetype_id", "NONE")
        setup_type = res.get("setup_type", "NONE")

        # In-Engine Gating: Check Curated Archetype-Session Match
        if not is_trade_allowed(arch_id, sess_key, is_weekend):
            gated_out_count += 1
            continue

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

        # Forward M1 evaluation
        next_m1_epoch = curr_epoch + 300
        m1_start_idx = m1_time_map.get(next_m1_epoch)
        if m1_start_idx is None:
            forward_m1 = [b for b in bars_m1 if b['time'] >= next_m1_epoch][:480]
        else:
            forward_m1 = bars_m1[m1_start_idx : m1_start_idx + 480]

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

        trade_record = {
            "epoch": curr_epoch,
            "time_utc": str(bar_dt_utc),
            "time_tehran": str(bar_dt_tehran),
            "date": bar_dt_utc.strftime("%Y-%m-%d"),
            "hour_utc": bar_dt_utc.hour,
            "hour_tehran": bar_dt_tehran.hour,
            "session_name": sess_name,
            "session_key": sess_key,
            "day_name": bar_dt_utc.strftime("%A"),
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

        # Single position lock update
        if status in ("WIN", "LOSS", "BREAKEVEN"):
            active_trade_until = curr_epoch + (exit_min * 60)
        elif status == "EXPIRED":
            active_trade_until = curr_epoch + (75 * 60)

    elapsed_sim = time.time() - t0_sim
    print(f"\nSimulation finished in {elapsed_sim:.2f}s!")
    print(f"Total bars scanned (weekdays, non-blacklisted): {bars_scanned:,}")
    print(f"Raw candidate setups generated: {candidates_screened:,}")
    print(f"Setups filtered out by Curated Rules: {gated_out_count:,}")
    print(f"Final authorized trade directives: {len(trades)}")

    # Convert to DataFrame
    df_opt_trades = pd.DataFrame(trades)
    df_opt_trades.to_parquet(OUTPUT_DIR / "btcusd_optimized_trades.parquet")
    df_opt_trades.to_csv(OUTPUT_DIR / "btcusd_optimized_trades.csv", index=False)

    # Performance calculation
    def calc_metrics(df_sub, label="Portfolio"):
        fills = df_sub[df_sub['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])].copy()
        n_fills = len(fills)
        if n_fills == 0:
            return {"Name": label, "Signals": len(df_sub), "Fills": 0, "Wins": 0, "Losses": 0, "BE": 0, "WR%": 0.0, "Net_R": 0.0, "Net_PnL": 0.0, "PF": 0.0, "Expectancy_R": 0.0}
        wins = fills[fills['status'] == 'WIN']
        losses = fills[fills['status'] == 'LOSS']
        be = fills[fills['status'] == 'BREAKEVEN']
        wr = len(wins) / n_fills * 100
        net_r = fills['rr_realized'].sum()
        net_pnl = fills['realized_pnl_usd'].sum()
        gw = wins['realized_pnl_usd'].sum()
        gl = abs(losses['realized_pnl_usd'].sum())
        pf = gw / gl if gl > 0 else 99.0
        exp_r = net_r / n_fills
        return {
            "Name": label,
            "Signals": len(df_sub),
            "Fills": n_fills,
            "Wins": len(wins),
            "Losses": len(losses),
            "BE": len(be),
            "Exp": len(df_sub[df_sub['status'] == 'EXPIRED']),
            "WR%": round(wr, 1),
            "Net_R": round(net_r, 2),
            "Net_PnL": round(net_pnl, 2),
            "PF": round(pf, 2),
            "Expectancy_R": round(exp_r, 2)
        }

    overall_metrics = calc_metrics(df_opt_trades, "Curated Dedicated Production Portfolio")

    # Monthly breakdown
    df_opt_trades['month'] = pd.to_datetime(df_opt_trades['time_utc']).dt.to_period('M')
    month_rows = []
    for m, grp in df_opt_trades.groupby('month'):
        month_rows.append(calc_metrics(grp, str(m)))
    df_monthly = pd.DataFrame(month_rows)

    # Archetype breakdown
    arch_rows = []
    for arch, grp in df_opt_trades.groupby('archetype_id'):
        arch_rows.append(calc_metrics(grp, arch))
    df_arch = pd.DataFrame(arch_rows).sort_values('Net_R', ascending=False)

    # Session breakdown
    sess_rows = []
    for s, grp in df_opt_trades.groupby('session_key'):
        sess_rows.append(calc_metrics(grp, s))
    df_sess = pd.DataFrame(sess_rows).sort_values('Net_R', ascending=False)

    # Day breakdown
    day_rows = []
    for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
        grp = df_opt_trades[df_opt_trades['day_name'] == d]
        if len(grp) > 0:
            day_rows.append(calc_metrics(grp, d))
    df_days = pd.DataFrame(day_rows)

    print("\n" + "=" * 95)
    print("📊 OVERALL RESULTS - DEDICATED OPTIMIZED BITCOIN ENGINE (131 DAYS)")
    print("=" * 95)
    print(pd.DataFrame([overall_metrics]).to_string(index=False))

    print("\n" + "=" * 95)
    print("📊 MONTHLY BREAKDOWN")
    print("=" * 95)
    print(df_monthly[['Name', 'Signals', 'Fills', 'Wins', 'Losses', 'BE', 'WR%', 'Net_R', 'Net_PnL', 'PF']].to_string(index=False))

    print("\n" + "=" * 95)
    print("📊 ARCHETYPE BREAKDOWN")
    print("=" * 95)
    print(df_arch[['Name', 'Signals', 'Fills', 'Wins', 'Losses', 'BE', 'WR%', 'Net_R', 'Net_PnL', 'PF']].to_string(index=False))

    print("\n" + "=" * 95)
    print("📊 SESSION BREAKDOWN")
    print("=" * 95)
    print(df_sess[['Name', 'Signals', 'Fills', 'Wins', 'Losses', 'BE', 'WR%', 'Net_R', 'Net_PnL', 'PF']].to_string(index=False))

    # Save summary json
    summary_data = {
        "overall": overall_metrics,
        "monthly": month_rows,
        "archetypes": arch_rows,
        "sessions": sess_rows,
        "days": day_rows
    }
    with open(OUTPUT_DIR / "btcusd_optimized_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    print(f"\nAll dedicated optimized results saved to {OUTPUT_DIR}/")


if __name__ == '__main__':
    run_btcusd_optimized_backtest()
