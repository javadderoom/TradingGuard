"""
TradingGuard Microstructure & Trade Management Optimizer
Performs exhaustive quantitative excursion analysis, trade management optimization
(Breakeven ratchets, Trailing Stops, Dynamic Session Exits, Volatility/Volume Filters),
and institutional benchmarking against ARCH-001, ARCH-014, and ARCH-015.
"""

import sys
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scratch.backtest_engine_base import (
    get_session_times, load_and_resample, compute_metrics,
    TZ_UTC, TZ_LONDON, TZ_NEW_YORK
)
from scratch.audit_model1_breakout import ASSET_CONFIGS as M1_CONFIGS
from scratch.audit_model2_judas_reversal import ASSET_CONFIGS as M2_CONFIGS
from scratch.audit_model3_smt_divergence import NQ_CONFIG as M3_CONFIG


def run_full_excursion_simulation(
    df_m1: pd.DataFrame,
    start_m1_idx: int,
    decision: str,
    entry: float,
    sl: float,
    target_rr: float,
    symbol: str,
    spread: float,
    slippage: float,
    commission_per_001_lot: float = 0.10,
    be_ratchet_rr: Optional[float] = None,
    trailing_stop_mode: Optional[str] = None,  # None, "STEP_15_25", "STEP_10_20", "ATR_TRAIL"
    atr_trail_dist: float = 0.0,
    session_exit_utc_hour: Optional[int] = None,  # e.g., 12 (London lunch), 16 (NY lunch), 21 (rollover)
    ttl_minutes: int = 60,
    lot: float = 0.01
) -> Dict[str, Any]:
    """
    Detailed forward M1 simulator recording exact MFE, MAE, and evaluating
    custom trade management rules (BE, trailing stops, session exits).
    """
    is_buy = (decision.upper() == "BUY")

    if "XAU" in symbol.upper():
        pip_val = 1.0
    elif "GBP" in symbol.upper() or "EUR" in symbol.upper():
        pip_val = 1000.0
    elif "NQ" in symbol.upper() or "SPX" in symbol.upper() or "YM" in symbol.upper():
        pip_val = 0.10
    else:
        pip_val = 1.0

    commission_total = commission_per_001_lot * (lot / 0.01)
    effective_entry = entry + slippage if is_buy else entry - slippage
    risk_pts = abs(effective_entry - sl)
    if risk_pts <= 0:
        return {"status": "INVALID_RISK", "realized_r": 0.0, "realized_pnl_usd": 0.0}

    tp = effective_entry + (risk_pts * target_rr) if is_buy else effective_entry - (risk_pts * target_rr)
    price_risk_usd = risk_pts * pip_val

    is_filled = False
    fill_idx = None
    active_sl = sl
    is_be_active = False

    n_bars = len(df_m1)
    end_idx = min(n_bars, start_m1_idx + 1440)  # max 24 hours

    forward_highs = df_m1['high'].values[start_m1_idx:end_idx]
    forward_lows = df_m1['low'].values[start_m1_idx:end_idx]
    forward_closes = df_m1['close'].values[start_m1_idx:end_idx]
    forward_times = df_m1['timestamp'].values[start_m1_idx:end_idx]

    peak_mfe_r = 0.0
    peak_mae_r = 0.0

    for rel_idx in range(len(forward_highs)):
        h = forward_highs[rel_idx]
        l = forward_lows[rel_idx]
        c = forward_closes[rel_idx]
        t = forward_times[rel_idx]
        dt_utc = datetime.datetime.fromtimestamp(t, tz=TZ_UTC)

        if not is_filled:
            if rel_idx >= ttl_minutes:
                return {
                    "status": "EXPIRED",
                    "realized_r": 0.0,
                    "realized_pnl_usd": 0.0,
                    "is_realized": True,
                    "fill_minute": None,
                    "exit_minute": rel_idx,
                    "mfe_r": 0.0,
                    "mae_r": 0.0,
                    "duration_m": 0,
                    "notes": "TTL expired"
                }
            if is_buy and (l + spread) <= entry:
                is_filled = True
                fill_idx = rel_idx
            elif (not is_buy) and h >= entry:
                is_filled = True
                fill_idx = rel_idx

        else:
            # Trade is active
            # Update MFE and MAE
            if is_buy:
                cur_mfe_pts = h - effective_entry
                cur_mae_pts = effective_entry - l
            else:
                cur_mfe_pts = effective_entry - (l + spread)
                cur_mae_pts = (h + spread) - effective_entry

            cur_mfe_r = cur_mfe_pts / risk_pts
            cur_mae_r = max(0.0, cur_mae_pts / risk_pts)

            if cur_mfe_r > peak_mfe_r:
                peak_mfe_r = cur_mfe_r
            if cur_mae_r > peak_mae_r:
                peak_mae_r = cur_mae_r

            # Check Dynamic Session Exit
            if session_exit_utc_hour is not None:
                # If current bar has reached or passed session_exit_utc_hour
                if dt_utc.hour >= session_exit_utc_hour and rel_idx > fill_idx:
                    # Flatten at market close of this bar
                    exit_price = c if is_buy else (c + spread)
                    exit_pnl = ((exit_price - effective_entry) if is_buy else (effective_entry - exit_price)) * pip_val - commission_total
                    realized_r = round(exit_pnl / price_risk_usd, 3)
                    status = "WIN" if exit_pnl > 0 else ("BREAKEVEN" if abs(exit_pnl) < commission_total * 2 else "LOSS")
                    return {
                        "status": f"SESSION_EXIT_{status}",
                        "realized_r": realized_r,
                        "realized_pnl_usd": round(exit_pnl, 2),
                        "is_realized": True,
                        "fill_minute": fill_idx,
                        "exit_minute": rel_idx,
                        "mfe_r": round(peak_mfe_r, 3),
                        "mae_r": round(peak_mae_r, 3),
                        "duration_m": rel_idx - fill_idx,
                        "notes": f"Session exit at {session_exit_utc_hour}:00 UTC"
                    }

            # Check SL / TP / BE / Trailing Stop
            if is_buy:
                hit_sl = (l <= active_sl)
                hit_tp = (h >= tp)

                if hit_sl and hit_tp:
                    loss_amount = -price_risk_usd - commission_total
                    return {
                        "status": "LOSS_COLLISION",
                        "realized_r": -1.0,
                        "realized_pnl_usd": round(loss_amount, 2),
                        "is_realized": True,
                        "fill_minute": fill_idx,
                        "exit_minute": rel_idx,
                        "mfe_r": round(peak_mfe_r, 3),
                        "mae_r": round(peak_mae_r, 3),
                        "duration_m": rel_idx - fill_idx,
                        "notes": "SL-first collision"
                    }

                if hit_sl:
                    if is_be_active:
                        be_pnl = (active_sl - effective_entry) * pip_val - commission_total
                        realized_r = round(be_pnl / price_risk_usd, 3)
                        status_str = "BREAKEVEN" if abs(realized_r) <= 0.1 else ("TRAIL_WIN" if realized_r > 0 else "LOSS")
                        return {
                            "status": status_str,
                            "realized_r": realized_r,
                            "realized_pnl_usd": round(be_pnl, 2),
                            "is_realized": True,
                            "fill_minute": fill_idx,
                            "exit_minute": rel_idx,
                            "mfe_r": round(peak_mfe_r, 3),
                            "mae_r": round(peak_mae_r, 3),
                            "duration_m": rel_idx - fill_idx,
                            "notes": f"Hit active SL ({active_sl:.2f})"
                        }
                    else:
                        loss_amount = -price_risk_usd - commission_total
                        return {
                            "status": "LOSS",
                            "realized_r": -1.0,
                            "realized_pnl_usd": round(loss_amount, 2),
                            "is_realized": True,
                            "fill_minute": fill_idx,
                            "exit_minute": rel_idx,
                            "mfe_r": round(peak_mfe_r, 3),
                            "mae_r": round(peak_mae_r, 3),
                            "duration_m": rel_idx - fill_idx,
                            "notes": "Hit Stop Loss"
                        }

                elif hit_tp:
                    reward_amount = (tp - effective_entry) * pip_val - commission_total
                    realized_r = round(reward_amount / price_risk_usd, 3)
                    return {
                        "status": "WIN",
                        "realized_r": realized_r,
                        "realized_pnl_usd": round(reward_amount, 2),
                        "is_realized": True,
                        "fill_minute": fill_idx,
                        "exit_minute": rel_idx,
                        "mfe_r": round(max(peak_mfe_r, target_rr), 3),
                        "mae_r": round(peak_mae_r, 3),
                        "duration_m": rel_idx - fill_idx,
                        "notes": f"Hit TP at {target_rr}R"
                    }

                # Ratchet / Trailing Stop updates at end of bar for subsequent bars
                # 1. BE Ratchet
                if be_ratchet_rr is not None and not is_be_active:
                    if peak_mfe_r >= be_ratchet_rr:
                        is_be_active = True
                        active_sl = effective_entry + spread

                # 2. Trailing Stops
                if trailing_stop_mode == "STEP_15_25":
                    # At +1.5R lock +0.5R; at +2.5R lock +1.5R; at +3.5R lock +2.5R
                    if peak_mfe_r >= 3.5:
                        cand_sl = effective_entry + (2.5 * risk_pts)
                        if cand_sl > active_sl:
                            active_sl = cand_sl
                            is_be_active = True
                    elif peak_mfe_r >= 2.5:
                        cand_sl = effective_entry + (1.5 * risk_pts)
                        if cand_sl > active_sl:
                            active_sl = cand_sl
                            is_be_active = True
                    elif peak_mfe_r >= 1.5:
                        cand_sl = effective_entry + (0.5 * risk_pts)
                        if cand_sl > active_sl:
                            active_sl = cand_sl
                            is_be_active = True

                elif trailing_stop_mode == "STEP_10_20":
                    # At +1.0R lock BE; at +2.0R lock +1.0R; at +3.0R lock +2.0R
                    if peak_mfe_r >= 3.0:
                        cand_sl = effective_entry + (2.0 * risk_pts)
                        if cand_sl > active_sl:
                            active_sl = cand_sl
                            is_be_active = True
                    elif peak_mfe_r >= 2.0:
                        cand_sl = effective_entry + (1.0 * risk_pts)
                        if cand_sl > active_sl:
                            active_sl = cand_sl
                            is_be_active = True
                    elif peak_mfe_r >= 1.0:
                        cand_sl = effective_entry + spread
                        if cand_sl > active_sl:
                            active_sl = cand_sl
                            is_be_active = True

                elif trailing_stop_mode == "ATR_TRAIL" and atr_trail_dist > 0:
                    # Once MFE >= 1.5R, trail at (h - atr_trail_dist)
                    if peak_mfe_r >= 1.5:
                        cand_sl = h - atr_trail_dist
                        if cand_sl > active_sl:
                            active_sl = cand_sl
                            is_be_active = True

            else:
                # SELL Position
                hit_sl = (h + spread >= active_sl)
                hit_tp = (l + spread <= tp)

                if hit_sl and hit_tp:
                    loss_amount = -price_risk_usd - commission_total
                    return {
                        "status": "LOSS_COLLISION",
                        "realized_r": -1.0,
                        "realized_pnl_usd": round(loss_amount, 2),
                        "is_realized": True,
                        "fill_minute": fill_idx,
                        "exit_minute": rel_idx,
                        "mfe_r": round(peak_mfe_r, 3),
                        "mae_r": round(peak_mae_r, 3),
                        "duration_m": rel_idx - fill_idx,
                        "notes": "SL-first collision"
                    }

                if hit_sl:
                    if is_be_active:
                        be_pnl = (effective_entry - active_sl) * pip_val - commission_total
                        realized_r = round(be_pnl / price_risk_usd, 3)
                        status_str = "BREAKEVEN" if abs(realized_r) <= 0.1 else ("TRAIL_WIN" if realized_r > 0 else "LOSS")
                        return {
                            "status": status_str,
                            "realized_r": realized_r,
                            "realized_pnl_usd": round(be_pnl, 2),
                            "is_realized": True,
                            "fill_minute": fill_idx,
                            "exit_minute": rel_idx,
                            "mfe_r": round(peak_mfe_r, 3),
                            "mae_r": round(peak_mae_r, 3),
                            "duration_m": rel_idx - fill_idx,
                            "notes": f"Hit active SL ({active_sl:.2f})"
                        }
                    else:
                        loss_amount = -price_risk_usd - commission_total
                        return {
                            "status": "LOSS",
                            "realized_r": -1.0,
                            "realized_pnl_usd": round(loss_amount, 2),
                            "is_realized": True,
                            "fill_minute": fill_idx,
                            "exit_minute": rel_idx,
                            "mfe_r": round(peak_mfe_r, 3),
                            "mae_r": round(peak_mae_r, 3),
                            "duration_m": rel_idx - fill_idx,
                            "notes": "Hit Stop Loss"
                        }

                elif hit_tp:
                    reward_amount = (effective_entry - tp) * pip_val - commission_total
                    realized_r = round(reward_amount / price_risk_usd, 3)
                    return {
                        "status": "WIN",
                        "realized_r": realized_r,
                        "realized_pnl_usd": round(reward_amount, 2),
                        "is_realized": True,
                        "fill_minute": fill_idx,
                        "exit_minute": rel_idx,
                        "mfe_r": round(max(peak_mfe_r, target_rr), 3),
                        "mae_r": round(peak_mae_r, 3),
                        "duration_m": rel_idx - fill_idx,
                        "notes": f"Hit TP at {target_rr}R"
                    }

                # Ratchet / Trailing Stop updates
                if be_ratchet_rr is not None and not is_be_active:
                    if peak_mfe_r >= be_ratchet_rr:
                        is_be_active = True
                        active_sl = effective_entry - spread

                if trailing_stop_mode == "STEP_15_25":
                    if peak_mfe_r >= 3.5:
                        cand_sl = effective_entry - (2.5 * risk_pts)
                        if cand_sl < active_sl:
                            active_sl = cand_sl
                            is_be_active = True
                    elif peak_mfe_r >= 2.5:
                        cand_sl = effective_entry - (1.5 * risk_pts)
                        if cand_sl < active_sl:
                            active_sl = cand_sl
                            is_be_active = True
                    elif peak_mfe_r >= 1.5:
                        cand_sl = effective_entry - (0.5 * risk_pts)
                        if cand_sl < active_sl:
                            active_sl = cand_sl
                            is_be_active = True

                elif trailing_stop_mode == "STEP_10_20":
                    if peak_mfe_r >= 3.0:
                        cand_sl = effective_entry - (2.0 * risk_pts)
                        if cand_sl < active_sl:
                            active_sl = cand_sl
                            is_be_active = True
                    elif peak_mfe_r >= 2.0:
                        cand_sl = effective_entry - (1.0 * risk_pts)
                        if cand_sl < active_sl:
                            active_sl = cand_sl
                            is_be_active = True
                    elif peak_mfe_r >= 1.0:
                        cand_sl = effective_entry - spread
                        if cand_sl < active_sl:
                            active_sl = cand_sl
                            is_be_active = True

                elif trailing_stop_mode == "ATR_TRAIL" and atr_trail_dist > 0:
                    if peak_mfe_r >= 1.5:
                        cand_sl = (l + spread) + atr_trail_dist
                        if cand_sl < active_sl:
                            active_sl = cand_sl
                            is_be_active = True

    return {
        "status": "OPEN_AT_END",
        "realized_r": 0.0,
        "realized_pnl_usd": 0.0,
        "is_realized": False,
        "mfe_r": round(peak_mfe_r, 3),
        "mae_r": round(peak_mae_r, 3),
        "duration_m": len(forward_highs) - fill_idx if fill_idx else 0,
        "notes": "Unclosed after 24h"
    }


