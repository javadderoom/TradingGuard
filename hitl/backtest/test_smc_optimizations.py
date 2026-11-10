"""
TradingGuard HITL - SMC Engine Optimization Matrix
Tests:
1. Breakeven threshold sensitivity (no BE, 1.0R, 1.5R, 1.8R, 2.0R, 2.2R, 2.5R)
2. Archetype pruning matrix:
   - Baseline: ARCH-001, ARCH-003, ARCH-004, ARCH-010, ARCH-011 (Calibrated)
   - Prune ARCH-001 (Judas Breaker)
   - Prune ARCH-004 (Expansion FVG)
   - Prune ARCH-011 (Nested Double MSS)
   - Keep only ARCH-003 and ARCH-010 (Confirmed MSS & Prominent Sweeps)
3. Session restriction matrix:
   - Restrict GBPUSD to London Sessions only (banning NY Open and NY Silver Bullet)
   - Restrict Gold to London Open + NY Open (banning London Continuation)
   - Restrict NQ to London Open only or NY Pre-Market only
4. Phase alignment:
   - Restrict GBPUSD to HTF_RETRACEMENT
   - Restrict Gold to PRO_EXPANSION + HTF_RETRACEMENT
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SCHEDULE_PATH = BASE_DIR / "backtest_results" / "smc_gap_audit" / "consolidated_full_1year_smc_trades_schedule.csv"
GOLD_ANNUAL_PATH = BASE_DIR / "backtest_results" / "gold_annual_4season_master_synthesis" / "annual_master_all_trades_ledger.csv"
GBP_ANNUAL_PATH = BASE_DIR / "backtest_results" / "gbpusd_annual_4season_master_synthesis" / "gbpusd_annual_master_all_trades_ledger.csv"

def analyze_sensitivity():
    df = pd.read_csv(SCHEDULE_PATH)
    calib = df[(df['is_calibrated'] == True) & (df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN']))].copy()

    def calc_stats(sub, name=""):
        n = len(sub)
        if n == 0:
            return {'Name': name, 'Fills': 0, 'Wins': 0, 'Losses': 0, 'BE': 0, 'WR': 0.0, 'Net_R': 0.0, 'PF': 0.0, 'Net_USD': 0.0, 'Max_DD_R': 0.0}
        w = (sub['status'] == 'WIN').sum()
        l = (sub['status'] == 'LOSS').sum()
        b = (sub['status'] == 'BREAKEVEN').sum()
        nr = sub['net_r'].sum()
        gw = sub[sub['net_r'] > 0]['net_r'].sum()
        gl = abs(sub[sub['net_r'] < 0]['net_r'].sum())
        pf = gw / max(0.001, gl)
        wr = (w / n) * 100.0
        pnl = sub['realized_usd'].sum()
        
        # Drawdown
        sub_c = sub.copy()
        sub_c['cum_r'] = sub_c['net_r'].cumsum()
        sub_c['hwm_r'] = sub_c['cum_r'].cummax()
        sub_c['dd_r'] = sub_c['hwm_r'] - sub_c['cum_r']
        max_dd = sub_c['dd_r'].max()
        
        return {
            'Name': name, 'Fills': n, 'Wins': w, 'Losses': l, 'BE': b,
            'WR': round(wr, 1), 'Net_R': round(nr, 2), 'PF': round(pf, 2),
            'Net_USD': round(pnl, 2), 'Max_DD_R': round(max_dd, 2)
        }

    results = []
    
    # 0. Baseline
    results.append(calc_stats(calib, "0. Baseline 3-Asset (Calibrated)"))

    # 1. Prune ARCH-001 completely
    sub1 = calib[calib['archetype_id'] != 'SETUP-ARCH-001']
    results.append(calc_stats(sub1, "1. Prune ARCH-001 (Judas Breaker)"))

    # 2. Prune ARCH-004 completely
    sub2 = calib[calib['archetype_id'] != 'SETUP-ARCH-004']
    results.append(calc_stats(sub2, "2. Prune ARCH-004 (Expansion FVG)"))

    # 3. Prune ARCH-001 and ARCH-004
    sub3 = calib[~calib['archetype_id'].isin(['SETUP-ARCH-001', 'SETUP-ARCH-004', 'SETUP-ARCH-011'])]
    results.append(calc_stats(sub3, "3. Pure Tier-1 (ARCH-003 & ARCH-010 Only)"))

    # 4. Prune ARCH-001 on GBP and NQ, keep on Gold
    sub4 = calib[~((calib['symbol'].isin(['GBPUSD', 'NQ'])) & (calib['archetype_id'] == 'SETUP-ARCH-001'))]
    results.append(calc_stats(sub4, "4. Prune ARCH-001 on GBPUSD & NQ"))

    # 5. Session: Restrict GBPUSD to London Sessions only (banning NY sessions)
    sub5 = calib[~((calib['symbol'] == 'GBPUSD') & (calib['session'].isin(['NY_Open', 'NY_Silver_Bullet'])))]
    results.append(calc_stats(sub5, "5. GBPUSD Gated to London Sessions Only"))

    # 6. Combined: GBP London Only + Prune ARCH-001 on NQ & GBP + Prune ARCH-011
    sub6 = calib[
        ~((calib['symbol'] == 'GBPUSD') & (calib['session'].isin(['NY_Open', 'NY_Silver_Bullet']))) &
        ~((calib['symbol'].isin(['GBPUSD', 'NQ'])) & (calib['archetype_id'] == 'SETUP-ARCH-001')) &
        (calib['archetype_id'] != 'SETUP-ARCH-011')
    ]
    results.append(calc_stats(sub6, "6. GBP London Only + Prune Toxic ARCH-001/011"))

    # 7. High Conviction: Pure Tier-1 (ARCH-003 + ARCH-010 on Gold & GBP) + Curated NQ
    sub7 = calib[
        calib['archetype_id'].isin(['SETUP-ARCH-003', 'SETUP-ARCH-010']) &
        ~((calib['symbol'] == 'GBPUSD') & (calib['session'].isin(['NY_Open', 'NY_Silver_Bullet'])))
    ]
    results.append(calc_stats(sub7, "7. Ultra-Pure Core: ARCH-003 & 010 (GBP London Only)"))

    # 8. All assets: Exclude losing sessions (Gold: no London_Continuation; GBP: no NY_Open/NY_SB; NQ: no NY_Pre_Market)
    sub8 = calib[
        ~((calib['symbol'] == 'XAUUSD') & (calib['session'] == 'London_Continuation')) &
        ~((calib['symbol'] == 'GBPUSD') & (calib['session'].isin(['NY_Open', 'NY_Silver_Bullet']))) &
        ~((calib['symbol'] == 'NQ') & (calib['session'] == 'NY_Pre_Market')) &
        (calib['archetype_id'] != 'SETUP-ARCH-011')
    ]
    results.append(calc_stats(sub8, "8. Session-Purified Suite (Peak Volume Windows Only)"))

    # 9. Session-Purified + Prune ARCH-001 on GBP & NQ
    sub9 = calib[
        ~((calib['symbol'] == 'XAUUSD') & (calib['session'] == 'London_Continuation')) &
        ~((calib['symbol'] == 'GBPUSD') & (calib['session'].isin(['NY_Open', 'NY_Silver_Bullet']))) &
        ~((calib['symbol'] == 'NQ') & (calib['session'] == 'NY_Pre_Market')) &
        ~((calib['symbol'].isin(['GBPUSD', 'NQ'])) & (calib['archetype_id'] == 'SETUP-ARCH-001')) &
        (calib['archetype_id'] != 'SETUP-ARCH-011')
    ]
    results.append(calc_stats(sub9, "9. Optimal Policy: Session-Purified + Toxic Archetypes Pruned"))

    # Detailed monthly evaluation of Optimal Policy
    opt = calib[
        (
            (calib['symbol'] == 'GBPUSD') & 
            (calib['session'].isin(['London_Open', 'London_Continuation'])) & 
            (calib['archetype_id'].isin(['SETUP-ARCH-002', 'SETUP-ARCH-003', 'SETUP-ARCH-010']))
        ) |
        (
            (calib['symbol'] == 'XAUUSD') & 
            (calib['session'].isin(['London_Open', 'NY_Open'])) & 
            (calib['archetype_id'].isin(['SETUP-ARCH-001', 'SETUP-ARCH-003', 'SETUP-ARCH-004', 'SETUP-ARCH-010']))
        ) |
        (
            (calib['symbol'] == 'NQ') & 
            (calib['session'] == 'London_Open') &
            (calib['archetype_id'] == 'SETUP-ARCH-001') &
            (calib['direction'] == 'SELL')
        )
    ].copy()

    opt = opt.sort_values(['date', 'symbol']).reset_index(drop=True)
    opt['cum_r'] = opt['net_r'].cumsum()
    opt['hwm_r'] = opt['cum_r'].cummax()
    opt['dd_r'] = opt['hwm_r'] - opt['cum_r']

    print("\n" + "=" * 80)
    print("DETAILED MONTH-BY-MONTH BREAKDOWN FOR OPTIMAL SMC POLICY:")
    print("=" * 80)
    print(f"{'Month':<10} | {'Fills':<5} | {'Wins':<4} | {'Losses':<6} | {'BE':<4} | {'WR%':<5} | {'Net R':<9} | {'PF':<5}")
    print("-" * 65)
    for m, g in opt.groupby('month'):
        gn, gw_cnt, gl_cnt, gb_cnt = len(g), (g['status'] == 'WIN').sum(), (g['status'] == 'LOSS').sum(), (g['status'] == 'BREAKEVEN').sum()
        gnr = g['net_r'].sum()
        ggw = g[g['net_r'] > 0]['net_r'].sum()
        ggl = abs(g[g['net_r'] < 0]['net_r'].sum())
        gpf = ggw / max(0.001, ggl)
        gwr = gw_cnt / gn * 100.0
        print(f"{m:<10} | {gn:<5} | {gw_cnt:<4} | {gl_cnt:<6} | {gb_cnt:<4} | {gwr:<5.1f} | {gnr:<+9.2f} | {gpf:<5.2f}")

    print("\n" + "=" * 80)
    print("ASSET BREAKDOWN FOR OPTIMAL SMC POLICY:")
    print("=" * 80)
    for sym, g in opt.groupby('symbol'):
        sn, sw, sl, sb = len(g), (g['status'] == 'WIN').sum(), (g['status'] == 'LOSS').sum(), (g['status'] == 'BREAKEVEN').sum()
        snr = g['net_r'].sum()
        sgw, sgl = g[g['net_r'] > 0]['net_r'].sum(), abs(g[g['net_r'] < 0]['net_r'].sum())
        spf = sgw / max(0.001, sgl)
        print(f"  {sym:<8} | Fills: {sn:<3} | W: {sw:<2} L: {sl:<2} BE: {sb:<2} | WR: {sw/sn*100:4.1f}% | Net R: {snr:+6.2f} | PF: {spf:.2f}")

    res_df = pd.DataFrame(results)
    print("\n" + "=" * 95)
    print("SMC OPTIMIZATION SENSITIVITY MATRIX:")
    print("=" * 95)
    print(res_df.to_string(index=False))
    return res_df

if __name__ == '__main__':
    analyze_sensitivity()

