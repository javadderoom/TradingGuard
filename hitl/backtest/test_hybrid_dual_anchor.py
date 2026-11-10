"""
TradingGuard HITL - Verification of Hybrid Dual-Anchor Architecture
Preserves the Macro Daily Directional Anchor (Model A) while enriching the
Pre-NY session card with London established range telemetry and revised intra-session targets.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.audit_pre_ny_reanchoring import load_gold_dataset

sym, d1, h1_bars, m5_bars = load_gold_dataset(min_days=260)

gold_ledger_path = BASE_DIR / "backtest_results" / "gold_annual_4season_master_synthesis" / "annual_master_all_trades_ledger.csv"
trades_df = pd.read_csv(gold_ledger_path)
trades_df = trades_df[trades_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])].copy()
trades_df['date'] = trades_df['date'].astype(str)
rat_trades = trades_df[trades_df['archetype_id'].isin(['SETUP-ARCH-001', 'SETUP-ARCH-003', 'SETUP-ARCH-010', 'SETUP-ARCH-014'])].copy()

# Run daily macro model
from hitl.backtest.optimize_trend_oracle import simulate_day_dataset, evaluate_classifier_rules
days_data = simulate_day_dataset(d1, d1, h1_bars, [])
calib_params = {
    "up_threshold": 1.5,
    "down_threshold": -1.5,
    "adr_exhaustion_pct": 55.0,
    "asian_range_max_pct": 35.0,
    "use_weekly_premium_discount": False,
    "use_h4_filter": False,
    "pdc_weight": 0.5
}
eval_res = evaluate_classifier_rules(days_data, calib_params, anchor="london")
trend_map = {row['date']: row['pred_state'] for _, row in eval_res["df"].iterrows()}

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

results = []
for _, t in rat_trades.iterrows():
    d = t['date']
    t_dir = t['direction']
    pred = trend_map.get(d, "SIDEWAYS")
    is_aligned = (t_dir == 'LONG' and pred == 'UP') or (t_dir == 'SHORT' and pred == 'DOWN')
    is_counter = (t_dir == 'LONG' and pred == 'DOWN') or (t_dir == 'SHORT' and pred == 'UP')
    if is_aligned: tp, be = 3.5, 1.5
    elif is_counter: tp, be = 1.5, 1.0
    else: tp, be = 3.5, 1.0
    r, s = simulate_trade_pnl(t, tp, be)
    results.append((r, s, t['session']))

df_res = pd.DataFrame(results, columns=['net_r', 'status', 'session'])
n = len(df_res)
w = len(df_res[df_res['status'] == 'WIN'])
l = len(df_res[df_res['status'] == 'LOSS'])
b = len(df_res[df_res['status'] == 'BREAKEVEN'])
net_r = df_res['net_r'].sum()
gw = df_res[df_res['net_r'] > 0]['net_r'].sum()
gl = abs(df_res[df_res['net_r'] < 0]['net_r'].sum())
pf = round(gw / max(0.01, gl), 2)

print(f"Hybrid Architecture Portfolio Total : {n} Fills | {w}W-{l}L-{b}BE | WR: {w/n*100:.1f}% | Net: {net_r:>+6.2f}R | PF: {pf:>4.2f}")

# NY session only
ny_sub = df_res[df_res['session'].str.contains('NY', case=False, na=False)]
ny_w = len(ny_sub[ny_sub['status'] == 'WIN'])
ny_l = len(ny_sub[ny_sub['status'] == 'LOSS'])
ny_b = len(ny_sub[ny_sub['status'] == 'BREAKEVEN'])
ny_net = ny_sub['net_r'].sum()
ny_gw = ny_sub[ny_sub['net_r'] > 0]['net_r'].sum()
ny_gl = abs(ny_sub[ny_sub['net_r'] < 0]['net_r'].sum())
ny_pf = round(ny_gw / max(0.01, ny_gl), 2)
print(f"Hybrid Architecture NY Sub-Session : {len(ny_sub)} Fills | {ny_w}W-{ny_l}L-{ny_b}BE | WR: {ny_w/len(ny_sub)*100:.1f}% | Net: {ny_net:>+6.2f}R | PF: {ny_pf:>4.2f}")
