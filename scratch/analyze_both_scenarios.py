import pandas as pd
import datetime

# Load M1 GBPUSD 2026 data
df = pd.read_parquet('backtest_results/cache/M1_GBPUSD_o_2026.parquet')

# Convert broker epoch (EET = UTC+2 in winter) to UTC and Tehran
df['dt_broker'] = pd.to_datetime(df['time'], unit='s')
df['dt_utc'] = df['dt_broker'] - pd.Timedelta(hours=2)
df['dt_tehran'] = df['dt_utc'] + pd.Timedelta(hours=3, minutes=30)

# Resample to 5M on UTC index
df_5m = df.set_index('dt_utc').resample('5min').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'tick_volume': 'sum'
}).dropna().reset_index()

df_5m['dt_broker'] = df_5m['dt_utc'] + pd.Timedelta(hours=2)
df_5m['dt_tehran'] = df_5m['dt_utc'] + pd.Timedelta(hours=3, minutes=30)

nov12 = df_5m[df_5m['dt_utc'].dt.date == datetime.date(2026, 11, 12)].copy()

print("=================================================================")
print("SCENARIO A: TRADINGVIEW UTC CLOCK (Matching the screenshot axis)")
print("=================================================================")
# 12:00 UTC candle
bar_1200_utc = nov12[nov12['dt_utc'] == datetime.datetime(2026, 11, 12, 12, 0)].iloc[0]
print(f"12:00 UTC Candle: O={bar_1200_utc['open']:.5f} H={bar_1200_utc['high']:.5f} L={bar_1200_utc['low']:.5f} C={bar_1200_utc['close']:.5f}")

# Look at the swing high around 12:00 UTC
sub_midday = nov12[(nov12['dt_utc'] >= datetime.datetime(2026, 11, 12, 11, 30)) & (nov12['dt_utc'] <= datetime.datetime(2026, 11, 12, 12, 30))]
print("\nMidday Window (11:30 - 12:30 UTC):")
for _, r in sub_midday.iterrows():
    print(f"UTC {r['dt_utc'].strftime('%H:%M')} | Tehran {r['dt_tehran'].strftime('%H:%M')} | H={r['high']:.5f} L={r['low']:.5f} C={r['close']:.5f}")

# 14:00 - 14:40 UTC candles (where 14:20-14:30 sweeps 12:00)
sub_sweep = nov12[(nov12['dt_utc'] >= datetime.datetime(2026, 11, 12, 14, 0)) & (nov12['dt_utc'] <= datetime.datetime(2026, 11, 12, 15, 0))]
print("\nSweep & Rollover Window (14:00 - 15:00 UTC):")
for _, r in sub_sweep.iterrows():
    is_sweep = " <<< SWEPT 12:00 HIGH" if r['high'] > bar_1200_utc['high'] else ""
    print(f"UTC {r['dt_utc'].strftime('%H:%M')} | Tehran {r['dt_tehran'].strftime('%H:%M')} | O={r['open']:.5f} H={r['high']:.5f} L={r['low']:.5f} C={r['close']:.5f}{is_sweep}")

print("\n=================================================================")
print("SCENARIO B: TEHRAN CLOCK (12:00 Tehran vs 14:20-14:30 Tehran)")
print("=================================================================")
# 12:00 Tehran is 08:30 UTC
bar_1200_teh = nov12[nov12['dt_tehran'] == datetime.datetime(2026, 11, 12, 12, 0)].iloc[0]
print(f"12:00 Tehran Candle (08:30 UTC): O={bar_1200_teh['open']:.5f} H={bar_1200_teh['high']:.5f} L={bar_1200_teh['low']:.5f} C={bar_1200_teh['close']:.5f}")

# 14:00 - 14:45 Tehran (10:30 - 11:15 UTC)
sub_teh = nov12[(nov12['dt_tehran'] >= datetime.datetime(2026, 11, 12, 14, 0)) & (nov12['dt_tehran'] <= datetime.datetime(2026, 11, 12, 14, 45))]
print("\nTehran Midday Window (14:00 - 14:45 Tehran):")
for _, r in sub_teh.iterrows():
    is_sweep = " <<< SWEPT 12:00 TEHRAN HIGH" if r['high'] > bar_1200_teh['high'] else ""
    print(f"Tehran {r['dt_tehran'].strftime('%H:%M')} | UTC {r['dt_utc'].strftime('%H:%M')} | O={r['open']:.5f} H={r['high']:.5f} L={r['low']:.5f} C={r['close']:.5f}{is_sweep}")
