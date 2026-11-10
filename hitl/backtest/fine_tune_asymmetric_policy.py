"""
TradingGuard HITL - Fine-Grained Policy Optimization for Asymmetric Trade Management
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
ratified_trades = trades_df[trades_df['archetype_id'].isin(['SETUP-ARCH-001', 'SETUP-ARCH-003', 'SETUP-ARCH-010', 'SETUP-ARCH-014'])].copy()

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

results = []

for al_tp in [3.0, 3.5, 4.0]:
    for al_be in [1.5, 1.8]:
        for ct_tp in [1.5, 2.0, 2.5]:
            for ct_be in [0.8, 1.0, 1.2]:
                for sd_tp in [2.0, 2.5, 3.0, 3.5]:
                    for sd_be in [1.0, 1.2, 1.5, 1.8]:
                        # Run
                        pnl_list = []
                        for _, t in ratified_trades.iterrows():
                            d = t['date']
                            t_dir = t['direction']
                            pred = trend_map.get(d, "SIDEWAYS")
                            is_aligned = (t_dir == 'LONG' and pred == 'UP') or (t_dir == 'SHORT' and pred == 'DOWN')
                            is_counter = (t_dir == 'LONG' and pred == 'DOWN') or (t_dir == 'SHORT' and pred == 'UP')

                            if is_aligned:
                                tp, be = al_tp, al_be
                            elif is_counter:
                                tp, be = ct_tp, ct_be
                            else:
                                tp, be = sd_tp, sd_be

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

# Sort by Net R, then PF
results.sort(key=lambda x: (x["net_r"], x["pf"]), reverse=True)

print(f"Evaluated {len(results)} asymmetric policy configurations.")
print("-" * 95)
print("Rank | Aligned TP/BE | Counter TP/BE | Sideways TP/BE | Net R  | PF   | Win Rate | W-L-BE")
print("-" * 95)
for idx, r in enumerate(results[:12], 1):
    print(f"#{idx:<3} | {r['al_tp']:.1f}R / {r['al_be']:.1f}R | {r['ct_tp']:.1f}R / {r['ct_be']:.1f}R  | {r['sd_tp']:.1f}R / {r['sd_be']:.1f}R   | {r['net_r']:>+6.2f}R | {r['pf']:>4.2f} | {r['wr']:>5.1f}%   | {r['w']}W-{r['l']}L-{r['b']}BE")
print("-" * 95)
