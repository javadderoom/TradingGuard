import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone
from hitl.backtest.fast_screener import (
    screen_ict_session,
    detect_breaker_and_mss,
    detect_prominent_sweep_and_mss,
    get_session_times_for_date
)
from hitl.screener_gate import tehran_hour_from_bar_time

mt5.initialize()
symbol = "XAUUSD_o" if mt5.symbol_info("XAUUSD_o") else "XAUUSD"

rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 500)
rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 100)
rates_d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 30)
mt5.shutdown()

df_m5 = pd.DataFrame(rates_m5)
df_m5['dt'] = pd.to_datetime(df_m5['time'], unit='s')
bars_m5 = df_m5.to_dict('records')

# Find bar 2026-11-11 10:00:00 or 10:05:00
target_dt = '2026-11-11 10:00:00'
target_idx = [i for i, b in enumerate(bars_m5) if str(b['dt']) == target_dt][0]

hist_m5 = bars_m5[:target_idx + 1]
curr_bar = hist_m5[-1]
bar_time = curr_bar['time']
th_hour = tehran_hour_from_bar_time(bar_time)

print(f"Target bar: {curr_bar['dt']} | epoch: {bar_time} | Tehran Hr: {th_hour}")

# Let's inspect session_window
session_window = hist_m5[-84:-10] if len(hist_m5) >= 84 else hist_m5[:-10]
range_high = max(b['high'] for b in session_window)
range_low = min(b['low'] for b in session_window)
print(f"Session window: {len(session_window)} bars | range_high: {range_high} | range_low: {range_low}")

recent_bars = hist_m5[-10:]
recent_high = max(b['high'] for b in recent_bars)
recent_low = min(b['low'] for b in recent_bars)
pierced_high = recent_high >= range_high
current_price = curr_bar['close']
print(f"recent_bars[-10] range: {recent_bars[0]['dt']} to {recent_bars[-1]['dt']}")
print(f"recent_high: {recent_high} | pierced_high: {pierced_high} | current_price: {current_price}")


# Check detect_prominent_sweep_and_mss
res_prom = detect_prominent_sweep_and_mss(hist_m5, symbol)
print(f"detect_prominent_sweep_and_mss: {res_prom}")

# Check detect_breaker_and_mss
res_breaker = detect_breaker_and_mss(hist_m5, lookback=24, symbol=symbol)
print(f"detect_breaker_and_mss: {res_breaker}")
