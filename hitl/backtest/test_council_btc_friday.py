import sys
import os
import datetime
from pathlib import Path
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.data_feed import HistoricalDataFeed, _convert_records
from hitl.council import convene_investment_council, parse_council_decision_detailed
from hitl.backtest.evaluator import evaluate_council_decision

REPORTS_DIR = BASE_DIR / "analysis_assets" / "council_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

def run_council_test():
    feed = HistoricalDataFeed()
    if not feed.engine.ensure_connected():
        print("Failed to connect to MT5")
        return

    sym = "BTCUSD"

    # Key trades to test:
    # 1. 18:10 Winner (BEARISH_SWEEP_FVG ARCH-002) -> Actual +3.47R (+$10.40)
    # 2. 16:30 Loser (BEARISH_PROMINENT_SWEEP_MSS ARCH-010) -> Actual -1.0R (-$2.70)
    # 3. 00:30 Loser (BULLISH_TREND_RETEST ARCH-009) -> Actual -1.0R (-$4.43)
    test_cases = [
        {
            "label": "Trade A (18:10 Winner)",
            "target_time": datetime.datetime(2026, 11, 6, 18, 10),
            "archetype_id": "SETUP-ARCH-002",
            "setup_name": "BEARISH_SWEEP_FVG",
            "direction": "SHORT",
            "entry_price": 76186.37,
            "stop_loss": 76486.37,
            "target_rr": 3.5,
            "risk_pts": 300.0,
            "baseline_status": "WIN",
            "baseline_r": 3.47,
            "baseline_pnl": 10.40
        },
        {
            "label": "Trade B (16:30 Loser)",
            "target_time": datetime.datetime(2026, 11, 6, 16, 30),
            "archetype_id": "SETUP-ARCH-010",
            "setup_name": "BEARISH_PROMINENT_SWEEP_MSS",
            "direction": "SHORT",
            "entry_price": 76003.02,
            "stop_loss": 76262.81,
            "target_rr": 3.5,
            "risk_pts": 259.79,
            "baseline_status": "LOSS",
            "baseline_r": -1.0,
            "baseline_pnl": -2.70
        }
    ]

    council_results = []

    for tc in test_cases:
        t_target = tc["target_time"]
        print("\n" + "=" * 80)
        print(f"CONVENING COUNCIL ON {tc['label']} at {t_target}")
        print(f"Setup: {tc['setup_name']} ({tc['archetype_id']}) | Dir: {tc['direction']}")
        print(f"Entry: {tc['entry_price']} | SL: {tc['stop_loss']} | Target: {tc['target_rr']}R")
        print(f"Baseline Outcome: {tc['baseline_status']} ({tc['baseline_r']:+.2f}R | ${tc['baseline_pnl']:+.2f})")
        print("=" * 80)

        dossier = feed.prepare_session_dossier(sym, t_target)
        if not dossier:
            print("Failed to prepare dossier")
            continue

        council_dossier = {
            "symbol": "BTCUSD",
            "resolved_symbol": "BTCUSD",
            "charts_ready": True,
            "chart_paths": dossier["chart_paths"],
            "bid": dossier["price_at_t"],
            "ask": dossier["price_at_t"] + 1.50,
            "spread_pts": 150,
            "usdx_bid": dossier.get("usdx_at_t", 102.0),
            "usdx_ask": dossier.get("usdx_at_t", 102.0) + 0.05,
            "macro_brief": dossier.get("macro_brief", "Macro calendar: Normal session conditions."),
            "macro_bias_prompt": dossier.get("macro_bias_prompt", "Directional filter: BEARISH_CONTINUATION"),
            "sentiment_brief": "Retail crowd positioning: 58% Long / 42% Short.",
            "telemetry_prompt": dossier.get("telemetry_prompt", ""),
            "tools_prompt": dossier.get("tools_prompt", ""),
            "active_exposure_prompt": "=== ACTIVE BROKER EXPOSURE ===\n• 0 open positions. Account flat.",
            "landmarks": dossier.get("landmarks")
        }

        screener_result = {
            "setup_type": tc["setup_name"],
            "archetype_id": tc["archetype_id"],
            "reason": f"Algorithmic candidate setup: {tc['archetype_id']} {tc['direction']}",
            "signal_bar_time": str(t_target),
            "entry_ref": tc["entry_price"],
            "sl_ref": tc["stop_loss"],
            "phase": "PRO_EXPANSION",
            "recommended_target_rr": tc["target_rr"]
        }

        t0 = time.time()
        report = convene_investment_council(
            symbol="BTCUSD",
            mode="tactical",
            screener_result=screener_result,
            historical_dossier=council_dossier
        )
        dt_council = time.time() - t0

        if not report:
            print("[Error] Council failed to produce report.")
            continue

        decision, parse_status = parse_council_decision_detailed(report)
        print(f"\n[Deliberation Complete in {dt_council:.1f}s]")
        print(f"Council Binding Directive: {decision} (Parse Status: {parse_status})")

        # Evaluate Council outcome
        if decision == "STAND_ASIDE":
            council_r = 0.0
            council_pnl = 0.0
            if tc["baseline_status"] == "LOSS":
                verdict = "PROTECTIVE VETO (Saved -1.0R / +${abs(tc['baseline_pnl']):.2f})"
            elif tc["baseline_status"] == "WIN":
                verdict = f"DAMAGING VETO (Missed +{tc['baseline_r']:.2f}R / +${tc['baseline_pnl']:.2f})"
            else:
                verdict = "NEUTRAL STAND_ASIDE"
        else:
            # Trade approved
            council_r = tc["baseline_r"]
            council_pnl = tc["baseline_pnl"]
            if tc["baseline_status"] == "WIN":
                verdict = f"APPROVED WINNER (+{council_r:.2f}R / +${council_pnl:.2f})"
            elif tc["baseline_status"] == "LOSS":
                verdict = f"APPROVED LOSS ({council_r:.2f}R / ${council_pnl:.2f})"
            else:
                verdict = "APPROVED BREAKEVEN"

        print(f"Verdict: {verdict}")
        
        # Save complete report to disk
        safe_name = tc['label'].replace(' ', '_').replace('(', '').replace(')', '')
        report_file = REPORTS_DIR / f"{safe_name}.md"
        with open(report_file, "w", encoding="utf-8") as rf:
            rf.write(report)
        print(f"Complete deliberation saved to: {report_file}")

        # Print CIO consensus
        lines = report.splitlines()
        cio_lines = [l for l in lines if any(k in l for k in ["CIO", "Consensus", "Order Type:", "BINDING", "VETO", "STAND_ASIDE", "Directive"])]
        for cl in cio_lines[:12]:
            try:
                print(f"  {cl}")
            except Exception:
                pass

        council_results.append({
            "test_case": tc,
            "decision": decision,
            "verdict": verdict,
            "council_r": council_r,
            "council_pnl": council_pnl,
            "report": report
        })

    print("\n" + "=" * 80)
    print("COUNCIL AUDIT SUMMARY ON BTCUSD (FRIDAY NOV 06, 2026)")
    print("=" * 80)
    for cr in council_results:
        tc = cr["test_case"]
        print(f"{tc['label']}: Decision={cr['decision']} | Baseline={tc['baseline_r']:+.2f}R (${tc['baseline_pnl']:+.2f}) -> Council={cr['council_r']:+.2f}R (${cr['council_pnl']:+.2f}) | {cr['verdict']}")

    mt5.shutdown()
    return council_results

if __name__ == "__main__":
    run_council_test()
