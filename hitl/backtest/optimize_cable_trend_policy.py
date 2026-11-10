"""
TradingGuard HITL - Cable (GBPUSD) Trend Policy Grid Search
Systematically evaluates target and breakeven ratchet combinations for Cable
to discover the mathematical optimum across the 90 Ratified Cable trades and 255 total trades.
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

results = []

# Grid search across TP (1.5 to 3.5) and BE ratchet (0.8 to 1.8)
for al_tp in [2.0, 2.5, 3.0]:
    for al_be in [1.0, 1.2, 1.5]:
        for ct_tp in [1.5, 2.0, 2.5, 3.0]:
            for ct_be in [0.8, 1.0, 1.2]:
                for sd_tp in [2.0, 2.5, 3.0]:
                    for sd_be in [0.8, 1.0, 1.2]:
                        pnl_list = []
                        for _, t in ratified.iterrows():
                            d = t['date']
                            t_dir = t['direction']
                            pred = trend_map.get(d, {}).get('pred_state', "SIDEWAYS")
                            is_aligned = (t_dir == 'LONG' and pred == 'UP') or (t_dir == 'SHORT' and pred == 'DOWN')
                            is_counter = (t_dir == 'LONG' and pred == 'DOWN') or (t_dir == 'SHORT' and pred == 'UP')

                            if is_aligned: tp, be = al_tp, al_be
                            elif is_counter: tp, be = ct_tp, ct_be
                            else: tp, be = sd_tp, sd_be

                            r, s = simulate_trade_pnl(t, tp, be)
                            pnl_list.append((r, s))

                        n = len(pnl_list)
                        w = sum(1 for r, s in pnl_list if s == 'WIN')
                        l = sum(1 for r, s in pnl_list if s == 'LOSS')
                        b = sum(1 for r, s in pnl_list if s == 'BREAKEVEN')
                        net_r = sum(r for r, s in pnl_list)
                        gw = sum(r for r, s in pnl_list if r > 0)
                        gl = abs(sum(r for r, s in pnl_list if r < 0))
                        pf = round(gw / max(0.01, gl), 2)
                        wr = round((w / n) * 100, 1)

                        results.append({
                            "al_tp": al_tp, "al_be": al_be,
                            "ct_tp": ct_tp, "ct_be": ct_be,
                            "sd_tp": sd_tp, "sd_be": sd_be,
                            "net_r": round(net_r, 2), "pf": pf, "wr": wr,
                            "w": w, "l": l, "b": b
                        })

results.sort(key=lambda x: (x["net_r"], x["pf"]), reverse=True)

print("=" * 95)
print(f"CABLE ASYMMETRIC POLICY OPTIMIZATION: TOP 10 MODELS (out of {len(results)} variations)")
print("=" * 95)
print("Rank | Aligned TP/BE | Counter TP/BE | Sideways TP/BE | Net R   | PF   | Win Rate | W-L-BE")
print("-" * 95)
for idx, r in enumerate(results[:10], 1):
    print(f"#{idx:<3} | {r['al_tp']:.1f}R / {r['al_be']:.1f}R | {r['ct_tp']:.1f}R / {r['ct_be']:.1f}R  | {r['sd_tp']:.1f}R / {r['sd_be']:.1f}R   | {r['net_r']:>+6.2f}R | {r['pf']:>4.2f} | {r['wr']:>5.1f}%   | {r['w']}W-{r['l']}L-{r['b']}BE")
print("=" * 95)
