import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
import numpy as np
import datetime
from typing import List, Dict, Any, Tuple
from hitl.backtest.evaluator import evaluate_council_decision, get_default_broker_spread
from hitl.backtest.session_clock import get_session_times_for_date

print("=== Starting Rigorous Zero-Lookahead Backtest of Midday Swing Sweep on GBPUSD ===")

# 1. Load M1 GBPUSD 2026 data
df_m1 = pd.read_parquet('backtest_results/cache/M1_GBPUSD_o_2026.parquet')
df_m1.sort_values('time', inplace=True)
df_m1.reset_index(drop=True, inplace=True)

# Determine broker time offset dynamically
# MT5 broker time is UTC+2 outside EU DST, UTC+3 inside EU DST
# EU DST: Last Sunday of March to last Sunday of October
def is_eu_dst(dt: datetime.datetime) -> bool:
    # Helper to check if date falls in European DST
    year = dt.year
    # Last Sunday of March
    mar_last_sun = max(datetime.datetime(year, 3, d, 1, 0, tzinfo=datetime.timezone.utc)
                       for d in range(25, 32) if datetime.datetime(year, 3, d).weekday() == 6)
    # Last Sunday of October
    oct_last_sun = max(datetime.datetime(year, 10, d, 1, 0, tzinfo=datetime.timezone.utc)
                       for d in range(25, 32) if datetime.datetime(year, 10, d).weekday() == 6)
    return mar_last_sun <= dt < oct_last_sun

# Add dt_utc
m1_times = pd.to_datetime(df_m1['time'], unit='s', utc=True)
# Broker offset: if EU DST, broker is UTC+3 (so UTC = broker - 3h), else UTC+2 (UTC = broker - 2h)
# Let's vectorize
offsets = np.where(
    (m1_times >= '2026-03-29 01:00:00+00:00') & (m1_times < '2026-10-25 01:00:00+00:00'),
    3 * 3600,
    2 * 3600
)
df_m1['utc_epoch'] = df_m1['time'] - offsets
df_m1['dt_utc'] = pd.to_datetime(df_m1['utc_epoch'], unit='s', utc=True)

# Build 5M bars from M1
df_5m = df_m1.set_index('dt_utc').resample('5min').agg({
    'time': 'first',
    'utc_epoch': 'first',
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'tick_volume': 'sum'
}).dropna().reset_index()

print(f"Loaded {len(df_m1)} M1 bars, {len(df_5m)} 5M bars.")

# Convert M1 to fast lookup array / dict per day to evaluate forward price action
m1_records = df_m1[['time', 'open', 'high', 'low', 'close', 'tick_volume']].to_dict('records')
m1_time_to_idx = {r['time']: i for i, r in enumerate(m1_records)}

def get_forward_m1(sig_m5_time: int, max_minutes: int = 480) -> List[Dict[str, Any]]:
    # Signal bar starts at sig_m5_time, closes at sig_m5_time + 300
    # Closed bars only: forward bars start at sig_m5_time + 300
    first_forward_time = sig_m5_time + 300
    idx = m1_time_to_idx.get(first_forward_time)
    if idx is None:
        # Search nearest forward
        for t in range(first_forward_time, first_forward_time + 300, 60):
            if t in m1_time_to_idx:
                idx = m1_time_to_idx[t]
                break
    if idx is None:
        return []
    return m1_records[idx : idx + max_minutes]

# Group 5M bars by UTC date
df_5m['date'] = df_5m['dt_utc'].dt.date
unique_dates = df_5m['date'].unique()
print(f"Total trading days: {len(unique_dates)}")

# We will test multiple configurations:
# Config 1: Market entry on MSS vs Limit entry at swept high/low
# Config 2: Target RR (2.0R, 2.5R, 3.0R, 3.5R)
# Config 3: Breakeven (None vs 1.5R)

