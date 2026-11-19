"""
Fast In-Memory Grid Optimizer & Nov 13 Stress Test
Loads parquet once per symbol, detects candidate setups once, then simulates across R:R grids in milliseconds.
"""

import sys
import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scratch.backtest_engine_base import (
    get_session_times, load_and_resample, simulate_order_execution, compute_metrics,
    TZ_UTC, TZ_LONDON, TZ_NEW_YORK
)
from scratch.audit_model1_breakout import ASSET_CONFIGS as M1_CONFIGS
from scratch.audit_model2_judas_reversal import ASSET_CONFIGS as M2_CONFIGS
from scratch.audit_model3_smt_divergence import NQ_CONFIG as M3_CONFIG

print("================================================================================")
print("FAST INSTITUTIONAL GRID AUDIT & STRESS TEST")
print("================================================================================")

# --- 1. MODEL 1 GRID AUDIT ---
print("\n>>> MODEL 1 (ISB-PC-01: Session Breakout Continuation) TARGET R:R GRID <<<")
for sym, cfg in M1_CONFIGS.items():
    df_m1, df_m5, df_h1, df_d1 = load_and_resample(str(BASE_DIR / cfg["parquet"]), sym)
    m1_time_to_idx = {t: idx for idx, t in enumerate(df_m1['timestamp'].values)}
    
    # Collect all triggered signals first
    df_m5['date_utc'] = df_m5['dt'].dt.date
    unique_dates = df_m5['date_utc'].unique()
    signals = []

    for d in unique_dates:
        sess = get_session_times(d)
        lon_open_ts = int(sess["london_open_utc"].timestamp())
        ny_open_ts = int(sess["ny_open_utc"].timestamp())
        nyse_open_ts = int(sess["nyse_open_utc"].timestamp())
        day_start_ts = int(datetime.datetime(d.year, d.month, d.day, 0, 0, tzinfo=TZ_UTC).timestamp())

        prev_d1 = df_d1[df_d1['timestamp'] < day_start_ts]
        if prev_d1.empty: continue
        adr14 = prev_d1['adr14'].iloc[-1]
        if pd.isna(adr14) or adr14 <= 0: continue

        m1_day = df_m1[(df_m1['timestamp'] >= day_start_ts) & (df_m1['timestamp'] < day_start_ts + 86400)]
        if m1_day.empty: continue

        m1_asia = m1_day[(m1_day['timestamp'] >= day_start_ts) & (m1_day['timestamp'] < lon_open_ts)]
        if m1_asia.empty: continue
        asia_high = m1_asia['high'].max()
        asia_low = m1_asia['low'].min()

        m1_london = m1_day[(m1_day['timestamp'] >= lon_open_ts) & (m1_day['timestamp'] < ny_open_ts)]
        london_high = m1_london['high'].max() if not m1_london.empty else None
        london_low = m1_london['low'].min() if not m1_london.empty else None

        if sym == "NQ":
            m1_nyse_or = m1_day[(m1_day['timestamp'] >= nyse_open_ts) & (m1_day['timestamp'] < nyse_open_ts + 900)]
            nyse_or_high = m1_nyse_or['high'].max() if not m1_nyse_or.empty else None
            nyse_or_low = m1_nyse_or['low'].min() if not m1_nyse_or.empty else None

        windows = [("London", lon_open_ts, lon_open_ts + 150 * 60, asia_high, asia_low)]
        if sym != "NQ":
            if london_high is not None and london_low is not None:
                windows.append(("NY", ny_open_ts, ny_open_ts + 150 * 60, london_high, london_low))
        else:
            if nyse_or_high is not None and nyse_or_low is not None:
                windows.append(("NYSE_Cash_ORB", nyse_open_ts + 900, nyse_open_ts + 150 * 60, nyse_or_high, nyse_or_low))

        for sess_name, w_start, w_end, bench_high, bench_low in windows:
            m5_window = df_m5[(df_m5['timestamp'] >= w_start) & (df_m5['timestamp'] < w_end)]
            if len(m5_window) < 2: continue
            trade_taken = False
            for i in range(len(m5_window) - 1):
                if trade_taken: break
                bar_t = m5_window.iloc[i]
                bar_t_next = m5_window.iloc[i+1]
                t_close_ts = bar_t['timestamp'] + 300

                closed_h1 = df_h1[df_h1['timestamp'] + 3600 <= t_close_ts]
                if len(closed_h1) < 6: continue
                latest_h1 = closed_h1.iloc[-1]
                h1_close = latest_h1['close']
                h1_ema = latest_h1['ema50']
                h1_slope = latest_h1['ema50_slope5']

                m1_up_to_t = m1_day[m1_day['timestamp'] < t_close_ts]
                if m1_up_to_t.empty: continue
                range_consumed = m1_up_to_t['high'].max() - m1_up_to_t['low'].min()
                if (range_consumed / adr14) > 0.70: continue

                candle_range = bar_t['high'] - bar_t['low']
                if candle_range <= 0: continue
                body_ratio = abs(bar_t['close'] - bar_t['open']) / candle_range
                upper_wick = bar_t['high'] - max(bar_t['open'], bar_t['close'])
                lower_wick = min(bar_t['open'], bar_t['close']) - bar_t['low']
                atr_m5 = bar_t['atr14']

                disp_ok = (candle_range >= 1.2 * atr_m5) or (candle_range >= cfg["min_disp"])
                if not (body_ratio >= 0.55 and disp_ok): continue

                # Long
                if (bar_t['close'] >= bench_high + cfg["delta"]) and (upper_wick / candle_range <= 0.25):
                    if not (h1_close > h1_ema and h1_slope > 0): continue
                    if not (bar_t_next['high'] > bar_t['high']): continue
                    entry = max(bench_high, bar_t['open'])
                    sl = bar_t['low'] - cfg["sl_buffer"]
                    risk = entry - sl
                    if not (cfg["min_risk"] <= risk <= cfg["max_risk"]): continue
                    
                    forward_start_ts = bar_t_next['timestamp'] + 300
                    start_idx = m1_time_to_idx.get(forward_start_ts)
                    if start_idx is None:
                        sub = df_m1[df_m1['timestamp'] >= forward_start_ts]
                        if sub.empty: continue
                        start_idx = sub.index[0]

                    signals.append({
                        "date": str(d), "time": str(bar_t['dt']), "session": sess_name,
                        "direction": "BUY", "entry": entry, "sl": sl, "start_idx": start_idx
                    })
                    trade_taken = True

                # Short
                elif (bar_t['close'] <= bench_low - cfg["delta"]) and (lower_wick / candle_range <= 0.25):
                    if not (h1_close < h1_ema and h1_slope < 0): continue
                    if not (bar_t_next['low'] < bar_t['low']): continue
                    entry = min(bench_low, bar_t['open'])
                    sl = bar_t['high'] + cfg["sl_buffer"]
                    risk = sl - entry
                    if not (cfg["min_risk"] <= risk <= cfg["max_risk"]): continue

                    forward_start_ts = bar_t_next['timestamp'] + 300
                    start_idx = m1_time_to_idx.get(forward_start_ts)
                    if start_idx is None:
                        sub = df_m1[df_m1['timestamp'] >= forward_start_ts]
                        if sub.empty: continue
                        start_idx = sub.index[0]

                    signals.append({
                        "date": str(d), "time": str(bar_t['dt']), "session": sess_name,
                        "direction": "SELL", "entry": entry, "sl": sl, "start_idx": start_idx
                    })
                    trade_taken = True

    print(f"\n--- {sym} (Detected {len(signals)} candidate signals) ---")
    for rr in [2.0, 2.5, 3.0, 3.5]:
        trades = []
        for s in signals:
            res = simulate_order_execution(
                df_m1=df_m1, start_m1_idx=s["start_idx"], decision=s["direction"],
                entry=s["entry"], sl=s["sl"], target_rr=rr, symbol=sym,
                spread=cfg["spread"], slippage=cfg["slippage"],
                commission_per_001_lot=cfg["commission"], be_ratchet_rr=1.8, ttl_minutes=60, lot=cfg["lot"]
            )
            res["session"] = s["session"]
            trades.append(res)
        
        m_all = compute_metrics(trades)
        lon_m = compute_metrics([t for t in trades if t["session"] == "London"])
        ny_m = compute_metrics([t for t in trades if t["session"] in ("NY", "NYSE_Cash_ORB")])
        print(f"  Target R:R = {rr}R | Overall: N={m_all['closed_trades']}, WR={m_all['win_rate_pct']}%, Net R={m_all['net_r']:+.2f}, PF={m_all['profit_factor']:.2f}, EV={m_all['ev_r']:+.3f}R, MaxDD={m_all['max_drawdown_r']:.2f}R | Lon Net R={lon_m['net_r']:+.2f} | NY Net R={ny_m['net_r']:+.2f}")


