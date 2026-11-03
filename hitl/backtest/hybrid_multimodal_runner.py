"""
TradingGuard HITL - Multimodal Hybrid SMC Backtest Runner
Fuses Exact Numerical SMC Telemetry with Multi-Timeframe Chart Images.
Evaluates historical Gold (XAUUSD) milestones across the past 3 months.
"""

import sys
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.data_feed import HistoricalDataFeed
from hitl.backtest.council_replay import convene_council_on_historical_dossier
from hitl.backtest.evaluator import evaluate_council_decision


def run_hybrid_pilot(num_sessions: int = 5):
    feed = HistoricalDataFeed()
    now = datetime.datetime.now()

    # Sample active session milestones across August, September, October
    milestones = [
        datetime.datetime(2026, 8, 7, 10, 30),   # August London Open
        datetime.datetime(2026, 8, 26, 16, 30),  # August NY Open
        datetime.datetime(2026, 9, 15, 10, 30),  # September London Open
        datetime.datetime(2026, 9, 29, 16, 30),  # September NY Open
        datetime.datetime(2026, 10, 20, 10, 30), # October London Open
    ][:num_sessions]

    print("=" * 75)
    print("🔬 MULTIMODAL HYBRID SMC EVALUATION (NUMERICAL TELEMETRY + 4 MTF CHARTS)")
    print(f"INSTRUMENT: XAUUSD | MILESTONES: {len(milestones)} Cross-Regime Sessions")
    print("GOVERNANCE: Max Risk $17.00 | TTL 75m | FVG/Breaker Execution | Base Lot 0.01")
    print("=" * 75)

    for idx, milestone in enumerate(milestones, 1):
        t_str = milestone.strftime("%Y-%m-%d %H:%M")
        print(f"\n[Hybrid Session {idx}/{len(milestones)}] {t_str} Tehran")

        dossier = feed.prepare_session_dossier("XAUUSD", milestone)
        if not dossier:
            print("⚠️ Skipped: Missing historical rates.")
            continue

        print("\n" + dossier.get("telemetry_prompt", ""))
        print("\n📸 4 MTF Charts Rendered (1D, 1H, 15M, 5M). Dispatching Multimodal Dossier to Council...")

        res = convene_council_on_historical_dossier(dossier)
        if not res:
            print("⚠️ Council failed or timed out.")
            continue

        dec = res['decision']
        print(f"\n⚖️ CIO Directive: [{dec}]")
        if dec != "STAND_ASIDE":
            print(f"   Entry: {res['entry']} | SL: {res['sl']} | TP: {res['tp']} | R:R: {res['rr']}")
            full_rep = res.get('full_report', '')
            for line in full_rep.splitlines():
                if "Executive Summary" in line or "Critical Trigger" in line:
                    print(f"   📋 {line.strip()}")

        forward_m1 = feed.get_forward_m1_bars("XAUUSD", milestone, hours_forward=6)
        eval_res = evaluate_council_decision(res, forward_m1, "XAUUSD")
        status = eval_res['status']
        pnl = eval_res['realized_pnl_usd']
        print(f"🎯 Execution Outcome: {status} (PnL: ${pnl:+.2f})")
        print(f"   Notes: {eval_res['notes']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    run_hybrid_pilot(num_sessions=5)
