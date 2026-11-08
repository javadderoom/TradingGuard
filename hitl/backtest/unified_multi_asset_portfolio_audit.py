"""
TradingGuard HITL - Unified Multi-Asset Production Portfolio Audit
Simulates side-by-side production deployment across:
  1. Gold (XAUUSD) - London Open & NY Pre-Open SMC Core (Target 3.5R, BE 1.8R)
  2. Cable (GBPUSD) - London Open SMC Core (Target 2.5R, BE 1.5R)
  3. Nasdaq 100 (NQ) - London Open & NY Pre-Market Curated Index Core (Target 3.5R, BE 1.5R)
Timeframe: August 1 to November 6, 2026 (3.2 months continuous MT5 broker M5/M1 data).
Computes portfolio diversification metrics, cross-asset correlation, Sharpe ratio, and drawdown smoothing.
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
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'unified_portfolio_audit'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_LONDON = ZoneInfo("Europe/London")
TZ_UTC = ZoneInfo("UTC")


def classify_session(dt_utc: datetime.datetime) -> Tuple[str, str]:
    dt_ny = dt_utc.astimezone(TZ_NEW_YORK)
    dt_lon = dt_utc.astimezone(TZ_LONDON)
    ny_time = dt_ny.time()
    lon_time = dt_lon.time()

    if dt_utc.weekday() in (5, 6):
        return "Weekend", "Weekend"

    if datetime.time(8, 0) <= lon_time < datetime.time(10, 30):
        return "London_Open", "London_Open"
    elif datetime.time(10, 30) <= lon_time < datetime.time(13, 0):
        return "London_Post_Open", "London_Post_Open"
    elif datetime.time(6, 30) <= lon_time < datetime.time(8, 0):
        return "London_Pre_Open", "London_Pre_Open"
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


def simulate_asset_trades(
    symbol: str,
    allowed_sessions: List[str],
    allowed_archetypes: Optional[List[str]],
    banned_archetypes: List[str],
    min_risk: float,
    max_risk: float,
    target_rr: float,
    be_rr: Optional[float],
    spread_pts: float,
    commission_usd: float,
    lot: float = 0.01,
    ttl_minutes: int = 60
) -> List[Dict[str, Any]]:
    print(f"\n--- Simulating Production Core for {symbol} ---")
    df_m5 = pd.read_parquet(CACHE_DIR / f"{symbol}_M5_2026.parquet" if symbol != "NQ" else CACHE_DIR / "NQ_M5_EXTENDED_2026.parquet")
    df_m1 = pd.read_parquet(CACHE_DIR / f"{symbol}_M1_2026.parquet" if symbol != "NQ" else CACHE_DIR / "NQ_M1_EXTENDED_2026.parquet")
    df_h1 = pd.read_parquet(CACHE_DIR / f"{symbol}_H1_2026.parquet" if symbol != "NQ" else CACHE_DIR / "NQ_H1_EXTENDED_2026.parquet")
    df_d1 = pd.read_parquet(CACHE_DIR / f"{symbol}_D1_2026.parquet" if symbol != "NQ" else CACHE_DIR / "NQ_D1_EXTENDED_2026.parquet")

    bars_m5_all = df_m5.to_dict('records')
    bars_m1_all = df_m1.to_dict('records')
    bars_h1_all = df_h1.to_dict('records')
    bars_d1_all = df_d1.to_dict('records')

    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1_all)}
    warmup_bars = 120
    total_m5 = len(bars_m5_all)

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

        if sess_key not in allowed_sessions:
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
            symbol=symbol,
            session_hour=bar_dt_tehran.hour,
            bars_1m=None,
            bars_1d=bars_1d_slice,
            closed_bars_only=True
        )

        if not res.get("has_setup") or res.get("setup_type") == "NONE":
            continue

        arch_id = res.get("archetype_id", "NONE")
        if arch_id in banned_archetypes:
            continue
        if allowed_archetypes and arch_id not in allowed_archetypes:
            continue

        setup_type = res.get("setup_type", "NONE")
        entry_p = res.get("entry_ref")
        sl_p = res.get("sl_ref")

        if not (entry_p and sl_p):
            continue

        risk_pts = abs(entry_p - sl_p)
        if risk_pts < min_risk or risk_pts > max_risk:
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

        precision = 1 if symbol == "NQ" else (2 if symbol == "XAUUSD" else 5)
        decision_dict = {
            "decision": direction,
            "entry": round(entry_p, precision),
            "sl": round(sl_p, precision),
            "tp": round(tp_p, precision),
            "lot": lot
        }

        eval_res = evaluate_council_decision(
            decision_dict=decision_dict,
            forward_m1_bars=forward_m1,
            symbol=symbol,
            spread_pts=spread_pts,
            breakeven_rr=be_rr if be_rr else 999.0,
            target_rr_cap=target_rr,
            commission_usd=commission_usd,
            slippage_pts=0.0,
            ttl_minutes=ttl_minutes
        )

        status = eval_res["status"]
        pnl = eval_res["realized_pnl_usd"]
        rr = eval_res.get("rr_realized", 0.0)
        exit_min = eval_res.get("exit_minute") or ttl_minutes

        trades.append({
            "symbol": symbol,
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
            active_until = curr_epoch + (exit_min * 60)
        elif status == "EXPIRED":
            active_until = curr_epoch + (ttl_minutes * 60)

    print(f"Simulation for {symbol} finished in {time.time()-t0:.2f}s! Signals: {len(trades)}")
    return trades


def run_portfolio_audit():
    print("=" * 95)
    print("🚀 TRADINGGUARD - UNIFIED MULTI-ASSET PRODUCTION PORTFOLIO AUDIT")
    print("Gold (XAUUSD) + Cable (GBPUSD) + Nasdaq 100 (NQ) | Aug 1 – Nov 6, 2026 Continuous Broker Data")
    print("=" * 95)

    # 1. Gold (XAUUSD): London Open, London Pre-Open, London Post-Open, NY Pre-Market
    # Policy: Target 3.5R, BE 1.8R, Spread 0.15, Commission 0.10, Risk 1.5 - 8.0 pts
    trades_xau = simulate_asset_trades(
        symbol="XAUUSD",
        allowed_sessions=["London_Open", "London_Pre_Open", "London_Post_Open", "NY_Pre_Market"],
        allowed_archetypes=["SETUP-ARCH-001", "SETUP-ARCH-002", "SETUP-ARCH-004", "SETUP-ARCH-005", "SETUP-ARCH-010"],
        banned_archetypes=["SETUP-ARCH-009"],
        min_risk=1.5,
        max_risk=8.0,
        target_rr=3.5,
        be_rr=1.8,
        spread_pts=0.15,
        commission_usd=0.10,
        lot=0.01,
        ttl_minutes=60
    )

    # 2. Cable (GBPUSD): London Open, London Pre-Open, London Post-Open
    # Policy: Target 2.5R, BE 1.5R, Spread 0.00025, Commission 0.10, Risk 8 - 35 pips (0.0008 - 0.0035)
    trades_gbp = simulate_asset_trades(
        symbol="GBPUSD",
        allowed_sessions=["London_Open", "London_Pre_Open", "London_Post_Open"],
        allowed_archetypes=["SETUP-ARCH-001", "SETUP-ARCH-004", "SETUP-ARCH-010"],
        banned_archetypes=["SETUP-ARCH-002", "SETUP-ARCH-009"],
        min_risk=0.0008,
        max_risk=0.0035,
        target_rr=2.5,
        be_rr=1.5,
        spread_pts=0.00025,
        commission_usd=0.10,
        lot=0.01,
        ttl_minutes=60
    )

    # 3. Nasdaq 100 (NQ): London Open, NY Pre-Market
    # Policy: Target 3.5R, BE 1.5R, Spread 1.0, Commission 0.10, Risk 15.0 - 120.0 pts
    trades_nq = simulate_asset_trades(
        symbol="NQ",
        allowed_sessions=["London_Open", "NY_Pre_Market"],
        allowed_archetypes=["SETUP-ARCH-001", "SETUP-ARCH-004", "SETUP-ARCH-010"],
        banned_archetypes=["SETUP-ARCH-002", "SETUP-ARCH-009"],
        min_risk=15.0,
        max_risk=120.0,
        target_rr=3.5,
        be_rr=1.5,
        spread_pts=1.0,
        commission_usd=0.10,
        lot=0.01,
        ttl_minutes=60
    )

    df_xau = pd.DataFrame(trades_xau)
    df_gbp = pd.DataFrame(trades_gbp)
    df_nq = pd.DataFrame(trades_nq)

    df_xau.to_parquet(OUTPUT_DIR / "trades_xauusd.parquet")
    df_gbp.to_parquet(OUTPUT_DIR / "trades_gbpusd.parquet")
    df_nq.to_parquet(OUTPUT_DIR / "trades_nq.parquet")

    # Combine all into unified trade stream
    df_all = pd.concat([df_xau, df_gbp, df_nq]).sort_values('epoch').reset_index(drop=True)
    df_all.to_parquet(OUTPUT_DIR / "unified_portfolio_trades.parquet")
    df_all.to_csv(OUTPUT_DIR / "unified_portfolio_trades.csv", index=False)

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

    s_xau = calc_stats(df_xau)
    s_gbp = calc_stats(df_gbp)
    s_nq = calc_stats(df_nq)
    s_all = calc_stats(df_all)

    print("\n" + "=" * 95)
    print("📊 MULTI-ASSET PRODUCTION PORTFOLIO BENCHMARK RESULTS")
    print("=" * 95)
    print(f"XAUUSD (Gold)   : {s_xau}")
    print(f"GBPUSD (Cable)  : {s_gbp}")
    print(f"NQ (Nasdaq 100) : {s_nq}")
    print(f"COMBINED PORTFOLIO: {s_all}")

    # Daily Return Analysis & Correlation
    # Create daily aggregated PnL and R
    dates = sorted(list(set(df_all['date'])))
    daily_records = []
    
    for d in dates:
        d_xau = df_xau[df_xau['date'] == d]
        d_gbp = df_gbp[df_gbp['date'] == d]
        d_nq = df_nq[df_nq['date'] == d]
        
        r_xau = d_xau['rr_realized'].sum() if len(d_xau) > 0 else 0.0
        r_gbp = d_gbp['rr_realized'].sum() if len(d_gbp) > 0 else 0.0
        r_nq = d_nq['rr_realized'].sum() if len(d_nq) > 0 else 0.0
        
        pnl_xau = d_xau['realized_pnl_usd'].sum() if len(d_xau) > 0 else 0.0
        pnl_gbp = d_gbp['realized_pnl_usd'].sum() if len(d_gbp) > 0 else 0.0
        pnl_nq = d_nq['realized_pnl_usd'].sum() if len(d_nq) > 0 else 0.0
        
        daily_records.append({
            "date": d,
            "r_xau": r_xau,
            "r_gbp": r_gbp,
            "r_nq": r_nq,
            "r_portfolio": r_xau + r_gbp + r_nq,
            "pnl_xau": pnl_xau,
            "pnl_gbp": pnl_gbp,
            "pnl_nq": pnl_nq,
            "pnl_portfolio": pnl_xau + pnl_gbp + pnl_nq
        })

    df_daily = pd.DataFrame(daily_records)
    df_daily.to_parquet(OUTPUT_DIR / "portfolio_daily_returns.parquet")
    df_daily.to_csv(OUTPUT_DIR / "portfolio_daily_returns.csv", index=False)

    # Compute correlation matrix of daily R returns
    corr_matrix = df_daily[['r_xau', 'r_gbp', 'r_nq']].corr()
    print("\n--- DAILY RETURN CORRELATION MATRIX (R-ALPHA) ---")
    print(corr_matrix.round(3))

    # Compute Drawdown & Sharpe for Portfolio vs Individual Assets
    def compute_risk_metrics(series_r):
        mean_r = series_r.mean()
        std_r = series_r.std()
        sharpe = (mean_r / std_r * np.sqrt(252)) if std_r > 0 else 0.0
        downside = series_r[series_r < 0]
        sortino = (mean_r / downside.std() * np.sqrt(252)) if len(downside) > 1 and downside.std() > 0 else 0.0
        cum_r = series_r.cumsum()
        peak = cum_r.cummax()
        dd = peak - cum_r
        max_dd = dd.max()
        return {
            "mean_daily_r": round(float(mean_r), 3),
            "std_daily_r": round(float(std_r), 3),
            "sharpe_annualized": round(float(sharpe), 2),
            "sortino_annualized": round(float(sortino), 2),
            "max_drawdown_r": round(float(max_dd), 2)
        }

    m_xau = compute_risk_metrics(df_daily['r_xau'])
    m_gbp = compute_risk_metrics(df_daily['r_gbp'])
    m_nq = compute_risk_metrics(df_daily['r_nq'])
    m_port = compute_risk_metrics(df_daily['r_portfolio'])

    print("\n--- RISK-ADJUSTED RETURN METRICS (ANNUALIZED) ---")
    print(f"XAUUSD Alone    : Sharpe: {m_xau['sharpe_annualized']:4.2f} | Sortino: {m_xau['sortino_annualized']:4.2f} | Max DD: {m_xau['max_drawdown_r']:5.2f}R")
    print(f"GBPUSD Alone    : Sharpe: {m_gbp['sharpe_annualized']:4.2f} | Sortino: {m_gbp['sortino_annualized']:4.2f} | Max DD: {m_gbp['max_drawdown_r']:5.2f}R")
    print(f"NQ Alone        : Sharpe: {m_nq['sharpe_annualized']:4.2f} | Sortino: {m_nq['sortino_annualized']:4.2f} | Max DD: {m_nq['max_drawdown_r']:5.2f}R")
    print(f"COMBINED PORTFOLIO: Sharpe: {m_port['sharpe_annualized']:4.2f} | Sortino: {m_port['sortino_annualized']:4.2f} | Max DD: {m_port['max_drawdown_r']:5.2f}R")

    summary = {
        "xau_stats": s_xau,
        "gbp_stats": s_gbp,
        "nq_stats": s_nq,
        "portfolio_stats": s_all,
        "correlation": corr_matrix.to_dict(),
        "risk_metrics": {
            "xau": m_xau,
            "gbp": m_gbp,
            "nq": m_nq,
            "portfolio": m_port
        }
    }

    with open(OUTPUT_DIR / "unified_portfolio_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n✅ Multi-Asset Portfolio Audit complete! Saved to {OUTPUT_DIR}")


if __name__ == '__main__':
    run_portfolio_audit()
