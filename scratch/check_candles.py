import pandas as pd
from zoneinfo import ZoneInfo
from datetime import datetime

tehran_tz = ZoneInfo("Asia/Tehran")
utc_tz = ZoneInfo("UTC")

for sym in ['GBPUSD_o', 'XAUUSD_o']:
    path = f'backtest_results/cache/M1_{sym}_2026.parquet'
    try:
        df = pd.read_parquet(path)
        print(f"\n==================== {sym} ====================")
        df['dt'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df.set_index('dt', inplace=True)
        
        # Resample to 5M
        ohlc = df.resample('5min').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
        
        # Filter for 2026-11-12
        mask = (ohlc.index >= '2026-11-12 05:00:00+00:00') & (ohlc.index <= '2026-11-12 16:00:00+00:00')
        sub = ohlc[mask].copy()
        print(f"5M bars count on 2026-11-12: {len(sub)}")
        for t, row in sub.iterrows():
            t_tehran = t.tz_convert(tehran_tz)
            if (t_tehran.hour in [11, 12, 13, 14, 15] and t_tehran.minute in [0, 5, 20, 25, 30, 35]):
                print(f"UTC {t.strftime('%H:%M')} | Tehran {t_tehran.strftime('%H:%M')} | O={row['open']:.5f} H={row['high']:.5f} L={row['low']:.5f} C={row['close']:.5f}")
    except Exception as e:
        print(f"{sym} error: {e}")
