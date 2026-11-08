"""
TradingGuard HITL - Nasdaq 100 (NQ) Curated Institutional Production Audit
Executes end-to-end algorithmic screening with calibrated filters across continuous MT5 broker data (Sep 1 to Nov 6, 2026).

Execution Filters:
1. Toxic Archetypes Decommissioned: SETUP-ARCH-002 & SETUP-ARCH-009 banned on NQ (saving +166.2R drag).
2. Session Confinement: Gated to high-liquidity Institutional Killzones:
   - London Open (08:00 - 10:30 London local): SETUP-ARCH-004 & SETUP-ARCH-010
   - NY Pre-Market (08:00 - 09:30 NY local): SETUP-ARCH-001 & SETUP-ARCH-010
3. Single-position serial gating with forward M1 execution (1.0 pt spread, $0.10 commission, 60m TTL, 1.5R BE ratchet).
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
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'nq_curated_production_audit'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_LONDON = ZoneInfo("Europe/London")
TZ_UTC = ZoneInfo("UTC")


def classify_curated_session(dt_utc: datetime.datetime) -> Tuple[bool, str, str]:
    """
    Returns (is_active_window, session_name, session_key).
    Only returns True for ratified active institutional trading windows for NQ.
    """
    dt_ny = dt_utc.astimezone(TZ_NEW_YORK)
    dt_lon = dt_utc.astimezone(TZ_LONDON)
    dt_tehran = dt_utc.astimezone(TZ_TEHRAN)

    ny_time = dt_ny.time()
    lon_time = dt_lon.time()

    if dt_utc.weekday() in (5, 6):
        return False, "Weekend", "Weekend"

    # 1. London Open (08:00 - 10:30 London Local) - Primary Trend Engine
    if datetime.time(8, 0) <= lon_time < datetime.time(10, 30):
        return True, f"London_Open (08:00-10:30 Lon | {dt_tehran.strftime('%H:%M')} Tehran)", "London_Open"

    # 2. NY Pre-Market (08:00 - 09:30 NY Local) - Institutional Forex/Index Transition
    elif datetime.time(8, 0) <= ny_time < datetime.time(9, 30):
        return True, f"NY_Pre_Market (08:00-09:30 NY | {dt_tehran.strftime('%H:%M')} Tehran)", "NY_Pre_Market"

    return False, "Off_Hours_Filtered", "Filtered"


def run_curated_nq_audit():
    print("=" * 95)
    print("🚀 TRADINGGUARD - NASDAQ 100 (NQ) CURATED PRODUCTION PORTFOLIO AUDIT")
    print("Calibrated Algorithmic Execution | Sep 1 to Nov 6, 2026 MT5 Broker Microstructure")
    print("=" * 95)

    m5_path = CACHE_DIR / 'NQ_M5_2026.parquet'
    m1_path = CACHE_DIR / 'NQ_M1_2026.parquet'
    h1_path = CACHE_DIR / 'NQ_H1_2026.parquet'
    d1_path = CACHE_DIR / 'NQ_D1_2026.parquet'

    df_m5 = pd.read_parquet(m5_path)
    df_m1 = pd.read_parquet(m1_path)
    df_h1 = pd.read_parquet(h1_path) if h1_path.exists() else None
    df_d1 = pd.read_parquet(d1_path) if d1_path.exists() else None

    bars_m5_all = df_m5.to_dict('records')
    bars_m1_all = df_m1.to_dict('records')
    bars_h1_all = df_h1.to_dict('records') if df_h1 is not None else []
    bars_d1_all = df_d1.to_dict('records') if df_d1 is not None else []

    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1_all)}

    warmup_bars = 120
    total_m5 = len(bars_m5_all)

    trades = []
    active_trade_until = 0

    t0 = time.time()
    print(f"Scanning {total_m5 - warmup_bars:,} M5 bars under curated institutional policy...")

    for i in range(warmup_bars, total_m5):
        curr_bar = bars_m5_all[i]
        curr_epoch = curr_bar['time']

        if curr_epoch < active_trade_until:
            continue

        bar_dt_utc = datetime.datetime.fromtimestamp(curr_epoch, tz=TZ_UTC)
        is_active, sess_name, sess_key = classify_curated_session(bar_dt_utc)
        if not is_active:
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

        # Decommission toxic archetypes on NQ
        if arch_id in ("SETUP-ARCH-002", "SETUP-ARCH-009"):
            continue

        # Session-specific archetype filtering:
        # London Open: SETUP-ARCH-004 & SETUP-ARCH-010
        # NY Pre-Market: SETUP-ARCH-001 & SETUP-ARCH-010
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
            "hour_utc": bar_dt_utc.hour,
            "hour_ny": bar_dt_ny.hour,
            "hour_tehran": bar_dt_tehran.hour,
            "session_name": sess_name,
            "session_key": sess_key,
            "day_name": day_name,
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

        if status in ("WIN", "LOSS", "BREAKEVEN"):
            active_trade_until = curr_epoch + (exit_min * 60)
        elif status == "EXPIRED":
            active_trade_until = curr_epoch + (60 * 60)

    elapsed = time.time() - t0
    print(f"Simulation completed in {elapsed:.2f}s! Evaluated {len(trades)} signals.")

    df_curated = pd.DataFrame(trades)
    df_curated.to_parquet(OUTPUT_DIR / "nq_curated_trades.parquet")
    df_curated.to_csv(OUTPUT_DIR / "nq_curated_trades.csv", index=False)

    fills = df_curated[df_curated['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
    n_fills = len(fills)
    wins = len(df_curated[df_curated['status'] == 'WIN'])
    losses = len(df_curated[df_curated['status'] == 'LOSS'])
    bes = len(df_curated[df_curated['status'] == 'BREAKEVEN'])
    exps = len(df_curated[df_curated['status'] == 'EXPIRED'])

    wr = (wins / n_fills * 100) if n_fills > 0 else 0.0
    net_r = float(df_curated['rr_realized'].sum())
    net_pnl = float(df_curated['realized_pnl_usd'].sum())

    gross_profit = float(df_curated[df_curated['realized_pnl_usd'] > 0]['realized_pnl_usd'].sum())
    gross_loss = abs(float(df_curated[df_curated['realized_pnl_usd'] < 0]['realized_pnl_usd'].sum()))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    print("\n" + "=" * 95)
    print("🏆 FINAL CURATED INSTITUTIONAL PERFORMANCE - NASDAQ 100 (2 MONTHS)")
    print("=" * 95)
    print(f"  Total Signals      : {len(df_curated)}")
    print(f"  Fills Executed     : {n_fills}")
    print(f"  Wins               : {wins}")
    print(f"  Losses             : {losses}")
    print(f"  Breakeven          : {bes}")
    print(f"  Expired            : {exps}")
    print(f"  Win Rate           : {wr:.1f}%")
    print(f"  Net Alpha (R)      : {net_r:+.2f}R")
    print(f"  Net PnL (USD)      : ${net_pnl:+.2f}")
    print(f"  Profit Factor      : {pf:.2f}")
    print(f"  Gross Profit       : ${gross_profit:.2f}")
    print(f"  Gross Loss         : ${gross_loss:.2f}")

    # Breakdown by Archetype
    print("\n--- PERFORMANCE BY ARCHETYPE ---")
    for arch, g in df_curated.groupby('archetype_id'):
        f_sub = g[g['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
        w_sub = len(g[g['status'] == 'WIN'])
        l_sub = len(g[g['status'] == 'LOSS'])
        be_sub = len(g[g['status'] == 'BREAKEVEN'])
        r_sub = g['rr_realized'].sum()
        pnl_sub = g['realized_pnl_usd'].sum()
        gp_sub = g[g['realized_pnl_usd'] > 0]['realized_pnl_usd'].sum()
        gl_sub = abs(g[g['realized_pnl_usd'] < 0]['realized_pnl_usd'].sum())
        pf_sub = (gp_sub / gl_sub) if gl_sub > 0 else (99.0 if gp_sub > 0 else 0.0)
        print(f"  {arch:15s} | Fills: {len(f_sub):2d} | W: {w_sub:2d} | L: {l_sub:2d} | BE: {be_sub:2d} | WR: {w_sub/len(f_sub)*100:5.1f}% | Net R: {r_sub:+6.2f}R | Net PnL: ${pnl_sub:+6.2f} | PF: {pf_sub:.2f}")

    # Breakdown by Session
    print("\n--- PERFORMANCE BY SESSION ---")
    for sess, g in df_curated.groupby('session_key'):
        f_sub = g[g['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
        w_sub = len(g[g['status'] == 'WIN'])
        l_sub = len(g[g['status'] == 'LOSS'])
        be_sub = len(g[g['status'] == 'BREAKEVEN'])
        r_sub = g['rr_realized'].sum()
        pnl_sub = g['realized_pnl_usd'].sum()
        gp_sub = g[g['realized_pnl_usd'] > 0]['realized_pnl_usd'].sum()
        gl_sub = abs(g[g['realized_pnl_usd'] < 0]['realized_pnl_usd'].sum())
        pf_sub = (gp_sub / gl_sub) if gl_sub > 0 else (99.0 if gp_sub > 0 else 0.0)
        print(f"  {sess:15s} | Fills: {len(f_sub):2d} | W: {w_sub:2d} | L: {l_sub:2d} | BE: {be_sub:2d} | WR: {w_sub/len(f_sub)*100:5.1f}% | Net R: {r_sub:+6.2f}R | Net PnL: ${pnl_sub:+6.2f} | PF: {pf_sub:.2f}")

    summary = {
        "signals": len(df_curated),
        "fills": n_fills,
        "wins": wins,
        "losses": losses,
        "be": bes,
        "expired": exps,
        "win_rate": round(wr, 1),
        "net_r": round(net_r, 2),
        "net_pnl": round(net_pnl, 2),
        "profit_factor": round(pf, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2)
    }
    with open(OUTPUT_DIR / "nq_curated_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n✅ Curated Audit complete! Results saved to {OUTPUT_DIR}")


if __name__ == '__main__':
    run_curated_nq_audit()
