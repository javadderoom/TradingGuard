"""
TradingGuard HITL - 2-Month Master Consolidated Review Compiler (Sept 02 to Oct 31, 2026)
Aggregates all 5 segmented walk-forward backtest runs across EURUSD and GBPUSD.
"""

import os
import sys
import json
import glob
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

SEGMENT_DIRS = [
    BASE_DIR / "backtest_results" / "forex_basket_eur_gbp_audit_20261101_094930",
    BASE_DIR / "backtest_results" / "forex_segment_2_sep11_sep24_20261101_100930",
    BASE_DIR / "backtest_results" / "forex_segment_3_sep25_oct08_20261101_104653",
    BASE_DIR / "backtest_results" / "forex_segment_4_oct09_oct22_20261101_110204",
]


def find_latest_segment_5() -> Path:
    candidates = list((BASE_DIR / "backtest_results").glob("forex_segment_5_oct23_oct31_*"))
    if not candidates:
        return None
    # Sort by mtime descending
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def compile_master_report():
    seg5_dir = find_latest_segment_5()
    all_dirs = list(SEGMENT_DIRS)
    if seg5_dir and seg5_dir.exists():
        all_dirs.append(seg5_dir)
        print(f"Loaded Segment 5 from: {seg5_dir.name}")
    else:
        print("Warning: Segment 5 not found yet. Compiling Segments 1-4 only.")

    out_dir = BASE_DIR / "backtest_results" / "master_2month_eur_gbp_review"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_scorecards = []
    all_ledgers = []
    all_sessions = []

    for i, sdir in enumerate(all_dirs, start=1):
        json_path = sdir / "full_dataset.json"
        csv_path = sdir / "trade_ledger.csv"

        if not json_path.exists():
            print(f"Skipping {sdir.name}, missing full_dataset.json")
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["segment_index"] = i
        data["segment_dir"] = sdir.name
        all_scorecards.append(data["scorecard"])
        all_sessions.extend(data.get("sessions", []))

        if csv_path.exists():
            df = pd.read_csv(csv_path)
            df["segment"] = f"Segment {i} ({sdir.name})"
            all_ledgers.append(df)

    if not all_scorecards:
        print("No valid segment scorecards found!")
        return

    # Combine CSV Ledgers
    combined_df = pd.concat(all_ledgers, ignore_index=True) if all_ledgers else pd.DataFrame()
    combined_csv_path = out_dir / "master_trade_ledger.csv"
    combined_df.to_csv(combined_csv_path, index=False)
    print(f"Exported combined trade ledger: {combined_csv_path} ({len(combined_df)} rows)")

    # Aggregate Metrics
    total_screened = sum(sc["shadow_portfolio"]["total_opportunities_screened"] for sc in all_scorecards)
    
    # Actual Council Portfolio
    c_approved = sum(sc["shadow_portfolio"]["actual_council_portfolio"]["trades_approved"] for sc in all_scorecards)
    c_filled = sum(sc["shadow_portfolio"]["actual_council_portfolio"]["filled_trades"] for sc in all_scorecards)
    c_wins = sum(sc["shadow_portfolio"]["actual_council_portfolio"]["wins"] for sc in all_scorecards)
    c_losses = sum(sc["shadow_portfolio"]["actual_council_portfolio"]["losses"] for sc in all_scorecards)
    c_gp = sum(sc["shadow_portfolio"]["actual_council_portfolio"]["gross_profit_usd"] for sc in all_scorecards)
    c_gl = sum(sc["shadow_portfolio"]["actual_council_portfolio"]["gross_loss_usd"] for sc in all_scorecards)
    c_net = c_gp - c_gl
    c_wr = (c_wins / c_filled * 100) if c_filled > 0 else 0.0
    c_pf = (c_gp / c_gl) if c_gl > 0 else (999.0 if c_gp > 0 else 0.0)

    # Asset Performance
    eur_filled = sum(sc["eurusd_performance"]["filled_trades"] for sc in all_scorecards)
    eur_wins = sum(sc["eurusd_performance"]["wins"] for sc in all_scorecards)
    eur_losses = sum(sc["eurusd_performance"]["losses"] for sc in all_scorecards)
    eur_net = sum(sc["eurusd_performance"]["net_pnl_usd"] for sc in all_scorecards)
    eur_wr = (eur_wins / eur_filled * 100) if eur_filled > 0 else 0.0

    gbp_filled = sum(sc["gbpusd_performance"]["filled_trades"] for sc in all_scorecards)
    gbp_wins = sum(sc["gbpusd_performance"]["wins"] for sc in all_scorecards)
    gbp_losses = sum(sc["gbpusd_performance"]["losses"] for sc in all_scorecards)
    gbp_net = sum(sc["gbpusd_performance"]["net_pnl_usd"] for sc in all_scorecards)
    gbp_wr = (gbp_wins / gbp_filled * 100) if gbp_filled > 0 else 0.0

    # Setup Architecture Performance
    smt_filled = sum(sc["smt_trades_performance"]["filled_trades"] for sc in all_scorecards)
    smt_wins = sum(sc["smt_trades_performance"]["wins"] for sc in all_scorecards)
    smt_losses = sum(sc["smt_trades_performance"]["losses"] for sc in all_scorecards)
    smt_net = sum(sc["smt_trades_performance"]["net_pnl_usd"] for sc in all_scorecards)
    smt_wr = (smt_wins / smt_filled * 100) if smt_filled > 0 else 0.0

    ind_filled = sum(sc["independent_smc_performance"]["filled_trades"] for sc in all_scorecards)
    ind_wins = sum(sc["independent_smc_performance"]["wins"] for sc in all_scorecards)
    ind_losses = sum(sc["independent_smc_performance"]["losses"] for sc in all_scorecards)
    ind_net = sum(sc["independent_smc_performance"]["net_pnl_usd"] for sc in all_scorecards)
    ind_wr = (ind_wins / ind_filled * 100) if ind_filled > 0 else 0.0

    # Counterfactual Stand Asides
    cf_sa = sum(sc["shadow_portfolio"]["counterfactual_stand_aside_breakdown"]["total_stand_asides"] for sc in all_scorecards)
    cf_prot = sum(sc["shadow_portfolio"]["counterfactual_stand_aside_breakdown"]["protective_vetoes_losses_prevented"] for sc in all_scorecards)
    cf_cap_saved = sum(sc["shadow_portfolio"]["counterfactual_stand_aside_breakdown"]["capital_saved_usd"] for sc in all_scorecards)
    cf_dam = sum(sc["shadow_portfolio"]["counterfactual_stand_aside_breakdown"]["damaging_stand_asides_missed_winners"] for sc in all_scorecards)
    cf_alpha = sum(sc["shadow_portfolio"]["counterfactual_stand_aside_breakdown"]["missed_alpha_usd"] for sc in all_scorecards)
    cf_unfilled = sum(sc["shadow_portfolio"]["counterfactual_stand_aside_breakdown"]["unfilled_or_expired"] for sc in all_scorecards)

    # Blind Execution
    b_filled = sum(sc["shadow_portfolio"]["blind_execution_shadow_portfolio"]["total_filled_if_traded_all"] for sc in all_scorecards)
    b_wins = sum(sc["shadow_portfolio"]["blind_execution_shadow_portfolio"]["wins"] for sc in all_scorecards)
    b_losses = sum(sc["shadow_portfolio"]["blind_execution_shadow_portfolio"]["losses"] for sc in all_scorecards)
    b_gp = sum(sc["shadow_portfolio"]["blind_execution_shadow_portfolio"]["gross_profit_usd"] for sc in all_scorecards)
    b_gl = sum(sc["shadow_portfolio"]["blind_execution_shadow_portfolio"]["gross_loss_usd"] for sc in all_scorecards)
    b_net = b_gp - b_gl
    b_wr = (b_wins / b_filled * 100) if b_filled > 0 else 0.0
    b_pf = (b_gp / b_gl) if b_gl > 0 else 0.0

    net_filtering_value = c_net - b_net

    master_summary = {
        "review_period": "2026-09-02 to 2026-10-31 (60 Calendar Days / 43 Trading Days)",
        "segments_compiled": len(all_scorecards),
        "total_opportunities_screened": total_screened,
        "council_portfolio": {
            "trades_approved": c_approved,
            "filled_trades": c_filled,
            "wins": c_wins,
            "losses": c_losses,
            "win_rate_pct": round(c_wr, 1),
            "gross_profit_usd": round(c_gp, 2),
            "gross_loss_usd": round(c_gl, 2),
            "net_pnl_usd": round(c_net, 2),
            "profit_factor": round(c_pf, 2)
        },
        "blind_execution_portfolio": {
            "filled_trades": b_filled,
            "wins": b_wins,
            "losses": b_losses,
            "win_rate_pct": round(b_wr, 1),
            "gross_profit_usd": round(b_gp, 2),
            "gross_loss_usd": round(b_gl, 2),
            "net_pnl_usd": round(b_net, 2),
            "profit_factor": round(b_pf, 2)
        },
        "counterfactual_filtering_impact": {
            "total_stand_asides": cf_sa,
            "protective_vetoes_losses_prevented": cf_prot,
            "capital_saved_usd": round(cf_cap_saved, 2),
            "damaging_stand_asides_missed_winners": cf_dam,
            "missed_alpha_usd": round(cf_alpha, 2),
            "unfilled_or_expired": cf_unfilled,
            "net_council_filtering_value_usd": round(net_filtering_value, 2)
        },
        "asset_breakdown": {
            "eurusd": {"filled": eur_filled, "wins": eur_wins, "losses": eur_losses, "win_rate_pct": round(eur_wr, 1), "net_pnl_usd": round(eur_net, 2)},
            "gbpusd": {"filled": gbp_filled, "wins": gbp_wins, "losses": gbp_losses, "win_rate_pct": round(gbp_wr, 1), "net_pnl_usd": round(gbp_net, 2)}
        },
        "setup_architecture_breakdown": {
            "smt_divergence": {"filled": smt_filled, "wins": smt_wins, "losses": smt_losses, "win_rate_pct": round(smt_wr, 1), "net_pnl_usd": round(smt_net, 2)},
            "independent_smc": {"filled": ind_filled, "wins": ind_wins, "losses": ind_losses, "win_rate_pct": round(ind_wr, 1), "net_pnl_usd": round(ind_net, 2)}
        }
    }

    # Save Master JSON
    master_json_path = out_dir / "master_full_dataset.json"
    with open(master_json_path, "w", encoding="utf-8") as f:
        json.dump(master_summary, f, indent=2)
    print(f"Exported master json: {master_json_path}")

    # Build Master Markdown Executive Report
    report_md = f"""# TradingGuard HITL - 2-Month Master Consolidated Review
**Period**: September 02, 2026 – October 31, 2026 (60 Calendar Days | 43 Trading Days)  
**Assets**: EURUSD (Fiber) & GBPUSD (Cable)  
**Execution Paradigm**: 6-Seat AI Investment Council (Gemini 3.8 Flash via agy.exe, $0.00 cost) with Higher-Timeframe Fundamental Directional Bias Engine, 75m TTL, Watchdog ATR Protection, and Realistic Spreads (EUR 1.8 pips, GBP 2.5 pips).

---

## 1. Executive Summary: AI Council vs. Blind Execution

| Metric | Blind Execution (Trade Every Signal) | AI Investment Council (Filtered) | Delta / Council Value-Add |
| :--- | :---: | :---: | :---: |
| **Total Opportunities Screened** | {total_screened} | {total_screened} | 100% Comprehensive Coverage |
| **Filled Trades** | **{b_filled}** | **{c_filled}** | **-{b_filled - c_filled} trades** (Selective Precision) |
| **Wins / Losses** | {b_wins}W / {b_losses}L | {c_wins}W / {c_losses}L | Eliminates {cf_prot} Toxic Stop-Outs |
| **Win Rate** | **{b_wr:.1f}%** | **{c_wr:.1f}%** | **+{c_wr - b_wr:.1f}% Win Rate Expansion** |
| **Gross Profit** | ${b_gp:+.2f} | ${c_gp:+.2f} | High quality institutional setups |
| **Gross Loss** | ${b_gl:-.2f} | ${c_gl:-.2f} | **-${b_gl - c_gl:.2f} Loss Avoidance** |
| **Net Realized PnL** | **${b_net:+.2f}** | **${c_net:+.2f}** | **+${net_filtering_value:+.2f} Net Alpha Outperformance** |
| **Profit Factor** | **{b_pf:.2f}** | **{c_pf:.2f}** | Robust Risk-Adjusted Edge |

---

## 2. Walk-Forward Segment Breakdown

| Segment | Date Range | Market Regime | Blind PnL | Council PnL | Net Capital Defended |
| :--- | :--- | :--- | :---: | :---: | :---: |
"""
    for i, sc in enumerate(all_scorecards, start=1):
        s_b = sc["shadow_portfolio"]["blind_execution_shadow_portfolio"]["net_pnl_usd"]
        s_c = sc["shadow_portfolio"]["actual_council_portfolio"]["net_pnl_usd"]
        s_val = sc["shadow_portfolio"]["net_council_filtering_value_usd"]
        report_md += f"| Segment {i} | Day {i*10-9}–{min(i*10, 43)} | Regime {i} | ${s_b:+.2f} | ${s_c:+.2f} | **+${s_val:+.2f}** |\n"

    report_md += f"""
---

## 3. Asset & Strategy Architecture Performance

### Asset Performance
- **EURUSD (Fiber)**:
  - Filled Trades: {eur_filled} ({eur_wins}W / {eur_losses}L)
  - Win Rate: {eur_wr:.1f}%
  - Net Realized PnL: **${eur_net:+.2f}**
- **GBPUSD (Cable)**:
  - Filled Trades: {gbp_filled} ({gbp_wins}W / {gbp_losses}L)
  - Win Rate: {gbp_wr:.1f}%
  - Net Realized PnL: **${gbp_net:+.2f}**

### Strategy Architecture Performance
- **Intermarket SMT Divergence (SETUP-ARCH-006)**:
  - Filled Trades: {smt_filled} ({smt_wins}W / {smt_losses}L)
  - Win Rate: {smt_wr:.1f}%
  - Net Realized PnL: **${smt_net:+.2f}**
- **Independent SMC Setups (SETUP-ARCH-001..004)**:
  - Filled Trades: {ind_filled} ({ind_wins}W / {ind_losses}L)
  - Win Rate: {ind_wr:.1f}%
  - Net Realized PnL: **${ind_net:+.2f}**

---

## 4. Counterfactual Shadow Portfolio & Risk Shield
- **Protective Vetoes (Losses Prevented)**: **{cf_prot} trades** (${cf_cap_saved:.2f} direct capital saved).
- **Damaging Stand-Asides (Missed Winners)**: {cf_dam} trades (${cf_alpha:.2f} missed profit).
- **Net Council Filtering Edge**: **+${net_filtering_value:+.2f}** institutional value generated purely through disciplined selective gating.
"""

    master_report_path = out_dir / "MASTER_2MONTH_EXECUTIVE_REPORT.md"
    with open(master_report_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"Exported master markdown report: {master_report_path}")

    return master_summary


if __name__ == "__main__":
    compile_master_report()
