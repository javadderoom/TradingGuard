"""
TradingGuard HITL - Full-Year 4-Season Master Quantitative Synthesis (2026)
Consolidates all 4 seasons of Gold (XAUUSD_o) Standalone Audits:
- Winter 2026: January 2 - February 27 (41 Days, 164 Sessions)
- Spring 2026: March 1 - April 30 (43 Days, 172 Sessions)
- Summer 2026: July 1 - August 31 (44 Days, 176 Sessions)
- Autumn 2026: September 1 - November 4 (47 Days, 188 Sessions)

Total Scope:
- 175 Trading Days
- 700 Institutional Sessions
- ~240,000 Continuous M1 Bars
- Over 60 Million Raw Broker Ticks Evaluated End-to-End
"""

import sys
import json
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "backtest_results" / "gold_annual_4season_master_synthesis"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def run_annual_master_synthesis():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 90)
    print("🏆 TRADINGGUARD - 2026 FULL-YEAR 4-SEASON MASTER QUANTITATIVE SYNTHESIS")
    print("Instrument: XAUUSD_o (Gold Standalone) | 175 Trading Days | 700 Institutional Sessions")
    print("=" * 90)

    # 1. Load Ledgers
    seasons = {
        'Winter': BASE_DIR / "backtest_results" / "gold_winter_2month_audit" / "winter_all_trades_ledger.csv",
        'Spring': BASE_DIR / "backtest_results" / "gold_spring_2month_audit" / "spring_all_trades_ledger.csv",
        'Summer': BASE_DIR / "backtest_results" / "gold_oos_2month_audit" / "oos_all_trades_ledger.csv",
        'Autumn': BASE_DIR / "backtest_results" / "gold_2month_quant_audit" / "autumn_all_trades_ledger.csv"
    }

    dfs = []
    for s_name, path in seasons.items():
        if path.exists():
            df = pd.read_csv(path)
            df['season'] = s_name
            dfs.append(df)
            print(f"Loaded {s_name}: {len(df)} candidate setup records.")
        else:
            print(f"⚠️ Warning: Missing {s_name} ledger at {path}")

    if not dfs:
        print("❌ Error: No season ledgers found!")
        return

    master_df = pd.concat(dfs, ignore_index=True)
    master_df.to_csv(OUTPUT_DIR / "annual_master_all_trades_ledger.csv", index=False)
    print(f"\n✅ Master Ledger Compiled: {len(master_df)} total trade opportunities.")

    def calc_stats(sub):
        n = len(sub)
        if n == 0:
            return {'fills': 0, 'wins': 0, 'losses': 0, 'be': 0, 'wr': 0.0, 'net_r': 0.0, 'pf': 0.0, 'ev': 0.0}
        w = len(sub[sub['status'] == 'WIN'])
        l = len(sub[sub['status'] == 'LOSS'])
        b = len(sub[sub['status'] == 'BREAKEVEN'])
        net_r = sub['net_r'].sum()
        gw = sub[sub['net_r'] > 0]['net_r'].sum()
        gl = abs(sub[sub['net_r'] < 0]['net_r'].sum())
        pf = round(gw / max(0.001, gl), 2)
        wr = round((w / n) * 100.0, 1)
        ev = round(net_r / n, 3)
        return {'fills': n, 'wins': w, 'losses': l, 'be': b, 'wr': wr, 'net_r': round(net_r, 2), 'pf': pf, 'ev': ev}

    # Baseline: All fills across all seasons
    base_fills = master_df[master_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
    st_base_annual = calc_stats(base_fills)

    # Calibrated: Exclude NY Silver Bullet, Exclude ARCH-002, ARCH-009
    calib_fills = master_df[
        (master_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])) &
        (master_df['session'] != 'NY_Silver_Bullet') &
        (~master_df['archetype_id'].isin(['SETUP-ARCH-002', 'SETUP-ARCH-009']))
    ]
    st_calib_annual = calc_stats(calib_fills)

    print("\n" + "=" * 90)
    print("📊 2026 ANNUAL MASTER HEAD-TO-HEAD: BASELINE VS CALIBRATED SUITE")
    print("=" * 90)
    print(f"ANNUAL BASELINE SUITE:   {st_base_annual['fills']} Fills | {st_base_annual['wins']}W - {st_base_annual['losses']}L - {st_base_annual['be']}BE | WR: {st_base_annual['wr']}% | Net: {st_base_annual['net_r']:+0.1f}R | PF: {st_base_annual['pf']} | EV: {st_base_annual['ev']:+0.3f}R")
    print(f"ANNUAL CALIBRATED SUITE: {st_calib_annual['fills']} Fills | {st_calib_annual['wins']}W - {st_calib_annual['losses']}L - {st_calib_annual['be']}BE | WR: {st_calib_annual['wr']}% | Net: {st_calib_annual['net_r']:+0.1f}R | PF: {st_calib_annual['pf']} | EV: {st_calib_annual['ev']:+0.3f}R")
    print("=" * 90)

    # Seasonal Progression Table
    print("\n📍 SEASONAL PROGRESSION BREAKDOWN (CALIBRATED SUITE):")
    season_metrics = {}
    for s_name in ['Winter', 'Spring', 'Summer', 'Autumn']:
        s_sub = calib_fills[calib_fills['season'] == s_name]
        st = calc_stats(s_sub)
        season_metrics[s_name] = st
        print(f"  * {s_name:<8} (2 Months): {st['fills']:>3} Fills | {st['wins']:>2}W - {st['losses']:>2}L - {st['be']:>2}BE | WR: {st['wr']:>5.1f}% | Net: {st['net_r']:>+6.1f}R | PF: {st['pf']:>4.2f} | EV: {st['ev']:>+5.3f}R")

    # Archetype Breakdown Across Full Year
    print("\n📍 FULL-YEAR PERFORMANCE BY SETUP ARCHETYPE (CALIBRATED SUITE):")
    arch_metrics = {}
    for arch in sorted(calib_fills['archetype_id'].dropna().unique()):
        a_sub = calib_fills[calib_fills['archetype_id'] == arch]
        st = calc_stats(a_sub)
        arch_name = a_sub['archetype'].iloc[0] if len(a_sub) > 0 and 'archetype' in a_sub else arch
        arch_metrics[arch] = {**st, 'name': arch_name}
        print(f"  * [{arch}] {arch_name:<25}: {st['fills']:>3} Fills | {st['wins']:>2}W - {st['losses']:>2}L - {st['be']:>2}BE | WR: {st['wr']:>5.1f}% | Net: {st['net_r']:>+6.1f}R | PF: {st['pf']:>4.2f}")

    # Session Breakdown Across Full Year
    print("\n📍 FULL-YEAR PERFORMANCE BY INSTITUTIONAL SESSION (CALIBRATED SUITE):")
    sess_metrics = {}
    for sess in sorted(calib_fills['session'].unique()):
        sess_sub = calib_fills[calib_fills['session'] == sess]
        st = calc_stats(sess_sub)
        sess_metrics[sess] = st
        print(f"  * {sess:<25}: {st['fills']:>3} Fills | {st['wins']:>2}W - {st['losses']:>2}L - {st['be']:>2}BE | WR: {st['wr']:>5.1f}% | Net: {st['net_r']:>+6.1f}R | PF: {st['pf']:>4.2f}")

    # Banned / Decommissioned Verification Across Full Year
    print("\n📍 BANNED & DECOMMISSIONED DRAG AUDIT (FULL-YEAR):")
    sb_sub = master_df[(master_df['session'] == 'NY_Silver_Bullet') & (master_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN']))]
    st_sb = calc_stats(sb_sub)
    print(f"  * NY Silver Bullet (Banned)  : {st_sb['fills']:>3} Fills | {st_sb['wins']:>2}W - {st_sb['losses']:>2}L - {st_sb['be']:>2}BE | WR: {st_sb['wr']:>5.1f}% | Net: {st_sb['net_r']:>+6.1f}R | PF: {st_sb['pf']:>4.2f}")

    arch2_sub = master_df[(master_df['archetype_id'] == 'SETUP-ARCH-002') & (master_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN']))]
    st_arch2 = calc_stats(arch2_sub)
    print(f"  * ARCH-002 Judas FVG (Decomm): {st_arch2['fills']:>3} Fills | {st_arch2['wins']:>2}W - {st_arch2['losses']:>2}L - {st_arch2['be']:>2}BE | WR: {st_arch2['wr']:>5.1f}% | Net: {st_arch2['net_r']:>+6.1f}R | PF: {st_arch2['pf']:>4.2f}")

    arch9_sub = master_df[(master_df['archetype_id'] == 'SETUP-ARCH-009') & (master_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN']))]
    st_arch9 = calc_stats(arch9_sub)
    print(f"  * ARCH-009 OTE Retrac (Decomm): {st_arch9['fills']:>3} Fills | {st_arch9['wins']:>2}W - {st_arch9['losses']:>2}L - {st_arch9['be']:>2}BE | WR: {st_arch9['wr']:>5.1f}% | Net: {st_arch9['net_r']:>+6.1f}R | PF: {st_arch9['pf']:>4.2f}")

    # Continuous Double MSS & Nested Double MSS Multi-Season Summary
    # Read nested double mss from all 4 seasons
    nest_winter_df = pd.read_csv(BASE_DIR / "backtest_results" / "gold_winter_nested_double_mss" / "winter_nested_double_mss_trades.csv") if (BASE_DIR / "backtest_results" / "gold_winter_nested_double_mss" / "winter_nested_double_mss_trades.csv").exists() else pd.DataFrame()
    nest_spring_df = pd.read_csv(BASE_DIR / "backtest_results" / "gold_spring_nested_double_mss" / "spring_nested_double_mss_trades.csv") if (BASE_DIR / "backtest_results" / "gold_spring_nested_double_mss" / "spring_nested_double_mss_trades.csv").exists() else pd.DataFrame()
    nest_summer_df = pd.read_csv(BASE_DIR / "backtest_results" / "gold_oos_nested_double_mss" / "oos_nested_double_mss_trades.csv") if (BASE_DIR / "backtest_results" / "gold_oos_nested_double_mss" / "oos_nested_double_mss_trades.csv").exists() else pd.DataFrame()
    nest_autumn_df = pd.read_csv(BASE_DIR / "backtest_results" / "nested_double_mss_audit" / "nested_double_mss_trades.csv") if (BASE_DIR / "backtest_results" / "nested_double_mss_audit" / "nested_double_mss_trades.csv").exists() else pd.DataFrame()

    all_nested_list = []
    if len(nest_winter_df): all_nested_list.append(nest_winter_df)
    if len(nest_spring_df): all_nested_list.append(nest_spring_df)
    if len(nest_summer_df): all_nested_list.append(nest_summer_df)
    if len(nest_autumn_df): all_nested_list.append(nest_autumn_df)

    if all_nested_list:
        all_nest_df = pd.concat(all_nested_list, ignore_index=True)
        nest_fills = all_nest_df[all_nest_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
        st_nest_annual = calc_stats(nest_fills)
        st_nest_sw = calc_stats(nest_fills[nest_fills['has_sweep'] == True])
        st_nest_nosw = calc_stats(nest_fills[nest_fills['has_sweep'] == False])

        print("\n" + "=" * 90)
        print("💎 2026 ANNUAL CONTINUOUS SETUP-ARCH-011 (NESTED DOUBLE MSS) PERFORMANCE:")
        print("=" * 90)
        print(f"Annual Nested Double MSS (All):      {st_nest_annual['fills']} Fills | {st_nest_annual['wins']}W - {st_nest_annual['losses']}L - {st_nest_annual['be']}BE | WR: {st_nest_annual['wr']}% | Net: {st_nest_annual['net_r']:+0.1f}R | PF: {st_nest_annual['pf']}")
        print(f"Annual Nested WITH Prior Sweep:      {st_nest_sw['fills']} Fills | {st_nest_sw['wins']}W - {st_nest_sw['losses']}L - {st_nest_sw['be']}BE | WR: {st_nest_sw['wr']}% | Net: {st_nest_sw['net_r']:+0.1f}R | PF: {st_nest_sw['pf']}")
        print(f"Annual Nested WITHOUT Sweep (Open):  {st_nest_nosw['fills']} Fills | {st_nest_nosw['wins']}W - {st_nest_nosw['losses']}L - {st_nest_nosw['be']}BE | WR: {st_nest_nosw['wr']}% | Net: {st_nest_nosw['net_r']:+0.1f}R | PF: {st_nest_nosw['pf']}")
        print("=" * 90)
    else:
        st_nest_annual = {}

    total_drag_r = st_sb['net_r'] + st_arch2['net_r'] + st_arch9['net_r']

    summary = {
        'audit_scope': 'Full-Year 2026 (Winter, Spring, Summer, Autumn)',
        'trading_days': 175,
        'institutional_sessions': 700,
        'symbol': 'XAUUSD_o',
        'baseline_annual': st_base_annual,
        'calibrated_annual': st_calib_annual,
        'seasonal_breakdown': season_metrics,
        'archetype_breakdown': arch_metrics,
        'session_breakdown': sess_metrics,
        'nested_double_mss_annual': st_nest_annual,
        'decommissioned_drag': {
            'ny_silver_bullet': st_sb,
            'arch_002': st_arch2,
            'arch_009': st_arch9,
            'total_drag_saved_r': round(total_drag_r, 2)
        }
    }

    with open(OUTPUT_DIR / "annual_master_summary_metrics.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n🎉 Annual Master Synthesis Saved to: {OUTPUT_DIR}")

if __name__ == "__main__":
    run_annual_master_synthesis()
