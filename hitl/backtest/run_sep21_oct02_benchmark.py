"""
TradingGuard HITL - 2-Week Out-of-Sample Benchmark (Sep 21 - Oct 02, 2026)
Automated Council Test evaluating newly ratified rules:
1. RULE-EXEC-036: POI Depth Scaling (Mean Threshold & OTE on wide zones).
2. SETUP-ARCH-007: Unmitigated ChoCh Origin & SMT Counter-Reaction.
3. Amended RULE-RISK-011: Strict 1.0 pip spread buffer for GBPUSD (no 9-pip floor).
4. Amended RULE-RISK-007: Strict 1.5-2.5 pip spread buffer for EURUSD (no 7.5-pip floor).
5. RULE-TARGET-037: Asymmetric Pro-Trend Target Anchoring to HTF Liquidity Pools.
6. Dynamic Seasonal Session Clock (session_clock.py).
"""

import sys
import time
import datetime
from pathlib import Path
from typing import Dict, List, Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.data_feed import HistoricalDataFeed, _convert_records
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.forex_cross_pair import detect_forex_smt_divergence, analyze_cross_pair_symbiosis, format_symbiotic_prompt
from hitl.backtest.council_replay import convene_council_on_historical_dossier
from hitl.backtest.evaluator import evaluate_council_decision, get_default_broker_spread
from hitl.backtest.logger import BacktestLogger
from hitl.backtest.session_clock import get_session_times_for_date
from hitl.counterfactual_auditor import CounterfactualOpportunityAuditor

SYMBOLS = ["GBPUSD", "EURUSD"]


def generate_benchmark_sessions(start_date: datetime.date, end_date: datetime.date) -> List[Dict[str, Any]]:
    """Generates all London and NY sessions for weekdays between start_date and end_date."""
    sessions = []
    cur = start_date
    while cur <= end_date:
        if cur.weekday() not in (5, 6): # Weekdays only
            s_times = get_session_times_for_date(cur)
            # London Session
            sessions.append({
                "date": cur,
                "session_name": "London Open",
                "datetime": s_times["london"]["tehran_time"].replace(tzinfo=None),
                "utc_str": s_times["london"]["utc_str"],
                "tehran_str": s_times["london"]["tehran_str"],
                "hour": s_times["london"]["hour_tehran"]
            })
            # New York Session
            sessions.append({
                "date": cur,
                "session_name": "NY Open",
                "datetime": s_times["new_york"]["tehran_time"].replace(tzinfo=None),
                "utc_str": s_times["new_york"]["utc_str"],
                "tehran_str": s_times["new_york"]["tehran_str"],
                "hour": s_times["new_york"]["hour_tehran"]
            })
        cur += datetime.timedelta(days=1)
    sessions.sort(key=lambda s: s["datetime"])
    return sessions


