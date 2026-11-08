import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import pandas as pd
from pathlib import Path
import time

if not mt5.initialize():
    print("MT5 init failed:", mt5.last_error())
    exit(1)

symbol = "NQ"
mt5.symbol_select(symbol, True)

CACHE_DIR = Path("backtest_results/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

dt_start = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
dt_end = datetime(2026, 11, 6, 23, 59, 59, tzinfo=timezone.utc)

print(f"=== CACHING 2-MONTH MARKET DATA FOR {symbol} ({dt_start.date()} to {dt_end.date()}) ===")

# Download M5 with warmup
r_m5 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, dt_start - timedelta(days=7), dt_end)
r_m1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, dt_start, dt_end)
r_h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, dt_start - timedelta(days=60), dt_end)
r_d1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, dt_start - timedelta(days=200), dt_end)

df_m5 = pd.DataFrame(r_m5)
df_m1 = pd.DataFrame(r_m1)
df_h1 = pd.DataFrame(r_h1)
df_d1 = pd.DataFrame(r_d1)

print(f"M5 bars: {len(df_m5):,} | M1 bars: {len(df_m1):,} | H1 bars: {len(df_h1):,} | D1 bars: {len(df_d1):,}")

# Save parquets
df_m5.to_parquet(CACHE_DIR / "NQ_M5_2026.parquet")
df_m1.to_parquet(CACHE_DIR / "NQ_M1_2026.parquet")
df_h1.to_parquet(CACHE_DIR / "NQ_H1_2026.parquet")
df_d1.to_parquet(CACHE_DIR / "NQ_D1_2026.parquet")

print("Saved all NQ cache parquets successfully!")
mt5.shutdown()
