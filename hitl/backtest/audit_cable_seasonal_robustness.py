"""
TradingGuard HITL - Cable (GBPUSD) Seasonal Robustness Audit
Verifies the Calibrated Asymmetric Policy across all 4 market seasons on Cable (GBPUSD).
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

OUTPUT_DIR = BASE_DIR / "backtest_results" / "gbpusd_trend_oracle_audit"

trend_df = pd.read_csv(OUTPUT_DIR / "gbpusd_omnitrend_3state_ledger.csv")
trend_df['date'] = trend_df['date'].astype(str)
trend_map = {row['date']: row for _, row in trend_df.iterrows()}

cable_ledger_path = BASE_DIR / "backtest_results" / "gbpusd_annual_4season_master_synthesis" / "gbpusd_annual_master_all_trades_ledger.csv"
trades_df = pd.read_csv(cable_ledger_path)
trades_df = trades_df[trades_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])].copy()
trades_df['date'] = trades_df['date'].astype(str)

ratified = trades_df[trades_df['archetype_id'].isin(['SETUP-ARCH-002', 'SETUP-ARCH-003', 'SETUP-ARCH-010'])].copy()

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

def run_season_audit(trades_sub, is_asym=True):
    results = []
    for _, t in trades_sub.iterrows():
        d = t['date']
        t_dir = t['direction']
        pred = trend_map.get(d, {}).get('pred_state', "SIDEWAYS")
        is_aligned = (t_dir == 'LONG' and pred == 'UP') or (t_dir == 'SHORT' and pred == 'DOWN')
        is_counter = (t_dir == 'LONG' and pred == 'DOWN') or (t_dir == 'SHORT' and pred == 'UP')

        if not is_asym:
            tp, be = 3.5, 1.8
        else:
            if is_aligned: tp, be = 2.0, 1.0
            elif is_counter: tp, be = 2.5, 1.0
            else: tp, be = 2.5, 0.8

        r, s = simulate_trade_pnl(t, tp, be)
        results.append((r, s))

    n = len(results)
    w = sum(1 for r, s in results if s == 'WIN')
    l = sum(1 for r, s in results if s == 'LOSS')
    b = sum(1 for r, s in results if s == 'BREAKEVEN')
    net_r = round(sum(r for r, s in results), 2)
    gw = sum(r for r, s in results if r > 0)
    gl = abs(sum(r for r, s in results if r < 0))
    pf = round(gw / max(0.01, gl), 2)
    wr = round((w / n) * 100, 1) if n > 0 else 0.0
    return {'n': n, 'w': w, 'l': l, 'b': b, 'net_r': net_r, 'pf': pf, 'wr': wr}

print("=" * 95)
print("CABLE (GBPUSD) SEASONAL ROBUSTNESS: UNOPTIMIZED BASELINE vs ASYMMETRIC TREND POLICY")
print("=" * 95)
print("Season       | Baseline (3.5R TP / 1.8R BE)           | Asymmetric Trend-Aware Execution")
print("             | Fills | W-L-BE    | WR%   | Net R  | PF  | Fills | W-L-BE    | WR%   | Net R  | PF")
print("-" * 95)

seasons = ratified['season'].dropna().unique().tolist()
for s in seasons:
    sub = ratified[ratified['season'] == s]
    base = run_season_audit(sub, is_asym=False)
    asym = run_season_audit(sub, is_asym=True)
    print(f"{s:<12} | {base['n']:>5} | {base['w']:>2}W-{base['l']:>2}L-{base['b']:>2}BE | {base['wr']:>4.1f}% | {base['net_r']:>+6.2f}R | {base['pf']:>4.2f} | {asym['n']:>5} | {asym['w']:>2}W-{asym['l']:>2}L-{asym['b']:>2}BE | {asym['wr']:>4.1f}% | {asym['net_r']:>+6.2f}R | {asym['pf']:>4.2f}")

print("-" * 95)
tot_base = run_season_audit(ratified, is_asym=False)
tot_asym = run_season_audit(ratified, is_asym=True)
print(f"{'ANNUAL TOTAL':<12} | {tot_base['n']:>5} | {tot_base['w']:>2}W-{tot_base['l']:>2}L-{tot_base['b']:>2}BE | {tot_base['wr']:>4.1f}% | {tot_base['net_r']:>+6.2f}R | {tot_base['pf']:>4.2f} | {tot_asym['n']:>5} | {tot_asym['w']:>2}W-{tot_asym['l']:>2}L-{tot_asym['b']:>2}BE | {tot_asym['wr']:>4.1f}% | {tot_asym['net_r']:>+6.2f}R | {tot_asym['pf']:>4.2f}")
print("=" * 95)

print("\n--- ALL CABLE TRADES (255 FILLS) ---")
all_base = run_season_audit(trades_df, is_asym=False)
all_asym = run_season_audit(trades_df, is_asym=True)
print(f"Baseline All Trades   : {all_base['n']} Fills | {all_base['w']}W-{all_base['l']}L-{all_base['b']}BE | WR: {all_base['wr']}% | Net: {all_base['net_r']:>+6.2f}R | PF: {all_base['pf']}")
print(f"Asymmetric All Trades : {all_asym['n']} Fills | {all_asym['w']}W-{all_asym['l']}L-{all_asym['b']}BE | WR: {all_asym['wr']}% | Net: {all_asym['net_r']:>+6.2f}R | PF: {all_asym['pf']}")