# Signal Extractors for the 3 Audited Models

def extract_model3_signals() -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    """Extracts candidate setups for Model 3 (Intermarket SMT Divergence NQ vs SPX/YM)."""
    df_nq_m1, df_nq_m5, _, _ = load_and_resample(str(BASE_DIR / M3_CONFIG["parquet"]), "NQ")
    df_spx_m1, df_spx_m5, _, _ = load_and_resample(str(BASE_DIR / "backtest_results/cache/SPX_M1_2026.parquet"), "SPX")
    df_ym_m1, df_ym_m5, _, _ = load_and_resample(str(BASE_DIR / "backtest_results/cache/YM_M1_2026.parquet"), "YM")

    m1_time_to_idx = {t: idx for idx, t in enumerate(df_nq_m1['timestamp'].values)}
    spx_m5_map = df_spx_m5.set_index('timestamp')
    ym_m5_map = df_ym_m5.set_index('timestamp')

    signals = []
    df_nq_m5['date_utc'] = df_nq_m5['dt'].dt.date
    unique_dates = df_nq_m5['date_utc'].unique()

    for d in unique_dates:
        sess = get_session_times(d)
        lon_open_ts = int(sess["london_open_utc"].timestamp())
        ny_open_ts = int(sess["ny_open_utc"].timestamp())
        nyse_open_ts = int(sess["nyse_open_utc"].timestamp())
        day_start_ts = int(datetime.datetime(d.year, d.month, d.day, 0, 0, tzinfo=TZ_UTC).timestamp())

        nq_m1_day = df_nq_m1[(df_nq_m1['timestamp'] >= day_start_ts) & (df_nq_m1['timestamp'] < day_start_ts + 86400)]
        spx_m1_day = df_spx_m1[(df_spx_m1['timestamp'] >= day_start_ts) & (df_spx_m1['timestamp'] < day_start_ts + 86400)]
        ym_m1_day = df_ym_m1[(df_ym_m1['timestamp'] >= day_start_ts) & (df_ym_m1['timestamp'] < day_start_ts + 86400)]

        if nq_m1_day.empty or spx_m1_day.empty or ym_m1_day.empty:
            continue

        nq_asia = nq_m1_day[(nq_m1_day['timestamp'] >= day_start_ts) & (nq_m1_day['timestamp'] < lon_open_ts)]
        spx_asia = spx_m1_day[(spx_m1_day['timestamp'] >= day_start_ts) & (spx_m1_day['timestamp'] < lon_open_ts)]
        ym_asia = ym_m1_day[(ym_m1_day['timestamp'] >= day_start_ts) & (ym_m1_day['timestamp'] < lon_open_ts)]

        nq_london = nq_m1_day[(nq_m1_day['timestamp'] >= lon_open_ts) & (nq_m1_day['timestamp'] < nyse_open_ts)]
        spx_london = spx_m1_day[(spx_m1_day['timestamp'] >= lon_open_ts) & (spx_m1_day['timestamp'] < nyse_open_ts)]
        ym_london = ym_m1_day[(ym_m1_day['timestamp'] >= lon_open_ts) & (ym_m1_day['timestamp'] < nyse_open_ts)]

        windows = []
        if not nq_asia.empty and not spx_asia.empty and not ym_asia.empty:
            windows.append((
                "London", lon_open_ts, lon_open_ts + 210 * 60,
                nq_asia['high'].max(), nq_asia['low'].min(),
                spx_asia['high'].max(), spx_asia['low'].min(),
                ym_asia['high'].max(), ym_asia['low'].min()
            ))
        if not nq_london.empty and not spx_london.empty and not ym_london.empty:
            windows.append((
                "NYSE_Cash", nyse_open_ts, nyse_open_ts + 210 * 60,
                nq_london['high'].max(), nq_london['low'].min(),
                spx_london['high'].max(), spx_london['low'].min(),
                ym_london['high'].max(), ym_london['low'].min()
            ))

        for sess_name, w_start, w_end, nq_bh, nq_bl, spx_bh, spx_bl, ym_bh, ym_bl in windows:
            nq_m5_window = df_nq_m5[(df_nq_m5['timestamp'] >= w_start) & (df_nq_m5['timestamp'] < w_end)]
            if len(nq_m5_window) < 5:
                continue

            trade_taken = False
            for i in range(len(nq_m5_window) - 4):
                if trade_taken:
                    break

                bar_t = nq_m5_window.iloc[i]
                ts_t = bar_t['timestamp']
                if ts_t not in spx_m5_map.index or ts_t not in ym_m5_map.index:
                    continue

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

                            fvg_vol = bar_fvg.get('tick_volume', 1)
                            fvg_idx_m5 = bar_fvg.name
                            avg_vol = df_nq_m5.loc[max(0, fvg_idx_m5-20):fvg_idx_m5-1, 'tick_volume'].mean() if fvg_idx_m5 >= 20 else fvg_vol

                            signals.append({
                                "model": "MODEL-SMT-CD-03",
                                "symbol": "NQ",
                                "session": sess_name,
                                "date": str(d),
                                "decision": "BUY",
                                "entry": entry,
                                "sl": sl,
                                "risk": risk,
                                "start_m1_idx": start_idx,
                                "signal_bar_time": str(bar_fvg['dt']),
                                "atr_m5": bar_fvg['atr14'],
                                "volume": fvg_vol,
                                "avg_volume": avg_vol,
                                "config": M3_CONFIG
                            })
                            trade_taken = True
                            break

                # Bearish SMT with Synchronized Breakout Veto
                nq_swept_high = (bar_t['high'] > nq_bh)
                spx_swept_high = (spx_bar_t['high'] > spx_bh)
                ym_swept_high = (ym_bar_t['high'] > ym_bh)

                if nq_swept_high and not (spx_swept_high and ym_swept_high) and not trade_taken:
                    sweep_extreme = bar_t['high']
                    for j in range(1, 4):
                        bar_fvg = nq_m5_window.iloc[i + j]
                        bar_prev2 = nq_m5_window.iloc[i + j - 2]
                        disp_candle = bar_fvg['open'] - bar_fvg['close']
                        if (bar_fvg['high'] < bar_prev2['low']) and (disp_candle >= M3_CONFIG["min_disp"]):
                            entry = bar_prev2['low']
                            sl = sweep_extreme + M3_CONFIG["sl_buffer"]
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

                            fvg_vol = bar_fvg.get('tick_volume', 1)
                            fvg_idx_m5 = bar_fvg.name
                            avg_vol = df_nq_m5.loc[max(0, fvg_idx_m5-20):fvg_idx_m5-1, 'tick_volume'].mean() if fvg_idx_m5 >= 20 else fvg_vol

                            signals.append({
                                "model": "MODEL-SMT-CD-03",
                                "symbol": "NQ",
                                "session": sess_name,
                                "date": str(d),
                                "decision": "SELL",
                                "entry": entry,
                                "sl": sl,
                                "risk": risk,
                                "start_m1_idx": start_idx,
                                "signal_bar_time": str(bar_fvg['dt']),
                                "atr_m5": bar_fvg['atr14'],
                                "volume": fvg_vol,
                                "avg_volume": avg_vol,
                                "config": M3_CONFIG
                            })
                            trade_taken = True
                            break

    return signals, df_nq_m1


