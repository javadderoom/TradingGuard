"""
Caches M5, M1, H1, D1 data for XAUUSD_o and GBPUSD_o from Aug 1 to Nov 7, 2026 directly from MT5.
"""

import sys
import datetime
from pathlib import Path
import pandas as pd
import MetaTrader5 as mt5

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CACHE_DIR = Path("backtest_results/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

dt_from = datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc)
dt_to = datetime.datetime(2026, 11, 7, tzinfo=datetime.timezone.utc)

timeframes = {
    "M5": mt5.TIMEFRAME_M5,
    "H1": mt5.TIMEFRAME_H1,
    "D1": mt5.TIMEFRAME_D1,
}

if not mt5.initialize():
    print("MT5 initialization failed!")
    sys.exit(1)

symbols = ["XAUUSD_o", "GBPUSD_o"]

for sym in symbols:
    clean_sym = "XAUUSD" if "XAU" in sym else "GBPUSD"
    for tf_name, tf_val in timeframes.items():
        out_path = CACHE_DIR / f"{clean_sym}_{tf_name}_2026.parquet"
        rates = mt5.copy_rates_range(sym, tf_val, dt_from, dt_to)
        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            df.to_parquet(out_path)
            print(f"✅ Cached {clean_sym} {tf_name}: {len(df)} bars -> {out_path}")
        else:
            print(f"❌ Failed to cache {clean_sym} {tf_name}")

    # For M1, download in monthly chunks
    m1_out_path = CACHE_DIR / f"{clean_sym}_M1_2026.parquet"
    chunks = [
        (datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)),
        (datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc)),
        (datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 11, 7, tzinfo=datetime.timezone.utc)),
    ]
    all_m1 = []
    for c_from, c_to in chunks:
        r = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, c_from, c_to)
        if r is not None and len(r) > 0:
            all_m1.append(pd.DataFrame(r))
    if all_m1:
        df_m1 = pd.concat(all_m1).drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)
        df_m1.to_parquet(m1_out_path)
        print(f"✅ Cached {clean_sym} M1: {len(df_m1)} bars -> {m1_out_path}")

mt5.shutdown()
print("All FX/Metals caching complete!")
