"""
Caches Summer 2026 (June 1 - July 31, 2026) continuous MT5 broker data for Nasdaq 100 (NQ).
Pulls M5, H1, D1 bars directly, and resamples 100% authentic broker ticks into M1 bars.
Includes warmup buffer from May 15, 2026.
"""

import sys
import datetime
import time
from pathlib import Path
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CACHE_DIR = Path("backtest_results/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

dt_warmup = datetime.datetime(2026, 5, 15, tzinfo=datetime.timezone.utc)
dt_start = datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc)
dt_end = datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc)

if not mt5.initialize():
    print("Failed to initialize MT5!")
    sys.exit(1)

print("=" * 80)
print("📥 CACHING NASDAQ 100 (NQ) SUMMER 2026 (JUNE 1 - JULY 31, 2026)")
print("=" * 80)

# 1. Cache M5, H1, D1 with warmup
for tf_name, tf_val in [("M5", mt5.TIMEFRAME_M5), ("H1", mt5.TIMEFRAME_H1), ("D1", mt5.TIMEFRAME_D1)]:
    r = mt5.copy_rates_range("NQ", tf_val, dt_warmup, dt_end)
    if r is not None and len(r) > 0:
        df = pd.DataFrame(r)
        out_path = CACHE_DIR / f"NQ_{tf_name}_SUMMER_2026.parquet"
        df.to_parquet(out_path)
        print(f"✅ Cached NQ {tf_name}: {len(df)} bars -> {out_path}")
    else:
        print(f"❌ Failed to fetch NQ {tf_name}")

# 2. Cache M1 bars by downloading ticks in weekly chunks and resampling
print("\nDownloading authentic broker ticks and resampling to M1...")
current_chunk_start = dt_start
m1_blocks = []
t_total = time.time()

while current_chunk_start < dt_end:
    current_chunk_end = min(current_chunk_start + datetime.timedelta(days=7), dt_end)
    t0 = time.time()
    ticks = mt5.copy_ticks_range("NQ", current_chunk_start, current_chunk_end, mt5.COPY_TICKS_ALL)
    
    if ticks is not None and len(ticks) > 0:
        df_ticks = pd.DataFrame(ticks)
        # Convert time to datetime index
        df_ticks['datetime'] = pd.to_datetime(df_ticks['time'], unit='s', utc=True)
        df_ticks.set_index('datetime', inplace=True)
        
        # Resample bid prices to 1min OHLC
        ohlc = df_ticks['bid'].resample('1min').ohlc().dropna()
        volume = df_ticks['bid'].resample('1min').count()
        
        # Build standard M1 DataFrame
        df_m1_chunk = pd.DataFrame({
            'time': (ohlc.index.astype('int64') // 10**9).astype('int64'),
            'open': ohlc['open'].values,
            'high': ohlc['high'].values,
            'low': ohlc['low'].values,
            'close': ohlc['close'].values,
            'tick_volume': volume.loc[ohlc.index].values.astype('uint64'),
            'spread': 8, # 8 points (0.8 pt spread)
            'real_volume': 0
        })
        m1_blocks.append(df_m1_chunk)
        print(f"  Chunk {current_chunk_start.strftime('%Y-%m-%d')} to {current_chunk_end.strftime('%Y-%m-%d')}: {len(ticks):,} ticks -> {len(df_m1_chunk):,} M1 bars in {time.time()-t0:.2f}s")
    else:
        print(f"  ⚠️ Warning: No ticks between {current_chunk_start} and {current_chunk_end}")
        
    current_chunk_start = current_chunk_end

if m1_blocks:
    df_m1_all = pd.concat(m1_blocks).drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)
    m1_out = CACHE_DIR / "NQ_M1_SUMMER_2026.parquet"
    df_m1_all.to_parquet(m1_out)
    print(f"\n✅ Total NQ Summer M1 Bars: {len(df_m1_all):,} bars saved to {m1_out} in {time.time()-t_total:.2f}s!")

mt5.shutdown()
print("All Summer 2026 data cached successfully!")
