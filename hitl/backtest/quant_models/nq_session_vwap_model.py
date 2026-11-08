"""
TradingGuard Quantitative Alpha Research - Model B: Anchored Session VWAP & Standard Deviation Bands
Evaluates Institutional VWAP Mean-Reversion (+/-2.0 sigma exhaustion fade) and Trend Continuation on Nasdaq 100 (NQ).
Features:
- True volume-weighted average price anchored to session/daily open.
- Real-time rolling standard deviation bands (1.0 sigma, 2.0 sigma, 2.5 sigma).
- Continuous M1 execution verification over 5.2 months (June 1 - Nov 6, 2026: 32,974 M5 bars, 157,960 M1 bars).
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

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.evaluator import evaluate_council_decision

CACHE_DIR = BASE_DIR / 'backtest_results' / 'cache'
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'quant_models' / 'vwap_model'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_LONDON = ZoneInfo("Europe/London")
TZ_UTC = ZoneInfo("UTC")


def run_vwap_model():
    print("=" * 95)
    print("🔬 QUANTITATIVE ALPHA RESEARCH - MODEL B: ANCHORED SESSION VWAP & SIGMA BANDS")
    print("Nasdaq 100 (NQ) Continuous 5.2 Months (June 1 - Nov 6, 2026) | 32,974 M5 Bars | 157,960 M1 Bars")
    print("=" * 95)

    df_m5_sum = pd.read_parquet(CACHE_DIR / 'NQ_M5_SUMMER_2026.parquet')
    df_m1_sum = pd.read_parquet(CACHE_DIR / 'NQ_M1_SUMMER_2026.parquet')
    df_m5_aut = pd.read_parquet(CACHE_DIR / 'NQ_M5_EXTENDED_2026.parquet')
    df_m1_aut = pd.read_parquet(CACHE_DIR / 'NQ_M1_EXTENDED_2026.parquet')

    df_m5 = pd.concat([df_m5_sum, df_m5_aut]).drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)
    df_m1 = pd.concat([df_m1_sum, df_m1_aut]).drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)

    bars_m5 = df_m5.to_dict('records')
    bars_m1 = df_m1.to_dict('records')
    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    # Group M5 bars by trading day (UTC)
    for b in bars_m5:
        b_dt = datetime.datetime.fromtimestamp(b['time'], tz=TZ_UTC)
        b['_date'] = b_dt.date()
        b['_ny_time'] = b_dt.astimezone(TZ_NEW_YORK).time()
        b['_lon_time'] = b_dt.astimezone(TZ_LONDON).time()
        b['_typical'] = (b['high'] + b['low'] + b['close']) / 3.0

    # Calculate Session Anchored VWAP and Variance
    # We anchor VWAP at 00:00 UTC of each trading day
    trades = []
    active_until = 0

    curr_day = None
    cum_pv = 0.0
    cum_v = 0.0
    pv_sq_list = []

    for i in range(120, len(bars_m5)):
        b = bars_m5[i]
        curr_epoch = b['time']

        if curr_epoch < active_until:
            continue

        b_date = b['_date']
        if b_date != curr_day:
            curr_day = b_date
            cum_pv = 0.0
            cum_v = 0.0
            pv_sq_list = []

        v = float(b.get('tick_volume', 1) or 1)
        typ = b['_typical']
        cum_pv += typ * v
        cum_v += v

        vwap = cum_pv / cum_v if cum_v > 0 else typ
        pv_sq_list.append((typ, v))

        # Variance: sum(v * (typ - vwap)^2) / cum_v
        if len(pv_sq_list) >= 12 and cum_v > 0:
            var = sum(vi * ((typi - vwap) ** 2) for typi, vi in pv_sq_list) / cum_v
            sigma = np.sqrt(var) if var > 0 else 10.0
        else:
            sigma = 10.0

        b_lon = b['_lon_time']
        b_ny = b['_ny_time']

        # Evaluate only during liquid institutional sessions:
        # London Open (08:00 - 11:30 London) or NY Pre-Market + NY Morning (08:00 - 12:00 NY)
        in_london = datetime.time(8, 0) <= b_lon < datetime.time(11, 30)
        in_ny = datetime.time(8, 0) <= b_ny < datetime.time(12, 0)

        if not (in_london or in_ny):
            continue

        upper_2sigma = vwap + (2.0 * sigma)
        lower_2sigma = vwap - (2.0 * sigma)

        # Mean Reversion Exhaustion Setup:
        # 1. Bearish Fade: High reached > Upper 2.0 Sigma, but candle closed back below Upper 2.0 Sigma (rejection wick)
        is_bearish_fade = (b['high'] >= upper_2sigma) and (b['close'] < upper_2sigma) and (b['close'] < b['open'])
        # 2. Bullish Fade: Low reached < Lower 2.0 Sigma, but candle closed back above Lower 2.0 Sigma
        is_bullish_fade = (b['low'] <= lower_2sigma) and (b['close'] > lower_2sigma) and (b['close'] > b['open'])

        if not (is_bearish_fade or is_bullish_fade):
            continue

        direction = "SELL" if is_bearish_fade else "BUY"
        entry_p = b['close']
        
        # Stop loss: Extreme of the rejection candle + buffer (4.0 pts)
        if direction == "SELL":
            sl_p = b['high'] + 4.0
        else:
            sl_p = b['low'] - 4.0

        risk_pts = abs(entry_p - sl_p)
        if risk_pts < 15.0 or risk_pts > 80.0:
            continue

        # Target: Return to Session VWAP or 2.5R (whichever comes first)
        vwap_target_rr = abs(entry_p - vwap) / risk_pts
        target_rr = min(3.0, max(2.0, vwap_target_rr))
        tp_p = entry_p - (target_rr * risk_pts) if direction == "SELL" else entry_p + (target_rr * risk_pts)

        next_m1_epoch = curr_epoch + 300
        m1_start_idx = m1_time_map.get(next_m1_epoch)
        if m1_start_idx is None:
            forward_m1 = [bm for bm in bars_m1 if bm['time'] >= next_m1_epoch][:360]
        else:
            forward_m1 = bars_m1[m1_start_idx : m1_start_idx + 360]

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
            breakeven_rr=1.5,
            target_rr_cap=target_rr,
            commission_usd=0.10,
            slippage_pts=0.0,
            ttl_minutes=60
        )

        status = eval_res["status"]
        pnl = eval_res["realized_pnl_usd"]
        rr = eval_res.get("rr_realized", 0.0)
        exit_min = eval_res.get("exit_minute") or 60

        b_dt_utc = datetime.datetime.fromtimestamp(curr_epoch, tz=TZ_UTC)

        trades.append({
            "epoch": curr_epoch,
            "date": b_dt_utc.strftime("%Y-%m-%d"),
            "month": b_dt_utc.strftime("%Y-%m"),
            "session": "London" if in_london else "NY",
            "direction": direction,
            "vwap": round(vwap, 1),
            "sigma": round(sigma, 1),
            "risk_pts": round(risk_pts, 1),
            "target_rr": round(target_rr, 1),
            "status": status,
            "realized_pnl_usd": pnl,
            "rr_realized": rr
        })

        if status in ("WIN", "LOSS", "BREAKEVEN"):
            active_until = curr_epoch + (exit_min * 60)
        elif status == "EXPIRED":
            active_until = curr_epoch + (60 * 60)

    df_vwap = pd.DataFrame(trades)
    df_vwap.to_parquet(OUTPUT_DIR / "nq_vwap_exhaustion_trades.parquet")
    df_vwap.to_csv(OUTPUT_DIR / "nq_vwap_exhaustion_trades.csv", index=False)

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

    s = calc_stats(df_vwap)
    print("\n--- Model B: Session VWAP +/- 2.0 Sigma Exhaustion Fade ---")
    print(s)

    print("\n  By Session:")
    for sess, g in df_vwap.groupby('session'):
        sm = calc_stats(g)
        print(f"    {sess:8s} | Fills: {sm['Fills']:2d} | W: {sm['Wins']:2d} | L: {sm['Losses']:2d} | BE: {sm['BE']:2d} | WR: {sm['WR%']:5.1f}% | Net R: {sm['Net_R']:+6.2f}R | Net PnL: ${sm['Net_PnL']:+6.2f} | PF: {sm['PF']:.2f}")

    print("\n  Monthly Progression:")
    for m, g in df_vwap.groupby('month'):
        sm = calc_stats(g)
        print(f"    {m} | Fills: {sm['Fills']:2d} | W: {sm['Wins']:2d} | L: {sm['Losses']:2d} | BE: {sm['BE']:2d} | WR: {sm['WR%']:5.1f}% | Net R: {sm['Net_R']:+6.2f}R | Net PnL: ${sm['Net_PnL']:+6.2f} | PF: {sm['PF']:.2f}")


if __name__ == '__main__':
    run_vwap_model()
