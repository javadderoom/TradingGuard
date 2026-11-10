"""
TradingGuard HITL - Asymmetric Trade Management Simulation
Evaluates the impact of dynamic target scaling and breakeven ratcheting
based on OmniTrend Oracle regime classifications across the 110 Ratified SMC trades.
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

# 1. Load market data and simulate trend classifications
sym, d1, h4, h1, ag_h1 = load_historical_market_data("XAUUSD_o", min_days=260)
days_data = simulate_day_dataset(d1, h4, h1, ag_h1)

# Test with Calibrated Model (Selective High Conviction)
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

# 2. Load trades ledger
gold_ledger_path = BASE_DIR / "backtest_results" / "gold_annual_4season_master_synthesis" / "annual_master_all_trades_ledger.csv"
trades_df = pd.read_csv(gold_ledger_path)
trades_df = trades_df[trades_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])].copy()
trades_df['date'] = trades_df['date'].astype(str)

ratified_trades = trades_df[trades_df['archetype_id'].isin(['SETUP-ARCH-001', 'SETUP-ARCH-003', 'SETUP-ARCH-010', 'SETUP-ARCH-014'])].copy()

def simulate_trade_pnl(trade, tp_r, be_trigger_r):
    """
    Simulates outcome of a trade given target (TP in R) and BE trigger (in R)
    using MFE and MAE.
    """
    mfe = float(trade['mfe_r'])
    mae = float(trade['mae_r'])

    # If trade hit SL before any significant upside
    if mae >= 1.0 and mfe < be_trigger_r:
        return -1.0, "LOSS"

    # If trade reached TP
    if mfe >= tp_r:
        # Check if MAE hit 1.0 before MFE hit TP?
        # In the original strategy, if it was a WIN, it reached the original TP (3.5R) without stopping out.
        # If it was a LOSS or BE, we check if MFE reached tp_r before stopping out.
        if trade['status'] == 'WIN':
            return tp_r, "WIN"
        elif mfe >= tp_r:
            # Conservative assumption: If it wasn't an original WIN, but MFE >= tp_r,
            # did it reach tp_r first? For conservative realism, if mae >= 1.0, assume stopped out unless original was BE.
            if trade['status'] == 'BREAKEVEN' or mae < 1.0:
                return tp_r, "WIN"
            else:
                return -1.0, "LOSS"

    # If trade didn't hit TP, but reached BE trigger
    if mfe >= be_trigger_r:
        return 0.0, "BREAKEVEN"

    # Otherwise loss
    return -1.0, "LOSS"


def evaluate_policy(aligned_tp, aligned_be, counter_tp, counter_be, side_tp, side_be, name="Policy"):
    results = []
    for _, t in ratified_trades.iterrows():
        d = t['date']
        t_dir = t['direction']
        pred = trend_map.get(d, "SIDEWAYS")

        is_aligned = (t_dir == 'LONG' and pred == 'UP') or (t_dir == 'SHORT' and pred == 'DOWN')
        is_counter = (t_dir == 'LONG' and pred == 'DOWN') or (t_dir == 'SHORT' and pred == 'UP')

        if is_aligned:
            tp, be = aligned_tp, aligned_be
            category = "ALIGNED"
        elif is_counter:
            tp, be = counter_tp, counter_be
            category = "COUNTER"
        else:
            tp, be = side_tp, side_be
            category = "SIDEWAYS"

        sim_net_r, sim_status = simulate_trade_pnl(t, tp, be)
        rec = dict(t)
        rec['sim_net_r'] = sim_net_r
        rec['sim_status'] = sim_status
        rec['category'] = category
        results.append(rec)

    res_df = pd.DataFrame(results)
    n = len(res_df)
    w = len(res_df[res_df['sim_status'] == 'WIN'])
    l = len(res_df[res_df['sim_status'] == 'LOSS'])
    b = len(res_df[res_df['sim_status'] == 'BREAKEVEN'])
    net_r = round(float(res_df['sim_net_r'].sum()), 2)
    gw = res_df[res_df['sim_net_r'] > 0]['sim_net_r'].sum()
    gl = abs(res_df[res_df['sim_net_r'] < 0]['sim_net_r'].sum())
    pf = round(gw / max(0.01, gl), 2)
    wr = round((w / n) * 100, 1)

    print(f"{name:<45} : {n} Fills | {w}W - {l}L - {b}BE | WR: {wr:>4.1f}% | Net: {net_r:>+6.2f}R | PF: {pf:>4.2f}")
    return pf, net_r, wr


print("=" * 85)
print("TESTING DYNAMIC ASYMMETRIC MANAGEMENT POLICIES ON RATIFIED SMC SUITE (110 TRADES)")
print("=" * 85)

# 1. Baseline static (3.5R TP, 1.8R BE for all)
print("\n--- BASELINE STATIC EXECUTION ---")
evaluate_policy(3.5, 1.8, 3.5, 1.8, 3.5, 1.8, "Baseline Static (All 3.5R TP / 1.8R BE)")

# 2. Test variations of Asymmetry
print("\n--- DYNAMIC ASYMMETRIC POLICIES ---")
# Policy A: Trend 3.5R/1.8R, Counter 2.0R/1.0R, Sideways 2.0R/1.2R
evaluate_policy(3.5, 1.8, 2.0, 1.0, 2.0, 1.2, "Policy A (Aligned 3.5R, Counter 2.0R, Side 2.0R)")

# Policy B: Trend 3.5R/1.5R, Counter 1.5R/1.0R, Sideways 2.5R/1.2R
evaluate_policy(3.5, 1.5, 1.5, 1.0, 2.5, 1.2, "Policy B (Aligned 3.5R, Counter 1.5R, Side 2.5R)")

# Policy C: Trend 3.5R/1.8R, Counter 2.0R/1.0R, Sideways 3.0R/1.5R
evaluate_policy(3.5, 1.8, 2.0, 1.0, 3.0, 1.5, "Policy C (Aligned 3.5R, Counter 2.0R, Side 3.0R)")

# Policy D: Trend 4.0R/2.0R, Counter 2.0R/1.0R, Sideways 2.5R/1.2R
evaluate_policy(4.0, 2.0, 2.0, 1.0, 2.5, 1.2, "Policy D (Aligned 4.0R, Counter 2.0R, Side 2.5R)")
