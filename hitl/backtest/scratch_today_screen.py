import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone
from hitl.backtest.fast_screener import screen_ict_session
from hitl.screener_gate import tehran_hour_from_bar_time

if not mt5.initialize():
    print("MT5 initialization failed")
    exit(1)

symbol = "XAUUSD_o" if mt5.symbol_info("XAUUSD_o") else "XAUUSD"
print("Using symbol:", symbol)

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

print(f"M5 range: {df_m5['dt'].iloc[0]} to {df_m5['dt'].iloc[-1]}")

today_indices = [i for i, b in enumerate(bars_m5) if b['dt'].strftime('%Y-%m-%d') == '2026-11-11']
print(f"Today M5 bars count: {len(today_indices)}")

found_setups = []
for idx in today_indices:
    hist_m5 = bars_m5[:idx + 1]
    curr_bar = hist_m5[-1]
    bar_time = curr_bar['time']
    th_hour = tehran_hour_from_bar_time(bar_time)
    hist_h1 = [b for b in bars_h1 if b['time'] <= bar_time]
    hist_d1 = [b for b in bars_d1 if b['time'] <= bar_time]
    
    res = screen_ict_session(
        bars_5m=hist_m5,
        bars_1h=hist_h1,
        symbol=symbol,
        session_hour=th_hour,
        bars_1m=None,
        bars_1d=hist_d1,
        closed_bars_only=True
    )
    if res.get('has_setup') and res.get('setup_type') != 'NONE':
        found_setups.append((curr_bar['dt'], th_hour, res))

print(f"Total setups found today: {len(found_setups)}")
for dt, th, res in found_setups:
    print(f"Time: {dt} (Tehran Hr: {th:.2f}) -> Arch: {res.get('archetype_id')} | Type: {res.get('setup_type')} | Entry: {res.get('entry_ref')} | SL: {res.get('sl_ref')} | Reason: {res.get('reason')}")
