import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import time
import pandas as pd
from pathlib import Path

if not mt5.initialize():
    print("MT5 init failed:", mt5.last_error())
    exit(1)

symbol = "BTCUSD"
CACHE_DIR = Path("backtest_results/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

dt_start = datetime(2026, 7, 1, tzinfo=timezone.utc)
dt_end = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)

print(f"=== DOWNLOADING TICKS & BUILDING M1 BARS FOR {symbol} ({dt_start.date()} to {dt_end.date()}) ===")

# Download M5, H1, D1 bars directly
r_m5 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, dt_start - timedelta(days=5), dt_end)
r_h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, dt_start - timedelta(days=60), dt_end)
r_d1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, dt_start - timedelta(days=200), dt_end)

print(f"M5 bars: {len(r_m5):,} | H1 bars: {len(r_h1):,} | D1 bars: {len(r_d1):,}")

# Download ticks in 7-day chunks
curr_start = dt_start
m1_bars_list = []

t0_all = time.time()
total_ticks = 0

while curr_start < dt_end:
    curr_end = min(curr_start + timedelta(days=7), dt_end)
    t0_chunk = time.time()
    ticks = mt5.copy_ticks_range(symbol, curr_start, curr_end, mt5.COPY_TICKS_ALL)
    if ticks is not None and len(ticks) > 0:
        total_ticks += len(ticks)
        # Convert ticks to M1 bars
        # Tick struct has 'time', 'bid', 'ask', 'last', 'volume'
        df_ticks = pd.DataFrame(ticks)
        # Use bid (or last if bid is 0)
        price_col = 'bid' if (df_ticks['bid'] > 0).all() else 'last'
        df_ticks['minute_epoch'] = (df_ticks['time'] // 60) * 60
        grp = df_ticks.groupby('minute_epoch')
        m1_chunk = grp[price_col].agg(['first', 'max', 'min', 'last', 'count']).reset_index()
        m1_chunk.columns = ['time', 'open', 'high', 'low', 'close', 'tick_volume']
        m1_chunk['spread'] = 150 # 1.50 in points
        m1_chunk['real_volume'] = 0
        m1_bars_list.append(m1_chunk)
        print(f"Chunk {curr_start.date()} to {curr_end.date()}: {len(ticks):,} ticks -> {len(m1_chunk):,} M1 bars ({time.time()-t0_chunk:.2f}s)")
    else:
        print(f"Warning: No ticks for {curr_start.date()} to {curr_end.date()}, error: {mt5.last_error()}")
    curr_start = curr_end

df_m1_summer = pd.concat(m1_bars_list, ignore_index=True).drop_duplicates(subset=['time']).sort_values('time')
df_m5_summer = pd.DataFrame(r_m5)
df_h1_summer = pd.DataFrame(r_h1)
df_d1_summer = pd.DataFrame(r_d1)

print(f"\nTotal ticks processed: {total_ticks:,} in {time.time()-t0_all:.2f}s")
print(f"Generated M1 bars: {len(df_m1_summer):,}")
print(f"M5 bars: {len(df_m5_summer):,}")

# Save parquets
df_m1_summer.to_parquet(CACHE_DIR / "BTCUSD_M1_SUMMER_2026.parquet")
df_m5_summer.to_parquet(CACHE_DIR / "BTCUSD_M5_SUMMER_2026.parquet")
df_h1_summer.to_parquet(CACHE_DIR / "BTCUSD_H1_SUMMER_2026.parquet")
df_d1_summer.to_parquet(CACHE_DIR / "BTCUSD_D1_SUMMER_2026.parquet")

print("Saved summer cache files successfully!")
mt5.shutdown()
