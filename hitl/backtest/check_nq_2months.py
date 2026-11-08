import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import pandas as pd
from pathlib import Path
import time

if not mt5.initialize():
    print("MT5 init failed:", mt5.last_error())
    exit(1)

symbol = "NQ"
if not mt5.symbol_select(symbol, True):
    print(f"Failed to select {symbol}")
    exit(1)

CACHE_DIR = Path("backtest_results/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

dt_start = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
dt_end = datetime(2026, 11, 6, 23, 59, 59, tzinfo=timezone.utc)

print(f"=== CHECKING & DOWNLOADING 2-MONTH DATA FOR {symbol} ({dt_start.date()} to {dt_end.date()}) ===")

# Download M5, H1, D1 bars
r_m5 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, dt_start - timedelta(days=5), dt_end)
r_h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, dt_start - timedelta(days=60), dt_end)
r_d1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, dt_start - timedelta(days=200), dt_end)

print(f"M5 bars: {len(r_m5) if r_m5 is not None else 0:,}")
print(f"H1 bars: {len(r_h1) if r_h1 is not None else 0:,}")
print(f"D1 bars: {len(r_d1) if r_d1 is not None else 0:,}")

# Check M1 bars directly
r_m1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, dt_start, dt_end)
print(f"M1 bars from copy_rates_range: {len(r_m1) if r_m1 is not None else 0:,}")

if r_m1 is not None and len(r_m1) > 0:
    t0_m1 = datetime.fromtimestamp(r_m1[0]['time'], tz=timezone.utc)
    t1_m1 = datetime.fromtimestamp(r_m1[-1]['time'], tz=timezone.utc)
    print(f"M1 range: from {t0_m1} to {t1_m1}")

# Check ticks if M1 is partial
if r_m1 is None or len(r_m1) < 50000:
    print("Checking ticks for September 1 to September 17...")
    ticks = mt5.copy_ticks_range(symbol, dt_start, dt_start + timedelta(days=2), mt5.COPY_TICKS_ALL)
    print("Early September sample ticks:", len(ticks) if ticks is not None else 0)

mt5.shutdown()