def extract_model1_signals(symbol: str = "NQ") -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    """Extracts candidate setups for Model 1 (Session Breakout Continuation)."""
    cfg = M1_CONFIGS[symbol]
    df_m1, df_m5, df_h1, df_d1 = load_and_resample(str(BASE_DIR / cfg["parquet"]), symbol)

    m1_time_to_idx = {t: idx for idx, t in enumerate(df_m1['timestamp'].values)}
    signals = []
    df_m5['date_utc'] = df_m5['dt'].dt.date
    unique_dates = df_m5['date_utc'].unique()

    for d in unique_dates:
        sess = get_session_times(d)
        lon_open_ts = int(sess["london_open_utc"].timestamp())
        ny_open_ts = int(sess["ny_open_utc"].timestamp())
        nyse_open_ts = int(sess["nyse_open_utc"].timestamp())
        day_start_ts = int(datetime.datetime(d.year, d.month, d.day, 0, 0, tzinfo=TZ_UTC).timestamp())

        prev_d1 = df_d1[df_d1['timestamp'] < day_start_ts]
        if prev_d1.empty:
            continue
        adr14 = prev_d1['adr14'].iloc[-1]
        if pd.isna(adr14) or adr14 <= 0:
            continue

        m1_day = df_m1[(df_m1['timestamp'] >= day_start_ts) & (df_m1['timestamp'] < day_start_ts + 86400)]
        if m1_day.empty:
            continue

        m1_asia = m1_day[(m1_day['timestamp'] >= day_start_ts) & (m1_day['timestamp'] < lon_open_ts)]
        if m1_asia.empty:
            continue
        asia_high = m1_asia['high'].max()
        asia_low = m1_asia['low'].min()

        windows = []
        if symbol == "NQ":
            m1_nyse_or = m1_day[(m1_day['timestamp'] >= nyse_open_ts) & (m1_day['timestamp'] < nyse_open_ts + 900)]
            if not m1_nyse_or.empty:
                windows.append(("NYSE_Cash_ORB", nyse_open_ts + 900, nyse_open_ts + 150 * 60, m1_nyse_or['high'].max(), m1_nyse_or['low'].min()))
        else:
            windows.append(("London", lon_open_ts, lon_open_ts + 150 * 60, asia_high, asia_low))

        for sess_name, w_start, w_end, bench_high, bench_low in windows:
            m5_window = df_m5[(df_m5['timestamp'] >= w_start) & (df_m5['timestamp'] < w_end)]
            if len(m5_window) < 2:
                continue

            trade_taken = False
            for i in range(len(m5_window) - 1):
                if trade_taken:
                    break

                bar_t = m5_window.iloc[i]
                bar_t_next = m5_window.iloc[i+1]
                t_close_ts = bar_t['timestamp'] + 300

                closed_h1 = df_h1[df_h1['timestamp'] + 3600 <= t_close_ts]
                if len(closed_h1) < 6:
                    continue
                latest_h1 = closed_h1.iloc[-1]
                h1_close = latest_h1['close']
                h1_ema = latest_h1['ema50']
                h1_slope = latest_h1['ema50_slope5']

                m1_up_to_t = m1_day[m1_day['timestamp'] < t_close_ts]
                if m1_up_to_t.empty:
                    continue
                range_consumed = m1_up_to_t['high'].max() - m1_up_to_t['low'].min()
                if (range_consumed / adr14) > 0.70:
                    continue

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
                    if not (h1_close > h1_ema and h1_slope > 0):
                        continue
                    if not (bar_t_next['high'] > bar_t['high']):
                        continue

                    entry = max(bench_high, bar_t['open'])
                    sl = bar_t['low'] - cfg["sl_buffer"]
                    risk = entry - sl
                    if not (cfg["min_risk"] <= risk <= cfg["max_risk"]):
                        continue

                    forward_start_ts = bar_t_next['timestamp'] + 300
                    if forward_start_ts not in m1_time_to_idx:
                        sub = df_m1[df_m1['timestamp'] >= forward_start_ts]
                        if sub.empty:
                            continue
                        start_idx = sub.index[0]
                    else:
                        start_idx = m1_time_to_idx[forward_start_ts]

                    vol = bar_t.get('tick_volume', 1)
                    idx_m5 = bar_t.name
                    avg_vol = df_m5.loc[max(0, idx_m5-20):idx_m5-1, 'tick_volume'].mean() if idx_m5 >= 20 else vol

                    signals.append({
                        "model": "MODEL-ISB-PC-01",
                        "symbol": symbol,
                        "session": sess_name,
                        "date": str(d),
                        "decision": "BUY",
                        "entry": entry,
                        "sl": sl,
                        "risk": risk,
                        "start_m1_idx": start_idx,
                        "signal_bar_time": str(bar_t['dt']),
                        "atr_m5": atr_m5,
                        "volume": vol,
                        "avg_volume": avg_vol,
                        "config": cfg
                    })
                    trade_taken = True

                # Bearish Breakout
                elif (bar_t['close'] <= bench_low - cfg["delta"]) and (lower_wick / candle_range <= 0.25):
                    if not (h1_close < h1_ema and h1_slope < 0):
                        continue
                    if not (bar_t_next['low'] < bar_t['low']):
                        continue

                    entry = min(bench_low, bar_t['open'])
                    sl = bar_t['high'] + cfg["sl_buffer"]
                    risk = sl - entry
                    if not (cfg["min_risk"] <= risk <= cfg["max_risk"]):
                        continue

                    forward_start_ts = bar_t_next['timestamp'] + 300
                    if forward_start_ts not in m1_time_to_idx:
                        sub = df_m1[df_m1['timestamp'] >= forward_start_ts]
                        if sub.empty:
                            continue
                        start_idx = sub.index[0]
                    else:
                        start_idx = m1_time_to_idx[forward_start_ts]

                    vol = bar_t.get('tick_volume', 1)
                    idx_m5 = bar_t.name
                    avg_vol = df_m5.loc[max(0, idx_m5-20):idx_m5-1, 'tick_volume'].mean() if idx_m5 >= 20 else vol

                    signals.append({
                        "model": "MODEL-ISB-PC-01",
                        "symbol": symbol,
                        "session": sess_name,
                        "date": str(d),
                        "decision": "SELL",
                        "entry": entry,
                        "sl": sl,
                        "risk": risk,
                        "start_m1_idx": start_idx,
                        "signal_bar_time": str(bar_t['dt']),
                        "atr_m5": atr_m5,
                        "volume": vol,
                        "avg_volume": avg_vol,
                        "config": cfg
                    })
                    trade_taken = True

    return signals, df_m1


