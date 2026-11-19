"""
Heal and update all Parquet files from MT5 terminal data.
Fills the Nov 4-5 gap in GBPUSD_o, syncs SPX, YM, NQ, XAUUSD_o up to right now.
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import MetaTrader5 as mt5
import pandas as pd
import datetime
from hitl.replay_data import ReplayDataManager, SYMBOL_CATALOG

if not mt5.initialize():
    print("Failed to initialize MT5")
    sys.exit(1)

dm = ReplayDataManager()

# 1. Specifically patch GBPUSD_o Nov 4-5 gap
print("Patching GBPUSD_o Nov 4-5 gap...")
t_from = datetime.datetime(2026, 11, 4, 18, 0)
t_to = datetime.datetime(2026, 11, 5, 20, 0)
rates_gbp = mt5.copy_rates_range("GBPUSD_o", mt5.TIMEFRAME_M1, t_from, t_to)
if rates_gbp is not None and len(rates_gbp) > 0:
    df_patch = pd.DataFrame(rates_gbp)
    cols = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
    for c in cols:
        if c not in df_patch.columns:
            df_patch[c] = 0.0
    df_patch = df_patch[cols]
    
    file_path = dm.cache_dir / SYMBOL_CATALOG["GBPUSD_o"]["cache_file"]
    df_existing = pd.read_parquet(file_path)
    df_merged = pd.concat([df_existing, df_patch], ignore_index=True)
    df_merged = df_merged.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    df_merged.to_parquet(file_path, index=False)
    print(f"GBPUSD_o gap patched! Total bars now: {len(df_merged)}")

# 2. Sync all symbols to latest moment
for sym in ["XAUUSD_o", "GBPUSD_o", "NQ", "SPX", "YM"]:
    print(f"Syncing {sym} to latest...")
    res = dm.sync_symbol_from_mt5(sym, days_back=10)
    print(f"  Result for {sym}: {res}")

print("\nAll parquet stores successfully synchronized!")
