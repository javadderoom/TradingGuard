"""
Audit Runner for Model 1: Institutional Session Breakout & Pullback Continuation (MODEL-ISB-PC-01)
Assets: XAUUSD_o, GBPUSD_o, NQ
Strict zero-lookahead, real broker spread & commission, SL-first collision resolution.
"""

import sys
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scratch.backtest_engine_base import (
    get_session_times, load_and_resample, simulate_order_execution, compute_metrics,
    TZ_UTC, TZ_LONDON, TZ_NEW_YORK
)

ASSET_CONFIGS = {
    "XAUUSD_o": {
        "parquet": "backtest_results/cache/M1_XAUUSD_o_2026.parquet",
        "spread": 0.22,
        "commission": 0.10,
        "slippage": 0.05,
        "delta": 0.50,
        "min_disp": 2.00,
        "sl_buffer": 1.00,
        "min_risk": 3.00,
        "max_risk": 9.00,
        "lot": 0.01,
        "pip_val": 1.0
    },
    "GBPUSD_o": {
        "parquet": "backtest_results/cache/M1_GBPUSD_o_2026.parquet",
        "spread": 0.00006,
        "commission": 0.10,
        "slippage": 0.00001,
        "delta": 0.0003,
        "min_disp": 0.0012,
        "sl_buffer": 0.0005,
        "min_risk": 0.0010,
        "max_risk": 0.0022,
        "lot": 0.01,
        "pip_val": 1000.0
    },
    "NQ": {
        "parquet": "backtest_results/cache/NQ_M1_EXTENDED_2026.parquet",
        "spread": 1.0,
        "commission": 0.10,
        "slippage": 0.25,
        "delta": 5.0,
        "min_disp": 25.0,
        "sl_buffer": 8.0,
        "min_risk": 15.0,
        "max_risk": 40.0,
        "lot": 0.01,
        "pip_val": 0.10
    }
}


