"""
Forensic Price Action Inspector for Nov 9 - Nov 13, 2026.
Analyzes exact M5/M1 price action during London and NY sessions to find the best institutional entries.
"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import MetaTrader5 as mt5
import datetime
import pandas as pd
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
symbols = ["NQ", "XAUUSD_o", "GBPUSD_o"]
m1 = {s: pd.DataFrame(mt5.copy_rates_range(s, mt5.TIMEFRAME_M1, START_DT, END_DT)) for s in symbols}
m5 = {s: pd.DataFrame(mt5.copy_rates_range(s, mt5.TIMEFRAME_M5, START_DT - datetime.timedelta(days=5), END_DT)) for s in symbols}
h1 = {s: pd.DataFrame(mt5.copy_rates_range(s, mt5.TIMEFRAME_H1, START_DT - datetime.timedelta(days=30), END_DT)) for s in symbols}

for s in symbols:
    for df in [m1[s], m5[s], h1[s]]:
        df['dt_utc'] = pd.to_datetime(df['time'] - offset_sec, unit='s', utc=True)
        df['timestamp'] = df['time']

# -----------------------------------------------------------------------------
# Case 1: Nov 9 (Mon) NQ +1,149 pt expansion day
# -----------------------------------------------------------------------------
print("\n" + "=" * 90)
print("CASE 1: Monday Nov 9 - NQ Pro-Trend Expansion (+1,149 pts)")
print("=" * 90)
# Look at London Open (08:00 UTC) and NY Open (13:00 / 14:30 UTC)
d_mon = datetime.date(2026, 11, 9)
st_mon = get_session_times_for_date(d_mon)
lon_ts_srv = int(st_mon["london"]["utc_time"].timestamp()) + offset_sec
ny_ts_srv = int(st_mon["new_york"]["utc_time"].timestamp()) + offset_sec
nyse_ts_srv = int(st_mon["nyse_open"]["utc_time"].timestamp()) + offset_sec

df_nq_m5 = m5["NQ"]
df_nq_m1 = m1["NQ"]

# Scan London open on NQ: Asian High breakout with retest
asia_bars = df_nq_m5[(df_nq_m5['time'] >= lon_ts_srv - 28800) & (df_nq_m5['time'] < lon_ts_srv)]
asia_h, asia_l = asia_bars['high'].max(), asia_bars['low'].min()
print(f"Asian Range: Low={asia_l:.1f}, High={asia_h:.1f} (Range: {asia_h - asia_l:.1f} pts)")

# London session bars [08:00 UTC .. 12:00 UTC]
lon_bars = df_nq_m5[(df_nq_m5['time'] >= lon_ts_srv) & (df_nq_m5['time'] < lon_ts_srv + 14400)]
for i, b in lon_bars.iterrows():
    if b['close'] > asia_h + 10.0:
        print(f"Asian High Breakout at {b['dt_utc'].strftime('%H:%M UTC')}: Close={b['close']:.1f}, High={b['high']:.1f}")
        # Next bar pullback
        entry = asia_h
        sl = b['low'] - 10.0
        risk = entry - sl
        sim = run_full_excursion_simulation(
            df_m1=df_nq_m1,
            start_m1_idx=df_nq_m1[df_nq_m1['time'] >= b['time'] + 300].index[0],
            decision="BUY",
            entry=b['close'],
            sl=b['low'] - 10.0,
            target_rr=3.0,
            symbol="NQ",
            spread=1.1,
            slippage=0.25,
            commission_per_001_lot=0.10,
            be_ratchet_rr=1.5,
            ttl_minutes=120,
            lot=0.01
        )
        print(f"  Simulation of Asian Breakout Continuation: Status={sim['status']}, Realized_R={sim['realized_r']:.2f}, PnL=${sim['realized_pnl_usd']:.2f}, MFE={sim['mfe_r']:.2f}R")
        break

# -----------------------------------------------------------------------------
# Case 2: Nov 10 (Tue) Gold Judas High Reversal / NY Breakdown (-$103 collapse)
# -----------------------------------------------------------------------------
print("\n" + "=" * 90)
print("CASE 2: Tuesday Nov 10 - Gold Bearish Breakdown (-$103 collapse)")
print("=" * 90)
d_tue = datetime.date(2026, 11, 10)
st_tue = get_session_times_for_date(d_tue)
lon_tue_srv = int(st_tue["london"]["utc_time"].timestamp()) + offset_sec
ny_tue_srv = int(st_tue["new_york"]["utc_time"].timestamp()) + offset_sec
df_xau_m5 = m5["XAUUSD_o"]
df_xau_m1 = m1["XAUUSD_o"]

# Look at London Session high: 4121.44, then NY open breakdown at 13:00-14:00 UTC
sub_xau_tue = df_xau_m5[(df_xau_m5['time'] >= lon_tue_srv) & (df_xau_m5['time'] <= ny_tue_srv + 7200)]
# Find when price breaks London Low (4068.47)
lon_low_pre_ny = df_xau_m5[(df_xau_m5['time'] >= lon_tue_srv) & (df_xau_m5['time'] < ny_tue_srv)]['low'].min()
print(f"London Low pre-NY: {lon_low_pre_ny:.2f}")

for i, b in sub_xau_tue[sub_xau_tue['time'] >= ny_tue_srv].iterrows():
    if b['close'] < lon_low_pre_ny - 2.0:
        entry = b['close']
        sl = b['high'] + 2.0
        risk = sl - entry
        print(f"NY Open Breakdown at {b['dt_utc'].strftime('%H:%M UTC')}: Entry={entry:.2f}, SL={sl:.2f} (Risk=${risk:.2f})")
        sim = run_full_excursion_simulation(
            df_m1=df_xau_m1,
            start_m1_idx=df_xau_m1[df_xau_m1['time'] >= b['time'] + 300].index[0],
            decision="SELL",
            entry=entry,
            sl=sl,
            target_rr=3.0,
            symbol="XAUUSD_o",
            spread=0.22,
            slippage=0.05,
            commission_per_001_lot=0.10,
            be_ratchet_rr=1.5,
            ttl_minutes=120,
            lot=0.01
        )
        print(f"  Simulation of NY Breakdown Short: Status={sim['status']}, Realized_R={sim['realized_r']:.2f}, PnL=${sim['realized_pnl_usd']:.2f}, MFE={sim['mfe_r']:.2f}R")
        break

# -----------------------------------------------------------------------------
# Case 3: Nov 12 (Thu) Gold NY Trend Continuation Short (-$115 collapse)
# -----------------------------------------------------------------------------
print("\n" + "=" * 90)
print("CASE 3: Thursday Nov 12 - Gold NY Trend Continuation Short (-$115 collapse)")
print("=" * 90)
d_thu = datetime.date(2026, 11, 12)
st_thu = get_session_times_for_date(d_thu)
ny_thu_srv = int(st_thu["new_york"]["utc_time"].timestamp()) + offset_sec

# Bar at 13:05 UTC (3929.66)
b_1305 = df_xau_m5[df_xau_m5['time'] == ny_thu_srv + 300].iloc[0]
entry_1305 = round(b_1305['close'], 2)
sl_1305 = round(b_1305['high'] + 1.50, 2)
risk_1305 = sl_1305 - entry_1305
print(f"13:05 UTC Continuation Trigger: Entry={entry_1305:.2f}, SL={sl_1305:.2f} (Risk=${risk_1305:.2f})")

sim_thu = run_full_excursion_simulation(
    df_m1=df_xau_m1,
    start_m1_idx=df_xau_m1[df_xau_m1['time'] >= b_1305['time'] + 300].index[0],
    decision="SELL",
    entry=entry_1305,
    sl=sl_1305,
    target_rr=3.5,
    symbol="XAUUSD_o",
    spread=0.22,
    slippage=0.05,
    commission_per_001_lot=0.10,
    be_ratchet_rr=1.5,
    ttl_minutes=180,
    lot=0.01
)
print(f"  Simulation: Status={sim_thu['status']}, Realized_R={sim_thu['realized_r']:.2f}, PnL=${sim_thu['realized_pnl_usd']:.2f}, MFE={sim_thu['mfe_r']:.2f}R")

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# Case 5: Monday Nov 9 - Gold & Cable London Sessions
# -----------------------------------------------------------------------------
print("\n" + "=" * 90)
print("CASE 5: Monday Nov 9 - Gold & Cable London Trend Analysis")
print("=" * 90)

for sym in ['XAUUSD_o', 'GBPUSD_o']:
    df_m5 = m5[sym]
    df_m1 = m1[sym]
    day_start_srv = int(datetime.datetime(2026, 11, 9, 0, 0, tzinfo=datetime.timezone.utc).timestamp()) + offset_sec
    asia = df_m5[(df_m5['time'] >= day_start_srv) & (df_m5['time'] < lon_ts_srv)]
    asia_h, asia_l = asia['high'].max(), asia['low'].min()
    print(f"{sym} Asian Range: {asia_l:.4f} - {asia_h:.4f}")

    # London session [08:00 - 13:00 UTC]
    lon_bars = df_m5[(df_m5['time'] >= lon_ts_srv) & (df_m5['time'] < ny_ts_srv)]
    # Look for pullback to Asian high after breakout or swing sweep
    print(f"  London Open price: {lon_bars['open'].iloc[0]:.4f}, High: {lon_bars['high'].max():.4f}, Low: {lon_bars['low'].min():.4f}")


