import MetaTrader5 as mt5
import datetime

mt5.initialize()
t_from = datetime.datetime(2026, 11, 6, 0, 0)
t_to = datetime.datetime(2026, 11, 6, 23, 59)
rates = mt5.copy_rates_range('BTCUSD', mt5.TIMEFRAME_M5, t_from, t_to)
print(f"M5 bars count on Friday Nov 06: {len(rates) if rates is not None else 0}")
if rates is not None and len(rates) > 0:
    t0 = datetime.datetime.fromtimestamp(rates[0]['time'])
    t1 = datetime.datetime.fromtimestamp(rates[-1]['time'])
    print(f"First bar: {t0} Open: {rates[0]['open']}")
    print(f"Last bar: {t1} Close: {rates[-1]['close']}")
    lows = [r['low'] for r in rates]
    highs = [r['high'] for r in rates]
    print(f"Day Low: {min(lows):.2f}, Day High: {max(highs):.2f}, Range: {max(highs)-min(lows):.2f}")
mt5.shutdown()