def extract_model2_signals(symbol: str = "XAUUSD_o") -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    """Extracts candidate setups for Model 2 (Statistical Extreme Judas Reversal - Bearish Shorts Only)."""
    cfg = M2_CONFIGS[symbol]
    df_m1, df_m5, df_h1, df_d1 = load_and_resample(str(BASE_DIR / cfg["parquet"]), symbol)

    m1_time_to_idx = {t: idx for idx, t in enumerate(df_m1['timestamp'].values)}
    signals = []
    df_m5['date_utc'] = df_m5['dt'].dt.date
    unique_dates = df_m5['date_utc'].unique()

    for d in unique_dates:
        sess = get_session_times(d)
        lon_open_ts = int(sess["london_open_utc"].timestamp())
        ny_open_ts = int(sess["ny_open_utc"].timestamp())
        day_start_ts = int(datetime.datetime(d.year, d.month, d.day, 0, 0, tzinfo=TZ_UTC).timestamp())

        prev_d1 = df_d1[df_d1['timestamp'] < day_start_ts]
        if prev_d1.empty:
            continue
        adr14 = prev_d1['adr14'].iloc[-1]
        pdh = prev_d1['high'].iloc[-1]
        pdl = prev_d1['low'].iloc[-1]

        m1_day = df_m1[(df_m1['timestamp'] >= day_start_ts) & (df_m1['timestamp'] < day_start_ts + 86400)]
        if m1_day.empty:
            continue

        m1_asia = m1_day[(m1_day['timestamp'] >= day_start_ts) & (m1_day['timestamp'] < lon_open_ts)]
        asia_high = m1_asia['high'].max() if not m1_asia.empty else None

        m1_london = m1_day[(m1_day['timestamp'] >= lon_open_ts) & (m1_day['timestamp'] < ny_open_ts)]
        london_high = m1_london['high'].max() if not m1_london.empty else None

        windows = []
        if asia_high is not None:
            bench_h = max(pdh, asia_high)
            windows.append(("London", lon_open_ts, lon_open_ts + 180 * 60, bench_h))

        if london_high is not None:
            bench_h = max(pdh, london_high)
            windows.append(("NY", ny_open_ts, ny_open_ts + 180 * 60, bench_h))

        for sess_name, w_start, w_end, bench_high in windows:
            m5_window = df_m5[(df_m5['timestamp'] >= w_start) & (df_m5['timestamp'] < w_end)]
            if len(m5_window) < 3:
                continue

            trade_taken = False
            for i in range(len(m5_window) - 1):
                if trade_taken:
                    break

                bar_t = m5_window.iloc[i]
                bar_t_next = m5_window.iloc[i+1]
                atr_m5 = bar_t['atr14']
                candle_range = bar_t['high'] - bar_t['low']
                if candle_range <= 0 or atr_m5 <= 0:
                    continue

                body = abs(bar_t['close'] - bar_t['open'])
                body_ratio = body / candle_range
                upper_wick = bar_t['high'] - max(bar_t['open'], bar_t['close'])
                upper_wick_ratio = upper_wick / candle_range

                dist_from_ema20 = abs(bar_t['close'] - bar_t['ema20'])
                stat_stretch_ok = (dist_from_ema20 >= 1.5 * atr_m5)

                if (bar_t['high'] > bench_high):
                    pen = bar_t['high'] - bench_high
                    if (cfg["min_depth"] <= pen <= cfg["max_depth"]) and (pen <= 1.0 * atr_m5):
                        if (upper_wick_ratio >= 0.40) and (body_ratio <= 0.35) and (bar_t['close'] <= bench_high + cfg["close_tol"]):
                            if stat_stretch_ok:
                                if bar_t_next['close'] < bar_t['low']:
                                    entry = bar_t_next['close']
                                    sl = bar_t['high'] + cfg["sl_buffer"]
                                    risk = sl - entry
                                    if 1.0 <= risk <= 15.0:
                                        forward_start_ts = bar_t_next['timestamp'] + 300
                                        if forward_start_ts not in m1_time_to_idx:
                                            sub = df_m1[df_m1['timestamp'] >= forward_start_ts]
                                            if sub.empty:
                                                continue
                                            start_idx = sub.index[0]
                                        else:
                                            start_idx = m1_time_to_idx[forward_start_ts]

                                        vol = bar_t.get('tick_volume', 1)
                                        idx_m5 = bar_t.name
                                        avg_vol = df_m5.loc[max(0, idx_m5-20):idx_m5-1, 'tick_volume'].mean() if idx_m5 >= 20 else vol

                                        signals.append({
                                            "model": "MODEL-SE-JSR-02",
                                            "symbol": symbol,
                                            "session": sess_name,
                                            "date": str(d),
                                            "decision": "SELL",
                                            "entry": entry,
                                            "sl": sl,
                                            "risk": risk,
                                            "start_m1_idx": start_idx,
                                            "signal_bar_time": str(bar_t['dt']),
                                            "atr_m5": atr_m5,
                                            "volume": vol,
                                            "avg_volume": avg_vol,
                                            "config": cfg
                                        })
                                        trade_taken = True

    return signals, df_m1


