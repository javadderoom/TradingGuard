import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
import numpy as np
import datetime
from typing import List, Dict, Any, Tuple
from hitl.backtest.session_clock import get_session_times_for_date

print("================================================================================")
print("  QUANTITATIVE ALPHA RESEARCH: LIQUIDITY SWEEP VS BREAK OF STRUCTURE ON GOLD   ")
print("================================================================================")

# 1. Load 2026 M1 Gold data
print("Loading Gold M1 dataset (2026)...")
df_m1 = pd.read_parquet('backtest_results/cache/M1_XAUUSD_o_2026.parquet')
df_m1.sort_values('time', inplace=True)
df_m1.reset_index(drop=True, inplace=True)

m1_times = pd.to_datetime(df_m1['time'], unit='s', utc=True)
offsets = np.where(
    (m1_times >= '2026-03-29 01:00:00+00:00') & (m1_times < '2026-10-25 01:00:00+00:00'),
    3 * 3600,
    2 * 3600
)
df_m1['utc_epoch'] = df_m1['time'] - offsets
df_m1['dt_utc'] = pd.to_datetime(df_m1['utc_epoch'], unit='s', utc=True)

# Resample to 5M
df_5m = df_m1.set_index('dt_utc').resample('5min').agg({
    'time': 'first',
    'utc_epoch': 'first',
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'tick_volume': 'sum'
}).dropna().reset_index()

# Resample to 1H
df_1h = df_m1.set_index('dt_utc').resample('1h').agg({
    'time': 'first',
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'tick_volume': 'sum'
}).dropna().reset_index()

# Resample to 1D
df_1d = df_m1.set_index('dt_utc').resample('1d').agg({
    'time': 'first',
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'tick_volume': 'sum'
}).dropna().reset_index()

print(f"Total 5M bars: {len(df_5m)} | Total 1H bars: {len(df_1h)} | Total Days: {len(df_1d)}")

# Indicators
tr_5m = np.maximum(
    df_5m['high'] - df_5m['low'],
    np.maximum(
        np.abs(df_5m['high'] - df_5m['close'].shift(1)),
        np.abs(df_5m['low'] - df_5m['close'].shift(1))
    )
)
df_5m['atr14'] = tr_5m.rolling(14).mean().fillna(1.50)
df_5m['vol_sma20'] = df_5m['tick_volume'].rolling(20).mean().fillna(df_5m['tick_volume'])

# 1H EMA50
df_1h['ema50'] = df_1h['close'].ewm(span=50, adjust=False).mean()
h1_dict = {r['time']: r for r in df_1h.to_dict('records')}
h1_times = np.array(df_1h['time'].values)

def get_h1_trend(sig_time: int) -> int:
    valid = h1_times[h1_times + 3600 <= sig_time]
    if len(valid) == 0:
        return 0
    h = h1_dict[valid[-1]]
    return 1 if h['close'] > h['ema50'] else -1

# Daily ADR
tr_1d = np.maximum(
    df_1d['high'] - df_1d['low'],
    np.maximum(
        np.abs(df_1d['high'] - df_1d['close'].shift(1)),
        np.abs(df_1d['low'] - df_1d['close'].shift(1))
    )
)
df_1d['adr14'] = tr_1d.rolling(14).mean().fillna(25.0)
daily_dict = {r['dt_utc'].date(): r for r in df_1d.to_dict('records')}

# M1 fast lookup
m1_records = df_m1[['time', 'open', 'high', 'low', 'close', 'tick_volume']].to_dict('records')
m1_time_to_idx = {r['time']: i for i, r in enumerate(m1_records)}

def get_forward_m1(sig_m5_time: int, max_minutes: int = 120) -> List[Dict[str, Any]]:
    first_forward_time = sig_m5_time + 300
    idx = m1_time_to_idx.get(first_forward_time)
    if idx is None:
        for t in range(first_forward_time, first_forward_time + 300, 60):
            if t in m1_time_to_idx:
                idx = m1_time_to_idx[t]
                break
    if idx is None:
        return []
    return m1_records[idx : idx + max_minutes]

# Group 5M bars by date
df_5m['date'] = df_5m['dt_utc'].dt.date
unique_dates = sorted(df_5m['date'].unique())

