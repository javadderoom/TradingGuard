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

print("=== Testing Institutional Filtered Midday Swing Sweep on GBPUSD ===")

# 1. Load M1 GBPUSD 2026 data
df_m1 = pd.read_parquet('backtest_results/cache/M1_GBPUSD_o_2026.parquet')
df_m1.sort_values('time', inplace=True)
df_m1.reset_index(drop=True, inplace=True)

# Add dt_utc
m1_times = pd.to_datetime(df_m1['time'], unit='s', utc=True)
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

# Build H1 bars for causal trend filter
df_1h = df_m1.set_index('dt_utc').resample('1h').agg({
    'time': 'first',
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last'
}).dropna().reset_index()

# Calculate causal H1 EMA50
df_1h['ema50'] = df_1h['close'].ewm(span=50, adjust=False).mean()
h1_dict = {r['time']: r for r in df_1h.to_dict('records')}
h1_times = np.array(df_1h['time'].values)

def get_latest_closed_h1(sig_time: int):
    # Find latest H1 bar that closed strictly before or at sig_time
    # H1 bar starting at T closes at T + 3600
    valid = h1_times[h1_times + 3600 <= sig_time]
    if len(valid) == 0:
        return None
    return h1_dict[valid[-1]]

# M1 records for forward eval
m1_records = df_m1[['time', 'open', 'high', 'low', 'close', 'tick_volume']].to_dict('records')
m1_time_to_idx = {r['time']: i for i, r in enumerate(m1_records)}

def get_forward_m1(sig_m5_time: int, max_minutes: int = 420) -> List[Dict[str, Any]]:
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

df_5m['date'] = df_5m['dt_utc'].dt.date
unique_dates = df_5m['date'].unique()

def run_filtered_simulation(target_rr=2.5, breakeven_rr=1.5, min_pivot_bars=5, min_sweep_pips=0.8):
    spread = get_default_broker_spread("GBPUSD_o")
    pip_size = 0.0001
    sl_buffer = 0.00015
    trades = []
    
    for d in unique_dates:
        day_bars = df_5m[df_5m['date'] == d].copy().reset_index(drop=True)
        if len(day_bars) < 30:
            continue
            
        stimes = get_session_times_for_date(d)
        lon_open_dt = stimes["london"]["utc_time"]
        ny_open_dt = stimes["new_york"]["utc_time"]
        nyse_open_dt = stimes["nyse_open"]["utc_time"]
        
        # Track major swing pivots (requiring min_pivot_bars on left and right)
        major_highs = []
        major_lows = []
        
        day_traded = False
        
        for i in range(min_pivot_bars, len(day_bars)):
            if day_traded:
                break
                
            cur_bar = day_bars.iloc[i]
            cur_dt = cur_bar['dt_utc']
            
            # Check if bar i - min_pivot_bars was a major swing pivot
            p_idx = i - min_pivot_bars
            p = day_bars.iloc[p_idx]
            
            # Major High check: p['high'] > all surrounding bars within min_pivot_bars
            window_bars = day_bars.iloc[max(0, p_idx - min_pivot_bars) : i + 1]
            if p['high'] == window_bars['high'].max() and (window_bars['high'] == p['high']).sum() == 1:
                if p['dt_utc'] >= lon_open_dt and p['dt_utc'] < ny_open_dt:
                    major_highs.append(p)
                    
            if p['low'] == window_bars['low'].min() and (window_bars['low'] == p['low']).sum() == 1:
                if p['dt_utc'] >= lon_open_dt and p['dt_utc'] < ny_open_dt:
                    major_lows.append(p)
                    
            # Trigger window: from 2 hours after London open up to NYSE Open + 60m
            if not (cur_dt >= lon_open_dt + datetime.timedelta(hours=2) and cur_dt <= nyse_open_dt + datetime.timedelta(minutes=60)):
                continue
                
            # Get H1 macro trend
            h1_bar = get_latest_closed_h1(int(cur_bar['time']))
            if h1_bar is None:
                continue
            h1_trend_bear = h1_bar['close'] < h1_bar['ema50']
            h1_trend_bull = h1_bar['close'] > h1_bar['ema50']
            
            # Check Bearish Setup: Only if H1 trend is BEARISH
            if h1_trend_bear:
                for mh in major_highs:
                    if cur_dt <= mh['dt_utc']:
                        continue
                    sweep_amt = cur_bar['high'] - mh['high']
                    if sweep_amt >= min_sweep_pips * pip_size:
                        bar_rng = cur_bar['high'] - cur_bar['low']
                        if bar_rng > 0:
                            upper_wick = (cur_bar['high'] - max(cur_bar['open'], cur_bar['close'])) / bar_rng
                            # Rejection wick >= 35% and closed bearish
                            if upper_wick >= 0.35 and cur_bar['close'] < cur_bar['open']:
                                entry_price = cur_bar['close']
                                sl_price = cur_bar['high'] + sl_buffer
                                risk_pts = sl_price - entry_price
                                if 0.00040 <= risk_pts <= 0.00200:
                                    tp_price = entry_price - (target_rr * risk_pts)
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
                                            slippage_pts=0.00002,
                                            commission_usd=0.10,
                                            max_risk_usd=12.0
                                        )
                                        res['date'] = d
                                        res['dt_utc'] = cur_bar['dt_utc']
                                        res['risk_pips'] = risk_pts / pip_size
                                        trades.append(res)
                                        day_traded = True
                                        break
                                        
            # Check Bullish Setup: Only if H1 trend is BULLISH
            if (not day_traded) and h1_trend_bull:
                for ml in major_lows:
                    if cur_dt <= ml['dt_utc']:
                        continue
                    sweep_amt = ml['low'] - cur_bar['low']
                    if sweep_amt >= min_sweep_pips * pip_size:
                        bar_rng = cur_bar['high'] - cur_bar['low']
                        if bar_rng > 0:
                            lower_wick = (min(cur_bar['open'], cur_bar['close']) - cur_bar['low']) / bar_rng
                            if lower_wick >= 0.35 and cur_bar['close'] > cur_bar['open']:
                                entry_price = cur_bar['close']
                                sl_price = cur_bar['low'] - sl_buffer
                                risk_pts = entry_price - sl_price
                                if 0.00040 <= risk_pts <= 0.00200:
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
                                        trades.append(res)
                                        day_traded = True
                                        break
                                        
    return trades

