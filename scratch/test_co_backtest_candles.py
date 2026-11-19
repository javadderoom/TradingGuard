import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from hitl.replay_data import ReplayDataManager

dm = ReplayDataManager()

# Test 5M candles for XAUUSD_o from 2026-11-11 00:00 to 2026-11-13 23:59:59
start_epoch = int(pd.Timestamp("2026-11-11 00:00:00").timestamp())
end_epoch = int(pd.Timestamp("2026-11-13 23:59:59").timestamp())

for sym in ['XAUUSD_o', 'GBPUSD_o', 'NQ']:
    res = dm.get_candles(symbol=sym, tf='5M', start_epoch=start_epoch, end_epoch=end_epoch)
    bars = res['bars']
    print(f"\n=== {sym} (5M) ===")
    print(f"Total 5M bars returned: {len(bars)}")
    if bars:
        df_bars = pd.DataFrame(bars)
        df_bars['dt'] = pd.to_datetime(df_bars['time'], unit='s')
        print(f"First bar: {df_bars['dt'].iloc[0]} ({df_bars['time'].iloc[0]})")
        print(f"Last bar:  {df_bars['dt'].iloc[-1]} ({df_bars['time'].iloc[-1]})")
        
        # Check gaps between 5M bars
        diffs = df_bars['time'].diff()
        gaps = diffs[diffs > 300]
        print(f"Gaps (>300s): {len(gaps)}")
        for idx in gaps.index[:10]:
            p_dt = df_bars.loc[idx-1, 'dt']
            c_dt = df_bars.loc[idx, 'dt']
            print(f"  Gap: {p_dt} -> {c_dt} (gap = {(df_bars.loc[idx, 'time'] - df_bars.loc[idx-1, 'time'])/60:.0f} mins)")