# --- 2. MODEL 2 GRID AUDIT (XAUUSD Shorts-Only vs All, and NQ) ---
print("\n\n>>> MODEL 2 (SE-JSR-02: Statistical Extreme Judas Reversal) TARGET R:R GRID <<<")
for sym, cfg in M2_CONFIGS.items():
    if sym == "GBPUSD_o": continue
    df_m1, df_m5, df_h1, df_d1 = load_and_resample(str(BASE_DIR / cfg["parquet"]), sym)
    m1_time_to_idx = {t: idx for idx, t in enumerate(df_m1['timestamp'].values)}

    # Sweep signals
    for mode in ["T1_CLOSE", "MIDPOINT"]:
        for shorts_only in ([True, False] if sym == "XAUUSD_o" else [False]):
            mode_lbl = f"{mode} ({'Shorts-Only' if shorts_only else 'All'})"
            # Collect signals
            df_m5['date_utc'] = df_m5['dt'].dt.date
            unique_dates = df_m5['date_utc'].unique()
            signals = []

            for d in unique_dates:
                sess = get_session_times(d)
                lon_open_ts = int(sess["london_open_utc"].timestamp())
                ny_open_ts = int(sess["ny_open_utc"].timestamp())
                nyse_open_ts = int(sess["nyse_open_utc"].timestamp())
                day_start_ts = int(datetime.datetime(d.year, d.month, d.day, 0, 0, tzinfo=TZ_UTC).timestamp())

                prev_d1 = df_d1[df_d1['timestamp'] < day_start_ts]
                if prev_d1.empty: continue
                pdh = prev_d1['high'].iloc[-1]
                pdl = prev_d1['low'].iloc[-1]
                adr14 = prev_d1['adr14'].iloc[-1]
                if pd.isna(adr14) or adr14 <= 0: continue

                m1_day = df_m1[(df_m1['timestamp'] >= day_start_ts) & (df_m1['timestamp'] < day_start_ts + 86400)]
                if m1_day.empty: continue

                m1_asia = m1_day[(m1_day['timestamp'] >= day_start_ts) & (m1_day['timestamp'] < lon_open_ts)]
                if m1_asia.empty: continue
                asia_high = m1_asia['high'].max()
                asia_low = m1_asia['low'].min()

                m1_london = m1_day[(m1_day['timestamp'] >= lon_open_ts) & (m1_day['timestamp'] < ny_open_ts)]
                london_high = m1_london['high'].max() if not m1_london.empty else None
                london_low = m1_london['low'].min() if not m1_london.empty else None

                windows = [("London", lon_open_ts, lon_open_ts + 210 * 60, asia_high, asia_low)]
                if sym != "NQ":
                    if london_high is not None and london_low is not None:
                        windows.append(("NY", ny_open_ts, ny_open_ts + 210 * 60, london_high, london_low))
                else:
                    if london_high is not None and london_low is not None:
                        windows.append(("NYSE_Cash", nyse_open_ts, nyse_open_ts + 210 * 60, london_high, london_low))

                for sess_name, w_start, w_end, bench_high, bench_low in windows:
                    m5_window = df_m5[(df_m5['timestamp'] >= w_start) & (df_m5['timestamp'] < w_end)]
                    if len(m5_window) < 2: continue
                    trade_taken = False
                    for i in range(len(m5_window) - 1):
                        if trade_taken: break
                        bar_t = m5_window.iloc[i]
                        bar_t_next = m5_window.iloc[i+1]
                        t_close_ts = bar_t['timestamp'] + 300

                        atr_m5 = bar_t['atr14']
                        ema20 = bar_t['ema20']
                        dist_ema20 = abs(bar_t['close'] - ema20)

                        m1_up_to_t = m1_day[m1_day['timestamp'] < t_close_ts]
                        range_consumed = m1_up_to_t['high'].max() - m1_up_to_t['low'].min() if not m1_up_to_t.empty else 0.0
                        adr_pct = range_consumed / adr14

                        candle_range = bar_t['high'] - bar_t['low']
                        if candle_range <= 0: continue
                        body_ratio = abs(bar_t['close'] - bar_t['open']) / candle_range
                        upper_wick = bar_t['high'] - max(bar_t['open'], bar_t['close'])
                        lower_wick = min(bar_t['open'], bar_t['close']) - bar_t['low']

                        # Short
                        for target_h in [bench_high, pdh]:
                            if trade_taken: break
                            if bar_t['high'] > target_h:
                                pen = bar_t['high'] - target_h
                                max_pen = min(cfg["max_depth"], 0.80 * atr_m5)
                                if not (cfg["min_depth"] <= pen <= max_pen): continue
                                if pen > 1.0 * atr_m5: continue
                                stretch_ok = (dist_ema20 >= 2.2 * atr_m5) or (adr_pct >= 0.75)
                                if not stretch_ok: continue
                                if not (upper_wick / candle_range >= 0.40 and body_ratio <= 0.35): continue
                                if bar_t['close'] > target_h + cfg["close_tol"]: continue
                                if not (bar_t_next['close'] < bar_t['low']): continue

                                entry = (bar_t['high'] + bar_t['low']) / 2.0 if mode == "MIDPOINT" else bar_t_next['close']
                                sl = bar_t['high'] + cfg["sl_buffer"]
                                if sl - entry <= 0: continue
                                
                                forward_start_ts = bar_t_next['timestamp'] + 300
                                start_idx = m1_time_to_idx.get(forward_start_ts)
                                if start_idx is None:
                                    sub = df_m1[df_m1['timestamp'] >= forward_start_ts]
                                    if sub.empty: continue
                                    start_idx = sub.index[0]

                                signals.append({
                                    "date": str(d), "session": sess_name, "direction": "SELL",
                                    "entry": entry, "sl": sl, "start_idx": start_idx
                                })
                                trade_taken = True
                                break

                        # Long
                        if not shorts_only and not trade_taken:
                            for target_l in [bench_low, pdl]:
                                if trade_taken: break
                                if bar_t['low'] < target_l:
                                    pen = target_l - bar_t['low']
                                    max_pen = min(cfg["max_depth"], 0.80 * atr_m5)
                                    if not (cfg["min_depth"] <= pen <= max_pen): continue
                                    if pen > 1.0 * atr_m5: continue
                                    stretch_ok = (dist_ema20 >= 2.2 * atr_m5) or (adr_pct >= 0.75)
                                    if not stretch_ok: continue
                                    if not (lower_wick / candle_range >= 0.40 and body_ratio <= 0.35): continue
                                    if bar_t['close'] < target_l - cfg["close_tol"]: continue
                                    if not (bar_t_next['close'] > bar_t['high']): continue

                                    entry = (bar_t['high'] + bar_t['low']) / 2.0 if mode == "MIDPOINT" else bar_t_next['close']
                                    sl = bar_t['low'] - cfg["sl_buffer"]
                                    if entry - sl <= 0: continue

                                    forward_start_ts = bar_t_next['timestamp'] + 300
                                    start_idx = m1_time_to_idx.get(forward_start_ts)
                                    if start_idx is None:
                                        sub = df_m1[df_m1['timestamp'] >= forward_start_ts]
                                        if sub.empty: continue
                                        start_idx = sub.index[0]

                                    signals.append({
                                        "date": str(d), "session": sess_name, "direction": "BUY",
                                        "entry": entry, "sl": sl, "start_idx": start_idx
                                    })
                                    trade_taken = True
                                    break

            print(f"\n--- {sym} [{mode_lbl}] (Detected {len(signals)} signals) ---")
            for rr in [1.5, 2.0, 2.5]:
                trades = []
                for s in signals:
                    res = simulate_order_execution(
                        df_m1=df_m1, start_m1_idx=s["start_idx"], decision=s["direction"],
                        entry=s["entry"], sl=s["sl"], target_rr=rr, symbol=sym,
                        spread=cfg["spread"], slippage=cfg["slippage"],
                        commission_per_001_lot=cfg["commission"], be_ratchet_rr=1.2, ttl_minutes=45, lot=cfg["lot"]
                    )
                    res["session"] = s["session"]
                    trades.append(res)
                m_all = compute_metrics(trades)
                lon_m = compute_metrics([t for t in trades if t["session"] == "London"])
                ny_m = compute_metrics([t for t in trades if t["session"] in ("NY", "NYSE_Cash")])
                print(f"  Target R:R = {rr}R | Overall: N={m_all['closed_trades']}, WR={m_all['win_rate_pct']}%, Net R={m_all['net_r']:+.2f}, PF={m_all['profit_factor']:.2f}, EV={m_all['ev_r']:+.3f}R, MaxDD={m_all['max_drawdown_r']:.2f}R | Lon Net R={lon_m['net_r']:+.2f} | NY Net R={ny_m['net_r']:+.2f}")