def run_2week_benchmark():
    sys.stdout.reconfigure(encoding='utf-8')
    feed = HistoricalDataFeed()
    logger = BacktestLogger(run_name="2week_sep21_oct02_benchmark")
    auditor = CounterfactualOpportunityAuditor()

    start_date = datetime.date(2026, 9, 21)
    end_date = datetime.date(2026, 10, 2)
    sessions = generate_benchmark_sessions(start_date, end_date)

    print("=" * 80)
    print("🏛️ TRADINGGUARD HITL - 2-WEEK OUT-OF-SAMPLE BENCHMARK (SEP 21 - OCT 02, 2026)")
    print(f"WINDOW: Monday, Sept 21 – Friday, Oct 02, 2026 (10 Trading Days)")
    print(f"ASSETS: {', '.join(SYMBOLS)} | TOTAL SESSIONS EVALUATED: {len(sessions) * len(SYMBOLS)}")
    print("ACTIVE RULES: RULE-EXEC-036 (Depth Scaling), SETUP-ARCH-007 (ChoCh Origin),")
    print("              RULE-RISK-011/007 (Precision Stops), RULE-TARGET-037 (HTF Target Run)")
    print("=" * 80)

    # Resolve symbols in MT5
    resolved_symbols = {}
    for s in SYMBOLS:
        res = feed.engine.resolve_symbol(s)
        if not res:
            print(f"❌ Error: Could not resolve {s} in MT5.")
            return
        resolved_symbols[s] = res

    results_summary = {
        "total_sessions": len(sessions) * len(SYMBOLS),
        "setups_detected": 0,
        "council_orders": 0,
        "stand_asides": 0,
        "filled_trades": 0,
        "wins": 0,
        "losses": 0,
        "expired": 0,
        "realized_pnl": 0.0,
        "blind_pnl": 0.0,
        "capital_saved": 0.0,
        "missed_alpha": 0.0,
        "trades": [],
        "audits": []
    }

    t_start = time.time()

    for s_idx, session in enumerate(sessions, 1):
        dt = session["datetime"]
        session_name = session["session_name"]
        date_str = session["date"].strftime("%Y-%m-%d")
        t_str = dt.strftime("%Y-%m-%d %H:%M")

        print(f"\n--- [{s_idx}/{len(sessions)}] {session_name} ({t_str} Tehran | {session['utc_str']}) ---")

        # 1. Fetch 5M & 1H bars for both GBPUSD and EURUSD for SMT & Symbiosis
        rates_5m = {}
        rates_1h = {}
        for sym in SYMBOLS:
            r5 = mt5.copy_rates_from(resolved_symbols[sym], mt5.TIMEFRAME_M5, dt, 85)
            r1 = mt5.copy_rates_from(resolved_symbols[sym], mt5.TIMEFRAME_H1, dt, 20)
            rates_5m[sym] = _convert_records(r5)
            rates_1h[sym] = _convert_records(r1)

        # 2. Intermarket SMT Divergence
        smt_info = detect_forex_smt_divergence(rates_5m["EURUSD"], rates_5m["GBPUSD"], session["hour"])
        symbiosis_info = analyze_cross_pair_symbiosis(rates_5m["GBPUSD"], rates_5m["EURUSD"], "GBPUSD", "EURUSD", smt_info)
        symbiosis_prompt = format_symbiotic_prompt(symbiosis_info)

        # 3. Screen and process each asset
        for sym in SYMBOLS:
            helper_sym = "EURUSD" if sym == "GBPUSD" else "GBPUSD"
            screener_res = screen_ict_session(
                rates_5m[sym],
                rates_1h[sym],
                sym,
                session["hour"],
                smt_info=smt_info
            )

            current_price = rates_5m[sym][-1]['close'] if rates_5m[sym] else 0.0

            if not screener_res.get("has_setup"):
                print(f"  • {sym}: [PASS] {screener_res.get('reason')}")
                continue

            results_summary["setups_detected"] += 1
            print(f"  ⚡ {sym} SETUP DETECTED: {screener_res.get('reason')}")

            # Prepare Dossier
            dossier = feed.prepare_session_dossier(sym, dt)
            dossier["telemetry_prompt"] = symbiosis_prompt + "\n\n" + dossier.get("telemetry_prompt", "")

            # Convene Council
            print(f"    🏛️ Convening AI Council for {sym}...")
            delib = convene_council_on_historical_dossier(dossier)

            if not delib:
                print(f"    ⚠️ Council returned empty deliberation.")
                continue

            decision = delib.get("decision", "STAND_ASIDE")
            print(f"    🗳️ Council Directive: [{decision}]")

            # Forward M1 Replay bars (12h)
            forward_m1 = feed.get_forward_m1_bars(sym, dt, hours_forward=12)

            if decision in ("BUY_LIMIT", "SELL_LIMIT"):
                results_summary["council_orders"] += 1
                order = {
                    "decision": decision,
                    "entry": delib.get("entry"),
                    "sl": delib.get("sl"),
                    "tp": delib.get("tp"),
                    "lot": delib.get("lot", 0.01),
                    "created_at": dt
                }
                print(f"    📋 Order: {decision} @ {order['entry']} | SL: {order['sl']} | TP: {order['tp']}")

                # Evaluate with Target Optimization & MFE
                eval_res = evaluate_council_decision(order, forward_m1, sym)
                status = eval_res.get("status")
                pnl = eval_res.get("realized_pnl_usd", 0.0)

                t_opt = eval_res.get("target_optimization", {})
                mfe = t_opt.get("mfe_price")
                max_rr = t_opt.get("max_rr_potential")
                eff = t_opt.get("capture_efficiency_pct")

                print(f"    📊 Result: {status} | PnL: ${pnl:+.2f} | MFE: {mfe} (Max R:R: {max_rr}R)")

                if status == "WIN":
                    results_summary["wins"] += 1
                    results_summary["filled_trades"] += 1
                    results_summary["realized_pnl"] += pnl
                elif status == "LOSS":
                    results_summary["losses"] += 1
                    results_summary["filled_trades"] += 1
                    results_summary["realized_pnl"] += pnl
                elif status == "EXPIRED":
                    results_summary["expired"] += 1

                results_summary["trades"].append({
                    "symbol": sym,
                    "datetime": t_str,
                    "decision": decision,
                    "entry": order["entry"],
                    "sl": order["sl"],
                    "tp": order["tp"],
                    "status": status,
                    "pnl": pnl,
                    "mfe": mfe,
                    "max_rr": max_rr,
                    "capture_efficiency": eff
                })

            else:
                results_summary["stand_asides"] += 1
                # Counterfactual audit on passed setup
                cf_audit = auditor.replay_missed_opportunity(screener_res, dossier, forward_m1, sym)
                results_summary["audits"].append(cf_audit)

                verdict = cf_audit.get("verdict")
                cap_saved = cf_audit.get("capital_saved", 0.0)
                missed = cf_audit.get("missed_alpha", 0.0)

                if verdict == "PROTECTIVE_VETO":
                    results_summary["capital_saved"] += cap_saved
                    print(f"    🛡️ Stand-Aside Justified: Saved ${cap_saved:.2f}")
                elif verdict == "DAMAGING_STAND_ASIDE":
                    results_summary["missed_alpha"] += missed
                    print(f"    ⚠️ Stand-Aside Missed Alpha: -${missed:.2f}")
                else:
                    print(f"    ⚪ Stand-Aside Neutral ({verdict})")

    elapsed = time.time() - t_start

    # Final Master Report
    print("\n" + "=" * 80)
    print("🏆 FINAL MASTER AUDIT REPORT: 2-WEEK OUT-OF-SAMPLE BENCHMARK")
    print(f"PERIOD: Sept 21 – Oct 02, 2026 | TOTAL SESSIONS EVALUATED: {results_summary['total_sessions']}")
    print(f"EXECUTION TIME: {elapsed:.1f}s")
    print("=" * 80)
    print(f"• Setups Detected by Fast Screener: {results_summary['setups_detected']}")
    print(f"• Council Directives: {results_summary['council_orders']} Orders | {results_summary['stand_asides']} Stand Asides")
    print(f"• Filled Trades: {results_summary['filled_trades']} ({results_summary['wins']}W / {results_summary['losses']}L | {results_summary['expired']} Expired)")
    
    wr = (results_summary["wins"] / max(1, results_summary["filled_trades"])) * 100 if results_summary["filled_trades"] > 0 else 0.0
    print(f"• Win Rate: {wr:.1f}%")
    print(f"• Realized Net PnL (0.01 lot): ${results_summary['realized_pnl']:+.2f}")
    print(f"• Capital Saved by Stand-Asides: +${results_summary['capital_saved']:.2f}")
    print(f"• Missed Alpha: -${results_summary['missed_alpha']:.2f}")
    net_edge = results_summary['realized_pnl'] + results_summary['capital_saved'] - results_summary['missed_alpha']
    print(f"• Net Council Value-Add: ${net_edge:+.2f}")
    print("=" * 80)

    # Save summary report to disk
    out_file = BASE_DIR / "hitl" / "logs" / "benchmark_sep21_oct02_report.txt"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("=== 2-WEEK BENCHMARK REPORT (SEP 21 - OCT 02, 2026) ===\n")
        f.write(f"Total Sessions: {results_summary['total_sessions']}\n")
        f.write(f"Setups Detected: {results_summary['setups_detected']}\n")
        f.write(f"Council Orders: {results_summary['council_orders']}\n")
        f.write(f"Stand Asides: {results_summary['stand_asides']}\n")
        f.write(f"Filled Trades: {results_summary['filled_trades']} ({results_summary['wins']}W / {results_summary['losses']}L)\n")
        f.write(f"Win Rate: {wr:.1f}%\n")
        f.write(f"Realized PnL: ${results_summary['realized_pnl']:+.2f}\n")
        f.write(f"Capital Saved: +${results_summary['capital_saved']:.2f}\n")
        f.write(f"Missed Alpha: -${results_summary['missed_alpha']:.2f}\n")
        f.write(f"Net Value-Add: ${net_edge:+.2f}\n\n")
        f.write("TRADES LEDGER:\n")
        for t in results_summary["trades"]:
            f.write(str(t) + "\n")

    print(f"\nDetailed report saved to: {out_file.as_posix()}")


if __name__ == "__main__":
    run_2week_benchmark()