def run_model1_audit(symbol: str, target_rr: float = 3.0) -> Tuple[pd.DataFrame, Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    cfg = ASSET_CONFIGS[symbol]
    df_m1, df_m5, df_h1, df_d1 = load_and_resample(str(BASE_DIR / cfg["parquet"]), symbol)

    # Pre-map M1 timestamps to indices for O(1) lookups
    m1_time_to_idx = {t: idx for idx, t in enumerate(df_m1['timestamp'].values)}
    
    # Pre-map H1 bars by timestamp for causal EMA lookup
    h1_records = df_h1.set_index('timestamp')
    d1_records = df_d1.set_index('timestamp')

    trades = []
    
    # Group M5 by date (UTC date)
    df_m5['date_utc'] = df_m5['dt'].dt.date
    unique_dates = df_m5['date_utc'].unique()

    for d in unique_dates:
        sess = get_session_times(d)
        lon_open_ts = int(sess["london_open_utc"].timestamp())
        ny_open_ts = int(sess["ny_open_utc"].timestamp())
        nyse_open_ts = int(sess["nyse_open_utc"].timestamp())

        day_start_ts = int(datetime.datetime(d.year, d.month, d.day, 0, 0, tzinfo=TZ_UTC).timestamp())
        
        # Prior Day D1 ADR
        # Lookup prior day ADR14
        prior_d1_ts = day_start_ts - 86400
        # Find latest available D1 bar before day_start_ts
        prev_d1 = df_d1[df_d1['timestamp'] < day_start_ts]
        if prev_d1.empty:
            continue
        adr14 = prev_d1['adr14'].iloc[-1]
        if pd.isna(adr14) or adr14 <= 0:
            continue

        # Get day's M1 bars
        m1_day = df_m1[(df_m1['timestamp'] >= day_start_ts) & (df_m1['timestamp'] < day_start_ts + 86400)]
        if m1_day.empty:
            continue

        # Asian Range: 00:00 UTC to London Open
        m1_asia = m1_day[(m1_day['timestamp'] >= day_start_ts) & (m1_day['timestamp'] < lon_open_ts)]
        if m1_asia.empty:
            continue
        asia_high = m1_asia['high'].max()
        asia_low = m1_asia['low'].min()

        # London Range: London Open to NY Open
        m1_london = m1_day[(m1_day['timestamp'] >= lon_open_ts) & (m1_day['timestamp'] < ny_open_ts)]
        london_high = m1_london['high'].max() if not m1_london.empty else None
        london_low = m1_london['low'].min() if not m1_london.empty else None

        # NQ Opening Range: First 15m of NYSE Cash Open
        if symbol == "NQ":
            m1_nyse_or = m1_day[(m1_day['timestamp'] >= nyse_open_ts) & (m1_day['timestamp'] < nyse_open_ts + 900)]
            nyse_or_high = m1_nyse_or['high'].max() if not m1_nyse_or.empty else None
            nyse_or_low = m1_nyse_or['low'].min() if not m1_nyse_or.empty else None

        # Windows to evaluate
        windows = [
            ("London", lon_open_ts, lon_open_ts + 150 * 60, asia_high, asia_low)
        ]
        if symbol != "NQ":
            if london_high is not None and london_low is not None:
                windows.append(("NY", ny_open_ts, ny_open_ts + 150 * 60, london_high, london_low))
        else:
            if nyse_or_high is not None and nyse_or_low is not None:
                windows.append(("NYSE_Cash_ORB", nyse_open_ts + 900, nyse_open_ts + 150 * 60, nyse_or_high, nyse_or_low))

        # Scan M5 bars inside windows
        for sess_name, w_start, w_end, bench_high, bench_low in windows:
            m5_window = df_m5[(df_m5['timestamp'] >= w_start) & (df_m5['timestamp'] < w_end)]
            if len(m5_window) < 2:
                continue

            trade_taken_in_window = False

            for i in range(len(m5_window) - 1):
                if trade_taken_in_window:
                    break  # One breakout setup per session window

                bar_t = m5_window.iloc[i]
                bar_t_next = m5_window.iloc[i+1]
                t_close_ts = bar_t['timestamp'] + 300

                # 1. Macro Gate: Causal H1 EMA50
                # Latest closed H1 bar strictly before or at t_close_ts
                closed_h1 = df_h1[df_h1['timestamp'] + 3600 <= t_close_ts]
                if len(closed_h1) < 6:
                    continue
                latest_h1 = closed_h1.iloc[-1]
                h1_close = latest_h1['close']
                h1_ema = latest_h1['ema50']
                h1_slope = latest_h1['ema50_slope5']

                # 2. ADR Headroom Gate
                m1_up_to_t = m1_day[m1_day['timestamp'] < t_close_ts]
                if m1_up_to_t.empty:
                    continue
                range_consumed = m1_up_to_t['high'].max() - m1_up_to_t['low'].min()
                if (range_consumed / adr14) > 0.70:
                    continue  # ADR exhausted

                # 3. Candle Quality Metrics
                candle_range = bar_t['high'] - bar_t['low']
                if candle_range <= 0:
                    continue
                body = abs(bar_t['close'] - bar_t['open'])
                body_ratio = body / candle_range
                upper_wick = bar_t['high'] - max(bar_t['open'], bar_t['close'])
                lower_wick = min(bar_t['open'], bar_t['close']) - bar_t['low']
                atr_m5 = bar_t['atr14']

                disp_ok = (candle_range >= 1.2 * atr_m5) or (candle_range >= cfg["min_disp"])
                if not (body_ratio >= 0.55 and disp_ok):
                    continue

                # Bullish Breakout
                if (bar_t['close'] >= bench_high + cfg["delta"]) and (upper_wick / candle_range <= 0.25):
                    # Gate check
                    if not (h1_close > h1_ema and h1_slope > 0):
                        continue
                    # Bar T+1 extension check
                    if not (bar_t_next['high'] > bar_t['high']):
                        continue

                    # Limit entry & SL
                    entry = max(bench_high, bar_t['open'])
                    sl = bar_t['low'] - cfg["sl_buffer"]
                    risk = entry - sl

                    if not (cfg["min_risk"] <= risk <= cfg["max_risk"]):
                        continue

                    # Forward M1 start: from close of bar_t_next (t_next + 300)
                    forward_start_ts = bar_t_next['timestamp'] + 300
                    if forward_start_ts not in m1_time_to_idx:
                        # find nearest >=
                        sub = df_m1[df_m1['timestamp'] >= forward_start_ts]
                        if sub.empty:
                            continue
                        start_idx = sub.index[0]
                    else:
                        start_idx = m1_time_to_idx[forward_start_ts]

                    res = simulate_order_execution(
                        df_m1=df_m1,
                        start_m1_idx=start_idx,
                        decision="BUY",
                        entry=entry,
                        sl=sl,
                        target_rr=target_rr,
                        symbol=symbol,
                        spread=cfg["spread"],
                        slippage=cfg["slippage"],
                        commission_per_001_lot=cfg["commission"],
                        be_ratchet_rr=1.8,
                        ttl_minutes=60,
                        lot=cfg["lot"]
                    )
                    res["symbol"] = symbol
                    res["session"] = sess_name
                    res["date"] = str(d)
                    res["bar_t_time"] = str(bar_t['dt'])
                    res["direction"] = "BUY"
                    res["entry"] = entry
                    res["sl"] = sl
                    res["risk"] = risk
                    trades.append(res)
                    trade_taken_in_window = True

                # Bearish Breakout
                elif (bar_t['close'] <= bench_low - cfg["delta"]) and (lower_wick / candle_range <= 0.25):
                    # Gate check
                    if not (h1_close < h1_ema and h1_slope < 0):
                        continue
                    # Bar T+1 extension check
                    if not (bar_t_next['low'] < bar_t['low']):
                        continue

                    # Limit entry & SL
                    entry = min(bench_low, bar_t['open'])
                    sl = bar_t['high'] + cfg["sl_buffer"]
                    risk = sl - entry

                    if not (cfg["min_risk"] <= risk <= cfg["max_risk"]):
                        continue

                    # Forward M1 start
                    forward_start_ts = bar_t_next['timestamp'] + 300
                    if forward_start_ts not in m1_time_to_idx:
                        sub = df_m1[df_m1['timestamp'] >= forward_start_ts]
                        if sub.empty:
                            continue
                        start_idx = sub.index[0]
                    else:
                        start_idx = m1_time_to_idx[forward_start_ts]

                    res = simulate_order_execution(
                        df_m1=df_m1,
                        start_m1_idx=start_idx,
                        decision="SELL",
                        entry=entry,
                        sl=sl,
                        target_rr=target_rr,
                        symbol=symbol,
                        spread=cfg["spread"],
                        slippage=cfg["slippage"],
                        commission_per_001_lot=cfg["commission"],
                        be_ratchet_rr=1.8,
                        ttl_minutes=60,
                        lot=cfg["lot"]
                    )
                    res["symbol"] = symbol
                    res["session"] = sess_name
                    res["date"] = str(d)
                    res["bar_t_time"] = str(bar_t['dt'])
                    res["direction"] = "SELL"
                    res["entry"] = entry
                    res["sl"] = sl
                    res["risk"] = risk
                    trades.append(res)
                    trade_taken_in_window = True

    df_trades = pd.DataFrame(trades)
    overall_metrics = compute_metrics(trades)

    # Session breakdown
    lon_trades = [t for t in trades if t.get("session") == "London"]
    ny_trades = [t for t in trades if t.get("session") in ("NY", "NYSE_Cash_ORB")]
    lon_metrics = compute_metrics(lon_trades)
    ny_metrics = compute_metrics(ny_trades)

    return df_trades, overall_metrics, lon_metrics, ny_metrics


if __name__ == "__main__":
    for sym in ["XAUUSD_o", "GBPUSD_o", "NQ"]:
        print(f"=== Auditing MODEL-ISB-PC-01 on {sym} ===")
        df_tr, overall, lon, ny = run_model1_audit(sym, target_rr=3.0)
        print(f"Overall Metrics (TP=3.0R):", overall)
        print(f"  London Session:", lon)
        print(f"  NY Session:    ", ny)
        print("-" * 60)
