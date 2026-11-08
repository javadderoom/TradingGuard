import os
import sys
from pathlib import Path
import datetime
import pandas as pd
import MetaTrader5 as mt5

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = BASE_DIR / 'backtest_results' / 'cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def cache_data():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return

    sym = 'BTCUSD'
    t_from = datetime.datetime(2026, 9, 1, 0, 0)
    t_to = datetime.datetime(2026, 11, 8, 23, 59)

    print("Fetching M5 bars from Sep 1 to Nov 8, 2026...")
    m5_rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, t_from, t_to)
    if m5_rates is None or len(m5_rates) == 0:
        print("Failed to fetch M5 rates")
        return

    df_m5 = pd.DataFrame(m5_rates)
    m5_cache_path = CACHE_DIR / 'BTCUSD_M5_2026.parquet'
    df_m5.to_parquet(m5_cache_path)
    t0_m5 = datetime.datetime.fromtimestamp(df_m5['time'].iloc[0])
    t1_m5 = datetime.datetime.fromtimestamp(df_m5['time'].iloc[-1])
    print(f"M5 bars cached: {len(df_m5)} rows ({t0_m5} to {t1_m5}) -> {m5_cache_path}")

    print("Fetching M1 bars from Sep 1 to Nov 8, 2026...")
    # Since M1 is large (~100,000 bars), let's fetch in chunks if needed or directly
    m1_rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, t_from, t_to)
    if m1_rates is None or len(m1_rates) == 0:
        print("Direct range copy returned None, fetching in 2-week chunks...")
        chunks = []
        cur_start = t_from
        while cur_start < t_to:
            cur_end = min(cur_start + datetime.timedelta(days=14), t_to)
            chunk = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, cur_start, cur_end)
            if chunk is not None and len(chunk) > 0:
                chunks.append(pd.DataFrame(chunk))
                print(f"  Fetched {len(chunk)} M1 bars ({cur_start} to {cur_end})")
            cur_start = cur_end
        if chunks:
            df_m1 = pd.concat(chunks).drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)
        else:
            print("Failed to fetch M1 chunks")
            return
    else:
        df_m1 = pd.DataFrame(m1_rates)

    m1_cache_path = CACHE_DIR / 'BTCUSD_M1_2026.parquet'
    df_m1.to_parquet(m1_cache_path)
    t0_m1 = datetime.datetime.fromtimestamp(df_m1['time'].iloc[0])
    t1_m1 = datetime.datetime.fromtimestamp(df_m1['time'].iloc[-1])
    print(f"M1 bars cached: {len(df_m1)} rows ({t0_m1} to {t1_m1}) -> {m1_cache_path}")

    # Also fetch H1 and D1 bars
    print("Fetching H1 bars...")
    h1_rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, datetime.datetime(2026, 1, 1), t_to)
    if h1_rates is not None:
        df_h1 = pd.DataFrame(h1_rates)
        df_h1.to_parquet(CACHE_DIR / 'BTCUSD_H1_2026.parquet')
        print(f"H1 bars cached: {len(df_h1)} rows")

    print("Fetching D1 bars...")
    d1_rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_D1, datetime.datetime(2025, 1, 1), t_to)
    if d1_rates is not None:
        df_d1 = pd.DataFrame(d1_rates)
        df_d1.to_parquet(CACHE_DIR / 'BTCUSD_D1_2026.parquet')
        print(f"D1 bars cached: {len(df_d1)} rows")

    mt5.shutdown()
    print("Cache creation complete!")

if __name__ == '__main__':
    cache_data()
