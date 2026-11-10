"""
TradingGuard HITL - OmniTrend Oracle Screener Integration Audit
Cross-references historical Gold trade executions against daily OmniTrend predictions
to evaluate whether filtering counter-trend setups enhances or degrades Net Alpha & Win Rate.
"""

import sys
import json
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "backtest_results" / "trend_oracle_audit"

# Load trend ledger
trend_df = pd.read_csv(OUTPUT_DIR / "omnitrend_3state_daily_accuracy_ledger.csv")
trend_df['date'] = trend_df['date'].astype(str)
trend_map = {row['date']: row for _, row in trend_df.iterrows()}

# Load gold master trades
gold_ledger_path = BASE_DIR / "backtest_results" / "gold_annual_4season_master_synthesis" / "annual_master_all_trades_ledger.csv"
if not gold_ledger_path.exists():
    print(f"File not found: {gold_ledger_path}")
    sys.exit(1)

trades_df = pd.read_csv(gold_ledger_path)
trades_df = trades_df[trades_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])].copy()
trades_df['date'] = trades_df['date'].astype(str)

print(f"Total Gold closed trades in ledger: {len(trades_df)}")

aligned_trades = []
counter_trades = []
sideways_trades = []

for _, t in trades_df.iterrows():
    d = t['date']
    t_dir = t['direction'] # LONG or SHORT
    is_win = t['status'] == 'WIN'
    is_loss = t['status'] == 'LOSS'
    is_be = t['status'] == 'BREAKEVEN'
    net_r = float(t.get('net_r', 0.0))

    if d in trend_map:
        pred_state = trend_map[d]['pred_state']
        
        # Check alignment
        is_aligned = (t_dir == 'LONG' and pred_state == 'UP') or (t_dir == 'SHORT' and pred_state == 'DOWN')
        is_counter = (t_dir == 'LONG' and pred_state == 'DOWN') or (t_dir == 'SHORT' and pred_state == 'UP')
        is_side = (pred_state == 'SIDEWAYS')

        rec = dict(t)
        rec['pred_state'] = pred_state
        rec['is_aligned'] = is_aligned
        rec['is_counter'] = is_counter
        rec['is_side'] = is_side

        if is_aligned:
            aligned_trades.append(rec)
        elif is_counter:
            counter_trades.append(rec)
        else:
            sideways_trades.append(rec)

def calc_stats(trade_list, name=""):
    if not trade_list:
        return {'name': name, 'count': 0, 'wins': 0, 'losses': 0, 'be': 0, 'wr': 0, 'net_r': 0, 'pf': 0}
    df_sub = pd.DataFrame(trade_list)
    n = len(df_sub)
    w = len(df_sub[df_sub['status'] == 'WIN'])
    l = len(df_sub[df_sub['status'] == 'LOSS'])
    b = len(df_sub[df_sub['status'] == 'BREAKEVEN'])
    net_r = round(float(df_sub['net_r'].sum()), 2)
    gw = df_sub[df_sub['net_r'] > 0]['net_r'].sum()
    gl = abs(df_sub[df_sub['net_r'] < 0]['net_r'].sum())
    pf = round(gw / max(0.01, gl), 2)
    wr = round((w / n) * 100, 1)
    return {'name': name, 'count': n, 'wins': w, 'losses': l, 'be': b, 'wr': wr, 'net_r': net_r, 'pf': pf}

all_stats = calc_stats(trades_df.to_dict('records'), "Baseline (All Trades)")
al_stats = calc_stats(aligned_trades, "Trend-Aligned Only (UP+Long / DOWN+Short)")
ct_stats = calc_stats(counter_trades, "Counter-Trend Setups (Fading Predicted Trend)")
sd_stats = calc_stats(sideways_trades, "Sideways Day Setups")

# Also test Ratified Production Archetypes only (ARCH-001, ARCH-003, ARCH-010, ARCH-014)
ratified_trades = trades_df[trades_df['archetype_id'].isin(['SETUP-ARCH-001', 'SETUP-ARCH-003', 'SETUP-ARCH-010', 'SETUP-ARCH-014'])].copy()

rat_all = []
rat_aligned = []
rat_counter = []
rat_side = []

for _, t in ratified_trades.iterrows():
    d = t['date']
    t_dir = t['direction']
    if d in trend_map:
        pred_state = trend_map[d]['pred_state']
        is_aligned = (t_dir == 'LONG' and pred_state == 'UP') or (t_dir == 'SHORT' and pred_state == 'DOWN')
        is_counter = (t_dir == 'LONG' and pred_state == 'DOWN') or (t_dir == 'SHORT' and pred_state == 'UP')
        
        rec = dict(t)
        rat_all.append(rec)
        if is_aligned:
            rat_aligned.append(rec)
        elif is_counter:
            rat_counter.append(rec)
        else:
            rat_side.append(rec)

r_all_st = calc_stats(rat_all, "Ratified Suite (All Directions)")
r_al_st = calc_stats(rat_aligned, "Ratified + Trend-Aligned Only")
r_ct_st = calc_stats(rat_counter, "Ratified + Counter-Trend Fades")
r_sd_st = calc_stats(rat_side, "Ratified + Sideways Equilibrium")

print("\n💎 RATIFIED INSTITUTIONAL SMC SETUPS UNDER OMNITREND ORACLE:")
print("=" * 85)
for s in [r_all_st, r_al_st, r_ct_st, r_sd_st]:
    print(f"{s['name']:<42} : {s['count']:>3} Fills | {s['wins']}W - {s['losses']}L - {s['be']}BE | WR: {s['wr']:>4.1f}% | Net: {s['net_r']:>+6.2f}R | PF: {s['pf']}")
print("=" * 85)