# Optimization and Excursion Analysis Functions

def evaluate_be_grid(signals: List[Dict[str, Any]], df_m1: pd.DataFrame, target_rr: float) -> List[Dict[str, Any]]:
    be_candidates = [None, 1.0, 1.2, 1.5, 1.8, 2.0]
    results = []
    for be in be_candidates:
        trades = []
        for s in signals:
            cfg = s["config"]
            res = run_full_excursion_simulation(
                df_m1=df_m1,
                start_m1_idx=s["start_m1_idx"],
                decision=s["decision"],
                entry=s["entry"],
                sl=s["sl"],
                target_rr=target_rr,
                symbol=s["symbol"],
                spread=cfg["spread"],
                slippage=cfg["slippage"],
                commission_per_001_lot=cfg["commission"],
                be_ratchet_rr=be,
                lot=cfg["lot"]
            )
            res["session"] = s["session"]
            trades.append(res)
        m = compute_metrics(trades)
        m["be_ratchet_rr"] = be if be is not None else "None"
        m["target_rr"] = target_rr
        results.append(m)
    return results


def evaluate_trailing_stops(signals: List[Dict[str, Any]], df_m1: pd.DataFrame, target_rr: float) -> List[Dict[str, Any]]:
    modes = [
        ("None (Static)", None, 0.0),
        ("Step Trail A (+1.5R->+0.5R, +2.5R->+1.5R)", "STEP_15_25", 0.0),
        ("Step Trail B (+1.0R->BE, +2.0R->+1.0R)", "STEP_10_20", 0.0),
        ("Dynamic ATR Trail (1.5x M5 ATR behind peak)", "ATR_TRAIL", 1.5)
    ]
    results = []
    for label, mode, atr_mult in modes:
        trades = []
        for s in signals:
            cfg = s["config"]
            atr_dist = s["atr_m5"] * atr_mult if mode == "ATR_TRAIL" else 0.0
            res = run_full_excursion_simulation(
                df_m1=df_m1,
                start_m1_idx=s["start_m1_idx"],
                decision=s["decision"],
                entry=s["entry"],
                sl=s["sl"],
                target_rr=target_rr,
                symbol=s["symbol"],
                spread=cfg["spread"],
                slippage=cfg["slippage"],
                commission_per_001_lot=cfg["commission"],
                be_ratchet_rr=1.8 if mode is None else None,
                trailing_stop_mode=mode,
                atr_trail_dist=atr_dist,
                lot=cfg["lot"]
            )
            res["session"] = s["session"]
            trades.append(res)
        m = compute_metrics(trades)
        m["trailing_mode"] = label
        m["target_rr"] = target_rr
        results.append(m)
    return results


