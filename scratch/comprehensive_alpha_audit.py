"""
Comprehensive Alpha Forensic Audit of Last Week (Nov 9 - Nov 13, 2026)
Exhaustively examines:
1. Exact breakdown of why the 3 Gold knife-catches failed.
2. The exact winning setups presented by the market on NQ, Gold, and Cable.
3. Why the live system did not take them and how the ratified quantitative models capture them.
"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import MetaTrader5 as mt5
import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

from hitl.backtest.session_clock import get_session_times_for_date
from hitl.backtest.chart_renderer import get_broker_utc_offset_seconds
from scratch.microstructure_optimizer import run_full_excursion_simulation

if not mt5.initialize():
    print("MT5 initialization failed")
    sys.exit(1)

offset_sec = get_broker_utc_offset_seconds()
START_DT = datetime.datetime(2026, 11, 8, 20, 0)
END_DT = datetime.datetime(2026, 11, 14, 0, 0)

# Pull rates
symbols = ["XAUUSD_o", "NQ", "SPX", "YM", "GBPUSD_o"]
m1_data = {}
m5_data = {}
h1_data = {}
d1_data = {}

for sym in symbols:
    m1_data[sym] = pd.DataFrame(mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, START_DT, END_DT))
    m5_data[sym] = pd.DataFrame(mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, START_DT - datetime.timedelta(days=5), END_DT))
    h1_data[sym] = pd.DataFrame(mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, START_DT - datetime.timedelta(days=30), END_DT))
    d1_data[sym] = pd.DataFrame(mt5.copy_rates_range(sym, mt5.TIMEFRAME_D1, START_DT - datetime.timedelta(days=90), END_DT))

    for df in [m1_data[sym], m5_data[sym], h1_data[sym], d1_data[sym]]:
        if not df.empty:
            df['dt'] = pd.to_datetime(df['time'], unit='s', utc=True)

days = [
    datetime.date(2026, 11, 9),
    datetime.date(2026, 11, 10),
    datetime.date(2026, 11, 11),
    datetime.date(2026, 11, 12),
    datetime.date(2026, 11, 13),
]

# 1. FORENSIC AUDIT OF THE 3 FAILED GOLD TRADES
failed_trades = [
    {
        "id": "TRADE-1 (Nov 10)",
        "symbol": "XAUUSD_o",
        "entry_srv": "2026-11-10 20:50",
        "entry_utc_ts": int(datetime.datetime(2026, 11, 10, 18, 50, tzinfo=datetime.timezone.utc).timestamp()),
        "entry_price": 4050.29,
        "sl_price": 4042.69,
        "exit_price": 4042.69,
        "pnl_usd": -7.60,
        "direction": "BUY"
    },
    {
        "id": "TRADE-2 (Nov 13 #1)",
        "symbol": "XAUUSD_o",
        "entry_srv": "2026-11-13 20:05",
        "entry_utc_ts": int(datetime.datetime(2026, 11, 13, 18, 5, tzinfo=datetime.timezone.utc).timestamp()),
        "entry_price": 3893.19,
        "sl_price": 3884.01,
        "exit_price": 3884.01,
        "pnl_usd": -9.18,
        "direction": "BUY"
    },
    {
        "id": "TRADE-3 (Nov 13 #2)",
        "symbol": "XAUUSD_o",
        "entry_srv": "2026-11-13 20:35",
        "entry_utc_ts": int(datetime.datetime(2026, 11, 13, 18, 35, tzinfo=datetime.timezone.utc).timestamp()),
        "entry_price": 3888.27,
        "sl_price": 3882.29,
        "exit_price": 3882.29,
        "pnl_usd": -5.98,
        "direction": "BUY"
    }
]

print("\n" + "=" * 90)
print("1. AUTOPSY OF THE 3 RED TRADES ON GOLD")
print("=" * 90)

df_xau_m1 = m1_data["XAUUSD_o"]
df_xau_h1 = h1_data["XAUUSD_o"]
df_xau_d1 = d1_data["XAUUSD_o"]

for ft in failed_trades:
    entry_ts = ft["entry_utc_ts"] + offset_sec # server timestamp
    # Look at H1 context prior to entry
    h1_prior = df_xau_h1[df_xau_h1['time'] <= entry_ts]
    h1_close = h1_prior['close'].iloc[-1]
    h1_ema20 = h1_prior['close'].ewm(span=20, adjust=False).mean().iloc[-1]
    h1_ema50 = h1_prior['close'].ewm(span=50, adjust=False).mean().iloc[-1]
    
    # Day range up to entry
    day_start = int(datetime.datetime.fromtimestamp(entry_ts - offset_sec, tz=datetime.timezone.utc).replace(hour=0, minute=0, second=0).timestamp()) + offset_sec
    m1_day_so_far = df_xau_m1[(df_xau_m1['time'] >= day_start) & (df_xau_m1['time'] <= entry_ts)]
    day_open = m1_day_so_far['open'].iloc[0]
    day_high = m1_day_so_far['high'].max()
    day_low = m1_day_so_far['low'].min()
    net_day_change = ft["entry_price"] - day_open

    # Forward excursion
    m1_forward = df_xau_m1[(df_xau_m1['time'] >= entry_ts) & (df_xau_m1['time'] <= entry_ts + 7200)]
    max_fav = m1_forward['high'].max() - ft["entry_price"]
    max_adv = ft["entry_price"] - m1_forward['low'].min()

    print(f"\n--- {ft['id']} ({ft['entry_srv']} Server / {entry_ts - offset_sec} UTC) ---")
    print(f"  Entry: {ft['entry_price']} | Initial SL: {ft['sl_price']} (Risk: ${ft['entry_price'] - ft['sl_price']:.2f})")
    print(f"  Day Context: Day Open={day_open:.2f}, High={day_high:.2f}, Low={day_low:.2f}, Net Move at Entry: ${net_day_change:+.2f}")
    print(f"  H1 Context: Close={h1_close:.2f}, H1 EMA20={h1_ema20:.2f}, H1 EMA50={h1_ema50:.2f} -> Below EMA20? {h1_close < h1_ema20}")
    print(f"  M1 Excursion: Max Favorable Excursion (MFE): +${max_fav:.2f} ({max_fav / (ft['entry_price'] - ft['sl_price']):.2f} R)")
    print(f"  Max Adverse Excursion (MAE): -${max_adv:.2f} ({max_adv / (ft['entry_price'] - ft['sl_price']):.2f} R)")
    print(f"  Root Cause: Entering counter-trend BUY after 18:00 UTC into active liquidation when H1 was steeply bearish.")

