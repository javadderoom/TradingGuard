import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import pandas as pd
from pathlib import Path

if not mt5.initialize():
    print("MT5 init failed:", mt5.last_error())
    exit(1)

CACHE_DIR = Path("backtest_results/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

dt_start = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
dt_end = datetime(2026, 11, 6, 23, 59, 59, tzinfo=timezone.utc)

for symbol in ['SPX', 'YM']:
    print(f"\n=== CACHING 3-MONTH MARKET DATA FOR {symbol} ({dt_start.date()} to {dt_end.date()}) ===")
    mt5.symbol_select(symbol, True)
    
    r_m5 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, dt_start - timedelta(days=7), dt_end)
    df_m5 = pd.DataFrame(r_m5)
    
    m1_chunks = []
    # August
    r_aug = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, datetime(2026, 8, 1, tzinfo=timezone.utc), datetime(2026, 9, 1, tzinfo=timezone.utc))
    if r_aug is not None and len(r_aug) > 0:
        m1_chunks.append(pd.DataFrame(r_aug))
        
    # September
    r_sep = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, datetime(2026, 9, 1, tzinfo=timezone.utc), datetime(2026, 10, 1, tzinfo=timezone.utc))
    if r_sep is not None and len(r_sep) > 0:
        m1_chunks.append(pd.DataFrame(r_sep))
        
    # October
    r_oct = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 11, 1, tzinfo=timezone.utc))
    if r_oct is not None and len(r_oct) > 0:
        m1_chunks.append(pd.DataFrame(r_oct))
        
    # November
    r_nov = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, datetime(2026, 11, 1, tzinfo=timezone.utc), dt_end)
    if r_nov is not None and len(r_nov) > 0:
        m1_chunks.append(pd.DataFrame(r_nov))
        
    df_m1 = pd.concat(m1_chunks, ignore_index=True).drop_duplicates(subset=['time']).sort_values(by='time')
    
    r_h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, dt_start - timedelta(days=60), dt_end)
    r_d1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, dt_start - timedelta(days=200), dt_end)
    
    df_h1 = pd.DataFrame(r_h1)
    df_d1 = pd.DataFrame(r_d1)
    
    print(f"Downloaded {symbol}: {len(df_m5):,} M5 bars | {len(df_m1):,} M1 bars | {len(df_h1):,} H1 bars | {len(df_d1):,} D1 bars")
    
    df_m5.to_parquet(CACHE_DIR / f"{symbol}_M5_2026.parquet")
    df_m1.to_parquet(CACHE_DIR / f"{symbol}_M1_2026.parquet")
    df_h1.to_parquet(CACHE_DIR / f"{symbol}_H1_2026.parquet")
    df_d1.to_parquet(CACHE_DIR / f"{symbol}_D1_2026.parquet")

print("\nSaved all SPX and YM cache parquets successfully!")
mt5.shutdown()
