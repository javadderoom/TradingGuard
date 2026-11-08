"""
TradingGuard HITL - S&P 500 (SPX) 3.2-Month Cross-Index Quantitative Audit
Evaluates institutional SMC screening across continuous MT5 broker data (Aug 1 to Nov 6, 2026: 20,652 M5 bars, 96,349 M1 bars).
Tests parameter transferability from NQ to SPX.
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
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'spx_3month_audit'
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


def run_spx_audit():
    print("=" * 95)
    print("🚀 TRADINGGUARD - S&P 500 (SPX) 3.2-MONTH CROSS-INDEX QUANTITATIVE AUDIT")
    print("Aug 1 to Nov 6, 2026 MT5 Broker Microstructure | 20,652 M5 Bars | 96,349 M1 Bars")
    print("=" * 95)

    df_m5 = pd.read_parquet(CACHE_DIR / 'SPX_M5_2026.parquet')
    df_m1 = pd.read_parquet(CACHE_DIR / 'SPX_M1_2026.parquet')
    df_h1 = pd.read_parquet(CACHE_DIR / 'SPX_H1_2026.parquet')
    df_d1 = pd.read_parquet(CACHE_DIR / 'SPX_D1_2026.parquet')

    bars_m5_all = df_m5.to_dict('records')
    bars_m1_all = df_m1.to_dict('records')
    bars_h1_all = df_h1.to_dict('records')
    bars_d1_all = df_d1.to_dict('records')

    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1_all)}
    warmup_bars = 120
    total_m5 = len(bars_m5_all)

    # 1. RAW BASELINE AUDIT
    print("\n1. Running S&P 500 Raw Baseline Simulation...")
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

        bars_5m_slice = bars_m5_all[i-120:i+1]
        bars_1h_slice = [b for b in bars_h1_all if b['time'] <= curr_epoch][-120:]
        bars_1d_slice = [b for b in bars_d1_all if b['time'] <= curr_epoch][-60:]

        if len(bars_1h_slice) < 10:
            continue

        res = screen_ict_session(
            bars_5m=bars_5m_slice,
            bars_1h=bars_1h_slice,
            symbol="SPX",
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
        # SPX risk boundaries: [3.0 pts, 25.0 pts] ($3.00 to $25.00 on 0.10 lot)
        if risk_pts < 3.0 or risk_pts > 25.0:
            continue

        is_buy = "BULLISH" in setup_type or "LONG" in setup_type
        direction = "BUY" if is_buy else "SELL"
        target_rr = 3.0
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
            symbol="SPX",
            spread_pts=0.5,         # 0.5 pt spread on S&P 500
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

        sess_name, sess_key = classify_session(bar_dt_utc)

        trades_raw.append({
            "epoch": curr_epoch,
            "date": bar_dt_utc.strftime("%Y-%m-%d"),
            "session_key": sess_key,
            "archetype_id": arch_id,
            "direction": direction,
            "risk_pts": risk_pts,
            "status": status,
            "realized_pnl_usd": pnl,
            "rr_realized": rr
        })

        if status in ("WIN", "LOSS", "BREAKEVEN"):
            active_until_raw = curr_epoch + (exit_min * 60)
        elif status == "EXPIRED":
            active_until_raw = curr_epoch + (60 * 60)

    print(f"SPX Raw simulation finished in {time.time()-t0:.2f}s! Signals: {len(trades_raw)}")
    df_spx_raw = pd.DataFrame(trades_raw)
    df_spx_raw.to_parquet(OUTPUT_DIR / "spx_raw_trades.parquet")

    # 2. CURATED PORTFOLIO AUDIT (London Open + NY Pre-Market with ARCH-001, 004, 010)
    print("\n2. Running S&P 500 Curated Institutional Policy Simulation...")
    trades_curated = []
    active_until_curated = 0
    t1 = time.time()

    for i in range(warmup_bars, total_m5):
        curr_bar = bars_m5_all[i]
        curr_epoch = curr_bar['time']

        if curr_epoch < active_until_curated:
            continue

        bar_dt_utc = datetime.datetime.fromtimestamp(curr_epoch, tz=TZ_UTC)
        sess_name, sess_key = classify_session(bar_dt_utc)

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
            symbol="SPX",
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
        if risk_pts < 3.0 or risk_pts > 25.0:
            continue

        is_buy = "BULLISH" in setup_type or "LONG" in setup_type
        direction = "BUY" if is_buy else "SELL"
        target_rr = 3.0
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
            symbol="SPX",
            spread_pts=0.5,
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

        trades_curated.append({
            "epoch": curr_epoch,
            "date": bar_dt_utc.strftime("%Y-%m-%d"),
            "session_key": sess_key,
            "archetype_id": arch_id,
            "direction": direction,
            "risk_pts": risk_pts,
            "status": status,
            "realized_pnl_usd": pnl,
            "rr_realized": rr
        })

        if status in ("WIN", "LOSS", "BREAKEVEN"):
            active_until_curated = curr_epoch + (exit_min * 60)
        elif status == "EXPIRED":
            active_until_curated = curr_epoch + (60 * 60)

    print(f"SPX Curated simulation finished in {time.time()-t1:.2f}s! Signals: {len(trades_curated)}")
    df_spx_cur = pd.DataFrame(trades_curated)
    df_spx_cur.to_parquet(OUTPUT_DIR / "spx_curated_trades.parquet")

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

    raw_s = calc_stats(df_spx_raw)
    cur_s = calc_stats(df_spx_cur)

    print("\n" + "=" * 95)
    print("📊 S&P 500 (SPX) 3.2-MONTH BENCHMARK RESULTS")
    print("=" * 95)
    print("SPX RAW BASELINE :", raw_s)
    print("SPX CURATED CORE :", cur_s)

    print("\n--- SPX CURATED BY ARCHETYPE ---")
    for arch, g in df_spx_cur.groupby('archetype_id'):
        s = calc_stats(g)
        print(f"  {arch:15s} | Fills: {s['Fills']:2d} | W: {s['Wins']:2d} | L: {s['Losses']:2d} | BE: {s['BE']:2d} | WR: {s['WR%']:5.1f}% | Net R: {s['Net_R']:+6.2f}R | Net PnL: ${s['Net_PnL']:+6.2f} | PF: {s['PF']:.2f}")

    print("\n--- SPX CURATED BY SESSION ---")
    for sess, g in df_spx_cur.groupby('session_key'):
        s = calc_stats(g)
        print(f"  {sess:15s} | Fills: {s['Fills']:2d} | W: {s['Wins']:2d} | L: {s['Losses']:2d} | BE: {s['BE']:2d} | WR: {s['WR%']:5.1f}% | Net R: {s['Net_R']:+6.2f}R | Net PnL: ${s['Net_PnL']:+6.2f} | PF: {s['PF']:.2f}")

    summary = {
        "raw_stats": raw_s,
        "curated_stats": cur_s
    }
    with open(OUTPUT_DIR / "spx_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n✅ SPX Audit complete! Results saved to {OUTPUT_DIR}")


if __name__ == '__main__':
    run_spx_audit()
