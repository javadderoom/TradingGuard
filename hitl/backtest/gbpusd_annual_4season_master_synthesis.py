"""
TradingGuard HITL - Full-Year 4-Season Master Quantitative Synthesis for British Pound (GBPUSD)
Consolidates all 4 seasons of GBPUSD_o Standalone Audits:
- Autumn 2026: September 1 - November 4 (47 Days, 188 Sessions)
- Summer 2026: July 1 - August 31 (44 Days, 176 Sessions)
- Winter 2026: January 2 - February 27 (41 Days, 164 Sessions)
- Spring 2026: March 1 - April 30 (43 Days, 172 Sessions)

Total Scope:
- 175 Trading Days
- 700 Institutional Sessions
- Resampled M1 Microstructure from 22.6 Million Raw Broker Ticks
"""

import sys
import json
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "backtest_results" / "gbpusd_annual_4season_master_synthesis"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CALIBRATED_EXCLUSIONS = "NY Silver Bullet session, SETUP-ARCH-009"


def build_annual_summary(
    *,
    symbol: str,
    baseline_annual,
    calibrated_annual,
    seasonal_breakdown,
    archetype_breakdown,
    session_breakdown,
    seasonal_breakdown_all_fills,
    archetype_breakdown_all_fills,
    session_breakdown_all_fills,
    decommissioned_drag,
):
    """Assemble the annual summary JSON with explicit populations.

    Pack 6: the historical file labelled its seasonal / archetype /
    session breakdowns as if they described the full year, but they
    were computed on CALIBRATED fills only (GBP: 123 of 255 fills).
    The old keys are kept unchanged for back-compat, but they are
    now explicitly labelled, and the all-fills variants are shipped
    alongside so any reader can see both populations without
    re-running the audit.
    """
    calib_fills = calibrated_annual["fills"]
    base_fills = baseline_annual["fills"]
    return {
        'audit_scope': 'Full-Year 2026 (Winter, Spring, Summer, Autumn)',
        'trading_days': 175,
        'institutional_sessions': 700,
        'symbol': symbol,
        'baseline_annual': baseline_annual,
        'calibrated_annual': calibrated_annual,
        'breakdown_population': {
            'seasonal_breakdown': (
                f'CALIBRATED fills only ({calib_fills} fills; excludes '
                f'{CALIBRATED_EXCLUSIONS}). NOT the full year.'
            ),
            'archetype_breakdown': (
                f'CALIBRATED fills only ({calib_fills} fills; excludes '
                f'{CALIBRATED_EXCLUSIONS}). NOT the full year.'
            ),
            'session_breakdown': (
                f'CALIBRATED fills only ({calib_fills} fills; excludes '
                f'{CALIBRATED_EXCLUSIONS}). NOT the full year.'
            ),
            'seasonal_breakdown_all_fills': f'ALL fills ({base_fills} fills, unfiltered).',
            'archetype_breakdown_all_fills': f'ALL fills ({base_fills} fills, unfiltered).',
            'session_breakdown_all_fills': f'ALL fills ({base_fills} fills, unfiltered).',
        },
        'seasonal_breakdown': seasonal_breakdown,
        'archetype_breakdown': archetype_breakdown,
        'session_breakdown': session_breakdown,
        'seasonal_breakdown_all_fills': seasonal_breakdown_all_fills,
        'archetype_breakdown_all_fills': archetype_breakdown_all_fills,
        'session_breakdown_all_fills': session_breakdown_all_fills,
        'decommissioned_drag': decommissioned_drag,
    }


