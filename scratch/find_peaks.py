import pandas as pd
import datetime
from zoneinfo import ZoneInfo

# Raw MT5 parquet: time column is epoch representing broker time (EET = UTC+2 in winter)
# Let's verify by matching with TradingView
df = pd.read_parquet('backtest_results/cache/M1_GBPUSD_o_2026.parquet')

# Convert MT5 broker epoch (which is at UTC+2) to:
# 1. Broker Server Time (MT5)
# 2. UTC Time (MT5 - 2h)
# 3. Tehran Time (UTC + 3h30m = MT5 + 1h30m)

# Since epoch in parquet is seconds from 1970 interpreted as UTC for broker time:
# e.g., 1794501300 -> 16:35:00
df['dt_broker'] = pd.to_datetime(df['time'], unit='s')
df['dt_utc'] = df['dt_broker'] - pd.Timedelta(hours=2)
df['dt_tehran'] = df['dt_utc'] + pd.Timedelta(hours=3, minutes=30)

# Resample to 5M using dt_utc as index
df_5m = df.set_index('dt_utc').resample('5min').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last'
}).dropna().reset_index()

df_5m['dt_broker'] = df_5m['dt_utc'] + pd.Timedelta(hours=2)
df_5m['dt_tehran'] = df_5m['dt_utc'] + pd.Timedelta(hours=3, minutes=30)

# Filter for today (2026-11-12)
today = df_5m[df_5m['dt_utc'].dt.date == datetime.date(2026, 11, 12)].copy()

print("Checking London start onwards...")
# London starts at 08:00 UTC (11:30 Tehran, 10:00 MT5)
after_london = today[today['dt_utc'] >= datetime.datetime(2026, 11, 12, 8, 0)].copy()

# Find all local peaks (swing highs)
peaks = []
for i in range(2, len(after_london) - 2):
    row = after_london.iloc[i]
    prev1 = after_london.iloc[i-1]
    prev2 = after_london.iloc[i-2]
    next1 = after_london.iloc[i+1]
    next2 = after_london.iloc[i+2]
    if row['high'] >= prev1['high'] and row['high'] >= prev2['high'] and row['high'] >= next1['high'] and row['high'] >= next2['high']:
        peaks.append(row)

peaks_df = pd.DataFrame(peaks)
print(f"Total swing peaks found after London open: {len(peaks_df)}")
for _, p in peaks_df.iterrows():
    print(f"UTC {p['dt_utc'].strftime('%H:%M')} | Tehran {p['dt_tehran'].strftime('%H:%M')} | Broker {p['dt_broker'].strftime('%H:%M')} | High={p['high']:.5f} Low={p['low']:.5f} Close={p['close']:.5f}")

# Print all candles between 08:00 UTC and 15:35 UTC
print("\n=== All Candles 08:00 to 15:35 UTC ===")
for _, c in after_london.iterrows():
    utc_str = c['dt_utc'].strftime('%H:%M')
    teh_str = c['dt_tehran'].strftime('%H:%M')
    brk_str = c['dt_broker'].strftime('%H:%M')
    print(f"UTC {utc_str} | Teh {teh_str} | Brk {brk_str} | O={c['open']:.5f} H={c['high']:.5f} L={c['low']:.5f} C={c['close']:.5f}")