print("\n--- Running Grid of Institutional Filters ---")
for p_bars in [3, 5, 8]:
    for sweep_p in [0.5, 1.0, 1.5]:
        for trr in [2.0, 2.5, 3.0]:
            for be in [None, 1.5]:
                trades = run_filtered_simulation(target_rr=trr, breakeven_rr=be, min_pivot_bars=p_bars, min_sweep_pips=sweep_p)
                filled = [t for t in trades if t['status'] in ['WIN', 'LOSS', 'BREAKEVEN']]
                if not filled:
                    continue
                wins = [t for t in filled if t['status'] == 'WIN']
                losses = [t for t in filled if t['status'] == 'LOSS']
                bes = [t for t in filled if t['status'] == 'BREAKEVEN']
                
                net_pnl = sum(t['realized_pnl_usd'] for t in filled)
                net_rr = sum(t.get('rr_realized', 0.0) for t in filled if t.get('rr_realized') is not None)
                gross_win = sum(t['realized_pnl_usd'] for t in wins)
                gross_loss = abs(sum(t['realized_pnl_usd'] for t in losses)) if losses else 0.001
                pf = gross_win / gross_loss if gross_loss > 0 else 0.0
                wr = len(wins) / len(filled) * 100
                
                if pf >= 1.0 or net_rr > 0:
                    print(f"Piv={p_bars} | Swp={sweep_p:.1f}p | RR={trr} | BE={str(be):<4} | Filled={len(filled):<2} | W={len(wins):<2} L={len(losses):<2} BE={len(bes):<2} | WR={wr:5.1f}% | NetPnL=${net_pnl:6.2f} | NetR={net_rr:5.1f}R | PF={pf:4.2f} <<< POSITIVE")
                else:
                    print(f"Piv={p_bars} | Swp={sweep_p:.1f}p | RR={trr} | BE={str(be):<4} | Filled={len(filled):<2} | W={len(wins):<2} L={len(losses):<2} BE={len(bes):<2} | WR={wr:5.1f}% | NetPnL=${net_pnl:6.2f} | NetR={net_rr:5.1f}R | PF={pf:4.2f}")