def run_simulation(entry_mode="market", target_rr=2.5, breakeven_rr=1.5, min_sweep_pips=0.5):
    spread = get_default_broker_spread("GBPUSD_o") # 0.00006 (0.6 pips)
    pip_size = 0.0001
    sl_buffer = 0.00015 # 1.5 pips buffer above sweep wick
    
    trades = []
    
    for d in unique_dates:
        day_bars = df_5m[df_5m['date'] == d].copy().reset_index(drop=True)
        if len(day_bars) < 30:
            continue
            
        # Get session times in UTC
        stimes = get_session_times_for_date(d)
        lon_open_dt = stimes["london"]["utc_time"]
        ny_open_dt = stimes["new_york"]["utc_time"]
        nyse_open_dt = stimes["nyse_open"]["utc_time"]
        
        # Identify London session swing pivots formed between London Open and 13:00 UTC
        # Search for setups triggering between 12:00 UTC and 16:00 UTC (pre-NY to early NY)
        
        # Track 5M swing highs and swing lows (3L / 3R or 2L / 2R)
        # To avoid lookahead, we only know a swing high is formed 2 bars after its peak
        swing_highs = [] # list of (idx, time, price)
        swing_lows = []
        
        for i in range(2, len(day_bars)):
            cur_bar = day_bars.iloc[i]
            cur_dt = cur_bar['dt_utc']
            
            # Check if bar i-2 was a local swing high (confirmed by i-1 and i)
            p = day_bars.iloc[i-2]
            if (p['high'] > day_bars.iloc[i-3]['high'] and 
                p['high'] > day_bars.iloc[i-4]['high'] if i >= 4 else True) and \
               (p['high'] >= day_bars.iloc[i-1]['high'] and p['high'] >= cur_bar['high']):
                if p['dt_utc'] >= lon_open_dt and p['dt_utc'] < ny_open_dt:
                    swing_highs.append({'time': p['time'], 'dt': p['dt_utc'], 'high': p['high'], 'bar': p})
                    
            if (p['low'] < day_bars.iloc[i-3]['low'] and 
                p['low'] < day_bars.iloc[i-4]['low'] if i >= 4 else True) and \
               (p['low'] <= day_bars.iloc[i-1]['low'] and p['low'] <= cur_bar['low']):
                if p['dt_utc'] >= lon_open_dt and p['dt_utc'] < ny_open_dt:
                    swing_lows.append({'time': p['time'], 'dt': p['dt_utc'], 'low': p['low'], 'bar': p})
            
            # Only trigger in pre-NY to early NY window: [12:00 UTC .. NYSE Open + 90m]
            if not (cur_dt >= lon_open_dt + datetime.timedelta(hours=3) and cur_dt <= nyse_open_dt + datetime.timedelta(minutes=90)):
                continue
                
            # Check Bearish Setup:
            # Bar i (or i-1) swept an earlier London swing high
            # We check if cur_bar or previous bar swept any active swing high
            for sh in swing_highs:
                if cur_bar['dt_utc'] <= sh['dt']:
                    continue
                # Condition: High breached sh['high'] by at least min_sweep_pips
                # and closed below sh['high'] (or formed rejection)
                sweep_amt = cur_bar['high'] - sh['high']
                if sweep_amt >= min_sweep_pips * pip_size:
                    # Check rejection: upper wick >= 30% of bar range, close below high
                    bar_rng = cur_bar['high'] - cur_bar['low']
                    if bar_rng > 0:
                        upper_wick = (cur_bar['high'] - max(cur_bar['open'], cur_bar['close'])) / bar_rng
                        if upper_wick >= 0.25 and cur_bar['close'] < cur_bar['high']:
                            # We found a sweep bar!
                            # Now check MSS confirmation: either cur_bar closed bearish, or next bar confirms
                            # Let's check cur_bar close: if it closed in lower 50%
                            if cur_bar['close'] < cur_bar['open']:
                                entry_price = cur_bar['close'] if entry_mode == "market" else sh['high']
                                sl_price = cur_bar['high'] + sl_buffer
                                risk_pts = sl_price - entry_price
                                
                                # Clamping risk: between 3 pips and 25 pips on GBPUSD
                                if 0.00030 <= risk_pts <= 0.00250:
                                    tp_price = entry_price - (target_rr * risk_pts)
                                    
                                    # Forward M1 simulation
                                    fwd_m1 = get_forward_m1(int(cur_bar['time']), max_minutes=420)
                                    if len(fwd_m1) >= 15:
                                        dec = {
                                            'decision': 'EXECUTE_SELL',
                                            'entry': entry_price,
                                            'sl': sl_price,
                                            'tp': tp_price,
                                            'target_rr': target_rr,
                                            'breakeven_rr': breakeven_rr,
                                            'lot': 0.01
                                        }
                                        res = evaluate_council_decision(
                                            decision_dict=dec,
                                            forward_m1_bars=fwd_m1,
                                            symbol='GBPUSD_o',
                                            spread_pts=spread,
                                            breakeven_rr=breakeven_rr,
                                            slippage_pts=0.00002, # 0.2 pip slippage stress
                                            commission_usd=0.10,
                                            max_risk_usd=12.0
                                        )
                                        res['date'] = d
                                        res['dt_utc'] = cur_bar['dt_utc']
                                        res['risk_pips'] = risk_pts / pip_size
                                        res['swept_time'] = sh['dt']
                                        trades.append(res)
                                        # Avoid multiple entries on same day for clean statistics
                                        break
                                        
            # Check Bullish Setup (symmetric):
            for sl in swing_lows:
                if cur_bar['dt_utc'] <= sl['dt']:
                    continue
                sweep_amt = sl['low'] - cur_bar['low']
                if sweep_amt >= min_sweep_pips * pip_size:
                    bar_rng = cur_bar['high'] - cur_bar['low']
                    if bar_rng > 0:
                        lower_wick = (min(cur_bar['open'], cur_bar['close']) - cur_bar['low']) / bar_rng
                        if lower_wick >= 0.25 and cur_bar['close'] > cur_bar['low']:
                            if cur_bar['close'] > cur_bar['open']:
                                entry_price = cur_bar['close'] if entry_mode == "market" else sl['low']
                                sl_price = cur_bar['low'] - sl_buffer
                                risk_pts = entry_price - sl_price
                                if 0.00030 <= risk_pts <= 0.00250:
                                    tp_price = entry_price + (target_rr * risk_pts)
                                    fwd_m1 = get_forward_m1(int(cur_bar['time']), max_minutes=420)
                                    if len(fwd_m1) >= 15:
                                        dec = {
                                            'decision': 'EXECUTE_BUY',
                                            'entry': entry_price,
                                            'sl': sl_price,
                                            'tp': tp_price,
                                            'target_rr': target_rr,
                                            'breakeven_rr': breakeven_rr,
                                            'lot': 0.01
                                        }
                                        res = evaluate_council_decision(
                                            decision_dict=dec,
                                            forward_m1_bars=fwd_m1,
                                            symbol='GBPUSD_o',
                                            spread_pts=spread,
                                            breakeven_rr=breakeven_rr,
                                            slippage_pts=0.00002,
                                            commission_usd=0.10,
                                            max_risk_usd=12.0
                                        )
                                        res['date'] = d
                                        res['dt_utc'] = cur_bar['dt_utc']
                                        res['risk_pips'] = risk_pts / pip_size
                                        res['swept_time'] = sl['dt']
                                        trades.append(res)
                                        break
                                        
    return trades