# --- 3. MODEL 3 GRID AUDIT ---
print("\n\n>>> MODEL 3 (SMT-CD-03: Intermarket SMT Divergence) TARGET R:R GRID <<<")
df_nq_m1, df_nq_m5, _, _ = load_and_resample(str(BASE_DIR / M3_CONFIG["parquet"]), "NQ")
df_spx_m1, df_spx_m5, _, _ = load_and_resample(str(BASE_DIR / "backtest_results/cache/SPX_M1_2026.parquet"), "SPX")
df_ym_m1, df_ym_m5, _, _ = load_and_resample(str(BASE_DIR / "backtest_results/cache/YM_M1_2026.parquet"), "YM")
m1_time_to_idx = {t: idx for idx, t in enumerate(df_nq_m1['timestamp'].values)}
spx_m5_map = df_spx_m5.set_index('timestamp')
ym_m5_map = df_ym_m5.set_index('timestamp')

df_nq_m5['date_utc'] = df_nq_m5['dt'].dt.date
unique_dates = df_nq_m5['date_utc'].unique()
m3_signals = []

for d in unique_dates:
    sess = get_session_times(d)
    lon_open_ts = int(sess["london_open_utc"].timestamp())
    nyse_open_ts = int(sess["nyse_open_utc"].timestamp())
    day_start_ts = int(datetime.datetime(d.year, d.month, d.day, 0, 0, tzinfo=TZ_UTC).timestamp())

    nq_m1_day = df_nq_m1[(df_nq_m1['timestamp'] >= day_start_ts) & (df_nq_m1['timestamp'] < day_start_ts + 86400)]
    spx_m1_day = df_spx_m1[(df_spx_m1['timestamp'] >= day_start_ts) & (df_spx_m1['timestamp'] < day_start_ts + 86400)]
    ym_m1_day = df_ym_m1[(df_ym_m1['timestamp'] >= day_start_ts) & (df_ym_m1['timestamp'] < day_start_ts + 86400)]
    if nq_m1_day.empty or spx_m1_day.empty or ym_m1_day.empty: continue

    nq_asia = nq_m1_day[(nq_m1_day['timestamp'] >= day_start_ts) & (nq_m1_day['timestamp'] < lon_open_ts)]
    spx_asia = spx_m1_day[(spx_m1_day['timestamp'] >= day_start_ts) & (spx_m1_day['timestamp'] < lon_open_ts)]
    ym_asia = ym_m1_day[(ym_m1_day['timestamp'] >= day_start_ts) & (ym_m1_day['timestamp'] < lon_open_ts)]

    nq_london = nq_m1_day[(nq_m1_day['timestamp'] >= lon_open_ts) & (nq_m1_day['timestamp'] < nyse_open_ts)]
    spx_london = spx_m1_day[(spx_m1_day['timestamp'] >= lon_open_ts) & (spx_m1_day['timestamp'] < nyse_open_ts)]
    ym_london = ym_m1_day[(ym_m1_day['timestamp'] >= lon_open_ts) & (ym_m1_day['timestamp'] < nyse_open_ts)]

    windows = []
    if not nq_asia.empty and not spx_asia.empty and not ym_asia.empty:
        windows.append(("London", lon_open_ts, lon_open_ts + 210 * 60, nq_asia['high'].max(), nq_asia['low'].min(), spx_asia['high'].max(), spx_asia['low'].min(), ym_asia['high'].max(), ym_asia['low'].min()))
    if not nq_london.empty and not spx_london.empty and not ym_london.empty:
        windows.append(("NYSE_Cash", nyse_open_ts, nyse_open_ts + 210 * 60, nq_london['high'].max(), nq_london['low'].min(), spx_london['high'].max(), spx_london['low'].min(), ym_london['high'].max(), ym_london['low'].min()))

    for sess_name, w_start, w_end, nq_bh, nq_bl, spx_bh, spx_bl, ym_bh, ym_bl in windows:
        nq_m5_window = df_nq_m5[(df_nq_m5['timestamp'] >= w_start) & (df_nq_m5['timestamp'] < w_end)]
        if len(nq_m5_window) < 5: continue
        trade_taken = False

        for i in range(len(nq_m5_window) - 4):
            if trade_taken: break
            bar_t = nq_m5_window.iloc[i]
            ts_t = bar_t['timestamp']
            if ts_t not in spx_m5_map.index or ts_t not in ym_m5_map.index: continue
            spx_bar_t = spx_m5_map.loc[ts_t]
            ym_bar_t = ym_m5_map.loc[ts_t]

            nq_swept_low = (bar_t['low'] < nq_bl)
            spx_swept_low = (spx_bar_t['low'] < spx_bl)
            ym_swept_low = (ym_bar_t['low'] < ym_bl)

            # Bullish SMT with Synchronized Liquidation Veto
            if nq_swept_low and not (spx_swept_low and ym_swept_low):
                sweep_extreme = bar_t['low']
                for j in range(1, 4):
                    bar_fvg = nq_m5_window.iloc[i + j]
                    bar_prev2 = nq_m5_window.iloc[i + j - 2]
                    disp = bar_fvg['close'] - bar_fvg['open']
                    if (bar_fvg['low'] > bar_prev2['high']) and (disp >= M3_CONFIG["min_disp"]):
                        entry = bar_prev2['high']
                        sl = sweep_extreme - M3_CONFIG["sl_buffer"]
                        risk = entry - sl
                        if risk <= 0 or risk > 60.0: continue
                        forward_start_ts = bar_fvg['timestamp'] + 300
                        start_idx = m1_time_to_idx.get(forward_start_ts)
                        if start_idx is None:
                            sub = df_nq_m1[df_nq_m1['timestamp'] >= forward_start_ts]
                            if sub.empty: continue
                            start_idx = sub.index[0]
                        m3_signals.append({
                            "date": str(d), "session": sess_name, "direction": "BUY",
                            "entry": entry, "sl": sl, "start_idx": start_idx
                        })
                        trade_taken = True
                        break

            nq_swept_high = (bar_t['high'] > nq_bh)
            spx_swept_high = (spx_bar_t['high'] > spx_bh)
            ym_swept_high = (ym_bar_t['high'] > ym_bh)

            # Bearish SMT with Synchronized Breakout Veto
            if nq_swept_high and not (spx_swept_high and ym_swept_high) and not trade_taken:
                sweep_extreme = bar_t['high']
                for j in range(1, 4):
                    bar_fvg = nq_m5_window.iloc[i + j]
                    bar_prev2 = nq_m5_window.iloc[i + j - 2]
                    disp = bar_fvg['open'] - bar_fvg['close']
                    if (bar_fvg['high'] < bar_prev2['low']) and (disp >= M3_CONFIG["min_disp"]):
                        entry = bar_prev2['low']
                        sl = sweep_extreme + M3_CONFIG["sl_buffer"]
                        risk = sl - entry
                        if risk <= 0 or risk > 60.0: continue
                        forward_start_ts = bar_fvg['timestamp'] + 300
                        start_idx = m1_time_to_idx.get(forward_start_ts)
                        if start_idx is None:
                            sub = df_nq_m1[df_nq_m1['timestamp'] >= forward_start_ts]
                            if sub.empty: continue
                            start_idx = sub.index[0]
                        m3_signals.append({
                            "date": str(d), "session": sess_name, "direction": "SELL",
                            "entry": entry, "sl": sl, "start_idx": start_idx
                        })
                        trade_taken = True
                        break

