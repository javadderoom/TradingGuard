import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
import numpy as np
import datetime
from hitl.backtest.session_clock import get_session_times_for_date

print("================================================================================")
print("  OUT-OF-SAMPLE VALIDATION: GOLD 2025 H2 (JUN - DEC 2025) BREACH EVENTS        ")
print("================================================================================")

# Load 2025 M5 Gold data
print("Loading Gold M5 dataset (2025 H2 OOS)...")
df_25 = pd.read_parquet('backtest_results/cache/M5_XAUUSD_o_2025.parquet')
df_25.sort_values('time', inplace=True)
df_25.reset_index(drop=True, inplace=True)

# Offset for 2025
m5_times = pd.to_datetime(df_25['time'], unit='s', utc=True)
offsets = np.where(
    (m5_times >= '2025-03-30 01:00:00+00:00') & (m5_times < '2025-10-26 01:00:00+00:00'),
    3 * 3600,
    2 * 3600
)
df_25['utc_epoch'] = df_25['time'] - offsets
df_25['dt_utc'] = pd.to_datetime(df_25['utc_epoch'], unit='s', utc=True)

df_5m = df_25.copy()
print(f"Total 2025 M5 bars: {len(df_5m)}")

# Indicators
tr_5m = np.maximum(
    df_5m['high'] - df_5m['low'],
    np.maximum(
        np.abs(df_5m['high'] - df_5m['close'].shift(1)),
        np.abs(df_5m['low'] - df_5m['close'].shift(1))
    )
)
df_5m['atr14'] = tr_5m.rolling(14).mean().fillna(1.50)

df_5m['date'] = df_5m['dt_utc'].dt.date
unique_dates = sorted(df_5m['date'].unique())

events_2025 = []
print(f"Scanning {len(unique_dates)} days in 2025 for all level breach events...")

for d_idx, d in enumerate(unique_dates):
    day_bars = df_5m[df_5m['date'] == d].copy().reset_index(drop=True)
    if len(day_bars) < 30:
        continue
        
    stimes = get_session_times_for_date(d)
    lon_open_dt = stimes["london"]["utc_time"]
    ny_open_dt = stimes["new_york"]["utc_time"]
    nyse_open_dt = stimes["nyse_open"]["utc_time"]
    
    # Asian range bounds
    asia_bars = day_bars[day_bars['dt_utc'] < lon_open_dt]
    asia_h = asia_bars['high'].max() if len(asia_bars) > 0 else None
    asia_l = asia_bars['low'].min() if len(asia_bars) > 0 else None
    
    levels_high = []
    levels_low = []
    if asia_h is not None:
        levels_high.append({'type': 'ASIAN_HIGH', 'price': asia_h, 'time': int(lon_open_dt.timestamp())})
    if asia_l is not None:
        levels_low.append({'type': 'ASIAN_LOW', 'price': asia_l, 'time': int(lon_open_dt.timestamp())})
        
    major_highs = []
    major_lows = []
    
    for i in range(5, len(day_bars) - 13):
        cur = day_bars.iloc[i]
        next_bar = day_bars.iloc[i+1]
        cur_dt = cur['dt_utc']
        
        p3 = day_bars.iloc[i-3]
        if (p3['high'] > day_bars.iloc[i-4]['high'] and p3['high'] > day_bars.iloc[i-5]['high'] and
            p3['high'] >= day_bars.iloc[i-2]['high'] and p3['high'] >= day_bars.iloc[i-1]['high']):
            major_highs.append({'type': 'SWING_HIGH', 'price': p3['high'], 'time': int(p3['time'])})
            
        if (p3['low'] < day_bars.iloc[i-4]['low'] and p3['low'] < day_bars.iloc[i-5]['low'] and
            p3['low'] <= day_bars.iloc[i-2]['low'] and p3['low'] <= day_bars.iloc[i-1]['low']):
            major_lows.append({'type': 'SWING_LOW', 'price': p3['low'], 'time': int(p3['time'])})
            
        all_highs = levels_high + major_highs
        all_lows = levels_low + major_lows
        
        bar_rng = cur['high'] - cur['low']
        if bar_rng <= 0:
            continue
            
        # High Breaches
        for lvl in all_highs:
            if cur['time'] <= lvl['time']:
                continue
            lvl_price = lvl['price']
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
                    
                next_close_below_cur_low = next_bar['close'] < cur['low']
                next_high_extended = next_bar['high'] > cur['high']
                
                # Forward window (next 12 bars M5 = 60 mins)
                fwd_bars = day_bars.iloc[i+1 : i+13]
                if len(fwd_bars) >= 6:
                    risk_pts = max(pen_pts + 0.50, 1.50)
                    rev_target = cur['close'] - (2.0 * risk_pts)
                    rev_stop = cur['high'] + 0.50
                    cont_target = cur['close'] + (2.0 * risk_pts)
                    cont_stop = lvl_price - 0.50
                    
                    hit_rev_tp = any(b['low'] <= rev_target for _, b in fwd_bars.iterrows())
                    hit_rev_sl = any(b['high'] >= rev_stop for _, b in fwd_bars.iterrows())
                    hit_cont_tp = any(b['high'] >= cont_target for _, b in fwd_bars.iterrows())
                    hit_cont_sl = any(b['low'] <= cont_stop for _, b in fwd_bars.iterrows())
                    
                    if hit_rev_tp and not hit_rev_sl:
                        outcome = 'SWEEP_REVERSAL'
                    elif hit_cont_tp and not hit_cont_sl:
                        outcome = 'BOS_CONTINUATION'
                    else:
                        outcome = 'CHOP'
                        
                    events_2025.append({
                        'date': d,
                        'time': int(cur['time']),
                        'dir': 'HIGH_BREACH',
                        'level_type': lvl['type'],
                        'pen_pts': pen_pts,
                        'wick_ratio': wick_ratio,
                        'body_ratio': body_ratio,
                        'close_loc': close_loc,
                        'next_mss': next_close_below_cur_low,
                        'next_ext': next_high_extended,
                        'outcome': outcome
                    })
                    break
                    
        # Low Breaches
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
                    
                next_close_above_cur_high = next_bar['close'] > cur['high']
                next_low_extended = next_bar['low'] < cur['low']
                
                fwd_bars = day_bars.iloc[i+1 : i+13]
                if len(fwd_bars) >= 6:
                    risk_pts = max(pen_pts + 0.50, 1.50)
                    rev_target = cur['close'] + (2.0 * risk_pts)
                    rev_stop = cur['low'] - 0.50
                    cont_target = cur['close'] - (2.0 * risk_pts)
                    cont_stop = lvl_price + 0.50
                    
                    hit_rev_tp = any(b['high'] >= rev_target for _, b in fwd_bars.iterrows())
                    hit_rev_sl = any(b['low'] <= rev_stop for _, b in fwd_bars.iterrows())
                    hit_cont_tp = any(b['low'] <= cont_target for _, b in fwd_bars.iterrows())
                    hit_cont_sl = any(b['high'] >= cont_stop for _, b in fwd_bars.iterrows())
                    
                    if hit_rev_tp and not hit_rev_sl:
                        outcome = 'SWEEP_REVERSAL'
                    elif hit_cont_tp and not hit_cont_sl:
                        outcome = 'BOS_CONTINUATION'
                    else:
                        outcome = 'CHOP'
                        
                    events_2025.append({
                        'date': d,
                        'time': int(cur['time']),
                        'dir': 'LOW_BREACH',
                        'level_type': lvl['type'],
                        'pen_pts': pen_pts,
                        'wick_ratio': wick_ratio,
                        'body_ratio': body_ratio,
                        'close_loc': close_loc,
                        'next_mss': next_close_above_cur_high,
                        'next_ext': next_low_extended,
                        'outcome': outcome
                    })
                    break

