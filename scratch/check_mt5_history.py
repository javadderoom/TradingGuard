import sys, os
sys.path.insert(0, os.path.abspath("."))
import MetaTrader5 as mt5
import datetime
from hitl.replay_forensics import server_epoch_to_zones

if not mt5.initialize():
    print("MT5 failed to initialize")
    sys.exit(1)

print("=== MT5 TERMINAL HISTORY AUDIT ===")
for sym in ['XAUUSD_o', 'NQ', 'GBPUSD_o', 'SPX', 'YM']:
    rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, datetime.datetime(2026, 1, 1), datetime.datetime(2026, 11, 15))
    if rates is not None and len(rates) > 0:
        z0 = server_epoch_to_zones(int(rates[0]['time']))
        z1 = server_epoch_to_zones(int(rates[-1]['time']))
        print(f"{sym} M1 in MT5: {len(rates):,} bars | {z0['date_str']} {z0['srv_str']} -> {z1['date_str']} {z1['srv_str']}")
    else:
        print(f"{sym} M1 in MT5: 0 bars returned")

    rates_m5 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, datetime.datetime(2026, 1, 1), datetime.datetime(2026, 11, 15))
    if rates_m5 is not None and len(rates_m5) > 0:
        z0 = server_epoch_to_zones(int(rates_m5[0]['time']))
        z1 = server_epoch_to_zones(int(rates_m5[-1]['time']))
        print(f"{sym} M5 in MT5: {len(rates_m5):,} bars | {z0['date_str']} {z0['srv_str']} -> {z1['date_str']} {z1['srv_str']}")
    else:
        print(f"{sym} M5 in MT5: 0 bars returned")
