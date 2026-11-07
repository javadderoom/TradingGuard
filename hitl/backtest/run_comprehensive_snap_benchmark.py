"""
TradingGuard HITL - Comprehensive SubQ Snap Multi-Month Benchmark Harness
Compares the Quantitative Screener baseline against the SubQ Snap Decision Engine
across hundreds of historical session milestones using the canonical execution simulator.
"""

import sys
import csv
import json
import time
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.config import BASE_DIR, MAX_RISK_USD
from hitl.backtest.data_feed import _convert_records
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.mtf_structure import analyze_mtf_state
from hitl.setup_registry import setup_registry
from hitl.snap_decision_engine import snap_engine
from hitl.tools.smc_tools import build_validated_order_plan
from hitl.backtest.evaluator import evaluate_council_decision, summarize_pnl

OUTPUT_DIR = BASE_DIR / "backtest_results" / "snap_evaluations"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_business_days(start_date: datetime.date, end_date: datetime.date) -> List[datetime.date]:
    """Generates all Monday-Friday dates in the range."""
    days = []
    curr = start_date
    while curr <= end_date:
        if curr.weekday() < 5:  # 0=Mon, 4=Fri
            days.append(curr)
        curr += datetime.timedelta(days=1)
    return days


def run_comprehensive_benchmark(
    start_date: datetime.date,
    end_date: datetime.date,
    symbols: List[str] = ["XAUUSD_o", "GBPUSD_o"],
    max_snap_evals: int = 50,
    suffix: str = ""
):
    terminal_path = r"C:\Program Files\LiteFinance MT5 Terminal\terminal64.exe"
    if not mt5.initialize(path=terminal_path):
        print("[Error] Failed to initialize MT5")
        return None

    print("==========================================================================================")
    print("🚀 TRADINGGUARD — SUBQ SNAP COMPREHENSIVE MULTI-MONTH BENCHMARK")
    print(f"Period: {start_date} to {end_date} | Symbols: {symbols}")
    print(f"Engine: SubQ Snap (subq-snap-1.1) vs Baseline Closed-Bar Screener")
    print("==========================================================================================")

    trading_days = generate_business_days(start_date, end_date)
    print(f"Total Trading Days in Evaluation Window: {len(trading_days)}")

    # Milestones (Broker Server Time: 10:00, 10:30, 11:00 London; 15:00, 15:30, 16:00 NY; 17:30, 18:00 SB)
    milestone_hours = [
        (10, 0), (10, 30), (11, 0),
        (15, 0), (15, 30), (16, 0),
        (17, 30), (18, 0)
    ]

    all_candidate_records = []
    snap_calls_count = 0
    total_checkpoints = 0

    t_start_total = time.perf_counter()

    for day in trading_days:
        for sym in symbols:
            clean_sym = "XAUUSD" if "XAU" in sym else "GBPUSD"
            is_fx = "GBP" in sym

            for hour, minute in milestone_hours:
                total_checkpoints += 1
                checkpoint_dt = datetime.datetime(day.year, day.month, day.day, hour, minute)

                # Fetch 120 bars ending strictly at checkpoint_dt (no lookahead)
                bars_5m = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M5, checkpoint_dt, 120))
                bars_1h = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_H1, checkpoint_dt, 120))
                bars_1d = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_D1, checkpoint_dt, 60))

                if not bars_5m or len(bars_5m) < 40 or not bars_1h or len(bars_1h) < 10:
                    continue

                # Run screener in closed_bars_only mode
                try:
                    screen_res = screen_ict_session(
                        bars_5m=bars_5m,
                        bars_1h=bars_1h,
                        symbol=clean_sym,
                        session_hour=hour,
                        bars_1d=bars_1d,
                        closed_bars_only=True
                    )
                except TypeError:
                    # Fallback if closed_bars_only is handled internally
                    screen_res = screen_ict_session(
                        bars_5m=bars_5m,
                        bars_1h=bars_1h,
                        symbol=clean_sym,
                        session_hour=hour,
                        bars_1d=bars_1d
                    )

                if not screen_res.get("has_setup", False):
                    continue

                arch_id = screen_res.get("archetype_id", "NONE")
                setup_type = screen_res.get("setup_type", "NONE")
                is_ratified = setup_registry.is_archetype_ratified(arch_id)

                if not is_ratified:
                    continue

                # Valid setup candidate detected!
                curr_b = bars_5m[-1]
                quote = {
                    "bid": curr_b['close'],
                    "ask": curr_b['close'] + (0.00015 if is_fx else 0.20),
                    "spread": 0.00015 if is_fx else 0.20
                }
                mtf_state = analyze_mtf_state(bars_1d, bars_1h, bars_5m, symbol=clean_sym)

                setup_type = screen_res.get("setup_type", "")
                proposed_dir = "LONG" if "BULLISH" in setup_type else ("SHORT" if "BEARISH" in setup_type else screen_res.get("direction", "NONE"))
                entry_p = screen_res.get("entry_ref", screen_res.get("entry_price", curr_b['close']))
                sl_p = screen_res.get("sl_ref", screen_res.get("sl_price", curr_b['close']))
                risk_pts = abs(entry_p - sl_p)
                if risk_pts <= 0:
                    continue

                target_rr = screen_res.get("recommended_target_rr", 2.5)
                tp_p = (entry_p + target_rr * risk_pts) if proposed_dir == "LONG" else (entry_p - target_rr * risk_pts)

                # Build Blind Order Plan
                blind_decision = "BUY_LIMIT" if proposed_dir == "LONG" else ("SELL_LIMIT" if proposed_dir == "SHORT" else "STAND_ASIDE")
                if blind_decision == "STAND_ASIDE":
                    continue

                # Forward M1 bars for 240 minutes
                fwd_rates = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, checkpoint_dt + datetime.timedelta(minutes=240), 240)
                fwd_m1 = _convert_records(fwd_rates)
                fwd_m1_valid = [b for b in fwd_m1 if b['time'] >= int(checkpoint_dt.timestamp())]

                if not fwd_m1_valid:
                    continue

                # 1. Simulate Blind Screener Execution
                blind_plan = {
                    "decision": blind_decision,
                    "entry": entry_p,
                    "sl": sl_p,
                    "tp": tp_p,
                    "lot": 0.01,
                    "risk_usd": risk_pts * (1000.0 if is_fx else 1.0),
                    "rr": target_rr
                }

                blind_sim = evaluate_council_decision(
                    decision_dict=blind_plan,
                    forward_m1_bars=fwd_m1_valid,
                    symbol=clean_sym
                )
                blind_status = blind_sim.get("status", "UNKNOWN")
                blind_pnl = blind_sim.get("realized_pnl_usd", 0.0)
                blind_rr = blind_sim.get("rr_realized", 0.0)

                # 2. Invoke SubQ Snap Decision Engine (Cap total calls if specified)
                snap_calls_count += 1
                if snap_calls_count > max_snap_evals:
                    print(f"\n[Limit] Reached maximum SubQ Snap evaluation cap ({max_snap_evals}). Ending scan.")
                    break

                session_lbl = f"{clean_sym}_{checkpoint_dt.strftime('%Y-%m-%d_%H:%M')}"
                print(f"[{snap_calls_count:02d}] {checkpoint_dt} | {clean_sym} | {arch_id} ({proposed_dir}) ➔ Querying SubQ Snap...", end="", flush=True)

                snap_setup_payload = {
                    "archetype_id": arch_id,
                    "setup_type": setup_type,
                    "direction": proposed_dir,
                    "entry_price": entry_p,
                    "sl_price": sl_p,
                    "target_price": tp_p
                }

                t0_snap = time.perf_counter()
                snap_res = snap_engine.evaluate_candidate(
                    symbol=clean_sym,
                    session_label=session_lbl,
                    screener_setup=snap_setup_payload,
                    mtf_state=mtf_state,
                    current_quote=quote
                )
                lat_ms = (time.perf_counter() - t0_snap) * 1000.0

                snap_dec = snap_res.get("decision", "STAND_ASIDE")
                snap_conf = snap_res.get("confidence", 0.0)
                snap_probs = snap_res.get("probabilities", {})
                snap_driver = snap_res.get("primary_driver", "NONE")
                snap_tier = snap_res.get("conviction_tier", "NONE")

                # 3. Simulate SubQ Snap Gated Outcome
                if snap_dec in ("BUY_LIMIT", "SELL_LIMIT"):
                    snap_plan = {
                        "decision": snap_dec,
                        "entry": entry_p,
                        "sl": sl_p,
                        "tp": tp_p,
                        "lot": 0.01,
                        "risk_usd": risk_pts * (1000.0 if is_fx else 1.0),
                        "rr": target_rr
                    }
                    snap_sim = evaluate_council_decision(
                        decision_dict=snap_plan,
                        forward_m1_bars=fwd_m1_valid,
                        symbol=clean_sym
                    )
                    snap_status = snap_sim.get("status", "UNKNOWN")
                    snap_pnl = snap_sim.get("realized_pnl_usd", 0.0)
                    snap_rr = snap_sim.get("rr_realized", 0.0)
                else:
                    snap_status = "STAND_ASIDE"
                    snap_pnl = 0.0
                    snap_rr = 0.0

                # 4. Classify Counterfactual Veto Value
                counterfactual_role = "N/A"
                if snap_dec == "STAND_ASIDE":
                    if blind_status == "LOSS":
                        counterfactual_role = "PROTECTIVE_VETO"
                    elif blind_status == "WIN":
                        counterfactual_role = "DAMAGING_STAND_ASIDE"
                    elif blind_status == "BREAKEVEN":
                        counterfactual_role = "NEUTRAL_SCRATCH_VETO"
                    elif blind_status in ("EXPIRED", "UNFILLED"):
                        counterfactual_role = "AVOIDED_EXPIRED"
                else:
                    counterfactual_role = "APPROVED_TRADE"

                print(f" {snap_dec} ({lat_ms:.0f}ms) | Blind: {blind_status} (${blind_pnl:+.2f}) ➔ Snap: {snap_status} (${snap_pnl:+.2f}) [{counterfactual_role}]")

                record = {
                    "timestamp": checkpoint_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "symbol": clean_sym,
                    "archetype_id": arch_id,
                    "setup_type": setup_type,
                    "screener_dir": proposed_dir,
                    "entry_price": entry_p,
                    "sl_price": sl_p,
                    "tp_price": tp_p,
                    "blind_status": blind_status,
                    "blind_pnl_usd": blind_pnl,
                    "blind_rr": blind_rr,
                    "snap_decision": snap_dec,
                    "snap_confidence": snap_conf,
                    "snap_prob_buy": snap_probs.get("BUY_LIMIT", 0.0),
                    "snap_prob_sell": snap_probs.get("SELL_LIMIT", 0.0),
                    "snap_prob_stand": snap_probs.get("STAND_ASIDE", 0.0),
                    "snap_driver": snap_driver,
                    "snap_tier": snap_tier,
                    "snap_latency_ms": lat_ms,
                    "snap_status": snap_status,
                    "snap_pnl_usd": snap_pnl,
                    "snap_rr": snap_rr,
                    "counterfactual_role": counterfactual_role
                }
                all_candidate_records.append(record)

            if snap_calls_count >= max_snap_evals:
                break
        if snap_calls_count >= max_snap_evals:
            break

    total_time = time.perf_counter() - t_start_total

    print("\n==========================================================================================")
    print("📊 BENCHMARK EXECUTION COMPLETE — GENERATING PERFORMANCE SCORECARD")
    print("==========================================================================================")
    print(f"Checkpoints Scanned: {total_checkpoints} | Candidate Setups Evaluated: {len(all_candidate_records)}")
    print(f"Total Execution Time: {total_time:.1f} seconds")

    if not all_candidate_records:
        print("[Notice] No candidates detected in the specified period.")
        return None

    # Write CSV Ledger
    file_tag = f"_{suffix}" if suffix else ""
    csv_path = OUTPUT_DIR / f"subq_snap_ledger{file_tag}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_candidate_records[0].keys()))
        writer.writeheader()
        writer.writerows(all_candidate_records)
    print(f"📁 Full CSV Ledger Saved: {csv_path}")

    # Compute Comparative Metrics
    # Portfolio A: Blind Screener
    blind_filled = [r for r in all_candidate_records if r["blind_status"] in ("WIN", "LOSS", "BREAKEVEN")]
    blind_wins = [r for r in blind_filled if r["blind_status"] == "WIN"]
    blind_losses = [r for r in blind_filled if r["blind_status"] == "LOSS"]
    blind_bes = [r for r in blind_filled if r["blind_status"] == "BREAKEVEN"]
    blind_net_pnl = sum(r["blind_pnl_usd"] for r in blind_filled)
    blind_gross_profit = sum(r["blind_pnl_usd"] for r in blind_wins)
    blind_gross_loss = abs(sum(r["blind_pnl_usd"] for r in blind_losses))
    blind_pf = (blind_gross_profit / blind_gross_loss) if blind_gross_loss > 0 else 0.0
    blind_wr = (len(blind_wins) / len(blind_filled) * 100.0) if blind_filled else 0.0

    # Portfolio B: SubQ Snap Gated
    snap_approvals = [r for r in all_candidate_records if r["snap_decision"] in ("BUY_LIMIT", "SELL_LIMIT")]
    snap_filled = [r for r in snap_approvals if r["snap_status"] in ("WIN", "LOSS", "BREAKEVEN")]
    snap_wins = [r for r in snap_filled if r["snap_status"] == "WIN"]
    snap_losses = [r for r in snap_filled if r["snap_status"] == "LOSS"]
    snap_bes = [r for r in snap_filled if r["snap_status"] == "BREAKEVEN"]
    snap_net_pnl = sum(r["snap_pnl_usd"] for r in snap_filled)
    snap_gross_profit = sum(r["snap_pnl_usd"] for r in snap_wins)
    snap_gross_loss = abs(sum(r["snap_pnl_usd"] for r in snap_losses))
    snap_pf = (snap_gross_profit / snap_gross_loss) if snap_gross_loss > 0 else 0.0
    snap_wr = (len(snap_wins) / len(snap_filled) * 100.0) if snap_filled else 0.0

    # Counterfactual Metrics
    prot_vetoes = [r for r in all_candidate_records if r["counterfactual_role"] == "PROTECTIVE_VETO"]
    dam_vetoes = [r for r in all_candidate_records if r["counterfactual_role"] == "DAMAGING_STAND_ASIDE"]
    avoided_exp = [r for r in all_candidate_records if r["counterfactual_role"] == "AVOIDED_EXPIRED"]

    capital_saved_usd = abs(sum(r["blind_pnl_usd"] for r in prot_vetoes))
    missed_alpha_usd = sum(r["blind_pnl_usd"] for r in dam_vetoes)
    net_snap_alpha_usd = capital_saved_usd - missed_alpha_usd

    # Latencies
    latencies = [r["snap_latency_ms"] for r in all_candidate_records]
    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
    min_lat = min(latencies) if latencies else 0.0
    max_lat = max(latencies) if latencies else 0.0

    summary = {
        "period": f"{start_date} to {end_date}",
        "total_checkpoints_scanned": total_checkpoints,
        "candidate_setups_evaluated": len(all_candidate_records),
        "subq_snap_calls": snap_calls_count,
        "blind_screener_portfolio": {
            "filled_trades": len(blind_filled),
            "wins": len(blind_wins),
            "losses": len(blind_losses),
            "breakevens": len(blind_bes),
            "win_rate_pct": round(blind_wr, 2),
            "net_pnl_usd": round(blind_net_pnl, 2),
            "profit_factor": round(blind_pf, 2)
        },
        "subq_snap_gated_portfolio": {
            "approved_orders": len(snap_approvals),
            "stand_asides": len(all_candidate_records) - len(snap_approvals),
            "stand_aside_rate_pct": round((len(all_candidate_records) - len(snap_approvals)) / len(all_candidate_records) * 100.0, 1),
            "filled_trades": len(snap_filled),
            "wins": len(snap_wins),
            "losses": len(snap_losses),
            "breakevens": len(snap_bes),
            "win_rate_pct": round(snap_wr, 2),
            "net_pnl_usd": round(snap_net_pnl, 2),
            "profit_factor": round(snap_pf, 2)
        },
        "counterfactual_analysis": {
            "protective_vetoes": len(prot_vetoes),
            "damaging_stand_asides": len(dam_vetoes),
            "avoided_expired": len(avoided_exp),
            "capital_saved_usd": round(capital_saved_usd, 2),
            "missed_alpha_usd": round(missed_alpha_usd, 2),
            "net_snap_value_usd": round(net_snap_alpha_usd, 2)
        },
        "latency_stats": {
            "avg_ms": round(avg_lat, 1),
            "min_ms": round(min_lat, 1),
            "max_ms": round(max_lat, 1)
        }
    }

    summary_path = OUTPUT_DIR / f"subq_snap_summary{file_tag}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"📁 JSON Summary Saved: {summary_path}")

    # Print Report
    print("\n" + "="*90)
    print("🏆 FINAL COMPARATIVE SCORECARD: BLIND SCREENER vs. SUBQ SNAP GATED")
    print("="*90)
    print(f"  • Total Candidates Detected:  {len(all_candidate_records)}")
    print(f"  • SubQ Snap Decision Speed:   avg {avg_lat:.0f}ms (min: {min_lat:.0f}ms, max: {max_lat:.0f}ms)")
    print(f"  • SubQ Stand-Aside Filtering: {summary['subq_snap_gated_portfolio']['stand_aside_rate_pct']}% of setups vetoed")
    print("-"*90)
    print(f"  BLIND SCREENER:  {len(blind_filled)} filled | {len(blind_wins)}W / {len(blind_losses)}L / {len(blind_bes)}BE | WR: {blind_wr:.1f}% | Net PnL: ${blind_net_pnl:+.2f} | PF: {blind_pf:.2f}")
    print(f"  SUBQ SNAP GATED: {len(snap_filled)} filled | {len(snap_wins)}W / {len(snap_losses)}L / {len(snap_bes)}BE | WR: {snap_wr:.1f}% | Net PnL: ${snap_net_pnl:+.2f} | PF: {snap_pf:.2f}")
    print("-"*90)
    print(f"  COUNTERFACTUAL VETO VALUE:")
    print(f"  • Protective Vetoes (Losses Saved):   {len(prot_vetoes)} trades (+${capital_saved_usd:.2f})")
    print(f"  • Damaging Vetoes (Missed Winners):   {len(dam_vetoes)} trades (-${missed_alpha_usd:.2f})")
    print(f"  • Avoided Expired / Dead Orders:      {len(avoided_exp)} trades")
    print(f"  • NET VALUE OF SUBQ SNAP FILTER:      ${net_snap_alpha_usd:+.2f}")
    print("="*90)

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SubQ Snap Comprehensive Benchmark Runner")
    parser.add_argument("--start", type=str, default="2026-08-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, default="2026-11-06", help="End date YYYY-MM-DD")
    parser.add_argument("--max-evals", type=int, default=50, help="Max SubQ Snap calls")
    parser.add_argument("--suffix", type=str, default="", help="File suffix tag")
    args = parser.parse_args()

    s_date = datetime.datetime.strptime(args.start, "%Y-%m-%d").date()
    e_date = datetime.datetime.strptime(args.end, "%Y-%m-%d").date()
    run_comprehensive_benchmark(s_date, e_date, symbols=["XAUUSD_o", "GBPUSD_o"], max_snap_evals=args.max_evals, suffix=args.suffix)
