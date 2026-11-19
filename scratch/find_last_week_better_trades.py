"""
Forensic Alpha Discovery: Finding Better Trades for Last Week (Nov 9 - Nov 13, 2026)
Exhaustively scans Gold, NQ, and GBPUSD across every session of last week:
1. SMT Divergence (NQ vs SPX/YM)
2. 15m Opening Range Breakout (NQ)
3. Trend Continuation Sweeps (Gold & Cable)
4. Statistical Extreme Judas Reversals (Gold)
Simulates exact order execution (entry, SL, TP, MFE, MAE, realized R, realized USD).
"""

import sys
import os
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import MetaTrader5 as mt5
from hitl.backtest.session_clock import get_session_times_for_date
from scratch.microstructure_optimizer import run_full_excursion_simulation
from hitl.replay_forensics import server_epoch_to_zones
from hitl.backtest.fast_screener import detect_ny_trend_continuation, detect_gold_judas_extreme_reversal

if not mt5.initialize():
    print("MT5 failed to initialize")
    sys.exit(1)

START_DT = datetime.datetime(2026, 11, 8, 20, 0) # Sunday open
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

    # Add datetime
    for df in [m1_data[sym], m5_data[sym], h1_data[sym], d1_data[sym]]:
        if not df.empty:
            df['dt'] = pd.to_datetime(df['time'], unit='s', utc=True)
            df['timestamp'] = df['time']

broker_spreads = {
    "XAUUSD_o": 0.22,
    "NQ": 1.1,
    "GBPUSD_o": 0.00010,
    "SPX": 0.5,
    "YM": 1.5
}

days = [
    datetime.date(2026, 11, 9),
    datetime.date(2026, 11, 10),
    datetime.date(2026, 11, 11),
    datetime.date(2026, 11, 12),
    datetime.date(2026, 11, 13),
]

discovered_setups = []

