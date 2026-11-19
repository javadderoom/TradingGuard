"""
Audit Runner for Model 3: Intermarket SMT Correlation Divergence (MODEL-SMT-CD-03)
Asset Triad: NQ (Executing Asset) vs SPX / YM (Radar Assets)
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

NQ_CONFIG = {
    "parquet": "backtest_results/cache/NQ_M1_EXTENDED_2026.parquet",
    "spread": 1.0,
    "commission": 0.10,
    "slippage": 0.25,
    "sl_buffer": 8.0,
    "min_disp": 20.0,
    "lot": 0.01,
    "pip_val": 0.10
}


def run_model3_audit(target_rr: float = 3.0) -> Tuple[pd.DataFrame, Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    # Load NQ, SPX, YM
    df_nq_m1, df_nq_m5, _, _ = load_and_resample(str(BASE_DIR / NQ_CONFIG["parquet"]), "NQ")
    df_spx_m1, df_spx_m5, _, _ = load_and_resample(str(BASE_DIR / "backtest_results/cache/SPX_M1_2026.parquet"), "SPX")
    df_ym_m1, df_ym_m5, _, _ = load_and_resample(str(BASE_DIR / "backtest_results/cache/YM_M1_2026.parquet"), "YM")

    m1_time_to_idx = {t: idx for idx, t in enumerate(df_nq_m1['timestamp'].values)}

    # Map M5 bars of SPX and YM by timestamp
    spx_m5_map = df_spx_m5.set_index('timestamp')
    ym_m5_map = df_ym_m5.set_index('timestamp')

    trades = []
    df_nq_m5['date_utc'] = df_nq_m5['dt'].dt.date
    unique_dates = df_nq_m5['date_utc'].unique()

    for d in unique_dates:
        sess = get_session_times(d)
        lon_open_ts = int(sess["london_open_utc"].timestamp())
        ny_open_ts = int(sess["ny_open_utc"].timestamp())
        nyse_open_ts = int(sess["nyse_open_utc"].timestamp())
        day_start_ts = int(datetime.datetime(d.year, d.month, d.day, 0, 0, tzinfo=TZ_UTC).timestamp())

        # Day M1 for NQ, SPX, YM
        nq_m1_day = df_nq_m1[(df_nq_m1['timestamp'] >= day_start_ts) & (df_nq_m1['timestamp'] < day_start_ts + 86400)]
        spx_m1_day = df_spx_m1[(df_spx_m1['timestamp'] >= day_start_ts) & (df_spx_m1['timestamp'] < day_start_ts + 86400)]
        ym_m1_day = df_ym_m1[(df_ym_m1['timestamp'] >= day_start_ts) & (df_ym_m1['timestamp'] < day_start_ts + 86400)]

        if nq_m1_day.empty or spx_m1_day.empty or ym_m1_day.empty:
            continue

        # Asian Range: 00:00 UTC to London Open
        nq_asia = nq_m1_day[(nq_m1_day['timestamp'] >= day_start_ts) & (nq_m1_day['timestamp'] < lon_open_ts)]
        spx_asia = spx_m1_day[(spx_m1_day['timestamp'] >= day_start_ts) & (spx_m1_day['timestamp'] < lon_open_ts)]
        ym_asia = ym_m1_day[(ym_m1_day['timestamp'] >= day_start_ts) & (ym_m1_day['timestamp'] < lon_open_ts)]

        # London Range: London Open to NYSE Cash Open
        nq_london = nq_m1_day[(nq_m1_day['timestamp'] >= lon_open_ts) & (nq_m1_day['timestamp'] < nyse_open_ts)]
        spx_london = spx_m1_day[(spx_m1_day['timestamp'] >= lon_open_ts) & (spx_m1_day['timestamp'] < nyse_open_ts)]
        ym_london = ym_m1_day[(ym_m1_day['timestamp'] >= lon_open_ts) & (ym_m1_day['timestamp'] < nyse_open_ts)]

        windows = []
        if not nq_asia.empty and not spx_asia.empty and not ym_asia.empty:
            windows.append((
                "London",
                lon_open_ts,
                lon_open_ts + 210 * 60,
                nq_asia['high'].max(), nq_asia['low'].min(),
                spx_asia['high'].max(), spx_asia['low'].min(),
                ym_asia['high'].max(), ym_asia['low'].min()
            ))

        if not nq_london.empty and not spx_london.empty and not ym_london.empty:
            windows.append((
                "NYSE_Cash",
                nyse_open_ts,
                nyse_open_ts + 210 * 60,
                nq_london['high'].max(), nq_london['low'].min(),
                spx_london['high'].max(), spx_london['low'].min(),
                ym_london['high'].max(), ym_london['low'].min()
            ))

        for sess_name, w_start, w_end, nq_bh, nq_bl, spx_bh, spx_bl, ym_bh, ym_bl in windows:
            nq_m5_window = df_nq_m5[(df_nq_m5['timestamp'] >= w_start) & (df_nq_m5['timestamp'] < w_end)]
            if len(nq_m5_window) < 5:
                continue

            trade_taken = False

            # Scan for SMT divergence
            for i in range(len(nq_m5_window) - 4):
                if trade_taken:
                    break

                bar_t = nq_m5_window.iloc[i]
                ts_t = bar_t['timestamp']

                if ts_t not in spx_m5_map.index or ts_t not in ym_m5_map.index:
                    continue

                spx_bar_t = spx_m5_map.loc[ts_t]
                ym_bar_t = ym_m5_map.loc[ts_t]

                # 1. BULLISH SMT: NQ sweeps low, while SPX or YM holds higher low
                nq_swept_low = (bar_t['low'] < nq_bl)
                spx_swept_low = (spx_bar_t['low'] < spx_bl)
                ym_swept_low = (ym_bar_t['low'] < ym_bl)

                # Synchronized liquidation veto: If BOTH SPX and YM also sweep low -> VETO
                if nq_swept_low and not (spx_swept_low and ym_swept_low):
                    # Valid Bullish SMT! Check follow-up displacement candle & FVG within 3 bars
                    sweep_extreme = bar_t['low']
                    for j in range(1, 4):
                        bar_fvg = nq_m5_window.iloc[i + j]
                        bar_prev2 = nq_m5_window.iloc[i + j - 2]
                        
                        # Bullish FVG: Low of current bar > High of 2 bars ago
                        disp = bar_fvg['close'] - bar_fvg['open']
                        if (bar_fvg['low'] > bar_prev2['high']) and (disp >= NQ_CONFIG["min_disp"]):
                            # Found FVG! Entry limit at proximal edge (High of bar_prev2)
                            entry = bar_prev2['high']
                            sl = sweep_extreme - NQ_CONFIG["sl_buffer"]
                            risk = entry - sl
                            if risk <= 0 or risk > 60.0:
                                continue

                            # Forward M1 start: close of bar_fvg
                            forward_start_ts = bar_fvg['timestamp'] + 300
                            if forward_start_ts not in m1_time_to_idx:
                                sub = df_nq_m1[df_nq_m1['timestamp'] >= forward_start_ts]
                                if sub.empty:
                                    continue
                                start_idx = sub.index[0]
                            else:
                                start_idx = m1_time_to_idx[forward_start_ts]

                            res = simulate_order_execution(
                                df_m1=df_nq_m1,
                                start_m1_idx=start_idx,
                                decision="BUY",
                                entry=entry,
                                sl=sl,
                                target_rr=target_rr,
                                symbol="NQ",
                                spread=NQ_CONFIG["spread"],
                                slippage=NQ_CONFIG["slippage"],
                                commission_per_001_lot=NQ_CONFIG["commission"],
                                be_ratchet_rr=1.8,
                                ttl_minutes=60,
                                lot=NQ_CONFIG["lot"]
                            )
                            res["symbol"] = "NQ"
                            res["session"] = sess_name
                            res["date"] = str(d)
                            res["bar_t_time"] = str(bar_fvg['dt'])
                            res["direction"] = "BUY"
                            res["entry"] = entry
                            res["sl"] = sl
                            res["risk"] = risk
                            trades.append(res)
                            trade_taken = True
                            break

                # 2. BEARISH SMT: NQ sweeps high, while SPX or YM holds lower high
                nq_swept_high = (bar_t['high'] > nq_bh)
                spx_swept_high = (spx_bar_t['high'] > spx_bh)
                ym_swept_high = (ym_bar_t['high'] > ym_bh)

                # Synchronized breakout veto: If BOTH SPX and YM also sweep high -> VETO
                if nq_swept_high and not (spx_swept_high and ym_swept_high) and not trade_taken:
                    sweep_extreme = bar_t['high']
                    for j in range(1, 4):
                        bar_fvg = nq_m5_window.iloc[i + j]
                        bar_prev2 = nq_m5_window.iloc[i + j - 2]

                        disp = bar_prev2['open'] - bar_fvg['close']  # or bar_fvg['open'] - bar_fvg['close']
                        disp_candle = bar_fvg['open'] - bar_fvg['close']
                        # Bearish FVG: High of current bar < Low of 2 bars ago
                        if (bar_fvg['high'] < bar_prev2['low']) and (disp_candle >= NQ_CONFIG["min_disp"]):
                            entry = bar_prev2['low']
                            sl = sweep_extreme + NQ_CONFIG["sl_buffer"]
                            risk = sl - entry
                            if risk <= 0 or risk > 60.0:
                                continue

                            forward_start_ts = bar_fvg['timestamp'] + 300
                            if forward_start_ts not in m1_time_to_idx:
                                sub = df_nq_m1[df_nq_m1['timestamp'] >= forward_start_ts]
                                if sub.empty:
                                    continue
                                start_idx = sub.index[0]
                            else:
                                start_idx = m1_time_to_idx[forward_start_ts]

                            res = simulate_order_execution(
                                df_m1=df_nq_m1,
                                start_m1_idx=start_idx,
                                decision="SELL",
                                entry=entry,
                                sl=sl,
                                target_rr=target_rr,
                                symbol="NQ",
                                spread=NQ_CONFIG["spread"],
                                slippage=NQ_CONFIG["slippage"],
                                commission_per_001_lot=NQ_CONFIG["commission"],
                                be_ratchet_rr=1.8,
                                ttl_minutes=60,
                                lot=NQ_CONFIG["lot"]
                            )
                            res["symbol"] = "NQ"
                            res["session"] = sess_name
                            res["date"] = str(d)
                            res["bar_t_time"] = str(bar_fvg['dt'])
                            res["direction"] = "SELL"
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
    print(f"=== Auditing MODEL-SMT-CD-03 on NQ (Radar: SPX, YM) ===")
    df_tr, overall, lon, ny = run_model3_audit(target_rr=3.0)
    print("Overall Metrics (TP=3.0R):", overall)
    print("  London Session:", lon)
    print("  NYSE Cash Session:", ny)
    print("-" * 60)
