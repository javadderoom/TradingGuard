"""
Diagnose OmniTrend Oracle 260-Day Historical Inversions
Analyzes the exact days where OmniTrend Oracle made a Critical Inversion (predicted UP but closed DOWN,
or predicted DOWN but closed UP) to discover the underlying mathematical patterns and market regimes.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LEDGER_PATH = BASE_DIR / "backtest_results" / "trend_oracle_audit" / "omnitrend_3state_daily_accuracy_ledger.csv"

if not LEDGER_PATH.exists():
    print(f"File not found: {LEDGER_PATH}")
    sys.exit(1)

df = pd.read_csv(LEDGER_PATH)

inversions = df[df["is_critical_inversion"] == True].copy()
hits = df[df["is_directional_hit"] == True].copy()
trend_calls = df[df["pred_state"].isin(["UP", "DOWN"])].copy()

print("=" * 80)
print(f"DIAGNOSTIC ANALYSIS OF OMNITREND 260-DAY INVERSIONS ({len(inversions)} Inversions / {len(trend_calls)} Trend Calls)")
print("=" * 80)

# 1. ADR and Pre-Session Range in Inversions vs Hits
inversions["adr_utilization"] = inversions["range"] / inversions["adr_14"]
hits["adr_utilization"] = hits["range"] / hits["adr_14"]

print(f"Mean ADR of Inversion Days : {inversions['adr_14'].mean():.2f} pts | Actual Range: {inversions['range'].mean():.2f} pts")
print(f"Mean ADR of Hit Days       : {hits['adr_14'].mean():.2f} pts | Actual Range: {hits['range'].mean():.2f} pts")

# 2. Confidence Distribution of Inversions
print("\nInversion Count by Confidence Tier:")
for conf in sorted(trend_calls["confidence"].unique()):
    sub = trend_calls[trend_calls["confidence"] == conf]
    sub_inv = sub[sub["is_critical_inversion"] == True]
    sub_hit = sub[sub["is_directional_hit"] == True]
    print(f"  Confidence {conf:.2f}: Total={len(sub):>3} | Hits={len(sub_hit):>3} ({len(sub_hit)/len(sub)*100:.1f}%) | Inversions={len(sub_inv):>3} ({len(sub_inv)/len(sub)*100:.1f}%)")

# 3. Monthly Breakdown of Inversions
df["month"] = df["date"].str[:7]
print("\nMonthly Performance Breakdown:")
print(f"{'Month':<8} | {'Total':<6} | {'UP':<5} | {'DOWN':<5} | {'SIDEWAYS':<8} | {'Dir Hit Rate':<12} | {'Inversions':<10}")
print("-" * 75)
for m in sorted(df["month"].unique()):
    sub_m = df[df["month"] == m]
    t_c = sub_m[sub_m["pred_state"].isin(["UP", "DOWN"])]
    h_c = t_c[t_c["is_directional_hit"] == True]
    inv_c = t_c[t_c["is_critical_inversion"] == True]
    up_c = len(sub_m[sub_m["pred_state"] == "UP"])
    dn_c = len(sub_m[sub_m["pred_state"] == "DOWN"])
    sd_c = len(sub_m[sub_m["pred_state"] == "SIDEWAYS"])
    hit_pct = (len(h_c) / max(1, len(t_c))) * 100
    print(f"{m:<8} | {len(sub_m):<6} | {up_c:<5} | {dn_c:<5} | {sd_c:<8} | {hit_pct:>5.1f}%      | {len(inv_c):>3} ({len(inv_c)/max(1,len(t_c))*100:.1f}%)")
print("-" * 75)
