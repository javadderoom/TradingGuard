"""
TradingGuard HITL - Trade Management & Excursion Optimizer
Analyzes historical approved setups across Gold and Forex baskets to find the
mathematically optimal Take-Profit (Target R:R) and Breakeven triggers segmented
strictly by Symbol (Asset) and Session (London, NY Open, NY Silver Bullet).
"""

import sys
import glob
import json
import time
import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.data_feed import HistoricalDataFeed, _convert_records
from hitl.backtest.evaluator import evaluate_council_decision, get_default_broker_spread


OUTPUT_DIR = BASE_DIR / "backtest_results" / "trade_management_optimization"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
POLICY_PATH = BASE_DIR / "hitl" / "memory" / "optimal_trade_management_policy.json"


def normalize_session_name(raw_session: str) -> str:
    """Consolidates granular session tags into primary trading killzones."""
    s = (raw_session or "").lower()
    if "london" in s:
        if "post" in s:
            return "London_Post_Open"
        elif "pre" in s:
            return "London_Pre_Open"
        return "London_Open"
    elif "silver bullet" in s:
        return "NY_Silver_Bullet"
    elif "ny" in s or "new york" in s:
        if "post" in s:
            return "NY_Post_Open"
        elif "pre" in s:
            return "NY_Pre_Open"
        return "NY_Open"
    return "Other"


def harvest_historical_approved_trades() -> List[Dict[str, Any]]:
    """Scans all backtest result directories and collects unique approved limit orders."""
    all_trades = {}
    json_files = glob.glob(str(BASE_DIR / "backtest_results" / "*" / "full_dataset.json"))

    for p in sorted(json_files):
        # Skip prior optimizer runs
        if "trade_management_optimization" in p:
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
                for s in d.get("sessions", []):
                    dec = s.get("decision", "")
                    if dec in ("BUY_LIMIT", "SELL_LIMIT"):
                        sym = s.get("symbol", "XAUUSD")
                        ts = s.get("timestamp", "")
                        entry = s.get("entry")
                        sl = s.get("sl")
                        tp = s.get("tp")
                        if not (entry and sl and tp and ts):
                            continue
                        
                        # Deduplicate by (symbol, timestamp, decision)
                        key = (sym, ts, dec)
                        if key not in all_trades:
                            all_trades[key] = {
                                "symbol": sym,
                                "timestamp": ts,
                                "session_raw": s.get("session", ""),
                                "session_norm": normalize_session_name(s.get("session", "")),
                                "decision": dec,
                                "entry": float(entry),
                                "sl": float(sl),
                                "tp": float(tp),
                                "original_status": s.get("status", "")
                            }
        except Exception as exc:
            print(f"[Optimizer] Failed to parse {p}: {exc}")

    trades_list = list(all_trades.values())
    trades_list.sort(key=lambda x: (x["symbol"], x["timestamp"]))
    return trades_list