# Run across different parameter variations
for mode in ["market", "limit"]:
    for trr in [2.0, 2.5, 3.0]:
        for be in [None, 1.5]:
            tr_list = run_simulation(entry_mode=mode, target_rr=trr, breakeven_rr=be, min_sweep_pips=0.5)
            # Filter filled trades
            filled = [t for t in tr_list if t['status'] in ['WIN', 'LOSS', 'BREAKEVEN']]
            wins = [t for t in filled if t['status'] == 'WIN']
            losses = [t for t in filled if t['status'] == 'LOSS']
            bes = [t for t in filled if t['status'] == 'BREAKEVEN']
            
            pnl_list = [t['realized_pnl_usd'] for t in filled]
            rr_list = [t.get('rr_realized', 0.0) for t in filled if t.get('rr_realized') is not None]
            
            net_pnl = sum(pnl_list)
            net_rr = sum(rr_list)
            gross_win = sum(t['realized_pnl_usd'] for t in wins)
            gross_loss = abs(sum(t['realized_pnl_usd'] for t in losses)) if losses else 0.001
            pf = gross_win / gross_loss if gross_loss > 0 else 0.0
            wr = len(wins) / len(filled) * 100 if filled else 0.0
            
            print(f"Mode={mode.upper():<6} | RR={trr} | BE={str(be):<4} | Filled={len(filled):<3} | W={len(wins):<2} L={len(losses):<2} BE={len(bes):<2} | WR={wr:5.1f}% | NetPnL=${net_pnl:6.2f} | NetR={net_rr:5.1f}R | PF={pf:4.2f}")
