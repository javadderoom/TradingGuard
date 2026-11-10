"""
TradingGuard HITL - Cable (GBPUSD) Screener Impact Audit
Cross-references historical Cable trade executions against daily OmniTrend predictions
to evaluate whether filtering counter-trend setups enhances or degrades Net Alpha & Win Rate,
and tests Asymmetric Dynamic Trade Management on Cable.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

OUTPUT_DIR = BASE_DIR / "backtest_results" / "gbpusd_trend_oracle_audit"

# Load Cable daily prediction ledger
trend_df = pd.read_csv(OUTPUT_DIR / "gbpusd_omnitrend_3state_ledger.csv")
trend_df['date'] = trend_df['date'].astype(str)
trend_map = {row['date']: row for _, row in trend_df.iterrows()}

# Load Cable master trades
cable_ledger_path = BASE_DIR / "backtest_results" / "gbpusd_annual_4season_master_synthesis" / "gbpusd_annual_master_all_trades_ledger.csv"
trades_df = pd.read_csv(cable_ledger_path)
trades_df = trades_df[trades_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])].copy()
trades_df['date'] = trades_df['date'].astype(str)

print(f"Total Cable closed trades in ledger: {len(trades_df)}")

# Separate ratified and all trades
# Ratified Cable suite: SETUP-ARCH-002, SETUP-ARCH-003, SETUP-ARCH-010
ratified = trades_df[trades_df['archetype_id'].isin(['SETUP-ARCH-002', 'SETUP-ARCH-003', 'SETUP-ARCH-010'])].copy()
print(f"Ratified Cable trades: {len(ratified)}")

def calc_stats(trade_list, name=""):
    if not trade_list:
        return {'name': name, 'count': 0, 'wins': 0, 'losses': 0, 'be': 0, 'wr': 0.0, 'net_r': 0.0, 'pf': 0.0}
    df_sub = pd.DataFrame(trade_list)
    n = len(df_sub)
    w = len(df_sub[df_sub['status'] == 'WIN'])
    l = len(df_sub[df_sub['status'] == 'LOSS'])
    b = len(df_sub[df_sub['status'] == 'BREAKEVEN'])
    net_r = round(float(df_sub['net_r'].sum()), 2)
    gw = df_sub[df_sub['net_r'] > 0]['net_r'].sum()
    gl = abs(df_sub[df_sub['net_r'] < 0]['net_r'].sum())
    pf = round(gw / max(0.01, gl), 2)
    wr = round((w / n) * 100, 1) if n > 0 else 0.0
    return {'name': name, 'count': n, 'wins': w, 'losses': l, 'be': b, 'wr': wr, 'net_r': net_r, 'pf': pf}

def partition_trades(df_scope):
    aligned = []
    counter = []
    sideways = []
    for _, t in df_scope.iterrows():
        d = t['date']
        t_dir = t['direction']
        if d in trend_map:
            pred_state = trend_map[d]['pred_state']
            is_aligned = (t_dir == 'LONG' and pred_state == 'UP') or (t_dir == 'SHORT' and pred_state == 'DOWN')
            is_counter = (t_dir == 'LONG' and pred_state == 'DOWN') or (t_dir == 'SHORT' and pred_state == 'UP')
            rec = dict(t)
            rec['pred_state'] = pred_state
            if is_aligned: aligned.append(rec)
            elif is_counter: counter.append(rec)
            else: sideways.append(rec)
    return aligned, counter, sideways

print("\n" + "=" * 85)
print("1. EMPIRICAL BREAKDOWN BY PREDICTED REGIME (STATIC EXECUTION 3.5R TP / 1.8R BE)")
print("=" * 85)

for scope_name, df_sub in [("Ratified Suite (ARCH-002, 003, 010)", ratified), ("All Archetypes (255 Fills)", trades_df)]:
    al, ct, sd = partition_trades(df_sub)
    s_tot = calc_stats(df_sub.to_dict('records'), "Total Portfolio (No Filter)")
    s_al = calc_stats(al, "Trend-Aligned Only (UP+Long / DOWN+Short)")
    s_ct = calc_stats(ct, "Counter-Trend Fades")
    s_sd = calc_stats(sd, "Sideways Day Setups")

    print(f"\n--- {scope_name} ---")
    for s in [s_tot, s_al, s_ct, s_sd]:
        print(f"  {s['name']:<42} : {s['count']:>3} Fills | {s['wins']}W - {s['losses']}L - {s['be']}BE | WR: {s['wr']:>4.1f}% | Net: {s['net_r']:>+6.2f}R | PF: {s['pf']:>4.2f}")


# 2. TEST DYNAMIC ASYMMETRIC TRADE MANAGEMENT ON CABLE
print("\n" + "=" * 85)
print("2. TESTING DYNAMIC ASYMMETRIC TRADE MANAGEMENT ON CABLE")
print("=" * 85)

def simulate_trade_pnl(trade, tp_r, be_trigger_r):
    mfe = float(trade['mfe_r'])
    mae = float(trade['mae_r'])
    if mae >= 1.0 and mfe < be_trigger_r:
        return -1.0, "LOSS"
    if mfe >= tp_r:
        if trade['status'] == 'WIN' or trade['status'] == 'BREAKEVEN' or mae < 1.0:
            return tp_r, "WIN"
        else:
            return -1.0, "LOSS"
    if mfe >= be_trigger_r:
        return 0.0, "BREAKEVEN"
    return -1.0, "LOSS"

def evaluate_cable_policy(trades_sub, al_tp, al_be, ct_tp, ct_be, sd_tp, sd_be, name="Policy"):
    results = []
    for _, t in trades_sub.iterrows():
        d = t['date']
        t_dir = t['direction']
        pred = trend_map.get(d, {}).get('pred_state', "SIDEWAYS")
        is_aligned = (t_dir == 'LONG' and pred == 'UP') or (t_dir == 'SHORT' and pred == 'DOWN')
        is_counter = (t_dir == 'LONG' and pred == 'DOWN') or (t_dir == 'SHORT' and pred == 'UP')

        if is_aligned: tp, be = al_tp, al_be
        elif is_counter: tp, be = ct_tp, ct_be
        else: tp, be = sd_tp, sd_be

        r, s = simulate_trade_pnl(t, tp, be)
        results.append((r, s))

    w = sum(1 for r, s in results if s == 'WIN')
    l = sum(1 for r, s in results if s == 'LOSS')
    b = sum(1 for r, s in results if s == 'BREAKEVEN')
    net_r = round(sum(r for r, s in results), 2)
    gw = sum(r for r, s in results if r > 0)
    gl = abs(sum(r for r, s in results if r < 0))
    pf = round(gw / max(0.01, gl), 2)
    wr = round((w / len(results)) * 100, 1) if results else 0.0
    print(f"{name:<45} : {len(results):>3} Fills | {w}W-{l}L-{b}BE | WR: {wr:>4.1f}% | Net: {net_r:>+6.2f}R | PF: {pf:>4.2f}")
    return pf, net_r, wr

print("\n--- RATIFIED CABLE SUITE (112 Fills) ---")
evaluate_cable_policy(ratified, 3.5, 1.8, 3.5, 1.8, 3.5, 1.8, "Baseline Static (All 3.5R TP / 1.8R BE)")
evaluate_cable_policy(ratified, 3.5, 1.5, 1.5, 1.0, 3.5, 1.0, "Policy B (Aligned 3.5R, Counter 1.5R, Side 3.5R)")
evaluate_cable_policy(ratified, 3.0, 1.5, 2.0, 1.0, 2.5, 1.0, "Policy E (Aligned 3.0R, Counter 2.0R, Side 2.5R)")
evaluate_cable_policy(ratified, 2.5, 1.2, 1.5, 1.0, 2.5, 1.0, "Policy F (Forex Snug: Aligned 2.5R, Counter 1.5R, Side 2.5R)")

print("\n--- ALL CABLE TRADES (255 Fills) ---")
evaluate_cable_policy(trades_df, 3.5, 1.8, 3.5, 1.8, 3.5, 1.8, "Baseline Static (All 3.5R TP / 1.8R BE)")
evaluate_cable_policy(trades_df, 3.5, 1.5, 1.5, 1.0, 3.5, 1.0, "Policy B (Aligned 3.5R, Counter 1.5R, Side 3.5R)")
evaluate_cable_policy(trades_df, 2.5, 1.2, 1.5, 1.0, 2.5, 1.0, "Policy F (Forex Snug: Aligned 2.5R, Counter 1.5R, Side 2.5R)")
