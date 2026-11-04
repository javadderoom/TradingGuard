"""
TradingGuard HITL - Structural Break Origin Engine & Multi-Day Retest Backtester
Tracks the true origins of Market Structure Shifts (MSS) and Breaks of Structure (BOS):
1. Maps exact institutional ignition bases across H1/M15 historical data across 2026.
2. Maintains a living lifecycle of Unmitigated Reversal (MSS) and Continuation (BOS) Origin Zones.
3. Simulates retests across subsequent days/weeks with precision invalidation and trailing management.
Full-Year 2026 Audit (Gold XAUUSD_o & Cable GBPUSD_o | 90M+ ticks).
"""

import os
import sys
import json
import time
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, List, Any, Tuple, Optional

import pandas as pd
import numpy as np

# Enforce UTF-8 on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

TZ_UTC = ZoneInfo("UTC")
CACHE_DIR = Path("backtest_results/cache")
OUT_DIR = Path("backtest_results/structural_origin_research")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def get_season_name(dt: datetime.datetime) -> str:
    m = dt.month
    if m in (12, 1, 2): return "Winter"
    elif m in (3, 4, 5): return "Spring"
    elif m in (6, 7, 8): return "Summer"
    elif m in (9, 10, 11): return "Autumn"
    return "Unknown"


def load_microstructure(symbol: str) -> Dict[str, Any]:
    cache_file = CACHE_DIR / f"M1_{symbol}_2026.parquet"
    if not cache_file.exists():
        raise RuntimeError(f"Cache file for {symbol} not found in {CACHE_DIR}")

    print(f"   [Cache Hit] Loading M1 bars for {symbol}...")
    df = pd.read_parquet(cache_file)
    bars_m1 = []
    for row in df.itertuples():
        bars_m1.append({
            'time': int(row.time),
            'dt': row.Index.to_pydatetime() if hasattr(row.Index, 'to_pydatetime') else row.Index,
            'open': float(row.open),
            'high': float(row.high),
            'low': float(row.low),
            'close': float(row.close),
            'tick_volume': int(row.tick_volume),
            'spread': int(row.spread)
        })

    print(f"   Resampling M5, M15, H1, and D1 bars from {len(bars_m1)} M1 bars...")
    df_bars = pd.DataFrame(bars_m1)
    df_bars['datetime'] = pd.to_datetime(df_bars['time'], unit='s', utc=True)
    df_bars.set_index('datetime', inplace=True)

    def _resamp(rule):
        res = df_bars['close'].resample(rule).ohlc().dropna()
        res['open'] = df_bars['open'].resample(rule).first()
        res['high'] = df_bars['high'].resample(rule).max()
        res['low'] = df_bars['low'].resample(rule).min()
        res['close'] = df_bars['close'].resample(rule).last()
        res['tick_volume'] = df_bars['tick_volume'].resample(rule).sum()
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

    bars_m5 = _resamp("5min")
    bars_m15 = _resamp("15min")
    bars_h1 = _resamp("60min")
    bars_d1 = _resamp("1D")

    return {
        'symbol': symbol,
        'is_fx': "GBP" in symbol or "EUR" in symbol,
        'm1': bars_m1,
        'm5': bars_m5,
        'm15': bars_m15,
        'h1': bars_h1,
        'd1': bars_d1
    }


