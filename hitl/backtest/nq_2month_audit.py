"""
TradingGuard HITL - Nasdaq 100 (NQ) 2-Month Algorithmic Screener Audit
Evaluates standalone SMC screening across continuous MT5 broker bars (Sep 1 to Nov 6, 2026: 14,856 M5 bars, 67,380 M1 bars).
Zero-Council, pure algorithmic execution with single-position serial gating.

Audits performance across:
1. Institutional Session Windows (NYSE Cash Open, NY Silver Bullet, NY Pre-Market, NY PM, London Open, London Cont, Asian/Globex)
2. 24-Hour Clock (UTC, NY Local, Tehran Local)
3. Setup Archetypes (SETUP-ARCH-001 through SETUP-ARCH-014)
4. Day of Week (Monday to Friday)
5. Direction (Long vs Short) & HTF Phase (PRO_EXPANSION vs HTF_RETRACEMENT)
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
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'nq_2month_audit'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_LONDON = ZoneInfo("Europe/London")
TZ_UTC = ZoneInfo("UTC")


def classify_nq_session(dt_utc: datetime.datetime) -> Tuple[str, str]:
    """
    Classifies the exact institutional trading session for Nasdaq 100 (NQ),
    dynamically resolving seasonal DST shifts using America/New_York and Europe/London.
    Returns: (session_full_name, session_short_key)
    """
    dt_ny = dt_utc.astimezone(TZ_NEW_YORK)
    dt_lon = dt_utc.astimezone(TZ_LONDON)
    dt_tehran = dt_utc.astimezone(TZ_TEHRAN)

    ny_time = dt_ny.time()
    lon_time = dt_lon.time()

    # Weekend check
    if dt_utc.weekday() in (5, 6):
        return "Weekend_Off_Hours", "Weekend"

    # 1. NYSE Cash Open (09:30 - 10:00 NY Local) - Peak Equity Volume
    if datetime.time(9, 30) <= ny_time < datetime.time(10, 0):
        return f"NYSE_Cash_Open (09:30-10:00 NY | {dt_tehran.strftime('%H:%M')} Tehran)", "NYSE_Cash_Open"

    # 2. NY Silver Bullet (10:00 - 11:00 NY Local) - Prime Algorithmic Sweep & FVG
    elif datetime.time(10, 0) <= ny_time < datetime.time(11, 0):
        return f"NY_Silver_Bullet (10:00-11:00 NY | {dt_tehran.strftime('%H:%M')} Tehran)", "NY_Silver_Bullet"

    # 3. NY Pre-Market (08:00 - 09:30 NY Local) - Macro Forex / Index Transition
    elif datetime.time(8, 0) <= ny_time < datetime.time(9, 30):
        return f"NY_Pre_Market (08:00-09:30 NY | {dt_tehran.strftime('%H:%M')} Tehran)", "NY_Pre_Market"

    # 4. NY Regular PM (11:00 - 16:00 NY Local) - Cash Trend & Close
    elif datetime.time(11, 0) <= ny_time < datetime.time(16, 0):
        return f"NY_Regular_PM (11:00-16:00 NY | {dt_tehran.strftime('%H:%M')} Tehran)", "NY_Regular_PM"

    # 5. London Open (08:00 - 10:30 London Local) - European Cash Open
    elif datetime.time(8, 0) <= lon_time < datetime.time(10, 30):
        return f"London_Open (08:00-10:30 Lon | {dt_tehran.strftime('%H:%M')} Tehran)", "London_Open"

    # 6. London Continuation (10:30 - 13:00 London Local)
    elif datetime.time(10, 30) <= lon_time < datetime.time(13, 0):
        return f"London_Continuation (10:30-13:00 Lon | {dt_tehran.strftime('%H:%M')} Tehran)", "London_Cont"

    # 7. Globex Overnight / Asian (00:00 - 07:00 UTC)
    elif datetime.time(0, 0) <= dt_utc.time() < datetime.time(7, 0):
        return f"Asian_Overnight (00:00-07:00 UTC | {dt_tehran.strftime('%H:%M')} Tehran)", "Asian_Overnight"

    # 8. Off-Hours / Settlement (Pacific & Post-Close)
    else:
        return f"Pacific_Off_Hours ({dt_utc.strftime('%H:%M')} UTC | {dt_tehran.strftime('%H:%M')} Tehran)", "Pacific_Off_Hours"


def run_nq_2month_audit():
    print("=" * 95)
    print("🚀 TRADINGGUARD - NASDAQ 100 (NQ) 2-MONTH STANDALONE SCREENER QUANTITATIVE AUDIT")
    print("Zero-Council Pure Algorithmic Pipeline | Sep 1 to Nov 6, 2026 MT5 Broker Microstructure")
    print("=" * 95)

    # 1. Load Parquet Data
    m5_path = CACHE_DIR / 'NQ_M5_2026.parquet'
    m1_path = CACHE_DIR / 'NQ_M1_2026.parquet'
    h1_path = CACHE_DIR / 'NQ_H1_2026.parquet'
    d1_path = CACHE_DIR / 'NQ_D1_2026.parquet'

    if not (m5_path.exists() and m1_path.exists()):
        print(f"Cache missing! Run cache_nq_data.py first.")
        return

    print("Loading cached NQ broker market data...")
    df_m5 = pd.read_parquet(m5_path)
    df_m1 = pd.read_parquet(m1_path)
    df_h1 = pd.read_parquet(h1_path) if h1_path.exists() else None
    df_d1 = pd.read_parquet(d1_path) if d1_path.exists() else None

    bars_m5_all = df_m5.to_dict('records')
    bars_m1_all = df_m1.to_dict('records')
    bars_h1_all = df_h1.to_dict('records') if df_h1 is not None else []
    bars_d1_all = df_d1.to_dict('records') if df_d1 is not None else []

    print(f"Loaded: {len(bars_m5_all):,} M5 bars | {len(bars_m1_all):,} M1 bars | {len(bars_h1_all):,} H1 bars | {len(bars_d1_all):,} D1 bars")

    # Build M1 index map by epoch timestamp for O(1) lookup
    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1_all)}

    warmup_bars = 120
    total_m5 = len(bars_m5_all)

    trades = []
    active_trade_until = 0  # Epoch timestamp when position closes / expires

    t0_sim = time.time()
    print(f"\nRunning chronological bar-by-bar simulation across {total_m5 - warmup_bars:,} M5 bars...")

    for i in range(warmup_bars, total_m5):
        curr_bar = bars_m5_all[i]
        curr_epoch = curr_bar['time']

        # Skip if a position or pending limit order is actively open (Single-Position Serial Gating)
        if curr_epoch < active_trade_until:
            continue

        bar_dt_utc = datetime.datetime.fromtimestamp(curr_epoch, tz=TZ_UTC)
        bar_dt_tehran = bar_dt_utc.astimezone(TZ_TEHRAN)
        bar_dt_ny = bar_dt_utc.astimezone(TZ_NEW_YORK)

        # Slice 120 M5 bars up to curr_epoch
        bars_5m_slice = bars_m5_all[i-120:i+1]

        # Slice H1 and D1 bars up to curr_epoch
        bars_1h_slice = [b for b in bars_h1_all if b['time'] <= curr_epoch][-120:]
        bars_1d_slice = [b for b in bars_d1_all if b['time'] <= curr_epoch][-60:]

        if len(bars_1h_slice) < 10:
            continue

        # Screen using Tehran hour to maintain existing session window anchors
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
        # Risk range check for NQ: [15.0 pts, 120.0 pts] ($1.50 to $12.00 on 0.10 lot)
        if risk_pts < 15.0 or risk_pts > 120.0:
            continue

        is_buy = "BULLISH" in setup_type or "LONG" in setup_type
        direction = "BUY" if is_buy else "SELL"
        target_rr = res.get("recommended_target_rr", 3.0)
        be_rr = res.get("recommended_be_rr", 1.5)
        tp_p = entry_p + (target_rr * risk_pts) if is_buy else entry_p - (target_rr * risk_pts)

        # Locate forward M1 bars
        # The signal bar closes at curr_epoch. Limit order begins on next minute.
        next_m1_epoch = curr_epoch + 300  # 5 min after current bar start
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
            "lot": 0.01  # Paired with pip_val=0.10 in evaluator -> $0.10/point (0.10 lot MT5 equivalent)
        }

        eval_res = evaluate_council_decision(
            decision_dict=decision_dict,
            forward_m1_bars=forward_m1,
            symbol="NQ",
            spread_pts=1.0,         # 1.0 point live MT5 broker spread
            breakeven_rr=be_rr,     # 1.5R breakeven ratchet
            target_rr_cap=target_rr,# 3.0R target cap
            commission_usd=0.10,    # $0.10 round-trip commission
            slippage_pts=0.0,
            ttl_minutes=60          # 60m TTL for index limit orders
        )

        status = eval_res["status"]
        pnl = eval_res["realized_pnl_usd"]
        rr = eval_res.get("rr_realized", 0.0)
        exit_min = eval_res.get("exit_minute") or 60
        fill_min = eval_res.get("fill_minute")

        # Session and Day Classification
        sess_name, sess_key = classify_nq_session(bar_dt_utc)
        day_name = bar_dt_utc.strftime("%A")
        is_weekend = bar_dt_utc.weekday() in (5, 6)

        trade_record = {
            "epoch": curr_epoch,
            "time_utc": str(bar_dt_utc),
            "time_ny": str(bar_dt_ny),
            "time_tehran": str(bar_dt_tehran),
            "date": bar_dt_utc.strftime("%Y-%m-%d"),
            "hour_utc": bar_dt_utc.hour,
            "hour_ny": bar_dt_ny.hour,
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
            "risk_usd": risk_pts * 0.10,
            "status": status,
            "realized_pnl_usd": pnl,
            "rr_realized": rr,
            "fill_minute": fill_min,
            "exit_minute": exit_min,
            "notes": eval_res.get("notes", "")
        }
        trades.append(trade_record)

        # Serial gating update
        if status in ("WIN", "LOSS", "BREAKEVEN"):
            active_trade_until = curr_epoch + (exit_min * 60)
        elif status == "EXPIRED":
            active_trade_until = curr_epoch + (60 * 60)

    elapsed_sim = time.time() - t0_sim
    print(f"Simulation completed in {elapsed_sim:.2f}s! Total signals evaluated: {len(trades)}")

    # Convert trades to DataFrame
    df_trades = pd.DataFrame(trades)
    df_trades.to_parquet(OUTPUT_DIR / "nq_2month_trades.parquet")
    df_trades.to_csv(OUTPUT_DIR / "nq_2month_trades.csv", index=False)

    # Performance Aggregation Helper
    def compute_metrics(subset: pd.DataFrame, label: str = "Group") -> dict:
        total = len(subset)
        if total == 0:
            return {
                "Name": label, "Signals": 0, "Fills": 0, "Wins": 0, "Losses": 0, "BE": 0, "Exp": 0,
                "WR%": 0.0, "Net_R": 0.0, "Net_PnL": 0.0, "PF": 0.0, "Expectancy_R": 0.0
            }

        fills = subset[subset['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
        n_fills = len(fills)
        wins = subset[subset['status'] == 'WIN']
        losses = subset[subset['status'] == 'LOSS']
        bes = subset[subset['status'] == 'BREAKEVEN']
        exps = subset[subset['status'] == 'EXPIRED']

        n_wins = len(wins)
        n_losses = len(losses)
        n_be = len(bes)
        n_exp = len(exps)

        wr = (n_wins / n_fills * 100) if n_fills > 0 else 0.0
        net_r = float(subset['rr_realized'].sum()) if total > 0 else 0.0
        net_pnl = float(subset['realized_pnl_usd'].sum()) if total > 0 else 0.0

        gross_profit = float(subset[subset['realized_pnl_usd'] > 0]['realized_pnl_usd'].sum())
        gross_loss = abs(float(subset[subset['realized_pnl_usd'] < 0]['realized_pnl_usd'].sum()))

        if gross_loss > 0:
            pf = gross_profit / gross_loss
        else:
            pf = 99.0 if gross_profit > 0 else 0.0

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

    # 1. Overall Portfolio Performance
    overall_metrics = compute_metrics(df_trades, "NASDAQ 100 Portfolio (Raw Screener)")

    # 2. Performance by Session
    session_rows = []
    for sess, group in df_trades.groupby('session_key'):
        full_name = group['session_name'].iloc[0]
        session_rows.append(compute_metrics(group, full_name))
    df_sessions = pd.DataFrame(session_rows).sort_values(by="Net_R", ascending=False)

    # 3. Performance by Archetype
    arch_rows = []
    for arch, group in df_trades.groupby('archetype_id'):
        arch_rows.append(compute_metrics(group, arch))
    df_archs = pd.DataFrame(arch_rows).sort_values(by="Net_R", ascending=False)

    # 4. Performance by 24h Clock (NY Local Hour)
    ny_hour_rows = []
    for h, group in df_trades.groupby('hour_ny'):
        label = f"{h:02d}:00 NY Local"
        ny_hour_rows.append(compute_metrics(group, label))
    df_ny_hours = pd.DataFrame(ny_hour_rows).sort_values(by="Name")

    # 5. Performance by Day of Week
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    day_rows = []
    for day in day_order:
        group = df_trades[df_trades['day_name'] == day]
        if not group.empty:
            day_rows.append(compute_metrics(group, day))
    df_days = pd.DataFrame(day_rows)

    # 6. Direction & Phase Breakdown
    dir_rows = []
    for d, group in df_trades.groupby('direction'):
        dir_rows.append(compute_metrics(group, d))
    df_dir = pd.DataFrame(dir_rows)

    phase_rows = []
    for p, group in df_trades.groupby('phase'):
        phase_rows.append(compute_metrics(group, p))
    df_phase = pd.DataFrame(phase_rows).sort_values(by="Net_R", ascending=False)

    # Print Summary Tables
    print("\n" + "=" * 95)
    print("📊 1. OVERALL PORTFOLIO PERFORMANCE (NASDAQ 100 - 2 MONTHS)")
    print("=" * 95)
    for k, v in overall_metrics.items():
        print(f"  {k:15s}: {v}")

    print("\n" + "=" * 95)
    print("🏛️ 2. BREAKDOWN BY INSTITUTIONAL SESSION")
    print("=" * 95)
    print(df_sessions.to_string(index=False))

    print("\n" + "=" * 95)
    print("🎯 3. BREAKDOWN BY SETUP ARCHETYPE")
    print("=" * 95)
    print(df_archs.to_string(index=False))

    print("\n" + "=" * 95)
    print("⏰ 4. BREAKDOWN BY 24-HOUR CLOCK (NEW YORK LOCAL TIME)")
    print("=" * 95)
    print(df_ny_hours.to_string(index=False))

    print("\n" + "=" * 95)
    print("📅 5. BREAKDOWN BY DAY OF WEEK")
    print("=" * 95)
    print(df_days.to_string(index=False))

    print("\n" + "=" * 95)
    print("🧭 6. DIRECTION & HTF PHASE BREAKDOWN")
    print("=" * 95)
    print("--- DIRECTION ---")
    print(df_dir.to_string(index=False))
    print("--- HTF PHASE ---")
    print(df_phase.to_string(index=False))

    # Save summary JSON
    summary_export = {
        "overall": overall_metrics,
        "sessions": df_sessions.to_dict('records'),
        "archetypes": df_archs.to_dict('records'),
        "ny_hours": df_ny_hours.to_dict('records'),
        "days": df_days.to_dict('records'),
        "directions": df_dir.to_dict('records'),
        "phases": df_phase.to_dict('records')
    }
    with open(OUTPUT_DIR / "nq_2month_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_export, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Audit complete! Results saved to {OUTPUT_DIR}")


if __name__ == '__main__':
    run_nq_2month_audit()