def evaluate_dynamic_session_exits(signals: List[Dict[str, Any]], df_m1: pd.DataFrame, target_rr: float) -> List[Dict[str, Any]]:
    # Dynamic session exit candidates:
    # None (Hold up to 24h)
    # 12:00 UTC (15:30 Tehran) -> London Lunch / Pre-NY Flat
    # 16:30 UTC (20:00 Tehran) -> NY Lunch / Afternoon lull
    # 21:00 UTC (00:30 Tehran) -> Rollover Flat (zero overnight exposure)
    exits = [
        ("Hold up to 24h (No early exit)", None),
        ("Flat at 12:00 UTC (London Lunch / Pre-NY)", 12),
        ("Flat at 16:30 UTC (NY Lunch / Afternoon Lull)", 16),
        ("Flat at 21:00 UTC (Pre-Rollover Protection)", 21)
    ]
    results = []
    for label, exit_hour in exits:
        trades = []
        for s in signals:
            cfg = s["config"]
            res = run_full_excursion_simulation(
                df_m1=df_m1,
                start_m1_idx=s["start_m1_idx"],
                decision=s["decision"],
                entry=s["entry"],
                sl=s["sl"],
                target_rr=target_rr,
                symbol=s["symbol"],
                spread=cfg["spread"],
                slippage=cfg["slippage"],
                commission_per_001_lot=cfg["commission"],
                be_ratchet_rr=1.8,
                session_exit_utc_hour=exit_hour,
                lot=cfg["lot"]
            )
            res["session"] = s["session"]
            trades.append(res)
        m = compute_metrics(trades)
        m["session_exit"] = label
        m["target_rr"] = target_rr
        results.append(m)
    return results


def evaluate_volatility_volume_filters(signals: List[Dict[str, Any]], df_m1: pd.DataFrame, target_rr: float) -> List[Dict[str, Any]]:
    # Baseline vs Volume >= 1.2x 20-bar avg vs ATR >= 50th percentile
    if not signals:
        return []

    atrs = [s["atr_m5"] for s in signals if "atr_m5" in s]
    median_atr = np.median(atrs) if atrs else 0.0

    filter_variants = [
        ("Baseline (Unfiltered)", lambda s: True),
        ("Volume Expansion (Vol >= 1.2x 20-bar SMA)", lambda s: s.get("volume", 0) >= 1.2 * s.get("avg_volume", 1)),
        ("High Volatility Regime (M5 ATR >= Median ATR)", lambda s: s.get("atr_m5", 0) >= median_atr),
        ("Combined (Vol >= 1.1x Avg AND ATR >= Median)", lambda s: s.get("volume", 0) >= 1.1 * s.get("avg_volume", 1) and s.get("atr_m5", 0) >= median_atr)
    ]

    results = []
    for label, filter_fn in filter_variants:
        filtered_signals = [s for s in signals if filter_fn(s)]
        trades = []
        for s in filtered_signals:
            cfg = s["config"]
            res = run_full_excursion_simulation(
                df_m1=df_m1,
                start_m1_idx=s["start_m1_idx"],
                decision=s["decision"],
                entry=s["entry"],
                sl=s["sl"],
                target_rr=target_rr,
                symbol=s["symbol"],
                spread=cfg["spread"],
                slippage=cfg["slippage"],
                commission_per_001_lot=cfg["commission"],
                be_ratchet_rr=1.8,
                lot=cfg["lot"]
            )
            res["session"] = s["session"]
            trades.append(res)
        m = compute_metrics(trades)
        m["filter_regime"] = label
        m["target_rr"] = target_rr
        m["filtered_signals_count"] = len(filtered_signals)
        results.append(m)
    return results


