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

print("================================================================================")
print("  PRO-TREND & ADR EXHAUSTION FILTERED SWEEP MODEL ON GOLD                       ")
print("================================================================================")

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

df_5m = df_m1.set_index('dt_utc').resample('5min').agg({
    'time': 'first',
    'utc_epoch': 'first',
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'tick_volume': 'sum'
}).dropna().reset_index()

df_1h = df_m1.set_index('dt_utc').resample('1h').agg({
    'time': 'first',
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'tick_volume': 'sum'
}).dropna().reset_index()

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
df_1d = df_m1.set_index('dt_utc').resample('1d').agg({
    'high': 'max',
    'low': 'min',
    'close': 'last'
}).dropna().reset_index()
tr_1d = np.maximum(
    df_1d['high'] - df_1d['low'],
    np.maximum(
        np.abs(df_1d['high'] - df_1d['close'].shift(1)),
        np.abs(df_1d['low'] - df_1d['close'].shift(1))
    )
)
df_1d['adr14'] = tr_1d.rolling(14).mean().fillna(25.0)
daily_dict = {r['dt_utc'].date(): r for r in df_1d.to_dict('records')}

m1_records = df_m1[['time', 'open', 'high', 'low', 'close', 'tick_volume']].to_dict('records')
m1_time_to_idx = {r['time']: i for i, r in enumerate(m1_records)}

def get_forward_m1(sig_m5_time: int, max_minutes: int = 360) -> List[Dict[str, Any]]:
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
unique_dates = sorted(df_5m['date'].unique())
spread = get_default_broker_spread("XAUUSD_o")

def run_pro_trend_sweeps(target_rr=2.0, breakeven_rr=1.5, max_trades_day=2):
    trades = []
    for d in unique_dates:
        day_bars = df_5m[df_5m['date'] == d].copy().reset_index(drop=True)
        if len(day_bars) < 30:
            continue
            
        stimes = get_session_times_for_date(d)
        lon_open_dt = stimes["london"]["utc_time"]
        nyse_open_dt = stimes["nyse_open"]["utc_time"]
        
        major_highs = []
        major_lows = []
        day_trade_count = 0
        
        for i in range(5, len(day_bars) - 2):
            if day_trade_count >= max_trades_day:
                break
                
            cur = day_bars.iloc[i]
            next_b = day_bars.iloc[i+1]
            cur_dt = cur['dt_utc']
            
            p3 = day_bars.iloc[i-3]
            if (p3['high'] > day_bars.iloc[i-4]['high'] and p3['high'] > day_bars.iloc[i-5]['high'] and
                p3['high'] >= day_bars.iloc[i-2]['high'] and p3['high'] >= day_bars.iloc[i-1]['high']):
                if p3['dt_utc'] >= lon_open_dt:
                    major_highs.append(p3['high'])
                    
            if (p3['low'] < day_bars.iloc[i-4]['low'] and p3['low'] < day_bars.iloc[i-5]['low'] and
                p3['low'] <= day_bars.iloc[i-2]['low'] and p3['low'] <= day_bars.iloc[i-1]['low']):
                if p3['dt_utc'] >= lon_open_dt:
                    major_lows.append(p3['low'])
                    
            if not (cur_dt >= lon_open_dt and cur_dt <= nyse_open_dt + datetime.timedelta(hours=2)):
                continue
                
            bar_rng = cur['high'] - cur['low']
            if bar_rng <= 0:
                continue
                
            h1_trend = get_h1_trend(int(cur['time']))
            
            # HIGH SWEEP REVERSAL: ONLY IF H1 TREND IS BEARISH (Trend-Aligned Pullback Reversal)
            if h1_trend == -1:
                for mh in major_highs:
                    if cur['high'] >= mh + 0.30 and cur['open'] <= mh:
                        upper_wick = cur['high'] - max(cur['open'], cur['close'])
                        if upper_wick / bar_rng >= 0.35 and cur['close'] <= mh + 0.50:
                            if next_b['close'] < cur['low']:
                                entry = next_b['close']
                                sl = cur['high'] + 0.50
                                risk_pts = sl - entry
                                if 1.50 <= risk_pts <= 15.00:
                                    tp = entry - (target_rr * risk_pts)
                                    fwd_m1 = get_forward_m1(int(next_b['time']), max_minutes=360)
                                    if len(fwd_m1) >= 15:
                                        dec = {
                                            'decision': 'EXECUTE_SELL',
                                            'entry': entry,
                                            'sl': sl,
                                            'tp': tp,
                                            'lot': 0.01
                                        }
                                        res = evaluate_council_decision(
                                            decision_dict=dec,
                                            forward_m1_bars=fwd_m1,
                                            symbol='XAUUSD_o',
                                            spread_pts=spread,
                                            breakeven_rr=breakeven_rr,
                                            slippage_pts=0.05,
                                            commission_usd=0.10,
                                            max_risk_usd=12.0
                                        )
                                        trades.append(res)
                                        day_trade_count += 1
                                        break
                                        
            # LOW SWEEP REVERSAL: ONLY IF H1 TREND IS BULLISH
            if h1_trend == 1 and day_trade_count < max_trades_day:
                for ml in major_lows:
                    if cur['low'] <= ml - 0.30 and cur['open'] >= ml:
                        lower_wick = min(cur['open'], cur['close']) - cur['low']
                        if lower_wick / bar_rng >= 0.35 and cur['close'] >= ml - 0.50:
                            if next_b['close'] > cur['high']:
                                entry = next_b['close']
                                sl = cur['low'] - 0.50
                                risk_pts = entry - sl
                                if 1.50 <= risk_pts <= 15.00:
                                    tp = entry + (target_rr * risk_pts)
                                    fwd_m1 = get_forward_m1(int(next_b['time']), max_minutes=360)
                                    if len(fwd_m1) >= 15:
                                        dec = {
                                            'decision': 'EXECUTE_BUY',
                                            'entry': entry,
                                            'sl': sl,
                                            'tp': tp,
                                            'lot': 0.01
                                        }
                                        res = evaluate_council_decision(
                                            decision_dict=dec,
                                            forward_m1_bars=fwd_m1,
                                            symbol='XAUUSD_o',
                                            spread_pts=spread,
                                            breakeven_rr=breakeven_rr,
                                            slippage_pts=0.05,
                                            commission_usd=0.10,
                                            max_risk_usd=12.0
                                        )
                                        trades.append(res)
                                        day_trade_count += 1
                                        break
    return trades

print("\n--- Running Pro-Trend Filtered Grid ---")
for trr in [1.8, 2.0, 2.2, 2.5]:
    for be in [None, 1.2, 1.5]:
        tr = run_pro_trend_sweeps(target_rr=trr, breakeven_rr=be, max_trades_day=1)
        filled = [t for t in tr if t['status'] in ['WIN', 'LOSS', 'BREAKEVEN']]
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
        
        sig_str = " <<< POSITIVE EDGE!" if pf > 1.20 else ""
        print(f"Pro-Trend Sweep | RR={trr} | BE={str(be):<4} | Filled={len(filled):<3} | W={len(wins):<2} L={len(losses):<2} BE={len(bes):<2} | WR={wr:5.1f}% | NetPnL=${net_pnl:6.2f} | NetR={net_rr:5.1f}R | PF={pf:4.2f}{sig_str}")
