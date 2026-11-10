"""
TradingGuard HITL - NASDAQ 100 Screener & Strategy Impact Audit
Cross-references OmniTrend Oracle predictions against authentic NQ trades
to measure win rate, profit factor, net alpha, and alignment behavior.
"""

import sys
import json
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

OUTPUT_DIR = BASE_DIR / "backtest_results" / "nq_trend_oracle_audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_nq_screener_impact_audit():
    # Load 3-state ledger
    ledger_path = OUTPUT_DIR / "nq_omnitrend_3state_ledger.csv"
    if not ledger_path.exists():
        raise FileNotFoundError(f"Missing {ledger_path}")
    ledger_df = pd.read_csv(ledger_path)
    pred_by_date = dict(zip(ledger_df["date"], ledger_df["pred_state"]))
    dol_by_date = dict(zip(ledger_df["date"], ledger_df["dol_type"]))

    # 1. Audit Unified 5-Month NQ Suite (190 filled trades)
    p5 = BASE_DIR / "backtest_results" / "nq_summer_2month_audit" / "nq_unified_5_month_trades.csv"
    trades_5m = pd.read_csv(p5)
    filled_5m = trades_5m[trades_5m["status"].isin(["WIN", "LOSS", "BREAKEVEN"])].copy()

    # Map alignment
    alignments_5m = []
    for _, row in filled_5m.iterrows():
        d = str(row["date"])
        pred = pred_by_date.get(d, "SIDEWAYS")
        direction = row["direction"].upper()

        if pred == "SIDEWAYS":
            alignments_5m.append("SIDEWAYS")
        elif (pred == "UP" and direction == "BUY") or (pred == "DOWN" and direction == "SELL"):
            alignments_5m.append("TREND_ALIGNED")
        else:
            alignments_5m.append("COUNTER_TREND")

    filled_5m["alignment"] = alignments_5m

    print("\n" + "=" * 85)
    print("📊 NASDAQ 100 5-MONTH SUITE: PERFORMANCE BY TREND ALIGNMENT (BASELINE 3.5R)")
    print("=" * 85)

    summary_rows_5m = []
    for cat in ["COUNTER_TREND", "TREND_ALIGNED", "SIDEWAYS"]:
        sub = filled_5m[filled_5m["alignment"] == cat]
        n = len(sub)
        if n == 0:
            continue
        wins = len(sub[sub["status"] == "WIN"])
        losses = len(sub[sub["status"] == "LOSS"])
        be = len(sub[sub["status"] == "BREAKEVEN"])
        wr = (wins / n) * 100.0

        gross_win = sum(row["rr_realized"] for _, row in sub.iterrows() if row["rr_realized"] > 0)
        gross_loss = abs(sum(row["rr_realized"] for _, row in sub.iterrows() if row["rr_realized"] < 0))
        net_r = gross_win - gross_loss
        pf = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)

        print(f"[{cat:13s}] Fills: {n:3d} | W: {wins:2d} | L: {losses:2d} | BE: {be:2d} | WR: {wr:5.1f}% | Net: {net_r:+6.2f}R | PF: {pf:5.2f}")
        summary_rows_5m.append({
            "category": cat,
            "fills": n,
            "wins": wins,
            "losses": losses,
            "be": be,
            "win_rate": round(wr, 1),
            "net_r": round(net_r, 2),
            "profit_factor": round(pf, 2)
        })

    # Total 5m baseline
    n_tot = len(filled_5m)
    w_tot = len(filled_5m[filled_5m["status"] == "WIN"])
    l_tot = len(filled_5m[filled_5m["status"] == "LOSS"])
    b_tot = len(filled_5m[filled_5m["status"] == "BREAKEVEN"])
    gw_tot = sum(row["rr_realized"] for _, row in filled_5m.iterrows() if row["rr_realized"] > 0)
    gl_tot = abs(sum(row["rr_realized"] for _, row in filled_5m.iterrows() if row["rr_realized"] < 0))
    net_tot = gw_tot - gl_tot
    pf_tot = (gw_tot / gl_tot) if gl_tot > 0 else 0.0
    print("-" * 85)
    print(f"[CONSOLIDATED ] Fills: {n_tot:3d} | W: {w_tot:2d} | L: {l_tot:2d} | BE: {b_tot:2d} | WR: {w_tot/n_tot*100:5.1f}% | Net: {net_tot:+6.2f}R | PF: {pf_tot:5.2f}")
    print("=" * 85)

    # 2. Check Curated Production Suite (London Bearish Judas Breakers)
    p_cur = BASE_DIR / "backtest_results" / "unified_portfolio_audit" / "trades_nq.parquet"
    if p_cur.exists():
        trades_cur = pd.read_parquet(p_cur)
        filled_cur = trades_cur[trades_cur["status"].isin(["WIN", "LOSS", "BREAKEVEN"])].copy()
        if len(filled_cur) > 0:
            alignments_cur = []
            for _, row in filled_cur.iterrows():
                d = str(row["date"])
                pred = pred_by_date.get(d, "SIDEWAYS")
                direction = row["direction"].upper()
                if pred == "SIDEWAYS":
                    alignments_cur.append("SIDEWAYS")
                elif (pred == "UP" and direction == "BUY") or (pred == "DOWN" and direction == "SELL"):
                    alignments_cur.append("TREND_ALIGNED")
                else:
                    alignments_cur.append("COUNTER_TREND")
            filled_cur["alignment"] = alignments_cur

            print("\n" + "=" * 85)
            print("📊 NASDAQ 100 RATIFIED SMC SUITE (16 Fills, ARCH-001 Bearish Breakers):")
            print("=" * 85)
            for cat in ["COUNTER_TREND", "TREND_ALIGNED", "SIDEWAYS"]:
                sub = filled_cur[filled_cur["alignment"] == cat]
                n = len(sub)
                if n == 0:
                    continue
                wins = len(sub[sub["status"] == "WIN"])
                losses = len(sub[sub["status"] == "LOSS"])
                be = len(sub[sub["status"] == "BREAKEVEN"])
                wr = (wins / n) * 100.0
                gw = sum(row["rr_realized"] for _, row in sub.iterrows() if row["rr_realized"] > 0)
                gl = abs(sum(row["rr_realized"] for _, row in sub.iterrows() if row["rr_realized"] < 0))
                net_r = gw - gl
                pf = (gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)
                print(f"[{cat:13s}] Fills: {n:3d} | W: {wins:2d} | L: {losses:2d} | BE: {be:2d} | WR: {wr:5.1f}% | Net: {net_r:+6.2f}R | PF: {pf:5.2f}")
            print("=" * 85 + "\n")

    # Save summary
    res_path = OUTPUT_DIR / "nq_alignment_baseline_summary.json"
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(summary_rows_5m, f, indent=2)
    print(f"✅ Saved NQ Alignment Baseline Summary to {res_path}")


if __name__ == "__main__":
    run_nq_screener_impact_audit()