def analyze_excursion_microstructure(signals: List[Dict[str, Any]], df_m1: pd.DataFrame, target_rr: float) -> Dict[str, Any]:
    """Computes comprehensive MFE/MAE distribution metrics across all executed trades."""
    raw_trades = []
    for s in signals:
        cfg = s["config"]
        # Run without BE ratchet to observe pure natural excursions before artificial termination
        res = run_full_excursion_simulation(
            df_m1=df_m1,
            start_m1_idx=s["start_m1_idx"],
            decision=s["decision"],
            entry=s["entry"],
            sl=s["sl"],
            target_rr=10.0,  # wide target to observe full potential MFE
            symbol=s["symbol"],
            spread=cfg["spread"],
            slippage=cfg["slippage"],
            commission_per_001_lot=cfg["commission"],
            be_ratchet_rr=None,
            lot=cfg["lot"]
        )
        res["signal_time"] = s.get("signal_bar_time")
        res["direction"] = s["decision"]
        res["risk"] = s["risk"]
        raw_trades.append(res)

    filled_trades = [t for t in raw_trades if t["status"] != "EXPIRED"]
    if not filled_trades:
        return {"filled_count": 0}

    mfes = [t["mfe_r"] for t in filled_trades]
    maes = [t["mae_r"] for t in filled_trades]
    durations = [t["duration_m"] for t in filled_trades]

    # Winners at target_rr vs Losers
    winners = [t for t in filled_trades if t["mfe_r"] >= target_rr]
    losers = [t for t in filled_trades if t["mfe_r"] < target_rr]

    # Excursion milestones
    mfe_ge_10 = sum(1 for m in mfes if m >= 1.0) / len(mfes) * 100.0
    mfe_ge_15 = sum(1 for m in mfes if m >= 1.5) / len(mfes) * 100.0
    mfe_ge_20 = sum(1 for m in mfes if m >= 2.0) / len(mfes) * 100.0
    mfe_ge_25 = sum(1 for m in mfes if m >= 2.5) / len(mfes) * 100.0
    mfe_ge_30 = sum(1 for m in mfes if m >= 3.0) / len(mfes) * 100.0
    mfe_ge_35 = sum(1 for m in mfes if m >= 3.5) / len(mfes) * 100.0
    mfe_ge_40 = sum(1 for m in mfes if m >= 4.0) / len(mfes) * 100.0

    # Avoidable losses: losers that reached >= 1.0R, >= 1.2R, >= 1.5R before reversing
    losers_mfe_ge_10 = sum(1 for t in losers if t["mfe_r"] >= 1.0)
    losers_mfe_ge_12 = sum(1 for t in losers if t["mfe_r"] >= 1.2)
    losers_mfe_ge_15 = sum(1 for t in losers if t["mfe_r"] >= 1.5)
    losers_mfe_ge_18 = sum(1 for t in losers if t["mfe_r"] >= 1.8)

    # MAE of winners (heat taken before reaching target)
    winner_maes = [t["mae_r"] for t in winners]

    return {
        "filled_trades_count": len(filled_trades),
        "median_mfe_r": round(float(np.median(mfes)), 2),
        "mean_mfe_r": round(float(np.mean(mfes)), 2),
        "p75_mfe_r": round(float(np.percentile(mfes, 75)), 2),
        "p90_mfe_r": round(float(np.percentile(mfes, 90)), 2),
        "max_mfe_r": round(float(np.max(mfes)), 2),
        "pct_reaching_1_0R": round(mfe_ge_10, 1),
        "pct_reaching_1_5R": round(mfe_ge_15, 1),
        "pct_reaching_2_0R": round(mfe_ge_20, 1),
        "pct_reaching_2_5R": round(mfe_ge_25, 1),
        "pct_reaching_3_0R": round(mfe_ge_30, 1),
        "pct_reaching_3_5R": round(mfe_ge_35, 1),
        "pct_reaching_4_0R": round(mfe_ge_40, 1),
        "total_losers": len(losers),
        "losers_with_mfe_ge_10R": losers_mfe_ge_10,
        "losers_with_mfe_ge_12R": losers_mfe_ge_12,
        "losers_with_mfe_ge_15R": losers_mfe_ge_15,
        "losers_with_mfe_ge_18R": losers_mfe_ge_18,
        "total_winners": len(winners),
        "winner_median_mae_r": round(float(np.median(winner_maes)), 2) if winner_maes else 0.0,
        "winner_p75_mae_r": round(float(np.percentile(winner_maes, 75)), 2) if winner_maes else 0.0,
        "winner_p90_mae_r": round(float(np.percentile(winner_maes, 90)), 2) if winner_maes else 0.0,
        "winner_max_mae_r": round(float(np.max(winner_maes)), 2) if winner_maes else 0.0,
        "median_trade_duration_min": int(np.median(durations)) if durations else 0,
        "mean_trade_duration_min": int(np.mean(durations)) if durations else 0
    }


