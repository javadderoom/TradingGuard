"""
TradingGuard HITL - Seasonal Robustness & Multi-Archetype Audit
Verifies whether the Asymmetric Policy holds across distinct market seasons
and across the entire 414-trade database (eliminating curve-fitting risk).
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.optimize_trend_oracle import (
    load_historical_market_data,
    simulate_day_dataset,
    evaluate_classifier_rules
)

sym, d1, h4, h1, ag_h1 = load_historical_market_data("XAUUSD_o", min_days=260)
days_data = simulate_day_dataset(d1, h4, h1, ag_h1)

model_params = {
    "up_threshold": 1.5,
    "down_threshold": -1.5,
    "adr_exhaustion_pct": 55.0,
    "asian_range_max_pct": 35.0,
    "use_weekly_premium_discount": False,
    "use_h4_filter": False,
    "pdc_weight": 0.5
}
eval_res = evaluate_classifier_rules(days_data, model_params, anchor="london")
trend_map = {row['date']: row['pred_state'] for _, row in eval_res["df"].iterrows()}

gold_ledger_path = BASE_DIR / "backtest_results" / "gold_annual_4season_master_synthesis" / "annual_master_all_trades_ledger.csv"
trades_df = pd.read_csv(gold_ledger_path)
trades_df = trades_df[trades_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])].copy()
trades_df['date'] = trades_df['date'].astype(str)

def simulate_trade_pnl(trade, tp_r, be_trigger_r):
    mfe = float(trade['mfe_r'])
    mae = float(trade['mae_r'])

    if mae >= 1.0 and mfe < be_trigger_r:
        return -1.0, "LOSS"

    if mfe >= tp_r:
        if trade['status'] == 'WIN':
            return tp_r, "WIN"
        elif trade['status'] == 'BREAKEVEN' or mae < 1.0:
            return tp_r, "WIN"
        else:
            return -1.0, "LOSS"

    if mfe >= be_trigger_r:
        return 0.0, "BREAKEVEN"

    return -1.0, "LOSS"

def run_portfolio_audit(trades_subset, policy_name, is_asymmetric=True):
    results = []
    for _, t in trades_subset.iterrows():
        d = t['date']
        t_dir = t['direction']
        pred = trend_map.get(d, "SIDEWAYS")
        is_aligned = (t_dir == 'LONG' and pred == 'UP') or (t_dir == 'SHORT' and pred == 'DOWN')
        is_counter = (t_dir == 'LONG' and pred == 'DOWN') or (t_dir == 'SHORT' and pred == 'UP')

        if not is_asymmetric:
            tp, be = 3.5, 1.8
        else:
            if is_aligned:
                tp, be = 3.5, 1.5
            elif is_counter:
                tp, be = 1.5, 1.0
            else:
                tp, be = 3.5, 1.0

        r, s = simulate_trade_pnl(t, tp, be)
        rec = dict(t)
        rec['sim_r'] = r
        rec['sim_s'] = s
        results.append(rec)

    df_res = pd.DataFrame(results)
    n = len(df_res)
    w = len(df_res[df_res['sim_s'] == 'WIN'])
    l = len(df_res[df_res['sim_s'] == 'LOSS'])
    b = len(df_res[df_res['sim_s'] == 'BREAKEVEN'])
    net_r = round(float(df_res['sim_r'].sum()), 2)
    gw = df_res[df_res['sim_r'] > 0]['sim_r'].sum()
    gl = abs(df_res[df_res['sim_r'] < 0]['sim_r'].sum())
    pf = round(gw / max(0.01, gl), 2)
    wr = round((w / n) * 100, 1) if n > 0 else 0.0

    return {'n': n, 'w': w, 'l': l, 'b': b, 'net_r': net_r, 'pf': pf, 'wr': wr}

# Audit Ratified Suite
ratified = trades_df[trades_df['archetype_id'].isin(['SETUP-ARCH-001', 'SETUP-ARCH-003', 'SETUP-ARCH-010', 'SETUP-ARCH-014'])].copy()

print("=" * 90)
print("SEASONAL & MULTI-ARCHETYPE VERIFICATION: BASELINE VS ASYMMETRIC EXECUTION")
print("=" * 90)

seasons = ratified['season'].dropna().unique().tolist()

print(f"\n1. RATIFIED SMC SUITE BY SEASON:")
print("-" * 90)
print("Season       | Baseline (3.5R TP / 1.8R BE)           | Asymmetric Trend-Aware Execution")
print("             | Fills | W-L-BE    | WR%   | Net R  | PF  | Fills | W-L-BE    | WR%   | Net R  | PF")
print("-" * 90)

for s in seasons:
    sub = ratified[ratified['season'] == s]
    base = run_portfolio_audit(sub, "Base", is_asymmetric=False)
    asym = run_portfolio_audit(sub, "Asym", is_asymmetric=True)
    print(f"{s:<12} | {base['n']:>5} | {base['w']:>2}W-{base['l']:>2}L-{base['b']:>2}BE | {base['wr']:>4.1f}% | {base['net_r']:>+6.2f}R | {base['pf']:>4.2f} | {asym['n']:>5} | {asym['w']:>2}W-{asym['l']:>2}L-{asym['b']:>2}BE | {asym['wr']:>4.1f}% | {asym['net_r']:>+6.2f}R | {asym['pf']:>4.2f}")

print("-" * 90)
tot_base = run_portfolio_audit(ratified, "Base", is_asymmetric=False)
tot_asym = run_portfolio_audit(ratified, "Asym", is_asymmetric=True)
print(f"{'ANNUAL TOTAL':<12} | {tot_base['n']:>5} | {tot_base['w']:>2}W-{tot_base['l']:>2}L-{tot_base['b']:>2}BE | {tot_base['wr']:>4.1f}% | {tot_base['net_r']:>+6.2f}R | {tot_base['pf']:>4.2f} | {tot_asym['n']:>5} | {tot_asym['w']:>2}W-{tot_asym['l']:>2}L-{tot_asym['b']:>2}BE | {tot_asym['wr']:>4.1f}% | {tot_asym['net_r']:>+6.2f}R | {tot_asym['pf']:>4.2f}")
print("=" * 90)

print(f"\n2. FULL 414-TRADE PORTFOLIO (ALL ARCHETYPES):")
all_base = run_portfolio_audit(trades_df, "Base", is_asymmetric=False)
all_asym = run_portfolio_audit(trades_df, "Asym", is_asymmetric=True)
print(f"Baseline All Trades   : {all_base['n']} Fills | {all_base['w']}W-{all_base['l']}L-{all_base['b']}BE | WR: {all_base['wr']}% | Net: {all_base['net_r']:>+6.2f}R | PF: {all_base['pf']}")
print(f"Asymmetric All Trades : {all_asym['n']} Fills | {all_asym['w']}W-{all_asym['l']}L-{all_asym['b']}BE | WR: {all_asym['wr']}% | Net: {all_asym['net_r']:>+6.2f}R | PF: {all_asym['pf']}")
