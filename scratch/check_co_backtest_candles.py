import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from hitl.replay_data import ReplayDataManager, SYMBOL_CATALOG

dm = ReplayDataManager()
for sym in ['XAUUSD_o', 'GBPUSD_o', 'NQ']:
    df = dm.load_m1_df(sym)
    print(f"=== {sym} ===")
    print("Total bars:", len(df))
    print("Min time:", df['time'].min(), pd.to_datetime(df['time'].min(), unit='s'))
    print("Max time:", df['time'].max(), pd.to_datetime(df['time'].max(), unit='s'))
    
    # Check if sorted
    is_sorted = df['time'].is_monotonic_increasing
    print("Is time monotonic increasing?", is_sorted)
    
    # Check duplicates
    dups = df['time'].duplicated().sum()
    print("Duplicate timestamps:", dups)
    
    # Look at November 2026 data
    t_nov1 = int(pd.Timestamp("2026-11-01").timestamp())
    df_nov = df[df['time'] >= t_nov1].copy()
    print(f"Bars in Nov 2026: {len(df_nov)}")
    if not df_nov.empty:
        df_nov = df_nov.reset_index(drop=True)
        diffs = df_nov['time'].diff()
        gaps = diffs[diffs > 60]
        print(f"Gaps (>60s) in Nov: {len(gaps)}")
        for idx in gaps.index[:10]:
            t_prev = df_nov.loc[idx-1, 'time']
            t_curr = df_nov.loc[idx, 'time']
            dt_prev = pd.to_datetime(t_prev, unit='s')
            dt_curr = pd.to_datetime(t_curr, unit='s')
            gap_min = (t_curr - t_prev) / 60
            # Weekend gap is normal, but what about weekday gaps?
            print(f"  Gap: {dt_prev} -> {dt_curr} ({gap_min:.1f} mins) [Day: {dt_prev.strftime('%a')}]")
