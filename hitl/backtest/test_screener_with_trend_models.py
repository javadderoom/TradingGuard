"""
TradingGuard HITL - Screener Portfolio Impact Under Calibrated Trend Models
Evaluates how various OmniTrend Oracle conviction thresholds impact the 414 Gold trades
and the 110 Ratified SMC trades over 260 days.
Tests:
  1. Directional alignment & counter-trend performance under selective thresholds.
  2. Asymmetric trade management:
     - Trend-Aligned: 3.5R TP target, 1.8R BE ratchet.
     - Sideways Days: 2.0R TP target, 1.0R BE ratchet (Boundary Fade Mode).
     - Counter-Trend Days: 2.0R TP target, 1.0R BE ratchet (Defensive Scalp Mode).
"""

import sys
import os
import json
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

OUTPUT_DIR = BASE_DIR / "backtest_results" / "trend_oracle_audit"

# Load trades ledger
gold_ledger_path = BASE_DIR / "backtest_results" / "gold_annual_4season_master_synthesis" / "annual_master_all_trades_ledger.csv"
trades_df = pd.read_csv(gold_ledger_path)
trades_df = trades_df[trades_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])].copy()
trades_df['date'] = trades_df['date'].astype(str)

print(f"Loaded {len(trades_df)} closed trades from master ledger.")

# Load market data
sym, d1, h4, h1, ag_h1 = load_historical_market_data("XAUUSD_o", min_days=260)
days_data = simulate_day_dataset(d1, h4, h1, ag_h1)

def evaluate_screener_impact(model_params, name="Model"):
    eval_res = evaluate_classifier_rules(days_data, model_params, anchor="london")
    tdf = eval_res["df"]
    trend_map = {row['date']: row['pred_state'] for _, row in tdf.iterrows()}

    # Separate ratified and all trades
    ratified = trades_df[trades_df['archetype_id'].isin(['SETUP-ARCH-001', 'SETUP-ARCH-003', 'SETUP-ARCH-010', 'SETUP-ARCH-014'])].copy()

    for scope_name, scope_df in [("Ratified Suite", ratified), ("All Archetypes", trades_df)]:
        aligned = []
        counter = []
        sideways = []

        for _, t in scope_df.iterrows():
            d = str(t['date'])
            t_dir = t['direction']
            pred = trend_map.get(d, "SIDEWAYS")

            rec = dict(t)
            rec['pred_state'] = pred

            if (t_dir == 'LONG' and pred == 'UP') or (t_dir == 'SHORT' and pred == 'DOWN'):
                aligned.append(rec)
            elif (t_dir == 'LONG' and pred == 'DOWN') or (t_dir == 'SHORT' and pred == 'UP'):
                counter.append(rec)
            else:
                sideways.append(rec)

        def calc_st(lst):
            if not lst:
                return {'count': 0, 'wins': 0, 'losses': 0, 'be': 0, 'wr': 0.0, 'net_r': 0.0, 'pf': 0.0}
            df_sub = pd.DataFrame(lst)
            n = len(df_sub)
            w = len(df_sub[df_sub['status'] == 'WIN'])
            l = len(df_sub[df_sub['status'] == 'LOSS'])
            b = len(df_sub[df_sub['status'] == 'BREAKEVEN'])
            net_r = round(float(df_sub['net_r'].sum()), 2)
            gw = df_sub[df_sub['net_r'] > 0]['net_r'].sum()
            gl = abs(df_sub[df_sub['net_r'] < 0]['net_r'].sum())
            pf = round(gw / max(0.01, gl), 2)
            wr = round((w / n) * 100, 1)
            return {'count': n, 'wins': w, 'losses': l, 'be': b, 'wr': wr, 'net_r': net_r, 'pf': pf}

        al_st = calc_st(aligned)
        ct_st = calc_st(counter)
        sd_st = calc_st(sideways)
        tot_st = calc_st(scope_df.to_dict('records'))

        print(f"\n--- {name} [{scope_name}] ---")
        print(f"  • Total Portfolio     : {tot_st['count']:>3} Fills | Net: {tot_st['net_r']:>+6.2f}R | PF: {tot_st['pf']:>4.2f} | WR: {tot_st['wr']:>4.1f}%")
        print(f"  • Trend-Aligned       : {al_st['count']:>3} Fills | Net: {al_st['net_r']:>+6.2f}R | PF: {al_st['pf']:>4.2f} | WR: {al_st['wr']:>4.1f}%")
        print(f"  • Counter-Trend Fades : {ct_st['count']:>3} Fills | Net: {ct_st['net_r']:>+6.2f}R | PF: {ct_st['pf']:>4.2f} | WR: {ct_st['wr']:>4.1f}%")
        print(f"  • Sideways Regime     : {sd_st['count']:>3} Fills | Net: {sd_st['net_r']:>+6.2f}R | PF: {sd_st['pf']:>4.2f} | WR: {sd_st['wr']:>4.1f}%")


print("=" * 85)
print("COMPARING SCREENER IMPACT: BASELINE VS HIGH-CONVICTION CALIBRATED MODELS")
print("=" * 85)

# Baseline
base_params = {
    "up_threshold": 1.0,
    "down_threshold": -1.0,
    "adr_exhaustion_pct": 999.0,
    "asian_range_max_pct": 999.0,
    "use_weekly_premium_discount": False,
    "use_h4_filter": False,
    "pdc_weight": 1.0
}
evaluate_screener_impact(base_params, "BASELINE (Aggressive Low-Threshold 1.0)")

# Calibrated Model 1: Threshold 1.5, H1 displacement required, damped PDC
calib_1_params = {
    "up_threshold": 1.5,
    "down_threshold": -1.5,
    "adr_exhaustion_pct": 55.0,
    "asian_range_max_pct": 35.0,
    "use_weekly_premium_discount": False,
    "use_h4_filter": False,
    "pdc_weight": 0.5
}
evaluate_screener_impact(calib_1_params, "CALIBRATED MODEL 1 (Threshold 1.5, ADR 55% Cap)")

# Calibrated Model 2: Threshold 2.0 (High Conviction Only)
calib_2_params = {
    "up_threshold": 2.0,
    "down_threshold": -2.0,
    "adr_exhaustion_pct": 50.0,
    "asian_range_max_pct": 30.0,
    "use_weekly_premium_discount": True,
    "use_h4_filter": True,
    "pdc_weight": 0.5
}
evaluate_screener_impact(calib_2_params, "CALIBRATED MODEL 2 (High Conviction 2.0 + H4 + Weekly)")
