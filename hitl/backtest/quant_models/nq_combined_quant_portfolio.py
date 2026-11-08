"""
TradingGuard Quantitative Alpha Research - Combined Institutional Quant Strategy
Combines:
  1. London Open 30-Minute Opening Range Breakout (ORB)
  2. NY Pre-Market HTF-Gated Major Liquidity Sweeps (SETUP-ARCH-001)
Evaluates continuous 5.2 months on Nasdaq 100 (June 1 - Nov 6, 2026: 32,974 M5 bars, 157,960 M1 bars).
"""

import sys
import os
import json
import time
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Tuple, Dict, Any, List
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.evaluator import evaluate_council_decision

CACHE_DIR = BASE_DIR / 'backtest_results' / 'cache'
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'quant_models' / 'combined_quant'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load trades from ORB (London Open) and HTF Gated Sweeps
df_orb = pd.read_parquet(OUTPUT_DIR.parent / 'orb_model' / 'nq_orb_london_open_trades.parquet')
df_htf = pd.read_parquet(OUTPUT_DIR.parent / 'htf_gated_model' / 'nq_htf_arch001_target_35_trades.parquet')

# Filter out warmup period before June 1, 2026
df_orb = df_orb[df_orb['date'] >= '2026-06-01'].copy()
df_htf = df_htf[df_htf['date'] >= '2026-06-01'].copy()

df_orb['strategy'] = 'London_30m_ORB'
df_htf['strategy'] = 'NY_HTF_Sweep_ARCH001'

# Combine and sort chronologically
df_comb = pd.concat([df_orb, df_htf]).sort_values('epoch').reset_index(drop=True)
df_comb.to_parquet(OUTPUT_DIR / 'nq_combined_quant_trades.parquet')
df_comb.to_csv(OUTPUT_DIR / 'nq_combined_quant_trades.csv', index=False)

def calc_stats(df_sub):
    fills = df_sub[df_sub['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
    n = len(fills)
    wins = len(df_sub[df_sub['status'] == 'WIN'])
    losses = len(df_sub[df_sub['status'] == 'LOSS'])
    be = len(df_sub[df_sub['status'] == 'BREAKEVEN'])
    exp = len(df_sub[df_sub['status'] == 'EXPIRED'])
    wr = (wins / n * 100) if n > 0 else 0.0
    net_r = df_sub['rr_realized'].sum() if len(df_sub) > 0 else 0.0
    net_pnl = df_sub['realized_pnl_usd'].sum() if len(df_sub) > 0 else 0.0
    gp = df_sub[df_sub['realized_pnl_usd'] > 0]['realized_pnl_usd'].sum() if len(df_sub) > 0 else 0.0
    gl = abs(df_sub[df_sub['realized_pnl_usd'] < 0]['realized_pnl_usd'].sum()) if len(df_sub) > 0 else 0.0
    pf = (gp / gl) if gl > 0 else (99.0 if gp > 0 else 0.0)
    return {
        "Signals": len(df_sub), "Fills": n, "Wins": wins, "Losses": losses, "BE": be, "Exp": exp,
        "WR%": round(wr, 1), "Net_R": round(net_r, 2), "Net_PnL": round(net_pnl, 2), "PF": round(pf, 2)
    }

s_orb = calc_stats(df_orb)
s_htf = calc_stats(df_htf)
s_all = calc_stats(df_comb)

print("=" * 95)
print("🚀 COMBINED INSTITUTIONAL QUANT STRATEGY ON NASDAQ 100 (NQ)")
print("June 1 to November 6, 2026 | Continuous MT5 Broker Microstructure")
print("=" * 95)
print(f"1. London 30m ORB          : {s_orb}")
print(f"2. NY HTF-Gated Sweeps     : {s_htf}")
print(f"COMBINED QUANT STRATEGY    : {s_all}")

print("\n--- Month-by-Month Progression ---")
df_comb['month'] = pd.to_datetime(df_comb['date']).dt.strftime('%Y-%m')
for m, g in df_comb.groupby('month'):
    sm = calc_stats(g)
    print(f"  {m} | Fills: {sm['Fills']:2d} | W: {sm['Wins']:2d} | L: {sm['Losses']:2d} | BE: {sm['BE']:2d} | WR: {sm['WR%']:5.1f}% | Net R: {sm['Net_R']:+6.2f}R | Net PnL: ${sm['Net_PnL']:+6.2f} | PF: {sm['PF']:.2f}")

summary = {
    "orb_stats": s_orb,
    "htf_stats": s_htf,
    "combined_stats": s_all
}
with open(OUTPUT_DIR / "combined_quant_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

print(f"\n✅ Combined Audit complete! Saved to {OUTPUT_DIR}")