for d in days:
    stimes = get_session_times_for_date(d)
    lon_open_ts = int(stimes["london"]["utc_time"].timestamp())
    ny_open_ts = int(stimes["new_york"]["utc_time"].timestamp())
    nyse_open_ts = int(stimes["nyse_open"]["utc_time"].timestamp())
    day_start_ts = int(datetime.datetime(d.year, d.month, d.day, 0, 0, tzinfo=datetime.timezone.utc).timestamp())

    # =========================================================================
    # A. SCAN NQ 15m OPENING RANGE BREAKOUT (NYSE Cash Open)
    # =========================================================================
    df_nq_m1 = m1_data["NQ"]
    df_nq_m5 = m5_data["NQ"]
    df_nq_h1 = h1_data["NQ"]
    df_nq_d1 = d1_data["NQ"]

    # 15m OR bars: [nyse_open_ts .. nyse_open_ts + 900)
    or_bars = df_nq_m5[(df_nq_m5['time'] >= nyse_open_ts) & (df_nq_m5['time'] < nyse_open_ts + 900)]
    if not or_bars.empty:
        or_high = or_bars['high'].max()
        or_low = or_bars['low'].min()
        or_range = or_high - or_low

        # Window after OR: next 2.5 hours
        post_or_bars = df_nq_m5[(df_nq_m5['time'] >= nyse_open_ts + 900) & (df_nq_m5['time'] < nyse_open_ts + 9000)]
        for i, bar in post_or_bars.iterrows():
            c_range = bar['high'] - bar['low']
            body = abs(bar['close'] - bar['open'])
            if c_range <= 0 or (body / c_range) < 0.50:
                continue

            # Prior H1 trend
            h1_prior = df_nq_h1[df_nq_h1['time'] < bar['time']]
            if len(h1_prior) < 10:
                continue
            h1_close = h1_prior['close'].iloc[-1]
            h1_ema50 = h1_prior['close'].ewm(span=50, adjust=False).mean().iloc[-1]

            # Bullish Breakout
            if bar['close'] > or_high + 5.0 and h1_close > h1_ema50:
                entry = max(or_high, bar['open'])
                sl = bar['low'] - 8.0
                risk = entry - sl
                if 15.0 <= risk <= 60.0:
                    # Run forward simulation
                    m1_idx_list = df_nq_m1[df_nq_m1['time'] >= bar['time'] + 300].index
                    if not m1_idx_list.empty:
                        start_m1 = m1_idx_list[0]
                        sim = run_full_excursion_simulation(
                            df_m1=df_nq_m1,
                            start_m1_idx=start_m1,
                            decision="BUY",
                            entry=entry,
                            sl=sl,
                            target_rr=3.5,
                            symbol="NQ",
                            spread=1.1,
                            slippage=0.25,
                            commission_per_001_lot=0.10,
                            be_ratchet_rr=1.5,
                            ttl_minutes=60,
                            lot=0.01
                        )
                        discovered_setups.append({
                            "Date": str(d),
                            "Time": bar['dt'].strftime("%H:%M UTC"),
                            "Symbol": "NQ",
                            "Model": "MODEL-ISB-PC-01 (15m ORB)",
                            "Direction": "BUY",
                            "Entry": entry,
                            "SL": sl,
                            "Risk_Pts": round(risk, 1),
                            "Status": sim["status"],
                            "Realized_R": sim["realized_r"],
                            "PnL_USD_001": sim["realized_pnl_usd"],
                            "MFE_R": sim["mfe_r"],
                            "Notes": f"ORB High breakout ({or_high:.1f})"
                        })
                        break # 1 trade per session

            # Bearish Breakout
            elif bar['close'] < or_low - 5.0 and h1_close < h1_ema50:
                entry = min(or_low, bar['open'])
                sl = bar['high'] + 8.0
                risk = sl - entry
                if 15.0 <= risk <= 60.0:
                    m1_idx_list = df_nq_m1[df_nq_m1['time'] >= bar['time'] + 300].index
                    if not m1_idx_list.empty:
                        start_m1 = m1_idx_list[0]
                        sim = run_full_excursion_simulation(
                            df_m1=df_nq_m1,
                            start_m1_idx=start_m1,
                            decision="SELL",
                            entry=entry,
                            sl=sl,
                            target_rr=3.5,
                            symbol="NQ",
                            spread=1.1,
                            slippage=0.25,
                            commission_per_001_lot=0.10,
                            be_ratchet_rr=1.5,
                            ttl_minutes=60,
                            lot=0.01
                        )
                        discovered_setups.append({
                            "Date": str(d),
                            "Time": bar['dt'].strftime("%H:%M UTC"),
                            "Symbol": "NQ",
                            "Model": "MODEL-ISB-PC-01 (15m ORB)",
                            "Direction": "SELL",
                            "Entry": entry,
                            "SL": sl,
                            "Risk_Pts": round(risk, 1),
                            "Status": sim["status"],
                            "Realized_R": sim["realized_r"],
                            "PnL_USD_001": sim["realized_pnl_usd"],
                            "MFE_R": sim["mfe_r"],
                            "Notes": f"ORB Low breakdown ({or_low:.1f})"
                        })
                        break

    # =========================================================================
    # B. SCAN SMT DIVERGENCE (NQ vs SPX / YM)
    # =========================================================================
    df_spx_m5 = m5_data["SPX"]
    df_ym_m5 = m5_data["YM"]
    if not df_spx_m5.empty and not df_ym_m5.empty:
        spx_map = df_spx_m5.set_index('time')
        ym_map = df_ym_m5.set_index('time')

        # Asian High/Low of NQ, SPX, YM
        nq_asia = df_nq_m5[(df_nq_m5['time'] >= day_start_ts) & (df_nq_m5['time'] < lon_open_ts)]
        spx_asia = df_spx_m5[(df_spx_m5['time'] >= day_start_ts) & (df_spx_m5['time'] < lon_open_ts)]
        ym_asia = df_ym_m5[(df_ym_m5['time'] >= day_start_ts) & (df_ym_m5['time'] < lon_open_ts)]

        if not nq_asia.empty and not spx_asia.empty and not ym_asia.empty:
            nq_ah, nq_al = nq_asia['high'].max(), nq_asia['low'].min()
            spx_ah, spx_al = spx_asia['high'].max(), spx_asia['low'].min()
            ym_ah, ym_al = ym_asia['high'].max(), ym_asia['low'].min()

            # London window
            lon_bars = df_nq_m5[(df_nq_m5['time'] >= lon_open_ts) & (df_nq_m5['time'] < lon_open_ts + 12600)]
            smt_taken = False
            for i in range(len(lon_bars) - 3):
                if smt_taken: break
                b_t = lon_bars.iloc[i]
                t_val = b_t['time']
                if t_val not in spx_map.index or t_val not in ym_map.index: continue
                b_spx = spx_map.loc[t_val]
                b_ym = ym_map.loc[t_val]

                # Bearish SMT: NQ sweeps High, SPX or YM fails
                nq_sw_h = b_t['high'] > nq_ah
                spx_sw_h = b_spx['high'] > spx_ah
                ym_sw_h = b_ym['high'] > ym_ah

                if nq_sw_h and not (spx_sw_h and ym_sw_h):
                    # Check next 3 bars for FVG displacement
                    sweep_ext = b_t['high']
                    for j in range(1, 4):
                        b_fvg = lon_bars.iloc[i + j]
                        b_prev2 = lon_bars.iloc[i + j - 2]
                        disp = b_fvg['open'] - b_fvg['close']
                        if (b_fvg['high'] < b_prev2['low']) and disp >= 20.0:
                            entry = b_prev2['low']
                            sl = sweep_ext + 8.0
                            risk = sl - entry
                            if 15.0 <= risk <= 60.0:
                                m1_sub = df_nq_m1[df_nq_m1['time'] >= b_fvg['time'] + 300]
                                if not m1_sub.empty:
                                    sim = run_full_excursion_simulation(
                                        df_m1=df_nq_m1,
                                        start_m1_idx=m1_sub.index[0],
                                        decision="SELL",
                                        entry=entry,
                                        sl=sl,
                                        target_rr=2.5,
                                        symbol="NQ",
                                        spread=1.1,
                                        slippage=0.25,
                                        commission_per_001_lot=0.10,
                                        be_ratchet_rr=1.0,
                                        session_exit_utc_hour=21,
                                        ttl_minutes=60,
                                        lot=0.01
                                    )
                                    discovered_setups.append({
                                        "Date": str(d),
                                        "Time": b_fvg['dt'].strftime("%H:%M UTC"),
                                        "Symbol": "NQ",
                                        "Model": "MODEL-SMT-CD-03 (SMT)",
                                        "Direction": "SELL",
                                        "Entry": entry,
                                        "SL": sl,
                                        "Risk_Pts": round(risk, 1),
                                        "Status": sim["status"],
                                        "Realized_R": sim["realized_r"],
                                        "PnL_USD_001": sim["realized_pnl_usd"],
                                        "MFE_R": sim["mfe_r"],
                                        "Notes": "Bearish SMT Divergence (London)"
                                    })
                                    smt_taken = True
                                    break

                # Bullish SMT: NQ sweeps Low, SPX or YM fails
                nq_sw_l = b_t['low'] < nq_al
                spx_sw_l = b_spx['low'] < spx_al
                ym_sw_l = b_ym['low'] < ym_al

                if nq_sw_l and not (spx_sw_l and ym_sw_l) and not smt_taken:
                    sweep_ext = b_t['low']
                    for j in range(1, 4):
                        b_fvg = lon_bars.iloc[i + j]
                        b_prev2 = lon_bars.iloc[i + j - 2]
                        disp = b_fvg['close'] - b_fvg['open']
                        if (b_fvg['low'] > b_prev2['high']) and disp >= 20.0:
                            entry = b_prev2['high']
                            sl = sweep_ext - 8.0
                            risk = entry - sl
                            if 15.0 <= risk <= 60.0:
                                m1_sub = df_nq_m1[df_nq_m1['time'] >= b_fvg['time'] + 300]
                                if not m1_sub.empty:
                                    sim = run_full_excursion_simulation(
                                        df_m1=df_nq_m1,
                                        start_m1_idx=m1_sub.index[0],
                                        decision="BUY",
                                        entry=entry,
                                        sl=sl,
                                        target_rr=2.5,
                                        symbol="NQ",
                                        spread=1.1,
                                        slippage=0.25,
                                        commission_per_001_lot=0.10,
                                        be_ratchet_rr=1.0,
                                        session_exit_utc_hour=21,
                                        ttl_minutes=60,
                                        lot=0.01
                                    )
                                    discovered_setups.append({
                                        "Date": str(d),
                                        "Time": b_fvg['dt'].strftime("%H:%M UTC"),
                                        "Symbol": "NQ",
                                        "Model": "MODEL-SMT-CD-03 (SMT)",
                                        "Direction": "BUY",
                                        "Entry": entry,
                                        "SL": sl,
                                        "Risk_Pts": round(risk, 1),
                                        "Status": sim["status"],
                                        "Realized_R": sim["realized_r"],
                                        "PnL_USD_001": sim["realized_pnl_usd"],
                                        "MFE_R": sim["mfe_r"],
                                        "Notes": "Bullish SMT Divergence (London)"
                                    })
                                    smt_taken = True
                                    break

    # =========================================================================
    # C. SCAN GOLD TREND CONTINUATIONS & PRO-TREND SWEEPS
    # =========================================================================
    df_xau_m1 = m1_data["XAUUSD_o"]
    df_xau_m5 = m5_data["XAUUSD_o"]
    df_xau_h1 = h1_data["XAUUSD_o"]
    df_xau_d1 = d1_data["XAUUSD_o"]

    # Gold NY Open Trend Continuation (SETUP-ARCH-015)
    # Scan every bar in NY window [ny_open_ts .. nyse_open_ts + 3600]
    ny_window_bars = df_xau_m5[(df_xau_m5['time'] >= ny_open_ts) & (df_xau_m5['time'] <= nyse_open_ts + 3600)]
    gold_cont_taken = False
    for i, b_curr in ny_window_bars.iterrows():
        if gold_cont_taken: break
        # Extract past bars up to b_curr
        past_m5 = df_xau_m5[df_xau_m5['time'] <= b_curr['time']].tail(90).to_dict('records')
        past_h1 = df_xau_h1[df_xau_h1['time'] <= b_curr['time']].tail(60).to_dict('records')
        past_d1 = df_xau_d1[df_xau_d1['time'] <= b_curr['time']].tail(30).to_dict('records')

        has_cont, c_dir, c_entry, c_sl, c_desc = detect_ny_trend_continuation(
            bars_5m=past_m5,
            bars_1h=past_h1,
            symbol="XAUUSD_o",
            bars_1d=past_d1
        )
        if has_cont:
            risk = abs(c_entry - c_sl)
            m1_sub = df_xau_m1[df_xau_m1['time'] >= b_curr['time'] + 300]
            if not m1_sub.empty:
                decision = "BUY" if c_dir == "BULLISH" else "SELL"
                sim = run_full_excursion_simulation(
                    df_m1=df_xau_m1,
                    start_m1_idx=m1_sub.index[0],
                    decision=decision,
                    entry=c_entry,
                    sl=c_sl,
                    target_rr=2.5,
                    symbol="XAUUSD_o",
                    spread=0.22,
                    slippage=0.05,
                    commission_per_001_lot=0.10,
                    be_ratchet_rr=1.5,
                    ttl_minutes=60,
                    lot=0.01
                )
                discovered_setups.append({
                    "Date": str(d),
                    "Time": b_curr['dt'].strftime("%H:%M UTC"),
                    "Symbol": "XAUUSD_o",
                    "Model": "SETUP-ARCH-015 (NY Cont)",
                    "Direction": decision,
                    "Entry": c_entry,
                    "SL": c_sl,
                    "Risk_Pts": round(risk, 2),
                    "Status": sim["status"],
                    "Realized_R": sim["realized_r"],
                    "PnL_USD_001": sim["realized_pnl_usd"],
                    "MFE_R": sim["mfe_r"],
                    "Notes": c_desc[:50]
                })
                gold_cont_taken = True
                break

    # =========================================================================
    # D. SCAN GOLD JUDAS SWING REVERSAL (London & NY)
    # =========================================================================
    lon_ny_bars = df_xau_m5[(df_xau_m5['time'] >= lon_open_ts) & (df_xau_m5['time'] <= nyse_open_ts + 3600)]
    judas_taken = False
    for i, b_curr in lon_ny_bars.iterrows():
        if judas_taken: break
        past_m5 = df_xau_m5[df_xau_m5['time'] <= b_curr['time']].tail(60).to_dict('records')
        past_h1 = df_xau_h1[df_xau_h1['time'] <= b_curr['time']].tail(40).to_dict('records')
        past_d1 = df_xau_d1[df_xau_d1['time'] <= b_curr['time']].tail(20).to_dict('records')

        has_jsr, j_dir, j_entry, j_sl, j_desc = detect_gold_judas_extreme_reversal(
            bars_5m=past_m5,
            bars_1h=past_h1,
            bars_1d=past_d1,
            symbol="XAUUSD_o"
        )
        if has_jsr:
            risk = abs(j_entry - j_sl)
            m1_sub = df_xau_m1[df_xau_m1['time'] >= b_curr['time'] + 300]
            if not m1_sub.empty:
                decision = "BUY" if j_dir == "BULLISH" else "SELL"
                sim = run_full_excursion_simulation(
                    df_m1=df_xau_m1,
                    start_m1_idx=m1_sub.index[0],
                    decision=decision,
                    entry=j_entry,
                    sl=j_sl,
                    target_rr=2.0,
                    symbol="XAUUSD_o",
                    spread=0.22,
                    slippage=0.05,
                    commission_per_001_lot=0.10,
                    be_ratchet_rr=1.0,
                    ttl_minutes=60,
                    lot=0.01
                )
                discovered_setups.append({
                    "Date": str(d),
                    "Time": b_curr['dt'].strftime("%H:%M UTC"),
                    "Symbol": "XAUUSD_o",
                    "Model": "SETUP-ARCH-018 (Judas Rev)",
                    "Direction": decision,
                    "Entry": j_entry,
                    "SL": j_sl,
                    "Risk_Pts": round(risk, 2),
                    "Status": sim["status"],
                    "Realized_R": sim["realized_r"],
                    "PnL_USD_001": sim["realized_pnl_usd"],
                    "MFE_R": sim["mfe_r"],
                    "Notes": j_desc[:50]
                })
                judas_taken = True
                break

print("\n" + "=" * 95)
print("🎯 CONSTRUCTIVE ALPHA DISCOVERY: BETTER TRADES FOUND FOR LAST WEEK")
print("=" * 95)

if discovered_setups:
    df_disc = pd.DataFrame(discovered_setups)
    print(df_disc.to_string(index=False))
    
    # Summary
    wins = len(df_disc[df_disc['Status'] == 'WIN'])
    losses = len(df_disc[df_disc['Status'].str.contains('LOSS')])
    bes = len(df_disc[df_disc['Status'] == 'BREAKEVEN'])
    exp = len(df_disc[df_disc['Status'] == 'EXPIRED'])
    net_r = df_disc['Realized_R'].sum()
    net_usd = df_disc['PnL_USD_001'].sum()
    print("-" * 95)
    print(f"Total Discovered Opportunities: {len(df_disc)}")
    print(f"Record: {wins} Wins | {losses} Losses | {bes} Breakeven | {exp} Expired")
    print(f"Total Net Alpha: {net_r:+.2f} R")
    print(f"Total Net USD (0.01 lot): ${net_usd:+.2f}")
    
    df_disc.to_csv("scratch/last_week_better_trades.csv", index=False)
else:
    print("No setups matched criteria.")