def find_swing_pivots(bars: List[Dict[str, Any]], left: int = 3, right: int = 3) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Finds confirmed swing highs and swing lows."""
    highs = []
    lows = []
    n = len(bars)
    for i in range(left, n - right):
        cur_h = bars[i]['high']
        cur_l = bars[i]['low']

        is_h = all(cur_h >= bars[i - k]['high'] for k in range(1, left + 1)) and \
               all(cur_h >= bars[i + k]['high'] for k in range(1, right + 1))
        if is_h:
            highs.append({'idx': i, 'time': bars[i]['time'], 'dt': bars[i]['dt'], 'price': cur_h})

        is_l = all(cur_l <= bars[i - k]['low'] for k in range(1, left + 1)) and \
               all(cur_l <= bars[i + k]['low'] for k in range(1, right + 1))
        if is_l:
            lows.append({'idx': i, 'time': bars[i]['time'], 'dt': bars[i]['dt'], 'price': cur_l})

    return highs, lows


def extract_structural_origins(bars_h1: List[Dict[str, Any]], is_fx: bool) -> List[Dict[str, Any]]:
    """
    Extracts all genuine H1 Structural Break Origins across the year.
    Detects both Reversal (MSS) and Continuation (BOS) ignition bases.
    """
    min_impulse = 0.0035 if is_fx else 15.0  # Min displacement points
    highs, lows = find_swing_pivots(bars_h1, left=3, right=3)

    origins = []
    all_pivots = sorted(highs + lows, key=lambda x: x['idx'])

    # Track active swing levels to detect structural breaks
    last_trend = "NONE"

    for i in range(10, len(bars_h1)):
        b = bars_h1[i]
        c = b['close']

        # Find preceding swing highs and lows that haven't been broken yet
        prior_h = [h for h in highs if h['idx'] < i]
        prior_l = [l for l in lows if l['idx'] < i]

        if not prior_h or not prior_l: continue

        recent_sw_high = prior_h[-1]
        recent_sw_low = prior_l[-1]

        # 1. BULLISH STRUCTURAL BREAK
        # Candle body closes above recent swing high
        if c > recent_sw_high['price'] and b['close'] > b['open']:
            # Find the ignition base: the lowest consolidation candle/base between swing high and current bar
            break_idx = i
            search_start = max(recent_sw_high['idx'], break_idx - 15)
            interim_bars = bars_h1[search_start : break_idx + 1]

            if interim_bars:
                base_bar = min(interim_bars, key=lambda x: x['low'])
                impulse_dist = c - base_bar['low']

                if impulse_dist >= min_impulse:
                    # Determine whether Reversal (MSS) or Continuation (BOS)
                    orig_type = "REVERSAL_MSS" if last_trend == "BEARISH" else "CONTINUATION_BOS"
                    last_trend = "BULLISH"

                    origin_zone = {
                        'origin_id': f"H1-ORIGIN-{base_bar['time']}-BULL-{orig_type[:3]}",
                        'symbol': 'GBPUSD' if is_fx else 'XAUUSD',
                        'type': orig_type,
                        'direction': 'BULLISH',
                        'timeframe': 'H1',
                        'created_time': base_bar['time'],
                        'created_dt': base_bar['dt'],
                        'break_time': b['time'],
                        'break_dt': b['dt'],
                        'origin_high': max(base_bar['open'], base_bar['close']),
                        'origin_low': base_bar['low'],
                        'invalidation_sl': base_bar['low'] - (0.0006 if is_fx else 2.00),
                        'impulse_size': round(impulse_dist, 5 if is_fx else 2),
                        'status': 'ACTIVE_UNMITIGATED',
                        'mitigated_time': None
                    }
                    origins.append(origin_zone)

        # 2. BEARISH STRUCTURAL BREAK
        # Candle body closes below recent swing low
        elif c < recent_sw_low['price'] and b['close'] < b['open']:
            break_idx = i
            search_start = max(recent_sw_low['idx'], break_idx - 15)
            interim_bars = bars_h1[search_start : break_idx + 1]

            if interim_bars:
                base_bar = max(interim_bars, key=lambda x: x['high'])
                impulse_dist = base_bar['high'] - c

                if impulse_dist >= min_impulse:
                    orig_type = "REVERSAL_MSS" if last_trend == "BULLISH" else "CONTINUATION_BOS"
                    last_trend = "BEARISH"

                    origin_zone = {
                        'origin_id': f"H1-ORIGIN-{base_bar['time']}-BEAR-{orig_type[:3]}",
                        'symbol': 'GBPUSD' if is_fx else 'XAUUSD',
                        'type': orig_type,
                        'direction': 'BEARISH',
                        'timeframe': 'H1',
                        'created_time': base_bar['time'],
                        'created_dt': base_bar['dt'],
                        'break_time': b['time'],
                        'break_dt': b['dt'],
                        'origin_high': base_bar['high'],
                        'origin_low': min(base_bar['open'], base_bar['close']),
                        'invalidation_sl': base_bar['high'] + (0.0006 if is_fx else 2.00),
                        'impulse_size': round(impulse_dist, 5 if is_fx else 2),
                        'status': 'ACTIVE_UNMITIGATED',
                        'mitigated_time': None
                    }
                    origins.append(origin_zone)

    # Deduplicate overlapping origins (keep most recent or strongest)
    filtered = []
    for og in origins:
        overlap = False
        for f in filtered[-5:]:
            if f['direction'] == og['direction'] and abs(f['created_time'] - og['created_time']) < 18000:
                overlap = True
                break
        if not overlap:
            filtered.append(og)

    return filtered


def simulate_origin_retest(
    origin: Dict[str, Any],
    entry_bar: Dict[str, Any],
    forward_m1: List[Dict[str, Any]],
    bars_m15_map: Dict[int, Dict[str, Any]],
    is_fx: bool
) -> Optional[Dict[str, Any]]:
    """Simulates trading the retest of an unmitigated structural break origin."""
    direction = origin['direction']
    entry = entry_bar['close']
    sl = origin['invalidation_sl']
    risk = abs(entry - sl)

    # Risk bounds
    min_risk = 0.0008 if is_fx else 4.00
    max_risk = 0.0022 if is_fx else 10.00
    if not (min_risk <= risk <= max_risk):
        return None

    spread = 0.00006 if is_fx else 0.20
    max_mfe_r = 0.0
    max_mae_r = 0.0

    # Policies
    # Policy 1: Static Target (3.5R Gold / 2.5R Cable with 1.8R/1.5R BE)
    p1_target = 2.5 if is_fx else 3.5
    p1_be = 1.5 if is_fx else 1.8
    p1_res = None
    p1_be_active = False

    # Policy 3: 15-Minute Structural Trailing Engine
    p3_res = None
    p3_be_active = False
    p3_trail_active = False
    p3_sl = sl

    recent_m15_highs = []
    recent_m15_lows = []
    last_m15_time = 0
    held_minutes = 0

    for m1_idx, b in enumerate(forward_m1):
        held_minutes = m1_idx + 1
        h = b['high']
        l = b['low']

        if direction == "BULLISH":
            cur_mfe = (h - entry - spread) / risk
            cur_mae = (entry - l + spread) / risk
        else:
            cur_mfe = (entry - l - spread) / risk
            cur_mae = (h - entry + spread) / risk

        if cur_mfe > max_mfe_r: max_mfe_r = cur_mfe
        if cur_mae > max_mae_r: max_mae_r = cur_mae

        # Check 15M bar completion
        bar_m15_slot = (b['time'] // 900) * 900
        if bar_m15_slot in bars_m15_map and bar_m15_slot != last_m15_time:
            last_m15_time = bar_m15_slot
            m15_b = bars_m15_map[bar_m15_slot]
            recent_m15_highs.append(m15_b['high'])
            recent_m15_lows.append(m15_b['low'])
            if len(recent_m15_highs) > 10:
                recent_m15_highs.pop(0)
                recent_m15_lows.pop(0)

        # Policy 1
        if p1_res is None:
            if not p1_be_active and max_mfe_r >= p1_be:
                p1_be_active = True
            hit_p1_tp = (max_mfe_r >= p1_target)
            hit_p1_sl = (l <= (entry if p1_be_active else sl)) if direction == "BULLISH" else (h >= (entry if p1_be_active else sl))
            if hit_p1_tp:
                p1_res = {'status': 'WIN', 'net_r': p1_target}
            elif hit_p1_sl:
                p1_res = {'status': 'BREAKEVEN' if p1_be_active else 'LOSS', 'net_r': 0.0 if p1_be_active else -1.0}

        # Policy 3 (15M Trailing)
        if p3_res is None:
            if not p3_be_active and max_mfe_r >= 3.0:
                p3_be_active = True
                p3_sl = entry + (0.2 * risk if direction == "BULLISH" else -0.2 * risk)

            if max_mfe_r >= 4.0 and len(recent_m15_lows) >= 3:
                p3_trail_active = True
                if direction == "BULLISH":
                    t_lvl = min(recent_m15_lows[-3:-1]) - (0.0002 if is_fx else 1.00)
                    if t_lvl > p3_sl: p3_sl = t_lvl
                else:
                    t_lvl = max(recent_m15_highs[-3:-1]) + (0.0002 if is_fx else 1.00)
                    if t_lvl < p3_sl: p3_sl = t_lvl

            hit_p3_sl = (l <= p3_sl) if direction == "BULLISH" else (h >= p3_sl)
            if hit_p3_sl:
                if p3_trail_active:
                    realized = ((p3_sl - entry) / risk) if direction == "BULLISH" else ((entry - p3_sl) / risk)
                    st = "TRAIL_WIN" if realized > 0.5 else ("BREAKEVEN" if realized >= -0.1 else "LOSS")
                    p3_res = {'status': st, 'net_r': round(max(realized, 0.0) if p3_be_active else -1.0, 2)}
                else:
                    p3_res = {'status': 'BREAKEVEN' if p3_be_active else 'LOSS', 'net_r': 0.2 if p3_be_active else -1.0}

        if (p1_res is not None and p3_res is not None) or held_minutes >= 480:
            break

    if p1_res is None:
        p1_res = {'status': 'BREAKEVEN' if p1_be_active else 'LOSS', 'net_r': 0.0 if p1_be_active else -1.0}
    if p3_res is None:
        last_c = forward_m1[-1]['close']
        realized = ((last_c - entry) / risk) if direction == "BULLISH" else ((entry - last_c) / risk)
        p3_res = {'status': 'TRAIL_WIN' if realized > 0.5 else 'BREAKEVEN', 'net_r': round(max(realized, 0.0) if p3_be_active else -1.0, 2)}

    return {
        'risk_pts': round(risk, 5 if is_fx else 2),
        'max_mfe_r': round(max_mfe_r, 2),
        'max_mae_r': round(max_mae_r, 2),
        'held_minutes': held_minutes,
        'p1_static': p1_res,
        'p3_trailing': p3_res
    }


def audit_structural_origins_for_symbol(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    symbol = data['symbol']
    is_fx = data['is_fx']
    bars_h1 = data['h1']
    bars_m5 = data['m5']
    bars_m15 = data['m15']
    bars_m1 = data['m1']

    print(f"\n🔍 Extracting Structural Break Origins for {symbol}...")
    origins = extract_structural_origins(bars_h1, is_fx)
    print(f"   => Found {len(origins)} macro structural break origins across 2026.")

    m1_map = {b['time']: idx for idx, b in enumerate(bars_m1)}
    m15_map = {b['time']: b for b in bars_m15}

    trades = []
    active_origins = []

    # Map M5 bars across the year
    # Simulate forward in time: when an origin is broken, it becomes active. When price retests it, simulate trade!
    for i in range(len(bars_m5)):
        b = bars_m5[i]
        t = b['time']

        # Activate newly broken origins
        for og in origins:
            if og['break_time'] <= t and og['status'] == 'ACTIVE_UNMITIGATED' and og not in active_origins:
                active_origins.append(og)

        # Check active origins for retests during London and NY sessions (07:00 - 16:00 UTC)
        if hasattr(b['dt'], 'hour') and 7 <= b['dt'].hour < 16:
            for og in list(active_origins):
                # Elapsed time since break: require at least 2 hours, allow up to 14 days
                elapsed_hours = (t - og['break_time']) / 3600.0
                if elapsed_hours < 2.0 or elapsed_hours > 336.0:  # 14 days max
                    if elapsed_hours > 336.0:
                        og['status'] = 'EXPIRED'
                        active_origins.remove(og)
                    continue

                is_bull = og['direction'] == 'BULLISH'
                # Check if current bar touches or enters the origin zone
                if is_bull:
                    # Price pulls back down into [origin_low, origin_high]
                    retested = (b['low'] <= og['origin_high'] and b['high'] >= og['origin_low'])
                    invalidated = (b['close'] < og['invalidation_sl'])
                else:
                    # Price rallies up into [origin_low, origin_high]
                    retested = (b['high'] >= og['origin_low'] and b['low'] <= og['origin_high'])
                    invalidated = (b['close'] > og['invalidation_sl'])

                if invalidated:
                    og['status'] = 'INVALIDATED'
                    active_origins.remove(og)
                    continue

                if retested:
                    # Retest trigger!
                    m1_idx = m1_map.get(t)
                    if m1_idx is not None:
                        forward_window = bars_m1[m1_idx:m1_idx + 480]
                        if len(forward_window) >= 120:
                            sim = simulate_origin_retest(og, b, forward_window, m15_map, is_fx)
                            if sim:
                                rec = {
                                    'date': str(b['dt'].date()),
                                    'season': get_season_name(b['dt']),
                                    'symbol': symbol,
                                    'origin_id': og['origin_id'],
                                    'origin_type': og['type'],
                                    'direction': og['direction'],
                                    'elapsed_hours': round(elapsed_hours, 1),
                                    'entry_time': str(b['dt']),
                                    'entry': b['close'],
                                    'sl': og['invalidation_sl'],
                                    'risk_pts': sim['risk_pts'],
                                    'max_mfe_r': sim['max_mfe_r'],
                                    'max_mae_r': sim['max_mae_r'],
                                    'held_minutes': sim['held_minutes'],
                                    'p1_status': sim['p1_static']['status'],
                                    'p1_net_r': sim['p1_static']['net_r'],
                                    'p3_status': sim['p3_trailing']['status'],
                                    'p3_net_r': sim['p3_trailing']['net_r']
                                }
                                trades.append(rec)
                                og['status'] = 'MITIGATED'
                                active_origins.remove(og)
                                break

    return trades


def run_structural_origin_research():
    print("=" * 95)
    print("🚀 TRADINGGUARD - STRUCTURAL BREAK ORIGIN (MSS/BOS) EMPIRICAL AUDIT")
    print("Full-Year 2026 Audit across Gold (XAUUSD_o) and Cable (GBPUSD_o)")
    print("=" * 95)

    all_trades = []
    scorecard = {}

    for sym in ["XAUUSD_o", "GBPUSD_o"]:
        data = load_microstructure(sym)
        sym_trades = audit_structural_origins_for_symbol(data)
        all_trades.extend(sym_trades)
        print(f"✅ Generated {len(sym_trades)} origin retest executions for {sym}.")

    df_all = pd.DataFrame(all_trades)
    csv_file = OUT_DIR / "structural_origin_retest_trades.csv"
    df_all.to_csv(csv_file, index=False)
    print(f"\n💾 Saved all trades to {csv_file}")

    print("\n" + "=" * 95)
    print("📊 STRUCTURAL BREAK ORIGIN MASTER SCORECARD")
    print("=" * 95)

    for sym in ["XAUUSD_o", "GBPUSD_o"]:
        df_sym = df_all[df_all['symbol'] == sym]
        if df_sym.empty: continue
        scorecard[sym] = {}

        print(f"\n--- {sym} MASTER RESULTS (Total Retest Fills: {len(df_sym)}) ---")
        
        # Segment by Origin Type: REVERSAL_MSS vs CONTINUATION_BOS
        for orig_type in ['ALL', 'REVERSAL_MSS', 'CONTINUATION_BOS']:
            df_sub = df_sym if orig_type == 'ALL' else df_sym[df_sym['origin_type'] == orig_type]
            if df_sub.empty: continue

            print(f"\n  [Origin Category: {orig_type}] ({len(df_sub)} Fills)")
            for p_key, p_name in [('p1', 'Policy 1: Static Target'), ('p3', 'Policy 3: 15M Structural Trailing')]:
                net = df_sub[f"{p_key}_net_r"].sum()
                wins = len(df_sub[df_sub[f"{p_key}_net_r"] > 0.5])
                losses = len(df_sub[df_sub[f"{p_key}_net_r"] <= -0.5])
                bes = len(df_sub) - wins - losses
                wr = (wins / len(df_sub)) * 100 if len(df_sub) > 0 else 0
                gw = df_sub[df_sub[f"{p_key}_net_r"] > 0][f"{p_key}_net_r"].sum()
                gl = abs(df_sub[df_sub[f"{p_key}_net_r"] < 0][f"{p_key}_net_r"].sum())
                pf = gw / gl if gl > 0 else 99.0

                five_r = len(df_sub[df_sub[f"{p_key}_net_r"] >= 5.0])
                eight_r = len(df_sub[df_sub[f"{p_key}_net_r"] >= 8.0])

                print(f"    * {p_name}: Net {net:+6.1f}R | WR: {wr:4.1f}% ({wins}W - {losses}L - {bes}BE) | PF: {pf:4.2f} | >=+5R: {five_r} | >=+8R: {eight_r}")

        # Seasonal performance on Policy 3
        print("\n  Seasonal Breakdown on Policy 3 (15M Trailing):")
        for s in ['Winter', 'Spring', 'Summer', 'Autumn']:
            df_s = df_sym[df_sym['season'] == s]
            s_net_p3 = df_s['p3_net_r'].sum() if len(df_s) > 0 else 0.0
            s_net_p1 = df_s['p1_net_r'].sum() if len(df_s) > 0 else 0.0
            s_w = len(df_s[df_s['p3_net_r'] > 0.5])
            s_l = len(df_s[df_s['p3_net_r'] <= -0.5])
            print(f"    - {s:6s}: {len(df_s):2d} Fills | Trailing Net: {s_net_p3:+5.1f}R ({s_w}W - {s_l}L) | Static Net: {s_net_p1:+5.1f}R")

    # Save JSON scorecard
    scorecard_file = OUT_DIR / "structural_origin_scorecard.json"
    with open(scorecard_file, 'w', encoding='utf-8') as f:
        json.dump(scorecard, f, indent=2)
    print(f"\n🎉 Saved JSON scorecard to {scorecard_file}")


if __name__ == "__main__":
    run_structural_origin_research()
