import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import datetime
from hitl.replay_data import ReplayDataManager, SYMBOL_CATALOG

dm = ReplayDataManager()

for sym, meta in SYMBOL_CATALOG.items():
    file_path = dm.cache_dir / meta["cache_file"]
    if not file_path.exists():
        print(f"File missing for {sym}: {file_path}")
        continue
    df = pd.read_parquet(file_path)
    df = df.sort_values("time").reset_index(drop=True)
    df['dt'] = pd.to_datetime(df['time'], unit='s')
    
    diffs = df['time'].diff()
    # Gaps larger than 10 minutes (600s)
    large_gaps = df[diffs > 600].copy()
    
    # Filter out normal weekend gaps (Friday 23:00+ to Sunday/Monday 00:00+)
    # and daily 1-hour maintenance gaps (23:59 to 01:00)
    abnormal_gaps = []
    for idx, row in large_gaps.iterrows():
        t_prev = df.loc[idx - 1, 'time']
        t_curr = row['time']
        dt_prev = df.loc[idx - 1, 'dt']
        dt_curr = row['dt']
        gap_hours = (t_curr - t_prev) / 3600.0
        
        # Weekend check: prev is Friday, curr is Sunday/Monday
        is_weekend = (dt_prev.weekday() == 4 and dt_curr.weekday() in (6, 0))
        # Daily roll check: 23:50+ to 01:05 (approx 1h)
        is_daily_roll = (gap_hours < 2.0 and dt_prev.hour in (22, 23) and dt_curr.hour in (0, 1))
        
        if not is_weekend and not is_daily_roll:
            abnormal_gaps.append((dt_prev, dt_curr, gap_hours, t_prev, t_curr))
            
    print(f"\n=======================================================")
    print(f"Symbol: {sym} ({meta['display_name']}) | Total Bars: {len(df)}")
    print(f"Range: {df['dt'].iloc[0]} to {df['dt'].iloc[-1]}")
    print(f"Abnormal Weekday Gaps: {len(abnormal_gaps)}")
    for g in abnormal_gaps[:10]:
        print(f"  Gap: {g[0]} -> {g[1]} ({g[2]:.2f} hours / {g[2]*60:.0f} mins) [Day: {g[0].strftime('%a')} to {g[1].strftime('%a')}]")
