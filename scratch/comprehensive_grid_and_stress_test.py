"""
Comprehensive Grid Optimizer & Nov 13 Liquidation Stress Test
"""

import sys
import datetime
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scratch.audit_model1_breakout import run_model1_audit
from scratch.audit_model2_judas_reversal import run_model2_audit
from scratch.audit_model3_smt_divergence import run_model3_audit

print("="*80)
print("PARAMETER SENSITIVITY GRID AUDIT")
print("="*80)

# 1. Model 1 Target R:R Sensitivity
print("\n--- Model 1 (ISB-PC-01) Target R:R Sensitivity ---")
for sym in ["XAUUSD_o", "GBPUSD_o", "NQ"]:
    print(f"\nAsset: {sym}")
    for rr in [2.0, 2.5, 3.0, 3.5]:
        _, overall, lon, ny = run_model1_audit(sym, target_rr=rr)
        print(f"  TP={rr}R -> Overall: N={overall['closed_trades']}, WR={overall['win_rate_pct']}%, Net R={overall['net_r']:+.2f}, PF={overall['profit_factor']:.2f}, EV={overall['ev_r']:+.3f}R, MaxDD={overall['max_drawdown_r']:.2f}R | Lon Net R={lon['net_r']:+.2f} | NY Net R={ny['net_r']:+.2f}")

# 2. Model 2 Target R:R & Entry Mode Sensitivity
print("\n\n--- Model 2 (SE-JSR-02) Entry Mode & Target R:R Sensitivity ---")
for sym in ["XAUUSD_o", "NQ"]:
    print(f"\nAsset: {sym}")
    for mode in ["T1_CLOSE", "MIDPOINT"]:
        for rr in [1.5, 2.0, 2.5]:
            shorts_only = (sym == "XAUUSD_o")
            _, overall, lon, ny = run_model2_audit(sym, target_rr=rr, entry_mode=mode, shorts_only=shorts_only)
            mode_lbl = "Shorts-Only" if shorts_only else "All"
            print(f"  Mode={mode} ({mode_lbl}), TP={rr}R -> N={overall['closed_trades']}, WR={overall['win_rate_pct']}%, Net R={overall['net_r']:+.2f}, PF={overall['profit_factor']:.2f}, EV={overall['ev_r']:+.3f}R, MaxDD={overall['max_drawdown_r']:.2f}R | Lon Net R={lon['net_r']:+.2f} | NY Net R={ny['net_r']:+.2f}")

# 3. Model 3 Target R:R Sensitivity
print("\n\n--- Model 3 (SMT-CD-03) Target R:R Sensitivity ---")
for rr in [2.5, 3.0, 3.5]:
    _, overall, lon, ny = run_model3_audit(target_rr=rr)
    print(f"  NQ (SPX/YM Radar), TP={rr}R -> N={overall['closed_trades']}, WR={overall['win_rate_pct']}%, Net R={overall['net_r']:+.2f}, PF={overall['profit_factor']:.2f}, EV={overall['ev_r']:+.3f}R, MaxDD={overall['max_drawdown_r']:.2f}R | Lon Net R={lon['net_r']:+.2f} | NY Net R={ny['net_r']:+.2f}")

# 4. Stress Test: Nov 13, 2026 Liquidation Analysis
print("\n\n" + "="*80)
print("NOV 13, 2026 HIGH-VOLUME LIQUIDATION STRESS TEST")
print("="*80)

for name, runner, args in [
    ("Model 1 XAUUSD", run_model1_audit, ("XAUUSD_o", 3.0)),
    ("Model 1 NQ", run_model1_audit, ("NQ", 3.0)),
    ("Model 2 XAUUSD (Shorts-Only)", run_model2_audit, ("XAUUSD_o", 2.0, "T1_CLOSE", True)),
    ("Model 2 NQ", run_model2_audit, ("NQ", 2.0, "T1_CLOSE", False)),
    ("Model 3 NQ (SMT)", run_model3_audit, (3.0,))
]:
    df_tr, _, _, _ = runner(*args)
    if not df_tr.empty and 'date' in df_tr.columns:
        nov13_tr = df_tr[df_tr['date'] == '2026-11-13']
        if not nov13_tr.empty:
            print(f"\n{name} on 2026-11-13:")
            for _, r in nov13_tr.iterrows():
                print(f"  Time: {r.get('bar_t_time')} | Dir: {r.get('direction')} | Status: {r.get('status')} | Net R: {r.get('realized_r'):+.2f} | PnL: ${r.get('realized_pnl_usd'):+.2f} | Notes: {r.get('notes')}")
        else:
            print(f"\n{name} on 2026-11-13: ZERO TRADES (Safely Filtered / Vetoed)")
