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

def run_losers_test():
    feed = HistoricalDataFeed()
    if not feed.engine.ensure_connected():
        print("Failed to connect to MT5")
        return

    sym = "BTCUSD"

    test_cases = [
        {
            "label": "Trade 1 (00:30 Asian Loser)",
            "target_time": datetime.datetime(2026, 11, 6, 0, 30),
            "archetype_id": "SETUP-ARCH-009",
            "setup_name": "BULLISH_TREND_RETEST",
            "direction": "LONG",
            "entry_price": 75989.30,
            "stop_loss": 75556.34,
            "target_rr": 3.5,
            "risk_pts": 432.96,
            "baseline_status": "LOSS",
            "baseline_r": -1.0,
            "baseline_pnl": -4.43
        },
        {
            "label": "Trade 4 (14:45 Pre-NY Loser)",
            "target_time": datetime.datetime(2026, 11, 6, 14, 45),
            "archetype_id": "SETUP-ARCH-009",
            "setup_name": "BEARISH_TREND_RETEST",
            "direction": "SHORT",
            "entry_price": 75825.33,
            "stop_loss": 76099.81,
            "target_rr": 3.5,
            "risk_pts": 274.48,
            "baseline_status": "LOSS",
            "baseline_r": -1.0,
            "baseline_pnl": -2.84
        }
    ]

    for tc in test_cases:
        t_target = tc["target_time"]
        print("\n" + "=" * 80)
        print(f"CONVENING COUNCIL ON {tc['label']} at {t_target}")
        print(f"Setup: {tc['setup_name']} ({tc['archetype_id']}) | Dir: {tc['direction']}")
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

        if decision == "STAND_ASIDE":
            verdict = f"PROTECTIVE VETO (Saved -1.0R / +${abs(tc['baseline_pnl']):.2f})"
        else:
            verdict = f"APPROVED LOSS ({tc['baseline_r']:+.2f}R | ${tc['baseline_pnl']:+.2f})"

        print(f"Verdict: {verdict}")
        safe_name = tc['label'].replace(' ', '_').replace('(', '').replace(')', '').replace(':', '')
        report_file = REPORTS_DIR / f"{safe_name}.md"
        with open(report_file, "w", encoding="utf-8") as rf:
            rf.write(report)
        print(f"Deliberation report saved to: {report_file}")

    mt5.shutdown()

if __name__ == "__main__":
    run_losers_test()