def run_trade_management_optimization(
    target_rr_grid: Optional[List[float]] = None,
    be_rr_grid: Optional[List[Optional[float]]] = None,
    min_trades_threshold: int = 2
) -> Dict[str, Any]:
    """
    Simulates matrix of (Target R:R, Breakeven R:R) across all historical trades.
    Identifies the highest-performing configuration for each (Symbol, Session) pair.
    """
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    feed = HistoricalDataFeed()
    if not feed.engine.ensure_connected():
        print("❌ Error: MT5 connection failed.")
        return {}

    target_rr_grid = target_rr_grid or [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    be_rr_grid = be_rr_grid or [None, 1.5, 1.8, 2.0, 2.5]

    print("=" * 85)
    print("🔬 TRADINGGUARD INSTITUTIONAL TRADE MANAGEMENT & EXCURSION OPTIMIZER")
    print(f"Target R:R Grid:     {target_rr_grid}")
    print(f"Breakeven R:R Grid:  {[b if b is not None else 'None' for b in be_rr_grid]}")
    print("Optimization Objective: Maximize Risk-Adjusted Net PnL & Profit Factor")
    print("=" * 85)

    raw_trades = harvest_historical_approved_trades()
    print(f"Total Unique Historical Approved Trades Harvested: {len(raw_trades)}")

    # 1. Fetch forward M1 bars for each trade from MT5
    resolved_symbols = {}
    valid_trades = []
    print("\n⏳ Fetching 12-hour forward M1 microstructure from broker...")

    for t in raw_trades:
        sym = t["symbol"]
        if sym not in resolved_symbols:
            resolved_symbols[sym] = feed.engine.resolve_symbol(sym)
        res_sym = resolved_symbols[sym]
        if not res_sym:
            continue

        try:
            # Parse timestamp
            ts_str = t["timestamp"]
            # Clean possible trailing annotations
            ts_clean = ts_str.split()[0] + " " + ts_str.split()[1] if len(ts_str.split()) >= 2 else ts_str
            t_dt = datetime.datetime.fromisoformat(ts_clean)
        except Exception:
            continue

        bars_raw = mt5.copy_rates_range(
            res_sym,
            mt5.TIMEFRAME_M1,
            t_dt,
            t_dt + datetime.timedelta(hours=12)
        )
        bars = _convert_records(bars_raw)
        if not bars:
            continue

        t["forward_m1"] = bars
        t["resolved_symbol"] = res_sym
        valid_trades.append(t)

    print(f"✅ Successfully hydrated {len(valid_trades)} trades with high-density M1 forward feeds.")

    # 2. Partition trades by (Symbol, Normalized Session)
    segmented_buckets: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for t in valid_trades:
        key = (t["symbol"], t["session_norm"])
        segmented_buckets.setdefault(key, []).append(t)

    # 3. Matrix Simulation
    optimization_results = {}
    optimal_policy = {}

    for (sym, sess), trade_group in sorted(segmented_buckets.items()):
        total_in_bucket = len(trade_group)
        print(f"\n⚡ Optimizing Segment: {sym} | {sess} ({total_in_bucket} trades)...")

        bucket_matrix = []

        for tgt_rr in target_rr_grid:
            for be_rr in be_rr_grid:
                be_label = f"{be_rr:.1f}R" if be_rr is not None else "None"
                total_pnl = 0.0
                wins = 0
                losses = 0
                breakevens = 0
                expired = 0
                saved_losses = 0
                choked_winners = 0

                for t in trade_group:
                    payload = {
                        "decision": t["decision"],
                        "entry": t["entry"],
                        "sl": t["sl"],
                        "tp": t["tp"],
                        "lot": 0.01
                    }
                    # Run with test parameters
                    res = evaluate_council_decision(
                        decision_dict=payload,
                        forward_m1_bars=t["forward_m1"],
                        symbol=sym,
                        breakeven_rr=be_rr if be_rr is not None else 999.0,
                        target_rr_cap=tgt_rr
                    )
                    status = res["status"]
                    pnl = res.get("realized_pnl_usd", 0.0)
                    total_pnl += pnl

                    if status == "WIN":
                        wins += 1
                    elif status == "LOSS":
                        losses += 1
                    elif status == "BREAKEVEN":
                        breakevens += 1
                    elif status == "EXPIRED":
                        expired += 1

                    # Diagnostic: Compare against counterfactual baseline (No BE)
                    if be_rr is not None:
                        res_nobe = evaluate_council_decision(
                            decision_dict=payload,
                            forward_m1_bars=t["forward_m1"],
                            symbol=sym,
                            breakeven_rr=999.0, # disabled BE
                            target_rr_cap=tgt_rr
                        )
                        if status == "BREAKEVEN" and res_nobe["status"] == "LOSS":
                            saved_losses += 1
                        elif status == "BREAKEVEN" and res_nobe["status"] == "WIN":
                            choked_winners += 1

                filled = wins + losses + breakevens
                g_profit = round(sum(tgt_rr * (abs(t["entry"] - t["sl"]) * (1.0 if "XAU" in sym else (50.0 if "XAG" in sym else 1000.0))) for _ in range(wins)), 2)
                # Compute authentic metrics
                win_rate = round((wins / filled * 100), 1) if filled > 0 else 0.0
                g_loss = abs(sum(-min(17.0, abs(t["entry"] - t["sl"]) * (1.0 if "XAU" in sym else (50.0 if "XAG" in sym else 1000.0))) for _ in range(losses)))
                profit_factor = round(g_profit / g_loss, 2) if g_loss > 0 else (99.0 if g_profit > 0 else 0.0)

                bucket_matrix.append({
                    "target_rr": tgt_rr,
                    "breakeven_rr": be_rr,
                    "breakeven_label": be_label,
                    "filled_trades": filled,
                    "wins": wins,
                    "losses": losses,
                    "breakevens": breakevens,
                    "expired": expired,
                    "win_rate_pct": win_rate,
                    "net_pnl_usd": round(total_pnl, 2),
                    "profit_factor": profit_factor,
                    "saved_losses": saved_losses,
                    "choked_winners": choked_winners
                })

        # Rank combinations by net PnL then Profit Factor
        bucket_matrix.sort(key=lambda x: (x["net_pnl_usd"], x["profit_factor"]), reverse=True)
        best = bucket_matrix[0]

        optimization_results[f"{sym}__{sess}"] = {
            "symbol": sym,
            "session": sess,
            "sample_size": total_in_bucket,
            "best_configuration": best,
            "full_grid": bucket_matrix
        }

        # Build policy
        optimal_policy.setdefault(sym, {})[sess] = {
            "target_rr": best["target_rr"],
            "breakeven_rr": best["breakeven_rr"],
            "win_rate_pct": best["win_rate_pct"],
            "expected_pf": best["profit_factor"],
            "sample_size": total_in_bucket
        }

        print(f"   🏆 Optimal Config: Target {best['target_rr']:.1f}R | BE {best['breakeven_label']} -> Net PnL: ${best['net_pnl_usd']:+.2f} | PF: {best['profit_factor']} (WR: {best['win_rate_pct']}%)")
        if best["saved_losses"] > 0:
            print(f"      🛡️ Saved {best['saved_losses']} stop-outs via BE (Choked: {best['choked_winners']} winners)")

    # 4. Export Structured JSON Policy
    with open(POLICY_PATH, "w", encoding="utf-8") as f:
        json.dump(optimal_policy, f, indent=2)

    # 5. Export Comprehensive Markdown Report
    report_md = _generate_optimizer_markdown(optimization_results, valid_trades)
    rep_path = OUTPUT_DIR / "OPTIMIZATION_REPORT.md"
    with open(rep_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print("\n" + "=" * 85)
    print("💾 OPTIMIZATION COMPLETED SUCCESSFULLY!")
    print(f"• Dynamic Policy Persisted to: {POLICY_PATH}")
    print(f"• Comprehensive Report at:     {rep_path}")
    print("=" * 85)

    return {
        "policy": optimal_policy,
        "results": optimization_results,
        "report_file": str(rep_path)
    }


def _generate_optimizer_markdown(results: Dict[str, Any], valid_trades: List[Dict[str, Any]]) -> str:
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S Tehran Time")
    lines = [
        "# 🔬 Institutional Trade Management & Excursion Optimization Report",
        f"> **Generated**: {now_str} | **Total Trades Replayed**: {len(valid_trades)}",
        "",
        "## Executive Overview",
        "This optimization engine evaluates forward M1 price paths across historical approved trades to resolve",
        "the optimal Target R:R cap and Breakeven ratchet for each specific asset and trading session.",
        "",
        "---",
        ""
    ]

    for key, data in results.items():
        sym = data["symbol"]
        sess = data["session"].replace("_", " ")
        sample = data["sample_size"]
        best = data["best_configuration"]

        lines.extend([
            f"### 📍 Asset Segment: **{sym}** · Session: **{sess}** ({sample} Trades)",
            f"- **Optimal Target**: `1:{best['target_rr']:.1f} R:R`",
            f"- **Optimal Breakeven Trigger**: `{best['breakeven_label']}`",
            f"- **Optimal Net Realized PnL**: `+${best['net_pnl_usd']:.2f}` (PF: `{best['profit_factor']}` · Win Rate: `{best['win_rate_pct']}%`)",
            f"- **Breakeven Defense Impact**: Defended **{best['saved_losses']}** stop-outs (Choked: {best['choked_winners']})",
            "",
            "| Target R:R | Breakeven Trigger | Fills | Win / Loss / BE | Win Rate | Net PnL ($) | Profit Factor | Saved Losses | Choked Winners |",
            "| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
        ])

        # Top 10 combinations
        for row in data["full_grid"][:10]:
            be_str = row["breakeven_label"]
            record_str = f"{row['wins']}W / {row['losses']}L / {row['breakevens']}BE"
            highlight = "**" if (row["target_rr"] == best["target_rr"] and row["breakeven_rr"] == best["breakeven_rr"]) else ""
            lines.append(
                f"| {highlight}1:{row['target_rr']:.1f}{highlight} | "
                f"{highlight}{be_str}{highlight} | "
                f"{row['filled_trades']} | "
                f"{record_str} | "
                f"{row['win_rate_pct']:.1f}% | "
                f"{highlight}${row['net_pnl_usd']:+.2f}{highlight} | "
                f"{row['profit_factor']:.2f} | "
                f"{row['saved_losses']} | "
                f"{row['choked_winners']} |"
            )
        lines.append("\n---\n")

    return "\n".join(lines)


if __name__ == "__main__":
    run_trade_management_optimization()
