import pandas as pd
import numpy as np
import datetime
from zoneinfo import ZoneInfo
from hitl.backtest.evaluator import evaluate_council_decision, get_default_broker_spread

# Load GBPUSD M1 2026
df_m1 = pd.read_parquet('backtest_results/cache/M1_GBPUSD_o_2026.parquet')

# Convert broker epoch (EET = UTC+2 in winter, UTC+3 in summer) to UTC and Tehran
# We use standard ZoneInfo logic or session clock
# Let's inspect session clock dynamic offset
from hitl.backtest.session_clock import get_session_times_for_date

# Convert M1 DataFrame to list of dicts for evaluator
df_m1['dt_broker'] = pd.to_datetime(df_m1['time'], unit='s')
# Broker is UTC+2 in winter, UTC+3 in summer
# Let's find UTC time by matching with broker DST:
# In Europe, DST starts last Sunday of March, ends last Sunday of October.
# During DST: Broker = UTC+3. Outside DST: Broker = UTC+2.
def get_broker_utc_offset(dt_series):
    # Vectorized check for European DST
    # March last Sunday to October last Sunday
    year = dt_series.dt.year
    # Approximate or exact:
    # A cleaner way: convert through ZoneInfo('Europe/Athens') or 'Europe/Bucharest' which is EET/EEST
    return pd.to_datetime(dt_series).dt.tz_localize('UTC') # We will handle dynamically

print("Loading data...")
df_m1.sort_values('time', inplace=True)
df_m1.reset_index(drop=True, inplace=True)

# Build 5M bars from M1
df_m1['dt_utc'] = pd.to_datetime(df_m1['time'], unit='s') - pd.Timedelta(hours=2) # default winter offset, will refine
df_5m = df_m1.set_index('dt_utc').resample('5min').agg({
    'time': 'first',
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'tick_volume': 'sum'
}).dropna().reset_index()

print(f"Total 5M bars: {len(df_5m)}")
