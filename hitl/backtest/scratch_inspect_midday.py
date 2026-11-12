import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone
from hitl.backtest.fast_screener import screen_ict_session
from hitl.screener_gate import tehran_hour_from_bar_time

mt5.initialize()
symbol = "XAUUSD_o" if mt5.symbol_info("XAUUSD_o") else "XAUUSD"

rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 500)
rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 100)
rates_d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 30)
mt5.shutdown()

df_m5 = pd.DataFrame(rates_m5)
df_m5['dt'] = pd.to_datetime(df_m5['time'], unit='s')
bars_m5 = df_m5.to_dict('records')

df_h1 = pd.DataFrame(rates_h1)
df_h1['dt'] = pd.to_datetime(df_h1['time'], unit='s')
bars_h1 = df_h1.to_dict('records')

df_d1 = pd.DataFrame(rates_d1)
df_d1['dt'] = pd.to_datetime(df_d1['time'], unit='s')
bars_d1 = df_d1.to_dict('records')

# Filter bars between 09:30 and 12:00
for idx, b in enumerate(bars_m5):
    dt = b['dt']
    if dt.strftime('%Y-%m-%d') == '2026-11-11' and 9 <= dt.hour <= 12:
        hist_m5 = bars_m5[:idx + 1]
        curr_bar = hist_m5[-1]
        bar_time = curr_bar['time']
        th_hour = tehran_hour_from_bar_time(bar_time)
        hist_h1 = [x for x in bars_h1 if x['time'] <= bar_time]
        hist_d1 = [x for x in bars_d1 if x['time'] <= bar_time]

        res = screen_ict_session(
            bars_5m=hist_m5,
            bars_1h=hist_h1,
            symbol=symbol,
            session_hour=th_hour,
            bars_1m=None,
            bars_1d=hist_d1,
            closed_bars_only=True
        )
        print(f"Bar {dt} (Tehran Hr {th_hour:.2f}) -> has_setup: {res.get('has_setup')}, type: {res.get('setup_type')}")
        print(f"   Reason: {res.get('reason')}")