def run_gbpusd_annual_master_synthesis():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 90)
    print("🇬🇧 TRADINGGUARD - 2026 FULL-YEAR 4-SEASON MASTER QUANTITATIVE SYNTHESIS FOR GBPUSD")
    print("Instrument: GBPUSD_o (Cable Standalone) | 175 Trading Days | 700 Institutional Sessions")
    print("=" * 90)

    # 1. Load Ledgers
    seasons = {
        'Winter': BASE_DIR / "backtest_results" / "gbpusd_winter_2month_audit" / "gbpusd_winter_all_trades_ledger.csv",
        'Spring': BASE_DIR / "backtest_results" / "gbpusd_spring_2month_audit" / "gbpusd_spring_all_trades_ledger.csv",
        'Summer': BASE_DIR / "backtest_results" / "gbpusd_summer_2month_audit" / "gbpusd_summer_all_trades_ledger.csv",
        'Autumn': BASE_DIR / "backtest_results" / "gbpusd_autumn_2month_audit" / "gbpusd_autumn_all_trades_ledger.csv"
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
    master_df.to_csv(OUTPUT_DIR / "gbpusd_annual_master_all_trades_ledger.csv", index=False)
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

    # Calibrated: Exclude NY Silver Bullet, Exclude ARCH-009 (OTE Retracement)
    calib_fills = master_df[
        (master_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])) &
        (master_df['session'] != 'NY_Silver_Bullet') &
        (~master_df['archetype_id'].isin(['SETUP-ARCH-009']))
    ]
    st_calib_annual = calc_stats(calib_fills)

    print("\n" + "=" * 90)
    print("📊 2026 ANNUAL MASTER HEAD-TO-HEAD: BASELINE VS CALIBRATED SUITE (GBPUSD)")
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

    # Pack 6: same breakdowns on ALL fills (baseline population), so
    # the JSON no longer presents the calibrated subset as the year.
    season_metrics_all = {}
    for s_name in ['Winter', 'Spring', 'Summer', 'Autumn']:
        season_metrics_all[s_name] = calc_stats(base_fills[base_fills['season'] == s_name])
    arch_metrics_all = {}
    for arch in sorted(base_fills['archetype_id'].dropna().unique()):
        a_sub = base_fills[base_fills['archetype_id'] == arch]
        arch_name = a_sub['archetype'].iloc[0] if len(a_sub) > 0 and 'archetype' in a_sub else arch
        arch_metrics_all[arch] = {**calc_stats(a_sub), 'name': arch_name}
    sess_metrics_all = {}
    for sess in sorted(base_fills['session'].unique()):
        sess_metrics_all[sess] = calc_stats(base_fills[base_fills['session'] == sess])

    # Banned / Decommissioned Verification Across Full Year
    print("\n📍 BANNED & DECOMMISSIONED DRAG AUDIT (FULL-YEAR):")
    sb_sub = master_df[(master_df['session'] == 'NY_Silver_Bullet') & (master_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN']))]
    st_sb = calc_stats(sb_sub)
    print(f"  * NY Silver Bullet (Banned)  : {st_sb['fills']:>3} Fills | {st_sb['wins']:>2}W - {st_sb['losses']:>2}L - {st_sb['be']:>2}BE | WR: {st_sb['wr']:>5.1f}% | Net: {st_sb['net_r']:>+6.1f}R | PF: {st_sb['pf']:>4.2f}")

    arch9_sub = master_df[(master_df['archetype_id'] == 'SETUP-ARCH-009') & (master_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN']))]
    st_arch9 = calc_stats(arch9_sub)
    print(f"  * ARCH-009 OTE Retrac (Decomm): {st_arch9['fills']:>3} Fills | {st_arch9['wins']:>2}W - {st_arch9['losses']:>2}L - {st_arch9['be']:>2}BE | WR: {st_arch9['wr']:>5.1f}% | Net: {st_arch9['net_r']:>+6.1f}R | PF: {st_arch9['pf']:>4.2f}")

    total_drag_r = st_sb['net_r'] + st_arch9['net_r']
    print(f"  => TOTAL CAPITAL PRESERVED BY CALIBRATION: {abs(total_drag_r):.1f}R SAVED!")

    summary = build_annual_summary(
        symbol='GBPUSD_o',
        baseline_annual=st_base_annual,
        calibrated_annual=st_calib_annual,
        seasonal_breakdown=season_metrics,
        archetype_breakdown=arch_metrics,
        session_breakdown=sess_metrics,
        seasonal_breakdown_all_fills=season_metrics_all,
        archetype_breakdown_all_fills=arch_metrics_all,
        session_breakdown_all_fills=sess_metrics_all,
        decommissioned_drag={
            'ny_silver_bullet': st_sb,
            'arch_009': st_arch9,
            'total_drag_saved_r': round(total_drag_r, 2)
        },
    )

    with open(OUTPUT_DIR / "gbpusd_annual_master_summary_metrics.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n🎉 GBPUSD Annual Master Synthesis Saved to: {OUTPUT_DIR}")

if __name__ == "__main__":
    run_gbpusd_annual_master_synthesis()
