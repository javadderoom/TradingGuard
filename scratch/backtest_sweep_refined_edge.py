import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
import numpy as np
import datetime
from hitl.backtest.evaluator import evaluate_council_decision, get_default_broker_spread
from hitl.backtest.session_clock import get_session_times_for_date

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

tr_5m = np.maximum(
    df_5m['high'] - df_5m['low'],
    np.maximum(
        np.abs(df_5m['high'] - df_5m['close'].shift(1)),
        np.abs(df_5m['low'] - df_5m['close'].shift(1))
    )
)
df_5m['atr14'] = tr_5m.rolling(14).mean().fillna(1.50)

df_1h = df_m1.set_index('dt_utc').resample('1h').agg({
    'time': 'first',
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last'
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

m1_records = df_m1[['time', 'open', 'high', 'low', 'close', 'tick_volume']].to_dict('records')
m1_time_to_idx = {r['time']: i for i, r in enumerate(m1_records)}

def get_forward_m1(sig_m5_time: int, max_minutes: int = 360):
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

def test_refined_sweep_model(target_rr=2.2, max_pen_atr=0.8, min_wick=0.45):
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
        day_traded = False
        
        for i in range(5, len(day_bars) - 2):
            if day_traded:
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
            atr = cur['atr14'] if cur['atr14'] > 0 else 1.50
            h1_trend = get_h1_trend(int(cur['time']))
            
            # Bearish Trend Reversal Sweep
            if h1_trend == -1:
                for mh in major_highs:
                    pen_pts = cur['high'] - mh
                    if 0.30 <= pen_pts <= (max_pen_atr * atr) and cur['open'] <= mh:
                        upper_wick = cur['high'] - max(cur['open'], cur['close'])
                        if upper_wick / bar_rng >= min_wick and cur['close'] <= mh + 0.30:
                            if next_b['close'] < cur['low']:
                                entry = next_b['close']
                                sl = cur['high'] + 0.50
                                risk_pts = sl - entry
                                if 1.50 <= risk_pts <= 15.00:
                                    tp = entry - (target_rr * risk_pts)
                                    fwd = get_forward_m1(int(next_b['time']), max_minutes=360)
                                    if len(fwd) >= 15:
                                        res = evaluate_council_decision(
                                            decision_dict={'decision': 'EXECUTE_SELL', 'entry': entry, 'sl': sl, 'tp': tp, 'lot': 0.01},
                                            forward_m1_bars=fwd,
                                            symbol='XAUUSD_o',
                                            spread_pts=spread,
                                            slippage_pts=0.05,
                                            commission_usd=0.10,
                                            max_risk_usd=12.0
                                        )
                                        trades.append(res)
                                        day_traded = True
                                        break
                                        
            # Bullish Trend Reversal Sweep
            if (not day_traded) and h1_trend == 1:
                for ml in major_lows:
                    pen_pts = ml - cur['low']
                    if 0.30 <= pen_pts <= (max_pen_atr * atr) and cur['open'] >= ml:
                        lower_wick = min(cur['open'], cur['close']) - cur['low']
                        if lower_wick / bar_rng >= min_wick and cur['close'] >= ml - 0.30:
                            if next_b['close'] > cur['high']:
                                entry = next_b['close']
                                sl = cur['low'] - 0.50
                                risk_pts = entry - sl
                                if 1.50 <= risk_pts <= 15.00:
                                    tp = entry + (target_rr * risk_pts)
                                    fwd = get_forward_m1(int(next_b['time']), max_minutes=360)
                                    if len(fwd) >= 15:
                                        res = evaluate_council_decision(
                                            decision_dict={'decision': 'EXECUTE_BUY', 'entry': entry, 'sl': sl, 'tp': tp, 'lot': 0.01},
                                            forward_m1_bars=fwd,
                                            symbol='XAUUSD_o',
                                            spread_pts=spread,
                                            slippage_pts=0.05,
                                            commission_usd=0.10,
                                            max_risk_usd=12.0
                                        )
                                        trades.append(res)
                                        day_traded = True
                                        break
    return trades

print("=== REFINED EMPIRICAL SWEEP RULES BACKTEST ===")
for pen_max in [0.5, 0.8, 1.0]:
    for wick_min in [0.40, 0.50]:
        for trr in [2.0, 2.5]:
            tr = test_refined_sweep_model(target_rr=trr, max_pen_atr=pen_max, min_wick=wick_min)
            filled = [t for t in tr if t['status'] in ['WIN', 'LOSS', 'BREAKEVEN']]
            if not filled:
                continue
            wins = [t for t in filled if t['status'] == 'WIN']
            losses = [t for t in filled if t['status'] == 'LOSS']
            net_pnl = sum(t['realized_pnl_usd'] for t in filled)
            net_rr = sum(t.get('rr_realized', 0.0) for t in filled if t.get('rr_realized') is not None)
            gross_win = sum(t['realized_pnl_usd'] for t in wins)
            gross_loss = abs(sum(t['realized_pnl_usd'] for t in losses)) if losses else 0.001
            pf = gross_win / gross_loss if gross_loss > 0 else 0.0
            wr = len(wins) / len(filled) * 100
            print(f"MaxPen={pen_max:.1f}xATR | MinWick={wick_min*100:.0f}% | RR={trr} | Fills={len(filled):<2} | W={len(wins):<2} L={len(losses):<2} | WR={wr:5.1f}% | NetPnL=${net_pnl:6.2f} | NetR={net_rr:5.1f}R | PF={pf:4.2f}")
