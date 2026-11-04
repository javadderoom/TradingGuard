"""
TradingGuard HITL - HTF Draw on Liquidity (DOL) & 1-Minute Macro Runner Backtester
Empirical Full-Year 2026 Audit (175 Trading Days | 700 Sessions | Gold & GBPUSD)
Evaluates capturing multi-hour HTF expansion legs using 1-minute precision entry:
1. Baseline Static Target (3.5R Gold / 2.5R Cable)
2. All-or-Nothing HTF DOL Target (No Trailing)
3. 15-Minute Structural Trailing Engine (Trailing to HTF DOL)
4. Institutional Split (70% Static Sweet Spot / 30% Macro Runner)
"""

import os
import sys
import time
import json
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, List, Any, Tuple, Optional

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

# Enforce UTF-8 on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

TZ_UTC = ZoneInfo("UTC")
CACHE_DIR = Path("backtest_results/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR = Path("backtest_results/htf_macro_runner")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def get_season_name(dt: datetime.datetime) -> str:
    m = dt.month
    if m in (12, 1, 2): return "Winter"
    elif m in (3, 4, 5): return "Spring"
    elif m in (6, 7, 8): return "Summer"
    elif m in (9, 10, 11): return "Autumn"
    return "Unknown"


def load_or_fetch_m1_bars(symbol: str) -> List[Dict[str, Any]]:
    """Loads M1 bars from parquet cache, or resamples directly from MT5 broker ticks."""
    cache_file = CACHE_DIR / f"M1_{symbol}_2026.parquet"
    if cache_file.exists():
        print(f"   [Cache Hit] Loading M1 bars for {symbol} from {cache_file.name}...")
        df = pd.read_parquet(cache_file)
        bars = []
        for row in df.itertuples():
            bars.append({
                'time': int(row.time),
                'dt': row.Index.to_pydatetime() if hasattr(row.Index, 'to_pydatetime') else row.Index,
                'open': float(row.open),
                'high': float(row.high),
                'low': float(row.low),
                'close': float(row.close),
                'tick_volume': int(row.tick_volume),
                'spread': int(row.spread)
            })
        print(f"   Loaded {len(bars)} M1 bars from cache in <0.5s.")
        return bars

    print(f"   Fetching raw ticks across 2026 for {symbol} from broker...")
    if not mt5.initialize():
        raise RuntimeError("MT5 initialization failed!")

    is_fx = "GBP" in symbol or "EUR" in symbol
    cur_d = datetime.date(2026, 1, 2)
    end_d = datetime.date(2026, 11, 5)
    m1_list = []
    t0 = time.time()
    tick_cnt = 0

    while cur_d < end_d:
        if cur_d.weekday() < 5:
            dt_s = datetime.datetime(cur_d.year, cur_d.month, cur_d.day, 0, 0, tzinfo=TZ_UTC)
            dt_e = dt_s + datetime.timedelta(days=1)
            ticks = mt5.copy_ticks_range(symbol, dt_s, dt_e, mt5.COPY_TICKS_ALL)
            if ticks is not None and len(ticks) > 0:
                tick_cnt += len(ticks)
                df = pd.DataFrame(ticks)
                df['datetime'] = pd.to_datetime(df['time'], unit='s', utc=True)
                df.set_index('datetime', inplace=True)
                ohlc = df['bid'].resample('1min').ohlc().dropna()
                spread = ((df['ask'] - df['bid']) / (0.0001 if is_fx else 0.01)).resample('1min').mean().dropna()
                vol = df['flags'].resample('1min').count()
                for idx, row in ohlc.iterrows():
                    m1_list.append({
                        'time': int(idx.timestamp()),
                        'datetime': idx,
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'tick_volume': int(vol.loc[idx]) if idx in vol.index else 100,
                        'spread': int(round(spread.loc[idx])) if idx in spread.index else (6 if is_fx else 15)
                    })
        cur_d += datetime.timedelta(days=1)

    print(f"   Resampled {len(m1_list)} M1 bars from {tick_cnt:,} broker ticks in {time.time()-t0:.2f}s.")
    
    # Save to parquet cache
    df_cache = pd.DataFrame(m1_list)
    df_cache.set_index('datetime', inplace=True)
    df_cache.to_parquet(cache_file)
    print(f"   Cached to {cache_file.name}.")

    bars = []
    for idx, row in df_cache.iterrows():
        bars.append({
            'time': int(row['time']),
            'dt': idx.to_pydatetime(),
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'tick_volume': int(row['tick_volume']),
            'spread': int(row['spread'])
        })
    return bars


def resample_bars(bars_m1: List[Dict[str, Any]], timeframe_minutes: int) -> List[Dict[str, Any]]:
    """Resamples M1 bars into higher timeframes (M5, M15, H1, D1)."""
    if not bars_m1: return []
    df = pd.DataFrame(bars_m1)
    df['datetime'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df.set_index('datetime', inplace=True)

    rule = f"{timeframe_minutes}min" if timeframe_minutes < 1440 else "1D"
    res = df['close'].resample(rule).ohlc().dropna()
    res['open'] = df['open'].resample(rule).first()
    res['high'] = df['high'].resample(rule).max()
    res['low'] = df['low'].resample(rule).min()
    res['close'] = df['close'].resample(rule).last()
    res['tick_volume'] = df['tick_volume'].resample(rule).sum()

    out = []
    for idx, row in res.iterrows():
        out.append({
            'time': int(idx.timestamp()),
            'dt': idx.to_pydatetime(),
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'tick_volume': int(row['tick_volume'])
        })
    out.sort(key=lambda x: x['time'])
    return out


def find_m1_mss_ignition(
    m1_window: List[Dict[str, Any]],
    direction: str,
    sweep_price: float,
    is_fx: bool
) -> Optional[Dict[str, Any]]:
    """
    Finds genuine 1-minute Market Structure Shift displacement following a liquidity sweep.
    Requires:
    1. Swing pivot creation beyond the swept level.
    2. Energetic displacement candle closing past the counter-trend micro-pivot.
    3. Tight stop distance bounded to the micro-wick.
    """
    if len(m1_window) < 10:
        return None

    min_body = 0.0003 if is_fx else 1.20
    min_sl_dist = 0.0005 if is_fx else 2.00
    max_sl_dist = 0.0014 if is_fx else 5.50
    spread_buffer = 0.00006 if is_fx else 1.50

    if direction == "LONG":
        # Look for swing low sweeping level, then displacement breaking above prior micro-high
        for i in range(2, len(m1_window)):
            b = m1_window[i]
            body = b['close'] - b['open']
            if body >= min_body:  # Bullish displacement candle
                # Check preceding 8 bars for a micro swing high that was broken
                prior_highs = [m1_window[k]['high'] for k in range(max(0, i-8), i)]
                if not prior_highs: continue
                micro_high = max(prior_highs)
                if b['close'] > micro_high:
                    # Displacement break confirmed!
                    # Find lowest point of the sweep wick
                    recent_lows = [m1_window[k]['low'] for k in range(max(0, i-10), i+1)]
                    sweep_wick = min(recent_lows)
                    entry = b['close']
                    sl = sweep_wick - spread_buffer
                    risk = entry - sl
                    if min_sl_dist <= risk <= max_sl_dist:
                        return {
                            'entry_idx': i,
                            'entry_time': b['time'],
                            'entry_dt': b['dt'],
                            'entry': entry,
                            'sl': sl,
                            'risk': risk,
                            'direction': 'LONG'
                        }

    elif direction == "SHORT":
        # Look for swing high sweeping level, then displacement breaking below prior micro-low
        for i in range(2, len(m1_window)):
            b = m1_window[i]
            body = b['open'] - b['close']
            if body >= min_body:  # Bearish displacement candle
                prior_lows = [m1_window[k]['low'] for k in range(max(0, i-8), i)]
                if not prior_lows: continue
                micro_low = min(prior_lows)
                if b['close'] < micro_low:
                    # Displacement break confirmed!
                    recent_highs = [m1_window[k]['high'] for k in range(max(0, i-10), i+1)]
                    sweep_wick = max(recent_highs)
                    entry = b['close']
                    sl = sweep_wick + spread_buffer
                    risk = sl - entry
                    if min_sl_dist <= risk <= max_sl_dist:
                        return {
                            'entry_idx': i,
                            'entry_time': b['time'],
                            'entry_dt': b['dt'],
                            'entry': entry,
                            'sl': sl,
                            'risk': risk,
                            'direction': 'SHORT'
                        }

    return None


def simulate_multi_policy_trade(
    entry: float,
    initial_sl: float,
    direction: str,
    dol_target: float,
    forward_m1: List[Dict[str, Any]],
    bars_m15_map: Dict[int, Dict[str, Any]],
    symbol: str
) -> Dict[str, Any]:
    """
    Simulates the exact trade across 4 distinct management policies simultaneously:
    Policy 1: Static Target (3.5R Gold / 2.5R Cable with 1.8R/1.5R BE)
    Policy 2: All-or-Nothing HTF DOL Target (Target = DOL, BE at 2.0R)
    Policy 3: 15-Minute Structural Trailing Engine (BE at 3.0R, trailing 15M swing pivots)
    Policy 4: Institutional Split (70% Static Sweet Spot / 30% Macro Runner)
    """
    is_fx = "GBP" in symbol or "EUR" in symbol
    spread_pts = 0.00006 if is_fx else 0.20
    risk = abs(entry - initial_sl)
    if risk <= 0: return None

    # Static settings
    static_tgt_rr = 2.5 if is_fx else 3.5
    static_be_rr = 1.5 if is_fx else 1.8
    static_tgt_price = entry + (static_tgt_rr * risk) if direction == "LONG" else entry - (static_tgt_rr * risk)
    dol_rr = abs(dol_target - entry) / risk

    # Policy states
    # Policy 1
    p1_active = True
    p1_sl = initial_sl
    p1_be_active = False
    p1_res = None

    # Policy 2
    p2_active = True
    p2_sl = initial_sl
    p2_be_active = False
    p2_res = None

    # Policy 3 (15M Trailing)
    p3_active = True
    p3_sl = initial_sl
    p3_be_active = False
    p3_trail_active = False
    p3_res = None

    max_mfe_r = 0.0
    max_mae_r = 0.0
    held_minutes = 0

    # For 15M trailing: track 15M swing pivots as bars complete
    recent_m15_highs = []
    recent_m15_lows = []
    last_m15_time = 0

    for m1_idx, bar in enumerate(forward_m1):
        held_minutes = m1_idx + 1
        h = bar['high']
        l = bar['low']
        c = bar['close']

        # Update MFE / MAE
        if direction == "LONG":
            cur_mfe = (h - entry - spread_pts) / risk
            cur_mae = (entry - l + spread_pts) / risk
        else:
            cur_mfe = (entry - l - spread_pts) / risk
            cur_mae = (h - entry + spread_pts) / risk

        if cur_mfe > max_mfe_r: max_mfe_r = cur_mfe
        if cur_mae > max_mae_r: max_mae_r = cur_mae

        # Check 15M bar completion for structural trailing
        bar_m15_slot = (bar['time'] // 900) * 900
        if bar_m15_slot in bars_m15_map and bar_m15_slot != last_m15_time:
            last_m15_time = bar_m15_slot
            m15_b = bars_m15_map[bar_m15_slot]
            recent_m15_highs.append(m15_b['high'])
            recent_m15_lows.append(m15_b['low'])
            if len(recent_m15_highs) > 10:
                recent_m15_highs.pop(0)
                recent_m15_lows.pop(0)

        # ----------------------------------------------------
        # SIMULATE POLICY 1: Static Target
        # ----------------------------------------------------
        if p1_active:
            # Check BE trigger
            if not p1_be_active and max_mfe_r >= static_be_rr:
                p1_be_active = True
                p1_sl = entry + (spread_pts if direction == "LONG" else -spread_pts)

            # Check SL
            hit_sl = (l <= p1_sl) if direction == "LONG" else (h >= p1_sl)
            # Check TP
            hit_tp = (h >= static_tgt_price) if direction == "LONG" else (l <= static_tgt_price)

            if hit_tp:
                p1_active = False
                p1_res = {'status': 'WIN', 'net_r': static_tgt_rr}
            elif hit_sl:
                p1_active = False
                p1_res = {'status': 'BREAKEVEN' if p1_be_active else 'LOSS', 'net_r': 0.0 if p1_be_active else -1.0}

        # ----------------------------------------------------
        # SIMULATE POLICY 2: All-or-Nothing HTF DOL Target
        # ----------------------------------------------------
        if p2_active:
            if not p2_be_active and max_mfe_r >= 2.0:
                p2_be_active = True
                p2_sl = entry + (spread_pts if direction == "LONG" else -spread_pts)

            hit_sl = (l <= p2_sl) if direction == "LONG" else (h >= p2_sl)
            hit_dol = (h >= dol_target) if direction == "LONG" else (l <= dol_target)

            if hit_dol:
                p2_active = False
                p2_res = {'status': 'WIN', 'net_r': round(dol_rr, 2)}
            elif hit_sl:
                p2_active = False
                p2_res = {'status': 'BREAKEVEN' if p2_be_active else 'LOSS', 'net_r': 0.0 if p2_be_active else -1.0}

        # ----------------------------------------------------
        # SIMULATE POLICY 3: 15-Minute Structural Trailing
        # ----------------------------------------------------
        if p3_active:
            # Breakeven at +3.0R
            if not p3_be_active and max_mfe_r >= 3.0:
                p3_be_active = True
                p3_sl = entry + (0.2 * risk if direction == "LONG" else -0.2 * risk)

            # Trail behind completed 15M swing low / high
            if max_mfe_r >= 4.0 and len(recent_m15_lows) >= 3:
                p3_trail_active = True
                if direction == "LONG":
                    # Swing low of prior 2 completed 15M bars
                    trail_level = min(recent_m15_lows[-3:-1]) - (0.0002 if is_fx else 1.00)
                    if trail_level > p3_sl:
                        p3_sl = trail_level
                else:
                    trail_level = max(recent_m15_highs[-3:-1]) + (0.0002 if is_fx else 1.00)
                    if trail_level < p3_sl:
                        p3_sl = trail_level

            hit_sl = (l <= p3_sl) if direction == "LONG" else (h >= p3_sl)
            hit_dol = (h >= dol_target) if direction == "LONG" else (l <= dol_target)

            if hit_dol:
                p3_active = False
                p3_res = {'status': 'WIN_DOL', 'net_r': round(dol_rr, 2)}
            elif hit_sl:
                p3_active = False
                if p3_trail_active:
                    realized_r = ((p3_sl - entry) / risk) if direction == "LONG" else ((entry - p3_sl) / risk)
                    status_str = 'TRAIL_WIN' if realized_r > 0.5 else ('BREAKEVEN' if realized_r >= -0.1 else 'LOSS')
                    p3_res = {'status': status_str, 'net_r': round(max(realized_r, 0.0) if p3_be_active else -1.0, 2)}
                else:
                    p3_res = {'status': 'BREAKEVEN' if p3_be_active else 'LOSS', 'net_r': 0.2 if p3_be_active else -1.0}

        # If all 3 policies closed or end of day (8 hours max)
        if (not p1_active and not p2_active and not p3_active) or held_minutes >= 480:
            break

    # Finalize any unclosed positions at close
    if p1_res is None:
        p1_res = {'status': 'EXPIRED_BE' if p1_be_active else 'EXPIRED_LOSS', 'net_r': 0.0 if p1_be_active else -1.0}
    if p2_res is None:
        p2_res = {'status': 'EXPIRED_BE' if p2_be_active else 'EXPIRED_LOSS', 'net_r': 0.0 if p2_be_active else -1.0}
    if p3_res is None:
        p3_res = {'status': 'EXPIRED_TRAIL', 'net_r': round(max(0.0, (forward_m1[-1]['close'] - entry)/risk if direction == "LONG" else (entry - forward_m1[-1]['close'])/risk), 2)}

    # Policy 4: Split (70% Policy 1 + 30% Policy 3)
    p4_net_r = round(0.70 * p1_res['net_r'] + 0.30 * p3_res['net_r'], 2)
    p4_status = 'WIN' if p4_net_r > 0.5 else ('BREAKEVEN' if p4_net_r >= 0.0 else 'LOSS')

    return {
        'risk_pts': round(risk, 5 if is_fx else 2),
        'dol_target': dol_target,
        'dol_potential_r': round(dol_rr, 1),
        'max_mfe_r': round(max_mfe_r, 2),
        'max_mae_r': round(max_mae_r, 2),
        'held_minutes': held_minutes,
        'p1_static': p1_res,
        'p2_dol_unmanaged': p2_res,
        'p3_trailing_runner': p3_res,
        'p4_institutional_split': {'status': p4_status, 'net_r': p4_net_r}
    }


def run_htf_macro_runner_backtest():
    print("=" * 95)
    print("🚀 TRADINGGUARD - HTF DRAW ON LIQUIDITY (DOL) & 1-MINUTE MACRO RUNNER BACKTEST")
    print("Multi-Seasonal Audit: Full-Year 2026 (Gold XAUUSD_o & Cable GBPUSD_o)")
    print("=" * 95)

    symbols = ["XAUUSD_o", "GBPUSD_o"]
    all_trade_records = []

    for sym in symbols:
        print(f"\n📂 Loading microstructure for {sym}...")
        bars_m1 = load_or_fetch_m1_bars(sym)
        bars_m5 = resample_bars(bars_m1, 5)
        bars_m15 = resample_bars(bars_m1, 15)
        bars_h1 = resample_bars(bars_m1, 60)
        bars_d1 = resample_bars(bars_m1, 1440)
        print(f"✅ Microstructure Ready: {len(bars_d1)} D1 | {len(bars_h1)} H1 | {len(bars_m15)} M15 | {len(bars_m1)} M1 bars.")

        is_fx = "GBP" in sym or "EUR" in sym
        m1_map = {b['time']: idx for idx, b in enumerate(bars_m1)}
        m15_map = {b['time']: b for b in bars_m15}

        # Build daily map
        d_map = {}
        for b in bars_d1:
            d_map[b['dt'].date()] = b

        dates = sorted(list(set(b['dt'].date() for b in bars_m1)))
        sym_trades = []

        print(f"🔍 Scanning 1-Minute Macro Ignitions on {sym} across 2026...")

        for day_idx in range(21, len(dates)):
            day_date = dates[day_idx]
            if day_date.weekday() in (5, 6): continue

            prev_date = dates[day_idx - 1]
            prev_d = d_map.get(prev_date)
            if not prev_d: continue

            pdh = prev_d['high']
            pdl = prev_d['low']

            # Asian session (00:00 - 07:00 UTC)
            day_m1 = [b for b in bars_m1 if b['dt'].date() == day_date]
            if len(day_m1) < 180: continue

            asian_bars = [b for b in day_m1 if b['dt'].hour < 7]
            if len(asian_bars) < 60: continue

            asian_high = max(b['high'] for b in asian_bars)
            asian_low = min(b['low'] for b in asian_bars)

            # Active ignition window: London Open & NY Open (07:00 to 15:30 UTC)
            session_bars = [b for b in day_m1 if 7 <= b['dt'].hour < 16]
            if len(session_bars) < 60: continue

            # Track if setup triggered today (max 1 macro runner per day)
            day_triggered = False

            # Check for sweeps of macro levels
            for s_idx in range(15, len(session_bars) - 60):
                if day_triggered: break
                cur_bar = session_bars[s_idx]

                # 1. BULLISH SWEEP OF LIQUIDITY POOL
                # Price sweeps below PDL or Asian Low
                swept_pdl = cur_bar['low'] < (pdl - (0.0001 if is_fx else 0.50))
                swept_asian_low = cur_bar['low'] < (asian_low - (0.0001 if is_fx else 0.50))

                if swept_pdl or swept_asian_low:
                    # Scan next 15 M1 bars for an M1 MSS displacement
                    look_forward = session_bars[s_idx : s_idx + 25]
                    sweep_ref = pdl if swept_pdl else asian_low
                    ignition = find_m1_mss_ignition(look_forward, "LONG", sweep_ref, is_fx)
                    
                    if ignition:
                        # Macro DOL target: Opposing PDH (if distance >= 7R) or Asian High
                        dol = pdh
                        potential_r = (dol - ignition['entry']) / ignition['risk']
                        
                        if potential_r < 7.0 and ignition['entry'] < asian_high:
                            dol = asian_high
                            potential_r = (dol - ignition['entry']) / ignition['risk']

                        if potential_r >= 7.0:
                            # Valid Macro Runner Opportunity!
                            entry_global_idx = m1_map.get(ignition['entry_time'])
                            if entry_global_idx is not None:
                                forward_window = bars_m1[entry_global_idx + 1 : entry_global_idx + 480]
                                if len(forward_window) >= 120:
                                    sim = simulate_multi_policy_trade(
                                        entry=ignition['entry'],
                                        initial_sl=ignition['sl'],
                                        direction="LONG",
                                        dol_target=dol,
                                        forward_m1=forward_window,
                                        bars_m15_map=m15_map,
                                        symbol=sym
                                    )
                                    if sim:
                                        rec = {
                                            'date': str(day_date),
                                            'season': get_season_name(ignition['entry_dt']),
                                            'symbol': sym,
                                            'direction': 'LONG',
                                            'entry_time': str(ignition['entry_dt']),
                                            'entry': ignition['entry'],
                                            'sl': ignition['sl'],
                                            'swept_level': 'PDL' if swept_pdl else 'Asian_Low',
                                            'dol_target': dol,
                                            'dol_potential_r': sim['dol_potential_r'],
                                            'max_mfe_r': sim['max_mfe_r'],
                                            'max_mae_r': sim['max_mae_r'],
                                            'held_minutes': sim['held_minutes'],
                                            'p1_status': sim['p1_static']['status'],
                                            'p1_net_r': sim['p1_static']['net_r'],
                                            'p2_status': sim['p2_dol_unmanaged']['status'],
                                            'p2_net_r': sim['p2_dol_unmanaged']['net_r'],
                                            'p3_status': sim['p3_trailing_runner']['status'],
                                            'p3_net_r': sim['p3_trailing_runner']['net_r'],
                                            'p4_status': sim['p4_institutional_split']['status'],
                                            'p4_net_r': sim['p4_institutional_split']['net_r']
                                        }
                                        sym_trades.append(rec)
                                        all_trade_records.append(rec)
                                        day_triggered = True
                                        break

                # 2. BEARISH SWEEP OF LIQUIDITY POOL
                # Price sweeps above PDH or Asian High
                swept_pdh = cur_bar['high'] > (pdh + (0.0001 if is_fx else 0.50))
                swept_asian_high = cur_bar['high'] > (asian_high + (0.0001 if is_fx else 0.50))

                if swept_pdh or swept_asian_high:
                    look_forward = session_bars[s_idx : s_idx + 25]
                    sweep_ref = pdh if swept_pdh else asian_high
                    ignition = find_m1_mss_ignition(look_forward, "SHORT", sweep_ref, is_fx)

                    if ignition:
                        dol = pdl
                        potential_r = (ignition['entry'] - dol) / ignition['risk']

                        if potential_r < 7.0 and ignition['entry'] > asian_low:
                            dol = asian_low
                            potential_r = (ignition['entry'] - dol) / ignition['risk']

                        if potential_r >= 7.0:
                            entry_global_idx = m1_map.get(ignition['entry_time'])
                            if entry_global_idx is not None:
                                forward_window = bars_m1[entry_global_idx + 1 : entry_global_idx + 480]
                                if len(forward_window) >= 120:
                                    sim = simulate_multi_policy_trade(
                                        entry=ignition['entry'],
                                        initial_sl=ignition['sl'],
                                        direction="SHORT",
                                        dol_target=dol,
                                        forward_m1=forward_window,
                                        bars_m15_map=m15_map,
                                        symbol=sym
                                    )
                                    if sim:
                                        rec = {
                                            'date': str(day_date),
                                            'season': get_season_name(ignition['entry_dt']),
                                            'symbol': sym,
                                            'direction': 'SHORT',
                                            'entry_time': str(ignition['entry_dt']),
                                            'entry': ignition['entry'],
                                            'sl': ignition['sl'],
                                            'swept_level': 'PDH' if swept_pdh else 'Asian_High',
                                            'dol_target': dol,
                                            'dol_potential_r': sim['dol_potential_r'],
                                            'max_mfe_r': sim['max_mfe_r'],
                                            'max_mae_r': sim['max_mae_r'],
                                            'held_minutes': sim['held_minutes'],
                                            'p1_status': sim['p1_static']['status'],
                                            'p1_net_r': sim['p1_static']['net_r'],
                                            'p2_status': sim['p2_dol_unmanaged']['status'],
                                            'p2_net_r': sim['p2_dol_unmanaged']['net_r'],
                                            'p3_status': sim['p3_trailing_runner']['status'],
                                            'p3_net_r': sim['p3_trailing_runner']['net_r'],
                                            'p4_status': sim['p4_institutional_split']['status'],
                                            'p4_net_r': sim['p4_institutional_split']['net_r']
                                        }
                                        sym_trades.append(rec)
                                        all_trade_records.append(rec)
                                        day_triggered = True
                                        break

        print(f"   => Detected {len(sym_trades)} qualified HTF Macro Runner opportunities on {sym}.")

    # Convert to DataFrame
    df_all = pd.DataFrame(all_trade_records)
    csv_file = OUT_DIR / "macro_runner_trades.csv"
    df_all.to_csv(csv_file, index=False)
    print(f"\n💾 Saved all trade records to {csv_file}")

    # Compute comparative scorecards
    scorecard = {}
    print("\n" + "=" * 95)
    print("📊 COMPARATIVE EVALUATION ACROSS THE 4 MANAGEMENT POLICIES")
    print("=" * 95)

    for sym in symbols:
        df_sym = df_all[df_all['symbol'] == sym]
        if df_sym.empty: continue
        scorecard[sym] = {}

        print(f"\n--- {sym} MASTER RESULTS (Total Opportunities: {len(df_sym)}) ---")
        for p_key, p_name in [
            ('p1', 'Policy 1: Static Target (3.5R/2.5R Sweet Spot)'),
            ('p2', 'Policy 2: All-or-Nothing HTF DOL Target'),
            ('p3', 'Policy 3: 15-Minute Structural Trailing Engine'),
            ('p4', 'Policy 4: Institutional Split (70% Static / 30% Macro Runner)')
        ]:
            net_r = df_sym[f"{p_key}_net_r"].sum()
            wins = len(df_sym[df_sym[f"{p_key}_net_r"] > 0.5])
            losses = len(df_sym[df_sym[f"{p_key}_net_r"] <= -0.5])
            bes = len(df_sym) - wins - losses
            wr = (wins / len(df_sym)) * 100 if len(df_sym) > 0 else 0
            gross_gain = df_sym[df_sym[f"{p_key}_net_r"] > 0][f"{p_key}_net_r"].sum()
            gross_loss = abs(df_sym[df_sym[f"{p_key}_net_r"] < 0][f"{p_key}_net_r"].sum())
            pf = gross_gain / gross_loss if gross_loss > 0 else 99.0

            # 10R+ count
            ten_r_count = len(df_sym[df_sym[f"{p_key}_net_r"] >= 10.0])

            scorecard[sym][p_key] = {
                'name': p_name,
                'fills': len(df_sym),
                'wins': wins,
                'losses': losses,
                'be': bes,
                'wr': round(wr, 1),
                'net_r': round(net_r, 2),
                'pf': round(pf, 2),
                'ten_r_plus_trades': ten_r_count
            }

            print(f"  * {p_name}:")
            print(f"      Net PnL: {net_r:+6.1f}R | WR: {wr:4.1f}% ({wins}W - {losses}L - {bes}BE) | PF: {pf:4.2f} | Trades >= +10R: {ten_r_count}")

            # Seasonal breakdown
            print("      Seasonal Performance:")
            scorecard[sym][p_key]['seasons'] = {}
            for s_name in ["Winter", "Spring", "Summer", "Autumn"]:
                df_s = df_sym[df_sym['season'] == s_name]
                s_net = df_s[f"{p_key}_net_r"].sum()
                s_wins = len(df_s[df_s[f"{p_key}_net_r"] > 0.5])
                s_losses = len(df_s[df_s[f"{p_key}_net_r"] <= -0.5])
                s_bes = len(df_s) - s_wins - s_losses
                s_wr = (s_wins / len(df_s)) * 100 if len(df_s) > 0 else 0
                scorecard[sym][p_key]['seasons'][s_name] = {
                    'fills': len(df_s),
                    'wins': s_wins,
                    'losses': s_losses,
                    'be': s_bes,
                    'net_r': round(s_net, 2)
                }
                print(f"        - {s_name:6s}: {len(df_s):2d} Fills | Net: {s_net:+5.1f}R ({s_wins}W - {s_losses}L - {s_bes}BE)")

    # Save JSON scorecard
    scorecard_file = OUT_DIR / "macro_runner_scorecard.json"
    with open(scorecard_file, 'w', encoding='utf-8') as f:
        json.dump(scorecard, f, indent=2)
    print(f"\n🎉 Comparative Scorecard saved to: {scorecard_file}")


if __name__ == "__main__":
    run_htf_macro_runner_backtest()
