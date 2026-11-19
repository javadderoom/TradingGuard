"""
Comprehensive Forensic Audit of Last Week (Nov 9 - Nov 13, 2026)
1. Deep-dive into the red trades taken by the bot.
2. Market structure and regime breakdown day-by-day (Nov 9, 10, 11, 12, 13) for Gold, NQ, and GBPUSD.
3. Constructive Alpha Discovery: Identifying high-probability institutional setups that occurred last week.
"""

import sys
import os
import json
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import MetaTrader5 as mt5
from hitl.backtest.fast_screener import (
    screen_ict_session,
    detect_ny_trend_continuation,
    detect_nq_opening_range_breakout,
    detect_nq_intermarket_smt,
    detect_gold_judas_extreme_reversal,
    get_session_times_for_date
)
from hitl.backtest.session_clock import get_session_times_for_date
from hitl.replay_forensics import server_epoch_to_zones

if not mt5.initialize():
    print("[ERROR] MT5 failed to initialize")
    sys.exit(1)

START_DT = datetime.datetime(2026, 11, 9, 0, 0)
END_DT = datetime.datetime(2026, 11, 14, 0, 0)

print("=" * 95)
print("🔬 FORENSIC AUDIT OF LAST WEEK: NOVEMBER 9 - NOVEMBER 13, 2026")
print("=" * 95)

# 1. Fetch exact historical rates from MT5 for all 5 assets
symbols = ["XAUUSD_o", "NQ", "GBPUSD_o", "SPX", "YM"]
rates_m1 = {}
rates_m5 = {}
rates_h1 = {}
rates_d1 = {}

for sym in symbols:
    # M1 rates
    r_m1 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, START_DT - datetime.timedelta(days=2), END_DT)
    # M5 rates
    r_m5 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, START_DT - datetime.timedelta(days=5), END_DT)
    # H1 rates
    r_h1 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, START_DT - datetime.timedelta(days=30), END_DT)
    # D1 rates
    r_d1 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_D1, START_DT - datetime.timedelta(days=90), END_DT)

    rates_m1[sym] = pd.DataFrame(r_m1) if r_m1 is not None else pd.DataFrame()
    rates_m5[sym] = pd.DataFrame(r_m5) if r_m5 is not None else pd.DataFrame()
    rates_h1[sym] = pd.DataFrame(r_h1) if r_h1 is not None else pd.DataFrame()
    rates_d1[sym] = pd.DataFrame(r_d1) if r_d1 is not None else pd.DataFrame()

    print(f"Loaded {sym}: M1={len(rates_m1[sym]):,} | M5={len(rates_m5[sym]):,} | H1={len(rates_h1[sym]):,} | D1={len(rates_d1[sym]):,}")

# 2. Detailed day-by-day price action breakdown
week_dates = [
    datetime.date(2026, 11, 9),
    datetime.date(2026, 11, 10),
    datetime.date(2026, 11, 11),
    datetime.date(2026, 11, 12),
    datetime.date(2026, 11, 13),
]

days_summary = []
for d in week_dates:
    day_start_ts = int(datetime.datetime(d.year, d.month, d.day, 0, 0, tzinfo=datetime.timezone.utc).timestamp())
    day_end_ts = day_start_ts + 86400
    stimes = get_session_times_for_date(d)

    # Gold stats for day
    df_xau_m5 = rates_m5["XAUUSD_o"]
    sub_xau = df_xau_m5[(df_xau_m5['time'] >= day_start_ts) & (df_xau_m5['time'] < day_end_ts)]
    xau_open = sub_xau['open'].iloc[0] if not sub_xau.empty else 0
    xau_close = sub_xau['close'].iloc[-1] if not sub_xau.empty else 0
    xau_high = sub_xau['high'].max() if not sub_xau.empty else 0
    xau_low = sub_xau['low'].min() if not sub_xau.empty else 0
    xau_net = xau_close - xau_open
    xau_range = xau_high - xau_low

    # NQ stats for day
    df_nq_m5 = rates_m5["NQ"]
    sub_nq = df_nq_m5[(df_nq_m5['time'] >= day_start_ts) & (df_nq_m5['time'] < day_end_ts)]
    nq_open = sub_nq['open'].iloc[0] if not sub_nq.empty else 0
    nq_close = sub_nq['close'].iloc[-1] if not sub_nq.empty else 0
    nq_high = sub_nq['high'].max() if not sub_nq.empty else 0
    nq_low = sub_nq['low'].min() if not sub_nq.empty else 0
    nq_net = nq_close - nq_open
    nq_range = nq_high - nq_low

    # GBPUSD stats for day
    df_gbp_m5 = rates_m5["GBPUSD_o"]
    sub_gbp = df_gbp_m5[(df_gbp_m5['time'] >= day_start_ts) & (df_gbp_m5['time'] < day_end_ts)]
    gbp_open = sub_gbp['open'].iloc[0] if not sub_gbp.empty else 0
    gbp_close = sub_gbp['close'].iloc[-1] if not sub_gbp.empty else 0
    gbp_high = sub_gbp['high'].max() if not sub_gbp.empty else 0
    gbp_low = sub_gbp['low'].min() if not sub_gbp.empty else 0
    gbp_net = (gbp_close - gbp_open) * 10000
    gbp_range = (gbp_high - gbp_low) * 10000

    days_summary.append({
        "Date": d.strftime("%Y-%m-%d (%a)"),
        "Gold_Open": f"{xau_open:.2f}",
        "Gold_Close": f"{xau_close:.2f}",
        "Gold_Range": f"${xau_range:.2f}",
        "Gold_Net": f"{xau_net:+.2f}",
        "NQ_Range": f"{nq_range:.1f} pts",
        "NQ_Net": f"{nq_net:+.1f} pts",
        "Cable_Range": f"{gbp_range:.1f} pips",
        "Cable_Net": f"{gbp_net:+.1f} pips"
    })

print("\n--- DAILY MACRO REGIME & EXPANSION OVERVIEW ---")
df_day_sum = pd.DataFrame(days_summary)
print(df_day_sum.to_string(index=False))

with open("scratch/last_week_days_summary.json", "w") as f:
    json.dump(days_summary, f, indent=2)