df_25_events = pd.DataFrame(events_2025)
print(f"Total 2025 H2 events: {len(df_25_events)}")
df_25_dir = df_25_events[df_25_events['outcome'].isin(['SWEEP_REVERSAL', 'BOS_CONTINUATION'])].copy()
df_25_dir['is_sweep'] = (df_25_dir['outcome'] == 'SWEEP_REVERSAL').astype(int)

print(f"2025 H2 Directional events: {len(df_25_dir)} (Sweeps: {(df_25_dir['is_sweep']==1).sum()}, BOS: {(df_25_dir['is_sweep']==0).sum()})")
base_25_sweep = df_25_dir['is_sweep'].mean() * 100
print(f"2025 Baseline Sweep Rate: {base_25_sweep:.2f}%\n")

print("--- 2025 OOS: Close Location ---")
print(pd.crosstab(df_25_dir['close_loc'], df_25_dir['outcome'], normalize='index') * 100)

print("\n--- 2025 OOS: Bar T+1 MSS Confirmation ---")
print(pd.crosstab(df_25_dir['next_mss'], df_25_dir['outcome'], normalize='index') * 100)

print("\n--- 2025 OOS: Bar T+1 Extension Confirmation ---")
print(pd.crosstab(df_25_dir['next_ext'], df_25_dir['outcome'], normalize='index') * 100)

# Test Rule 1 in 2025 OOS
rule_sweep_1_25 = (df_25_dir['close_loc'].isin(['INSIDE', 'MARGINAL_OUTSIDE'])) & (df_25_dir['wick_ratio'] >= 0.50) & (df_25_dir['next_mss'] == True)
sample_r1_25 = df_25_dir[rule_sweep_1_25]
sw_rate_25 = sample_r1_25['is_sweep'].mean() * 100 if len(sample_r1_25) > 0 else 0
print(f"\n2025 OOS Rule 1 (Wick >= 50% + Close Inside/Marginal + Next Bar MSS):")
print(f"  Count: {len(sample_r1_25)} | Sweep Reversals: {(sample_r1_25['is_sweep']==1).sum()} | BOS Continuations: {(sample_r1_25['is_sweep']==0).sum()}")
print(f"  Sweep Probability: {sw_rate_25:.1f}% (vs {base_25_sweep:.1f}% baseline)")