events = []
print(f"Scanning {len(unique_dates)} days for all level breach events...")

for d_idx, d in enumerate(unique_dates):
    day_bars = df_5m[df_5m['date'] == d].copy().reset_index(drop=True)
    if len(day_bars) < 30:
        continue
        
    stimes = get_session_times_for_date(d)
    lon_open_dt = stimes["london"]["utc_time"]
    ny_open_dt = stimes["new_york"]["utc_time"]
    nyse_open_dt = stimes["nyse_open"]["utc_time"]
    
    # Previous day high/low
    pdh = None
    pdl = None
    if d_idx > 0:
        prev_d = unique_dates[d_idx - 1]
        prev_day_bars = df_5m[df_5m['date'] == prev_d]
        if len(prev_day_bars) > 0:
            pdh = prev_day_bars['high'].max()
            pdl = prev_day_bars['low'].min()
            
    # Asian range bounds (00:00 to London Open)
    asia_bars = day_bars[day_bars['dt_utc'] < lon_open_dt]
    asia_h = asia_bars['high'].max() if len(asia_bars) > 0 else None
    asia_l = asia_bars['low'].min() if len(asia_bars) > 0 else None
    
    # Active levels to monitor
    # Each level: {'type': ..., 'price': ..., 'created_time': ...}
    levels_high = []
    levels_low = []
    
    if pdh is not None:
        levels_high.append({'type': 'PDH', 'price': pdh, 'time': 0})
    if pdl is not None:
        levels_low.append({'type': 'PDL', 'price': pdl, 'time': 0})
    if asia_h is not None:
        levels_high.append({'type': 'ASIAN_HIGH', 'price': asia_h, 'time': int(lon_open_dt.timestamp())})
    if asia_l is not None:
        levels_low.append({'type': 'ASIAN_LOW', 'price': asia_l, 'time': int(lon_open_dt.timestamp())})
        
    # Active swing pivots (3L/3R and 5L/5R)
    major_highs = []
    major_lows = []
    
    # We step through the day
    for i in range(5, len(day_bars) - 1):
        cur = day_bars.iloc[i]
        next_bar = day_bars.iloc[i+1] # Bar T+1
        cur_dt = cur['dt_utc']
        cur_time = int(cur['time'])
        
        # Check swing high formation at i-3 (confirmed 3 bars ago)
        p3 = day_bars.iloc[i-3]
        if (p3['high'] > day_bars.iloc[i-4]['high'] and p3['high'] > day_bars.iloc[i-5]['high'] and
            p3['high'] >= day_bars.iloc[i-2]['high'] and p3['high'] >= day_bars.iloc[i-1]['high']):
            major_highs.append({'type': 'SWING_HIGH', 'price': p3['high'], 'time': int(p3['time'])})
            
        # Swing low at i-3
        if (p3['low'] < day_bars.iloc[i-4]['low'] and p3['low'] < day_bars.iloc[i-5]['low'] and
            p3['low'] <= day_bars.iloc[i-2]['low'] and p3['low'] <= day_bars.iloc[i-1]['low']):
            major_lows.append({'type': 'SWING_LOW', 'price': p3['low'], 'time': int(p3['time'])})
            
        # Combine all active levels
        all_highs = levels_high + major_highs
        all_lows = levels_low + major_lows
        
        # Determine session
        if cur_dt < lon_open_dt:
            session = 'ASIA'
        elif cur_dt < lon_open_dt + datetime.timedelta(hours=2):
            session = 'LONDON_OPEN'
        elif cur_dt < ny_open_dt:
            session = 'LONDON_MIDDAY'
        elif cur_dt <= nyse_open_dt + datetime.timedelta(hours=1):
            session = 'NY_OPEN'
        else:
            session = 'NY_LATE'
            
        # Calculate ADR consumed so far
        day_so_far = day_bars.iloc[: i + 1]
        day_range_so_far = day_so_far['high'].max() - day_so_far['low'].min()
        adr = daily_dict.get(d, {}).get('adr14', 25.0)
        adr_consumed_pct = (day_range_so_far / adr) * 100.0 if adr > 0 else 0.0
        
        h1_trend = get_h1_trend(cur_time)
        bar_rng = cur['high'] - cur['low']
        if bar_rng <= 0:
            continue
            
        atr = cur['atr14'] if cur['atr14'] > 0 else 1.50
        vol_ratio = cur['tick_volume'] / cur['vol_sma20'] if cur['vol_sma20'] > 0 else 1.0
        
        # 1. Check HIGH BREACHES
        for lvl in all_highs:
            if cur['time'] <= lvl['time']:
                continue
            lvl_price = lvl['price']
            # Breach condition: bar high exceeds level by >= $0.20
            if cur['high'] >= lvl_price + 0.20 and cur['open'] <= lvl_price:
                pen_pts = cur['high'] - lvl_price
                upper_wick = cur['high'] - max(cur['open'], cur['close'])
                wick_ratio = upper_wick / bar_rng
                body_ratio = abs(cur['close'] - cur['open']) / bar_rng
                close_pct = (cur['close'] - cur['low']) / bar_rng
                
                if cur['close'] < lvl_price:
                    close_loc = 'INSIDE'
                elif cur['close'] <= lvl_price + 0.50:
                    close_loc = 'MARGINAL_OUTSIDE'
                else:
                    close_loc = 'STRONG_OUTSIDE'
                    
                # Bar T+1 confirmation
                next_close_below_cur_low = next_bar['close'] < cur['low'] # Instant MSS
                next_high_extended = next_bar['high'] > cur['high'] # Instant extension
                
                # Forward evaluation over next 60 minutes
                fwd_m1 = get_forward_m1(cur_time, max_minutes=60)
                if len(fwd_m1) >= 15:
                    risk_pts = max(pen_pts + 0.50, 1.50)
                    # Reversal direction (SHORT): target is lvl_price - 2*risk_pts, invalidation is cur['high'] + 1.0
                    rev_target = cur['close'] - (2.0 * risk_pts)
                    rev_stop = cur['high'] + 0.50
                    
                    # Continuation direction (LONG): target is cur['close'] + 2*risk_pts, invalidation is cur['low']
                    cont_target = cur['close'] + (2.0 * risk_pts)
                    cont_stop = lvl_price - 0.50
                    
                    # Track what happens first
                    mfe_down = cur['close'] - min(b['low'] for b in fwd_m1)
                    mfe_up = max(b['high'] for b in fwd_m1) - cur['close']
                    
                    mfe_rev_r = mfe_down / risk_pts
                    mfe_cont_r = mfe_up / risk_pts
                    
                    # Classification
                    hit_rev_tp = any(b['low'] <= rev_target for b in fwd_m1)
                    hit_rev_sl = any(b['high'] >= rev_stop for b in fwd_m1)
                    
                    hit_cont_tp = any(b['high'] >= cont_target for b in fwd_m1)
                    hit_cont_sl = any(b['low'] <= cont_stop for b in fwd_m1)
                    
                    if hit_rev_tp and not hit_rev_sl:
                        outcome = 'SWEEP_REVERSAL'
                    elif hit_cont_tp and not hit_cont_sl:
                        outcome = 'BOS_CONTINUATION'
                    elif mfe_rev_r >= 1.5 and mfe_cont_r < 0.8:
                        outcome = 'SWEEP_REVERSAL'
                    elif mfe_cont_r >= 1.5 and mfe_rev_r < 0.8:
                        outcome = 'BOS_CONTINUATION'
                    else:
                        outcome = 'CHOP'
                        
                    events.append({
                        'date': d,
                        'time': cur_time,
                        'dt_utc': cur_dt,
                        'dir': 'HIGH_BREACH',
                        'level_type': lvl['type'],
                        'level_price': lvl_price,
                        'pen_pts': pen_pts,
                        'pen_to_atr': pen_pts / atr,
                        'wick_ratio': wick_ratio,
                        'body_ratio': body_ratio,
                        'close_loc': close_loc,
                        'close_pct': close_pct,
                        'vol_ratio': vol_ratio,
                        'session': session,
                        'adr_consumed_pct': adr_consumed_pct,
                        'is_pro_trend': (h1_trend == 1),
                        'next_mss': next_close_below_cur_low,
                        'next_ext': next_high_extended,
                        'mfe_rev_r': mfe_rev_r,
                        'mfe_cont_r': mfe_cont_r,
                        'outcome': outcome
                    })
                    break # Only 1 breach event per bar
                    
        # 2. Check LOW BREACHES
        for lvl in all_lows:
            if cur['time'] <= lvl['time']:
                continue
            lvl_price = lvl['price']
            if cur['low'] <= lvl_price - 0.20 and cur['open'] >= lvl_price:
                pen_pts = lvl_price - cur['low']
                lower_wick = min(cur['open'], cur['close']) - cur['low']
                wick_ratio = lower_wick / bar_rng
                body_ratio = abs(cur['close'] - cur['open']) / bar_rng
                close_pct = (cur['close'] - cur['low']) / bar_rng
                
                if cur['close'] > lvl_price:
                    close_loc = 'INSIDE'
                elif cur['close'] >= lvl_price - 0.50:
                    close_loc = 'MARGINAL_OUTSIDE'
                else:
                    close_loc = 'STRONG_OUTSIDE'
                    
                next_close_above_cur_high = next_bar['close'] > cur['high'] # Instant MSS
                next_low_extended = next_bar['low'] < cur['low'] # Instant extension
                
                fwd_m1 = get_forward_m1(cur_time, max_minutes=60)
                if len(fwd_m1) >= 15:
                    risk_pts = max(pen_pts + 0.50, 1.50)
                    rev_target = cur['close'] + (2.0 * risk_pts)
                    rev_stop = cur['low'] - 0.50
                    cont_target = cur['close'] - (2.0 * risk_pts)
                    cont_stop = lvl_price + 0.50
                    
                    mfe_up = max(b['high'] for b in fwd_m1) - cur['close']
                    mfe_down = cur['close'] - min(b['low'] for b in fwd_m1)
                    
                    mfe_rev_r = mfe_up / risk_pts
                    mfe_cont_r = mfe_down / risk_pts
                    
                    hit_rev_tp = any(b['high'] >= rev_target for b in fwd_m1)
                    hit_rev_sl = any(b['low'] <= rev_stop for b in fwd_m1)
                    
                    hit_cont_tp = any(b['low'] <= cont_target for b in fwd_m1)
                    hit_cont_sl = any(b['high'] >= cont_stop for b in fwd_m1)
                    
                    if hit_rev_tp and not hit_rev_sl:
                        outcome = 'SWEEP_REVERSAL'
                    elif hit_cont_tp and not hit_cont_sl:
                        outcome = 'BOS_CONTINUATION'
                    elif mfe_rev_r >= 1.5 and mfe_cont_r < 0.8:
                        outcome = 'SWEEP_REVERSAL'
                    elif mfe_cont_r >= 1.5 and mfe_rev_r < 0.8:
                        outcome = 'BOS_CONTINUATION'
                    else:
                        outcome = 'CHOP'
                        
                    events.append({
                        'date': d,
                        'time': cur_time,
                        'dt_utc': cur_dt,
                        'dir': 'LOW_BREACH',
                        'level_type': lvl['type'],
                        'level_price': lvl_price,
                        'pen_pts': pen_pts,
                        'pen_to_atr': pen_pts / atr,
                        'wick_ratio': wick_ratio,
                        'body_ratio': body_ratio,
                        'close_loc': close_loc,
                        'close_pct': 1.0 - close_pct, # normalized so 1.0 = strong rejection wick
                        'vol_ratio': vol_ratio,
                        'session': session,
                        'adr_consumed_pct': adr_consumed_pct,
                        'is_pro_trend': (h1_trend == -1),
                        'next_mss': next_close_above_cur_high,
                        'next_ext': next_low_extended,
                        'mfe_rev_r': mfe_rev_r,
                        'mfe_cont_r': mfe_cont_r,
                        'outcome': outcome
                    })
                    break

df_events = pd.DataFrame(events)
print(f"\n================================================================================")
print(f"Total Level Breach Events Extracted: {len(df_events)}")
print(f"Outcome Distribution:")
print(df_events['outcome'].value_counts())
print(f"Percentages:\n{df_events['outcome'].value_counts(normalize=True)*100}")
print("================================================================================")

# Save events dataset
df_events.to_parquet('scratch/gold_breach_events_2026.parquet')
print("Saved breach events to scratch/gold_breach_events_2026.parquet")
