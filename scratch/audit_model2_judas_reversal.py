"""
Audit Runner for Model 2: Statistical Extreme Judas Swing Reversal (MODEL-SE-JSR-02)
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
        "min_depth": 0.30,
        "max_depth": 2.50,
        "close_tol": 0.40,
        "sl_buffer": 1.20,
        "lot": 0.01,
        "pip_val": 1.0
    },
    "GBPUSD_o": {
        "parquet": "backtest_results/cache/M1_GBPUSD_o_2026.parquet",
        "spread": 0.00006,
        "commission": 0.10,
        "slippage": 0.00001,
        "min_depth": 0.0003,
        "max_depth": 0.0015,
        "close_tol": 0.0002,
        "sl_buffer": 0.0004,
        "lot": 0.01,
        "pip_val": 1000.0
    },
    "NQ": {
        "parquet": "backtest_results/cache/NQ_M1_EXTENDED_2026.parquet",
        "spread": 1.0,
        "commission": 0.10,
        "slippage": 0.25,
        "min_depth": 5.0,
        "max_depth": 25.0,
        "close_tol": 3.0,
        "sl_buffer": 6.0,
        "lot": 0.01,
        "pip_val": 0.10
    }
}


def run_model2_audit(symbol: str, target_rr: float = 2.0, entry_mode: str = "T1_CLOSE", shorts_only: bool = False) -> Tuple[pd.DataFrame, Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    cfg = ASSET_CONFIGS[symbol]
    df_m1, df_m5, df_h1, df_d1 = load_and_resample(str(BASE_DIR / cfg["parquet"]), symbol)

    m1_time_to_idx = {t: idx for idx, t in enumerate(df_m1['timestamp'].values)}

    trades = []
    df_m5['date_utc'] = df_m5['dt'].dt.date
    unique_dates = df_m5['date_utc'].unique()

    for d in unique_dates:
        sess = get_session_times(d)
        lon_open_ts = int(sess["london_open_utc"].timestamp())
        ny_open_ts = int(sess["ny_open_utc"].timestamp())
        nyse_open_ts = int(sess["nyse_open_utc"].timestamp())
        day_start_ts = int(datetime.datetime(d.year, d.month, d.day, 0, 0, tzinfo=TZ_UTC).timestamp())

        # Prior Day High/Low and ADR
        prev_d1 = df_d1[df_d1['timestamp'] < day_start_ts]
        if prev_d1.empty:
            continue
        pdh = prev_d1['high'].iloc[-1]
        pdl = prev_d1['low'].iloc[-1]
        adr14 = prev_d1['adr14'].iloc[-1]
        if pd.isna(adr14) or adr14 <= 0:
            continue

        # Day's M1 bars
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

        # Windows to evaluate
        # London Session: 07:00 - 10:30 UTC summer / 08:00 - 11:30 UTC winter (sweeps Asian H/L or PDH/PDL)
        # NY Session: 12:00 - 15:30 UTC summer / 13:00 - 16:30 UTC winter (sweeps London H/L or PDH/PDL)
        windows = [
            ("London", lon_open_ts, lon_open_ts + 210 * 60, asia_high, asia_low)
        ]
        if symbol != "NQ":
            if london_high is not None and london_low is not None:
                windows.append(("NY", ny_open_ts, ny_open_ts + 210 * 60, london_high, london_low))
        else:
            # For NQ: London and NYSE Cash Session (13:30/14:30 to +210 min)
            if london_high is not None and london_low is not None:
                windows.append(("NYSE_Cash", nyse_open_ts, nyse_open_ts + 210 * 60, london_high, london_low))

        for sess_name, w_start, w_end, bench_high, bench_low in windows:
            m5_window = df_m5[(df_m5['timestamp'] >= w_start) & (df_m5['timestamp'] < w_end)]
            if len(m5_window) < 2:
                continue

            # Compute Session VWAP on M1 bars from w_start
            m1_sess = df_m1[(df_m1['timestamp'] >= w_start) & (df_m1['timestamp'] < w_end)].copy()
            if m1_sess.empty:
                continue
            tp_series = (m1_sess['high'] + m1_sess['low'] + m1_sess['close']) / 3.0
            vol_series = m1_sess['tick_volume'].replace(0, 1)
            cum_pv = (tp_series * vol_series).cumsum()
            cum_v = vol_series.cumsum()
            m1_sess['vwap'] = cum_pv / cum_v
            # Rolling std
            cum_pv2 = (vol_series * ((tp_series - m1_sess['vwap'])**2)).cumsum()
            m1_sess['vwap_std'] = np.sqrt(cum_pv2 / cum_v).replace(0, 0.001)

            m1_sess_map = m1_sess.set_index('timestamp')

            trade_taken = False

            for i in range(len(m5_window) - 1):
                if trade_taken:
                    break

                bar_t = m5_window.iloc[i]
                bar_t_next = m5_window.iloc[i+1]
                t_close_ts = bar_t['timestamp'] + 300

                # Check Bar T timestamp in M1 VWAP
                last_m1_ts = bar_t['timestamp'] + 240
                if last_m1_ts in m1_sess_map.index:
                    vwap_val = m1_sess_map.loc[last_m1_ts, 'vwap']
                    vwap_std = m1_sess_map.loc[last_m1_ts, 'vwap_std']
                    z_score = (bar_t['close'] - vwap_val) / vwap_std
                else:
                    z_score = 0.0

                # ATR and EMA stretch
                atr_m5 = bar_t['atr14']
                ema20 = bar_t['ema20']
                dist_ema20 = abs(bar_t['close'] - ema20)

                # Day consumed range
                m1_up_to_t = m1_day[m1_day['timestamp'] < t_close_ts]
                range_consumed = m1_up_to_t['high'].max() - m1_up_to_t['low'].min() if not m1_up_to_t.empty else 0.0
                adr_pct = range_consumed / adr14

                candle_range = bar_t['high'] - bar_t['low']
                if candle_range <= 0:
                    continue
                body = abs(bar_t['close'] - bar_t['open'])
                body_ratio = body / candle_range
                upper_wick = bar_t['high'] - max(bar_t['open'], bar_t['close'])
                lower_wick = min(bar_t['open'], bar_t['close']) - bar_t['low']

                # Benchmarks to test: both Session benchmark and PDH/PDL
                high_candidates = [bench_high, pdh]
                low_candidates = [bench_low, pdl]

                # --- 1. BEARISH JUDAS REVERSAL (High Sweep -> SHORT) ---
                for target_h in high_candidates:
                    if trade_taken:
                        break
                    if bar_t['high'] > target_h:
                        penetration = bar_t['high'] - target_h
                        max_allowed_pen = min(cfg["max_depth"], 0.80 * atr_m5)
                        
                        # Bounded penetration & Runaway Blowout Veto
                        if not (cfg["min_depth"] <= penetration <= max_allowed_pen):
                            continue
                        if penetration > 1.0 * atr_m5:
                            continue

                        # Statistical Stretch Gate
                        stretch_ok = (z_score >= 2.00) or (dist_ema20 >= 2.2 * atr_m5) or (adr_pct >= 0.75)
                        if not stretch_ok:
                            continue

                        # Absorption Footprint (Bar T)
                        if not (upper_wick / candle_range >= 0.40 and body_ratio <= 0.35):
                            continue
                        if bar_t['close'] > target_h + cfg["close_tol"]:
                            continue

                        # Mandatory Bar T+1 MSS confirmation
                        if not (bar_t_next['close'] < bar_t['low']):
                            continue

                        # Execution
                        if entry_mode == "MIDPOINT":
                            entry = (bar_t['high'] + bar_t['low']) / 2.0
                        else:
                            entry = bar_t_next['close']

                        sl = bar_t['high'] + cfg["sl_buffer"]
                        risk = sl - entry
                        if risk <= 0:
                            continue

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
                            be_ratchet_rr=1.2,
                            ttl_minutes=45,
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
                        trade_taken = True
                        break

                # --- 2. BULLISH JUDAS REVERSAL (Low Sweep -> LONG) ---
                if not shorts_only and not trade_taken:
                    for target_l in low_candidates:
                        if trade_taken:
                            break
                        if bar_t['low'] < target_l:
                            penetration = target_l - bar_t['low']
                            max_allowed_pen = min(cfg["max_depth"], 0.80 * atr_m5)

                            if not (cfg["min_depth"] <= penetration <= max_allowed_pen):
                                continue
                            if penetration > 1.0 * atr_m5:
                                continue

                            stretch_ok = (z_score <= -2.00) or (dist_ema20 >= 2.2 * atr_m5) or (adr_pct >= 0.75)
                            if not stretch_ok:
                                continue

                            if not (lower_wick / candle_range >= 0.40 and body_ratio <= 0.35):
                                continue
                            if bar_t['close'] < target_l - cfg["close_tol"]:
                                continue

                            # Mandatory Bar T+1 MSS confirmation
                            if not (bar_t_next['close'] > bar_t['high']):
                                continue

                            if entry_mode == "MIDPOINT":
                                entry = (bar_t['high'] + bar_t['low']) / 2.0
                            else:
                                entry = bar_t_next['close']

                            sl = bar_t['low'] - cfg["sl_buffer"]
                            risk = entry - sl
                            if risk <= 0:
                                continue

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
                                decision="BUY",
                                entry=entry,
                                sl=sl,
                                target_rr=target_rr,
                                symbol=symbol,
                                spread=cfg["spread"],
                                slippage=cfg["slippage"],
                                commission_per_001_lot=cfg["commission"],
                                be_ratchet_rr=1.2,
                                ttl_minutes=45,
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
                            trade_taken = True
                            break

    df_trades = pd.DataFrame(trades)
    overall_metrics = compute_metrics(trades)

    lon_trades = [t for t in trades if t.get("session") == "London"]
    ny_trades = [t for t in trades if t.get("session") in ("NY", "NYSE_Cash")]
    lon_metrics = compute_metrics(lon_trades)
    ny_metrics = compute_metrics(ny_trades)

    return df_trades, overall_metrics, lon_metrics, ny_metrics


if __name__ == "__main__":
    for sym in ["XAUUSD_o", "GBPUSD_o", "NQ"]:
        print(f"=== Auditing MODEL-SE-JSR-02 on {sym} (All Directions, TP=2.0R) ===")
        df_tr, overall, lon, ny = run_model2_audit(sym, target_rr=2.0, entry_mode="T1_CLOSE", shorts_only=False)
        print("Overall:", overall)
        print("  London:", lon)
        print("  NY:    ", ny)

        if sym == "XAUUSD_o":
            print(f"=== Auditing MODEL-SE-JSR-02 on {sym} (Bearish Judas Breaker Priority / Shorts Only) ===")
            df_tr_s, overall_s, lon_s, ny_s = run_model2_audit(sym, target_rr=2.0, entry_mode="T1_CLOSE", shorts_only=True)
            print("Overall Shorts-Only:", overall_s)
            print("  London Shorts-Only:", lon_s)
            print("  NY Shorts-Only:    ", ny_s)

        print("-" * 60)
