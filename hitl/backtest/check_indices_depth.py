import MetaTrader5 as mt5
from datetime import datetime, timezone
import pandas as pd

if not mt5.initialize():
    print("MT5 init failed")
    exit(1)

symbols = ['NQ', 'SPX', 'YM', 'FDAX']
for sym in symbols:
    mt5.symbol_select(sym, True)
    r_m5 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 50000)
    r_m1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 100000)
    
    m5_len = len(r_m5) if r_m5 is not None else 0
    m1_len = len(r_m1) if r_m1 is not None else 0
    m5_first = datetime.fromtimestamp(r_m5[0]['time']) if m5_len > 0 else 'None'
    m1_first = datetime.fromtimestamp(r_m1[0]['time']) if m1_len > 0 else 'None'
    
    print(f"[{sym}] M5 bars: {m5_len:,} (from {m5_first}) | M1 bars: {m1_len:,} (from {m1_first})")

mt5.shutdown()
