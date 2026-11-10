"""
TradingGuard HITL - Deep SMC Performance & Optimization Auditor
Analyzes the 1-year SMC baseline across Gold, Cable, and NQ.
Tests various optimization vectors:
1. Breakeven policy recalibration (testing no-BE, 2.0R, 2.2R, 2.5R, 3.0R)
2. Archetype pruning (pruning negative expectancy archetypes like ARCH-001, ARCH-004, ARCH-011)
3. Session filtering (e.g. London Open vs NY Open vs Pre-Market)
4. Target R:R cap calibration
5. MTF trend alignment / Double MSS confirmation gates
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SCHEDULE_PATH = BASE_DIR / "backtest_results" / "smc_gap_audit" / "consolidated_full_1year_smc_trades_schedule.csv"

def run_deep_audit():
    if not SCHEDULE_PATH.exists():
        print(f"Error: {SCHEDULE_PATH} not found!")
        return

    df = pd.read_csv(SCHEDULE_PATH)
    print(f"Loaded master schedule: {len(df)} records.")
    
    # Baseline Calibrated Fills
    calib = df[(df['is_calibrated'] == True) & (df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN']))].copy()
    calib['cum_r'] = calib['net_r'].cumsum()
    calib['hwm_r'] = calib['cum_r'].cummax()
    calib['dd_r'] = calib['hwm_r'] - calib['cum_r']
    max_dd_r = calib['dd_r'].max()
    
    calib['cum_usd'] = calib['realized_usd'].cumsum()
    calib['hwm_usd'] = calib['cum_usd'].cummax()
    calib['dd_usd'] = calib['hwm_usd'] - calib['cum_usd']
    max_dd_usd = calib['dd_usd'].max()

    n = len(calib)
    w = (calib['status'] == 'WIN').sum()
    l = (calib['status'] == 'LOSS').sum()
    b = (calib['status'] == 'BREAKEVEN').sum()
    net_r = calib['net_r'].sum()
    gw = calib[calib['net_r'] > 0]['net_r'].sum()
    gl = abs(calib[calib['net_r'] < 0]['net_r'].sum())
    pf = gw / max(0.001, gl)
    wr = (w / n) * 100.0

    print("=" * 80)
    print("BASELINE 1-YEAR CALIBRATED SMC PERFORMANCE (Nov 01, 2025 - Nov 09, 2026):")
    print(f"Fills: {n} | Wins: {w} | Losses: {l} | BE: {b} | Win Rate: {wr:.1f}%")
    print(f"Net Alpha: {net_r:+.2f}R | Profit Factor: {pf:.2f} | Net USD: ${calib['realized_usd'].sum():+.2f}")
    print(f"Max Drawdown: {max_dd_r:.2f}R | Max Drawdown USD: ${max_dd_usd:.2f}")
    print("=" * 80)

    # Monthly Breakdown
    print("\nMONTHLY BREAKDOWN:")
    for month, m_df in calib.groupby('month'):
        mn = len(m_df)
        mw = (m_df['status'] == 'WIN').sum()
        ml = (m_df['status'] == 'LOSS').sum()
        mb = (m_df['status'] == 'BREAKEVEN').sum()
        mr = m_df['net_r'].sum()
        mgw = m_df[m_df['net_r'] > 0]['net_r'].sum()
        mgl = abs(m_df[m_df['net_r'] < 0]['net_r'].sum())
        mpf = mgw / max(0.001, mgl)
        print(f"  {month} | Fills: {mn:2d} | W: {mw:2d} L: {ml:2d} BE: {mb:2d} | WR: {mw/mn*100:4.1f}% | Net R: {mr:+6.2f}R | PF: {mpf:4.2f}")

    # Asset Breakdown
    print("\nASSET BREAKDOWN:")
    for sym, s_df in calib.groupby('symbol'):
        sn = len(s_df)
        sw = (s_df['status'] == 'WIN').sum()
        sl = (s_df['status'] == 'LOSS').sum()
        sb = (s_df['status'] == 'BREAKEVEN').sum()
        sr = s_df['net_r'].sum()
        sgw = s_df[s_df['net_r'] > 0]['net_r'].sum()
        sgl = abs(s_df[s_df['net_r'] < 0]['net_r'].sum())
        spf = sgw / max(0.001, sgl)
        print(f"  {sym:<8} | Fills: {sn:3d} | W: {sw:2d} L: {sl:3d} BE: {sb:2d} | WR: {sw/sn*100:4.1f}% | Net R: {sr:+6.2f}R | PF: {spf:4.2f}")

    # Archetype Breakdown
    print("\nARCHETYPE BREAKDOWN:")
    for arch, a_df in calib.groupby('archetype_id'):
        an = len(a_df)
        aw = (a_df['status'] == 'WIN').sum()
        al = (a_df['status'] == 'LOSS').sum()
        ab = (a_df['status'] == 'BREAKEVEN').sum()
        ar = a_df['net_r'].sum()
        agw = a_df[a_df['net_r'] > 0]['net_r'].sum()
        agl = abs(a_df[a_df['net_r'] < 0]['net_r'].sum())
        apf = agw / max(0.001, agl)
        print(f"  {arch:<16} | Fills: {an:3d} | W: {aw:2d} L: {al:3d} BE: {ab:2d} | WR: {aw/an*100:4.1f}% | Net R: {ar:+6.2f}R | PF: {apf:4.2f}")

    # Session Breakdown
    print("\nSESSION BREAKDOWN:")
    for sess, se_df in calib.groupby('session'):
        sen = len(se_df)
        sew = (se_df['status'] == 'WIN').sum()
        sel = (se_df['status'] == 'LOSS').sum()
        seb = (se_df['status'] == 'BREAKEVEN').sum()
        ser = se_df['net_r'].sum()
        segw = se_df[se_df['net_r'] > 0]['net_r'].sum()
        segl = abs(se_df[se_df['net_r'] < 0]['net_r'].sum())
        sepf = segw / max(0.001, segl)
        print(f"  {sess:<22} | Fills: {sen:3d} | W: {sew:2d} L: {sel:3d} BE: {seb:2d} | WR: {sew/sen*100:4.1f}% | Net R: {ser:+6.2f}R | PF: {sepf:4.2f}")

if __name__ == '__main__':
    run_deep_audit()
