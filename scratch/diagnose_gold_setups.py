import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import MetaTrader5 as mt5
import datetime
from hitl.backtest.session_clock import get_session_times_for_date
from hitl.backtest.chart_renderer import get_broker_utc_offset_seconds
import pandas as pd

if not mt5.initialize():
    print("MT5 failed")
    exit(1)

offset_sec = get_broker_utc_offset_seconds()
START_DT = datetime.datetime(2026, 11, 8, 20, 0)
END_DT = datetime.datetime(2026, 11, 14, 0, 0)

m5 = pd.DataFrame(mt5.copy_rates_range('XAUUSD_o', mt5.TIMEFRAME_M5, START_DT - datetime.timedelta(days=5), END_DT))
h1 = pd.DataFrame(mt5.copy_rates_range('XAUUSD_o', mt5.TIMEFRAME_H1, START_DT - datetime.timedelta(days=30), END_DT))
d1 = pd.DataFrame(mt5.copy_rates_range('XAUUSD_o', mt5.TIMEFRAME_D1, START_DT - datetime.timedelta(days=90), END_DT))

for d in [datetime.date(2026, 11, 10), datetime.date(2026, 11, 12)]:
    stimes = get_session_times_for_date(d)
    lon_utc = int(stimes['london']['utc_time'].timestamp())
    ny_utc = int(stimes['new_york']['utc_time'].timestamp())
    nyse_utc = int(stimes['nyse_open']['utc_time'].timestamp())
    day_start_utc = int(datetime.datetime(d.year, d.month, d.day, 0, 0, tzinfo=datetime.timezone.utc).timestamp())
    
    sub = m5[(m5['time'] - offset_sec >= ny_utc) & (m5['time'] - offset_sec <= nyse_utc + 3600)]
    print(f"\n=== {d} ===")
    
    for i, b in sub.iterrows():
        b_time_utc = b['time'] - offset_sec
        b_dt = datetime.datetime.fromtimestamp(b_time_utc, tz=datetime.timezone.utc)
        
        # prior bars
        m5_day = m5[(m5['time'] - offset_sec >= day_start_utc) & (m5['time'] - offset_sec <= b_time_utc)]
        asia_bars = m5_day[m5_day['time'] - offset_sec < lon_utc]
        post_lon = m5_day[m5_day['time'] - offset_sec >= lon_utc]
        
        asia_h = asia_bars['high'].max()
        asia_l = asia_bars['low'].min()
        lon_l = post_lon['low'].min()
        
        # check prior 6 bars sweep
        m5_prior = m5[m5['time'] < b['time']].tail(6)
        prior_6_h = m5_prior['high'].max()
        prior_6_l = m5_prior['low'].min()
        
        swept_p6_h = b['high'] > prior_6_h
        swept_p6_l = b['low'] < prior_6_l
        
        c_range = b['high'] - b['low']
        upper_wick = b['high'] - max(b['open'], b['close'])
        lower_wick = min(b['open'], b['close']) - b['low']
        
        # H1 trend
        h1_prior = h1[h1['time'] < b['time']]
        h1_close = h1_prior['close'].iloc[-1]
        h1_ema50 = h1_prior['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        
        # Pullback check
        retrace = b['high'] - lon_l
        move_down = asia_l - lon_l
        pullback_pct = (retrace / move_down * 100) if move_down > 0 else 0
        
        if swept_p6_h or swept_p6_l:
            print(f"{b_dt.strftime('%H:%M UTC')}: C={b['close']:.2f}, R={c_range:.2f}, SwH={swept_p6_h}, SwL={swept_p6_l}, UpWick={upper_wick:.2f}, Pullback={pullback_pct:.1f}%, H1_EMA50_align={h1_close < h1_ema50}")
