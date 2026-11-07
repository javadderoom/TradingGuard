"""
TradingGuard HITL - SubQ Snap Pooled Benchmark Synthesis
Aggregates all 150 SubQ Snap candidate evaluations across Spring, Summer, and Autumn 2026.
"""

import sys
import json
import pandas as pd
from pathlib import Path

# Enforce UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
EVAL_DIR = BASE_DIR / "backtest_results" / "snap_evaluations"

files = [
    EVAL_DIR / "subq_snap_comprehensive_ledger.csv",
    EVAL_DIR / "subq_snap_ledger_autumn_late.csv",
    EVAL_DIR / "subq_snap_ledger_spring.csv"
]

dfs = []
for f in files:
    if f.exists():
        df = pd.read_csv(f)
        dfs.append(df)
        print(f"Loaded {len(df)} rows from {f.name}")

if not dfs:
    print("No CSV files found!")
    sys.exit(1)

master_df = pd.concat(dfs, ignore_index=True)
master_csv = EVAL_DIR / "subq_snap_master_pooled_ledger_150.csv"
master_df.to_csv(master_csv, index=False)
print(f"Saved {len(master_df)} pooled rows to {master_csv.name}")

# Metrics
total_evals = len(master_df)
snap_stand_asides = len(master_df[master_df["snap_decision"] == "STAND_ASIDE"])
stand_aside_rate = (snap_stand_asides / total_evals) * 100.0

avg_latency = master_df["snap_latency_ms"].mean()
p50_latency = master_df["snap_latency_ms"].median()
p90_latency = master_df["snap_latency_ms"].quantile(0.90)
min_latency = master_df["snap_latency_ms"].min()
max_latency = master_df["snap_latency_ms"].max()

# Closed Trades Only (Pack 6 Standards)
blind_closed = master_df[master_df["blind_status"].isin(["WIN", "LOSS", "BREAKEVEN"])]
blind_wins = blind_closed[blind_closed["blind_status"] == "WIN"]
blind_losses = blind_closed[blind_closed["blind_status"] == "LOSS"]
blind_net = blind_closed["blind_pnl_usd"].sum()
blind_gross_profit = blind_wins["blind_pnl_usd"].sum()
blind_gross_loss = abs(blind_losses["blind_pnl_usd"].sum())
blind_pf = (blind_gross_profit / blind_gross_loss) if blind_gross_loss > 0 else 0.0
blind_wr = (len(blind_wins) / len(blind_closed) * 100.0) if len(blind_closed) > 0 else 0.0

snap_closed = master_df[master_df["snap_status"].isin(["WIN", "LOSS", "BREAKEVEN"])]
snap_wins = snap_closed[snap_closed["snap_status"] == "WIN"]
snap_losses = snap_closed[snap_closed["snap_status"] == "LOSS"]
snap_net = snap_closed["snap_pnl_usd"].sum()
snap_gross_profit = snap_wins["snap_pnl_usd"].sum()
snap_gross_loss = abs(snap_losses["snap_pnl_usd"].sum())
snap_pf = (snap_gross_profit / snap_gross_loss) if snap_gross_loss > 0 else 0.0
snap_wr = (len(snap_wins) / len(snap_closed) * 100.0) if len(snap_closed) > 0 else 0.0

# Counterfactual
prot_vetoes = master_df[master_df["counterfactual_role"] == "PROTECTIVE_VETO"]
dam_vetoes = master_df[master_df["counterfactual_role"] == "DAMAGING_STAND_ASIDE"]
avoided_exp = master_df[master_df["counterfactual_role"] == "AVOIDED_EXPIRED"]

capital_saved = abs(prot_vetoes["blind_pnl_usd"].sum())
missed_alpha = dam_vetoes["blind_pnl_usd"].sum()
net_snap_alpha = capital_saved - missed_alpha

# Primary Drivers
driver_counts = master_df["snap_driver"].value_counts().to_dict()

pooled_summary = {
    "total_candidate_setups": total_evals,
    "stand_aside_rate_pct": round(stand_aside_rate, 2),
    "latency_stats_ms": {
        "mean": round(avg_latency, 1),
        "median_p50": round(p50_latency, 1),
        "p90": round(p90_latency, 1),
        "min": round(min_latency, 1),
        "max": round(max_latency, 1)
    },
    "blind_screener_baseline": {
        "closed_trades": len(blind_closed),
        "wins": len(blind_wins),
        "losses": len(blind_losses),
        "win_rate_pct": round(blind_wr, 2),
        "net_realized_pnl_usd": round(blind_net, 2),
        "profit_factor": round(blind_pf, 2)
    },
    "subq_snap_gated": {
        "approved_orders": total_evals - snap_stand_asides,
        "closed_trades": len(snap_closed),
        "wins": len(snap_wins),
        "losses": len(snap_losses),
        "win_rate_pct": round(snap_wr, 2),
        "net_realized_pnl_usd": round(snap_net, 2),
        "profit_factor": round(snap_pf, 2)
    },
    "counterfactual_veto_value": {
        "protective_vetoes_count": len(prot_vetoes),
        "damaging_stand_asides_count": len(dam_vetoes),
        "avoided_expired_count": len(avoided_exp),
        "capital_saved_usd": round(capital_saved, 2),
        "missed_alpha_usd": round(missed_alpha, 2),
        "net_snap_alpha_usd": round(net_snap_alpha, 2)
    },
    "veto_driver_breakdown": driver_counts
}

summary_json = EVAL_DIR / "subq_snap_master_pooled_summary.json"
with open(summary_json, "w", encoding="utf-8") as f:
    json.dump(pooled_summary, f, indent=2)

print("\n" + "="*95)
print("🏛️ SUBQ SNAP MASTER POOLED SYNTHESIS (150 HISTORICAL SESSIONS AUDITED)")
print("="*95)
print(f"Total Candidate Setups Evaluated: {total_evals}")
print(f"SubQ Snap Stand-Aside Rate:       {stand_aside_rate:.1f}% ({snap_stand_asides} of {total_evals})")
print(f"Average Decision Latency:         {avg_latency:.1f}ms (p50: {p50_latency:.1f}ms, p90: {p90_latency:.1f}ms)")
print("-"*95)
print(f"BLIND SCREENER BASELINE:  {len(blind_closed)} closed | {len(blind_wins)}W / {len(blind_losses)}L | WR: {blind_wr:.1f}% | Net PnL: ${blind_net:+.2f} | PF: {blind_pf:.2f}")
print(f"SUBQ SNAP GATED:          {len(snap_closed)} closed | {len(snap_wins)}W / {len(snap_losses)}L | WR: {snap_wr:.1f}% | Net PnL: ${snap_net:+.2f} | PF: {snap_pf:.2f}")
print("-"*95)
print("COUNTERFACTUAL VETO AUDIT:")
print(f"  • Protective Vetoes (Losses Saved): {len(prot_vetoes)} trades (+${capital_saved:.2f} capital saved)")
print(f"  • Damaging Vetoes (Missed Winners): {len(dam_vetoes)} trades (-${missed_alpha:.2f} missed alpha)")
print(f"  • Avoided Expired / Dead Orders:    {len(avoided_exp)} setups")
print(f"  • NET VALUE OF SUBQ SNAP FILTER:    +${net_snap_alpha:.2f} NET VALUE ADDED")
print("-"*95)
print("VETO DRIVERS DISTRIBUTION:")
for d, cnt in driver_counts.items():
    print(f"  • {d}: {cnt} ({cnt/total_evals*100:.1f}%)")
print("="*95)
