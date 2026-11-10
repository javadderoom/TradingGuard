"""
TradingGuard HITL - Audit of New York Session Trades Under Pre-NY Re-Anchoring
Examines how New York session trade executions in the 110 Ratified SMC suite
and the 414 total trade catalog perform under Pre-London vs Pre-NY Re-Anchoring.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.audit_pre_ny_reanchoring import load_gold_dataset, run_dual_session_benchmark

sym, d1, h1, m5_bars = load_gold_dataset(min_days=260)
df_benchmark, summary = run_dual_session_benchmark(d1, h1, m5_bars)

# Create lookup maps for day predictions
map_pred_a = {row['date']: row['pred_a'] for _, row in df_benchmark.iterrows()}
map_pred_b = {row['date']: row['pred_b'] for _, row in df_benchmark.iterrows()}

gold_ledger_path = BASE_DIR / "backtest_results" / "gold_annual_4season_master_synthesis" / "annual_master_all_trades_ledger.csv"
trades_df = pd.read_csv(gold_ledger_path)
trades_df = trades_df[trades_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])].copy()
trades_df['date'] = trades_df['date'].astype(str)

# Filter for New York Session trades
ny_trades = trades_df[trades_df['session'].str.contains('NY', case=False, na=False)].copy()
print(f"Total New York session closed trades in master ledger: {len(ny_trades)}")

# Also Ratified NY trades
rat_ny = ny_trades[ny_trades['archetype_id'].isin(['SETUP-ARCH-001', 'SETUP-ARCH-003', 'SETUP-ARCH-010', 'SETUP-ARCH-014'])].copy()
print(f"Ratified New York session trades: {len(rat_ny)}")

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

def evaluate_ny_portfolio(trades_subset, pred_map, name="Model"):
    results = []
    for _, t in trades_subset.iterrows():
        d = t['date']
        t_dir = t['direction']
        pred = pred_map.get(d, "SIDEWAYS")
        is_aligned = (t_dir == 'LONG' and pred == 'UP') or (t_dir == 'SHORT' and pred == 'DOWN')
        is_counter = (t_dir == 'LONG' and pred == 'DOWN') or (t_dir == 'SHORT' and pred == 'UP')

        if is_aligned:
            tp, be = 3.5, 1.5
            cat = "ALIGNED"
        elif is_counter:
            tp, be = 1.5, 1.0
            cat = "COUNTER"
        else:
            tp, be = 3.5, 1.0
            cat = "SIDEWAYS"

        r, s = simulate_trade_pnl(t, tp, be)
        rec = dict(t)
        rec['sim_r'] = r
        rec['sim_s'] = s
        rec['cat'] = cat
        results.append(rec)

    res_df = pd.DataFrame(results)
    n = len(res_df)
    w = len(res_df[res_df['sim_s'] == 'WIN'])
    l = len(res_df[res_df['sim_s'] == 'LOSS'])
    b = len(res_df[res_df['sim_s'] == 'BREAKEVEN'])
    net_r = round(float(res_df['sim_r'].sum()), 2)
    gw = res_df[res_df['sim_r'] > 0]['sim_r'].sum()
    gl = abs(res_df[res_df['sim_r'] < 0]['sim_r'].sum())
    pf = round(gw / max(0.01, gl), 2)
    wr = round((w / n) * 100, 1) if n > 0 else 0.0

    print(f"{name:<42} : {n:>3} Fills | {w}W-{l}L-{b}BE | WR: {wr:>4.1f}% | Net: {net_r:>+6.2f}R | PF: {pf:>4.2f}")
    return pf, net_r, wr

print("\n" + "=" * 80)
print("EVALUATING NEW YORK SESSION TRADES UNDER PRE-LONDON vs PRE-NY RE-ANCHOR")
print("=" * 80)
print("\n--- RATIFIED SMC SUITE (NY TRADES ONLY) ---")
evaluate_ny_portfolio(rat_ny, map_pred_a, "Model A: Static Pre-London Forecast")
evaluate_ny_portfolio(rat_ny, map_pred_b, "Model B: Dynamic Pre-NY Re-Anchor")

print("\n--- ALL ARCHETYPES (ALL NY TRADES) ---")
evaluate_ny_portfolio(ny_trades, map_pred_a, "Model A: Static Pre-London Forecast")
evaluate_ny_portfolio(ny_trades, map_pred_b, "Model B: Dynamic Pre-NY Re-Anchor")
