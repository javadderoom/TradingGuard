import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
import numpy as np
import datetime
from hitl.backtest.session_clock import get_session_times_for_date

df_m1 = pd.read_parquet('backtest_results/cache/M1_GBPUSD_o_2026.parquet')
df_m1.sort_values('time', inplace=True)
df_m1.reset_index(drop=True, inplace=True)

# Offset for Nov 12 (winter, UTC+2)
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

df_5m['date'] = df_5m['dt_utc'].dt.date
today_bars = df_5m[df_5m['date'] == datetime.date(2026, 11, 12)].copy().reset_index(drop=True)
print(f"Today 5M bars: {len(today_bars)}")

stimes = get_session_times_for_date(datetime.date(2026, 11, 12))
lon_open_dt = stimes["london"]["utc_time"]
ny_open_dt = stimes["new_york"]["utc_time"]
nyse_open_dt = stimes["nyse_open"]["utc_time"]

print(f"London Open: {lon_open_dt}")
print(f"NY Open: {ny_open_dt}")
print(f"NYSE Open: {nyse_open_dt}")

swing_highs = []
for i in range(2, len(today_bars)):
    cur_bar = today_bars.iloc[i]
    cur_dt = cur_bar['dt_utc']
    p = today_bars.iloc[i-2]
    # Check swing high condition
    cond_left = (p['high'] >= today_bars.iloc[i-3]['high']) if i >= 3 else True
    cond_right = (p['high'] >= today_bars.iloc[i-1]['high']) and (p['high'] >= cur_bar['high'])
    if cond_left and cond_right:
        if p['dt_utc'] >= lon_open_dt:
            swing_highs.append({'dt': p['dt_utc'], 'high': p['high']})
            print(f"Swing high at i={i-2}: dt={p['dt_utc'].strftime('%H:%M')} high={p['high']:.5f}")

print(f"Total swing highs registered: {len(swing_highs)}")

for i in range(2, len(today_bars)):
    cur_bar = today_bars.iloc[i]
    cur_dt = cur_bar['dt_utc']
    for sh in swing_highs:
        if cur_dt > sh['dt'] and cur_bar['high'] > sh['high']:
            sweep_amt = cur_bar['high'] - sh['high']
            bar_rng = cur_bar['high'] - cur_bar['low']
            upper_wick = (cur_bar['high'] - max(cur_bar['open'], cur_bar['close'])) / bar_rng if bar_rng > 0 else 0
            print(f"Sweep candidate: bar={cur_dt.strftime('%H:%M')} swept sh={sh['dt'].strftime('%H:%M')} (sh_h={sh['high']:.5f}, cur_h={cur_bar['high']:.5f}, diff={sweep_amt*10000:.1f} pips, wick={upper_wick*100:.1f}%, C<O={cur_bar['close'] < cur_bar['open']})")