def main():
    print("=" * 80)
    print("TRADINGGUARD SENIOR QUANTITATIVE MICROSTRUCTURE & TRADE MANAGEMENT OPTIMIZATION")
    print("=" * 80)

    # 1. MODEL-SMT-CD-03 (NQ vs SPX/YM)
    print("\n>>> Extracting signals for MODEL-SMT-CD-03 (NQ Intermarket SMT Divergence)...")
    m3_signals, df_nq_m1 = extract_model3_signals()
    print(f"Total Model 3 candidate signals found: {len(m3_signals)}")

    print("\n--- Model 3: Excursion Microstructure Analysis (Pure Run without artificial exit) ---")
    m3_excursion = analyze_excursion_microstructure(m3_signals, df_nq_m1, target_rr=2.5)
    for k, v in m3_excursion.items():
        print(f"  {k}: {v}")

    print("\n--- Model 3: Breakeven Ratchet Threshold Optimization (Target 2.5R) ---")
    m3_be_results = evaluate_be_grid(m3_signals, df_nq_m1, target_rr=2.5)
    for r in m3_be_results:
        print(f"  BE Ratchet: {r['be_ratchet_rr']:<6} | WR: {r['win_rate_pct']:>5.2f}% | Wins: {r['wins']} Losses: {r['losses']} BE: {r['breakevens']} | Net R: {r['net_r']:>+6.2f}R | Net USD: ${r['realized_net_usd']:>+6.2f} | PF: {r['profit_factor']:>5.2f} | EV: {r['ev_r']:>+5.3f}R | Max DD: {r['max_drawdown_r']:>4.2f}R | t-stat: {r['t_stat']:>+5.2f}")

    print("\n--- Model 3: Trailing Stop Mechanics Evaluation (Target 3.5R) ---")
    m3_trail_results = evaluate_trailing_stops(m3_signals, df_nq_m1, target_rr=3.5)
    for r in m3_trail_results:
        print(f"  Trailing Mode: {r['trailing_mode']:<45} | Net R: {r['net_r']:>+6.2f}R | PF: {r['profit_factor']:>5.2f} | WR: {r['win_rate_pct']:>5.2f}% | Max DD: {r['max_drawdown_r']:>4.2f}R")

    print("\n--- Model 3: Dynamic Session Exit Evaluation (Target 2.5R) ---")
    m3_sess_results = evaluate_dynamic_session_exits(m3_signals, df_nq_m1, target_rr=2.5)
    for r in m3_sess_results:
        print(f"  Session Exit: {r['session_exit']:<48} | Net R: {r['net_r']:>+6.2f}R | PF: {r['profit_factor']:>5.2f} | WR: {r['win_rate_pct']:>5.2f}% | Max DD: {r['max_drawdown_r']:>4.2f}R")

    print("\n--- Model 3: Volatility & Volume Filter Evaluation (Target 2.5R) ---")
    m3_vol_results = evaluate_volatility_volume_filters(m3_signals, df_nq_m1, target_rr=2.5)
    for r in m3_vol_results:
        print(f"  Filter: {r['filter_regime']:<48} | N: {r['closed_trades']} | Net R: {r['net_r']:>+6.2f}R | PF: {r['profit_factor']:>5.2f} | WR: {r['win_rate_pct']:>5.2f}% | Max DD: {r['max_drawdown_r']:>4.2f}R")

    # 2. MODEL-ISB-PC-01 (NQ NYSE Cash ORB)
    print("\n" + "=" * 80)
    print(">>> Extracting signals for MODEL-ISB-PC-01 (NQ NYSE Cash Open ORB)...")
    m1_signals, df_m1_nq = extract_model1_signals(symbol="NQ")
    print(f"Total Model 1 (NQ ORB) candidate signals found: {len(m1_signals)}")

    print("\n--- Model 1: Excursion Microstructure Analysis ---")
    m1_excursion = analyze_excursion_microstructure(m1_signals, df_m1_nq, target_rr=3.0)
    for k, v in m1_excursion.items():
        print(f"  {k}: {v}")

    print("\n--- Model 1: Breakeven Ratchet Threshold Optimization (Target 3.0R) ---")
    m1_be_results = evaluate_be_grid(m1_signals, df_m1_nq, target_rr=3.0)
    for r in m1_be_results:
        print(f"  BE Ratchet: {r['be_ratchet_rr']:<6} | WR: {r['win_rate_pct']:>5.2f}% | Wins: {r['wins']} Losses: {r['losses']} BE: {r['breakevens']} | Net R: {r['net_r']:>+6.2f}R | Net USD: ${r['realized_net_usd']:>+6.2f} | PF: {r['profit_factor']:>5.2f} | EV: {r['ev_r']:>+5.3f}R | Max DD: {r['max_drawdown_r']:>4.2f}R | t-stat: {r['t_stat']:>+5.2f}")

    print("\n--- Model 1: Trailing Stop Mechanics Evaluation (Target 3.5R) ---")
    m1_trail_results = evaluate_trailing_stops(m1_signals, df_m1_nq, target_rr=3.5)
    for r in m1_trail_results:
        print(f"  Trailing Mode: {r['trailing_mode']:<45} | Net R: {r['net_r']:>+6.2f}R | PF: {r['profit_factor']:>5.2f} | WR: {r['win_rate_pct']:>5.2f}% | Max DD: {r['max_drawdown_r']:>4.2f}R")

    print("\n--- Model 1: Dynamic Session Exit Evaluation (Target 3.0R) ---")
    m1_sess_results = evaluate_dynamic_session_exits(m1_signals, df_m1_nq, target_rr=3.0)
    for r in m1_sess_results:
        print(f"  Session Exit: {r['session_exit']:<48} | Net R: {r['net_r']:>+6.2f}R | PF: {r['profit_factor']:>5.2f} | WR: {r['win_rate_pct']:>5.2f}% | Max DD: {r['max_drawdown_r']:>4.2f}R")

    print("\n--- Model 1: Volatility & Volume Filter Evaluation (Target 3.0R) ---")
    m1_vol_results = evaluate_volatility_volume_filters(m1_signals, df_m1_nq, target_rr=3.0)
    for r in m1_vol_results:
        print(f"  Filter: {r['filter_regime']:<48} | N: {r['closed_trades']} | Net R: {r['net_r']:>+6.2f}R | PF: {r['profit_factor']:>5.2f} | WR: {r['win_rate_pct']:>5.2f}% | Max DD: {r['max_drawdown_r']:>4.2f}R")

    # 3. MODEL-SE-JSR-02 (Gold Bearish Judas Skew)
    print("\n" + "=" * 80)
    print(">>> Extracting signals for MODEL-SE-JSR-02 (Gold Bearish Judas Skew)...")
    m2_signals, df_xau_m1 = extract_model2_signals(symbol="XAUUSD_o")
    print(f"Total Model 2 (Gold Shorts) candidate signals found: {len(m2_signals)}")

    print("\n--- Model 2: Excursion Microstructure Analysis ---")
    m2_excursion = analyze_excursion_microstructure(m2_signals, df_xau_m1, target_rr=2.0)
    for k, v in m2_excursion.items():
        print(f"  {k}: {v}")

    print("\n--- Model 2: Breakeven Ratchet Threshold Optimization (Target 2.0R) ---")
    m2_be_results = evaluate_be_grid(m2_signals, df_xau_m1, target_rr=2.0)
    for r in m2_be_results:
        print(f"  BE Ratchet: {r['be_ratchet_rr']:<6} | WR: {r['win_rate_pct']:>5.2f}% | Wins: {r['wins']} Losses: {r['losses']} BE: {r['breakevens']} | Net R: {r['net_r']:>+6.2f}R | Net USD: ${r['realized_net_usd']:>+6.2f} | PF: {r['profit_factor']:>5.2f} | EV: {r['ev_r']:>+5.3f}R | Max DD: {r['max_drawdown_r']:>4.2f}R | t-stat: {r['t_stat']:>+5.2f}")

    print("\n--- Model 2: Trailing Stop Mechanics Evaluation (Target 2.5R) ---")
    m2_trail_results = evaluate_trailing_stops(m2_signals, df_xau_m1, target_rr=2.5)
    for r in m2_trail_results:
        print(f"  Trailing Mode: {r['trailing_mode']:<45} | Net R: {r['net_r']:>+6.2f}R | PF: {r['profit_factor']:>5.2f} | WR: {r['win_rate_pct']:>5.2f}% | Max DD: {r['max_drawdown_r']:>4.2f}R")

    print("\n--- Model 2: Dynamic Session Exit Evaluation (Target 2.0R) ---")
    m2_sess_results = evaluate_dynamic_session_exits(m2_signals, df_xau_m1, target_rr=2.0)
    for r in m2_sess_results:
        print(f"  Session Exit: {r['session_exit']:<48} | Net R: {r['net_r']:>+6.2f}R | PF: {r['profit_factor']:>5.2f} | WR: {r['win_rate_pct']:>5.2f}% | Max DD: {r['max_drawdown_r']:>4.2f}R")

    # Consolidate and export optimization findings
    import json
    summary_data = {
        "model3_smt": {
            "excursion": m3_excursion,
            "be_grid": m3_be_results,
            "trailing_stops": m3_trail_results,
            "session_exits": m3_sess_results,
            "volatility_filters": m3_vol_results
        },
        "model1_breakout": {
            "excursion": m1_excursion,
            "be_grid": m1_be_results,
            "trailing_stops": m1_trail_results,
            "session_exits": m1_sess_results,
            "volatility_filters": m1_vol_results
        },
        "model2_judas": {
            "excursion": m2_excursion,
            "be_grid": m2_be_results,
            "trailing_stops": m2_trail_results,
            "session_exits": m2_sess_results
        }
    }

    out_file = BASE_DIR / "scratch" / "microstructure_optimization_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)
    print(f"\n[DONE] Microstructure optimization complete! Results saved to {out_file}")


if __name__ == "__main__":
    main()