print(f"\n--- NQ SMT Divergence (Detected {len(m3_signals)} candidate signals) ---")
for rr in [2.5, 3.0, 3.5, 4.0]:
    trades = []
    for s in m3_signals:
        res = simulate_order_execution(
            df_m1=df_nq_m1, start_m1_idx=s["start_idx"], decision=s["direction"],
            entry=s["entry"], sl=s["sl"], target_rr=rr, symbol="NQ",
            spread=M3_CONFIG["spread"], slippage=M3_CONFIG["slippage"],
            commission_per_001_lot=M3_CONFIG["commission"], be_ratchet_rr=1.8, ttl_minutes=60, lot=M3_CONFIG["lot"]
        )
        res["session"] = s["session"]
        trades.append(res)
    m_all = compute_metrics(trades)
    lon_m = compute_metrics([t for t in trades if t["session"] == "London"])
    ny_m = compute_metrics([t for t in trades if t["session"] in ("NY", "NYSE_Cash")])
    print(f"  Target R:R = {rr}R | Overall: N={m_all['closed_trades']}, WR={m_all['win_rate_pct']}%, Net R={m_all['net_r']:+.2f}, PF={m_all['profit_factor']:.2f}, EV={m_all['ev_r']:+.3f}R, MaxDD={m_all['max_drawdown_r']:.2f}R | Lon Net R={lon_m['net_r']:+.2f} | NY Net R={ny_m['net_r']:+.2f}")

print("\n================================================================================")
print("COMPLETED FAST GRID AUDIT")
print("================================================================================")
