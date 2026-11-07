"""
TradingGuard HITL - Historical Council Replay & Outcome Verification Runner
Evaluates the 3-Round Adversarial Multi-Agent Council on authentic historical trading sessions:
1. Prepares exact historical multi-timeframe charts and market telemetry at timestamp T (zero lookahead).
2. Convenes the 3-Round Council (ICT Strategist, Macro Officer, Adversarial Auditor, CIO Arbitrator).
3. Evaluates Council decision against forward M1 broker bar execution.
"""

import sys
import os
import json
import time
import datetime
from pathlib import Path

# Force UTF-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.mt5_engine import MT5Engine
from hitl.backtest.data_feed import HistoricalDataFeed, _convert_records
from hitl.council import convene_investment_council, parse_council_decision_detailed
from hitl.backtest.evaluator import evaluate_council_decision, summarize_pnl


def test_historical_trade(trade_meta: dict):
    print("=" * 80)
    print(f"HISTORICAL COUNCIL VERIFICATION: {trade_meta['date']} ({trade_meta['session']})")
    print(f"Symbol: {trade_meta['symbol']} | Archetype: {trade_meta['archetype_id']} | Direction: {trade_meta['direction']}")
    print(f"Candidate Setup: Entry={trade_meta['entry_price']} | SL={trade_meta['stop_loss']} | Target={trade_meta.get('target_rr', 3.5)}R")
    print(f"Actual Baseline Outcome: {trade_meta['status']} ({trade_meta['net_r']:+.1f}R)")
    print("=" * 80)

    feed = HistoricalDataFeed()
    if not feed.engine.ensure_connected():
        print("[Error] Failed to connect to MT5.")
        return

    sym = trade_meta['symbol']
    clean_sym = "XAUUSD" if "XAU" in sym else "GBPUSD"
    t_target = trade_meta['target_time']

    print(f"\n[1/3] Assembling zero-lookahead historical dossier at {t_target}...")
    dossier = feed.prepare_session_dossier(sym, t_target)
    if not dossier:
        print("[Error] Failed to generate historical session dossier.")
        return

    # Adapt dossier format to match convene_investment_council expectations
    council_dossier = {
        "symbol": clean_sym,
        "resolved_symbol": sym,
        "charts_ready": True,
        "chart_paths": dossier["chart_paths"],
        "bid": dossier["price_at_t"],
        "ask": dossier["price_at_t"] + (0.00020 if "GBP" in clean_sym else 0.20),
        "spread_pts": 20 if "GBP" in clean_sym else 2,
        "usdx_bid": dossier.get("usdx_at_t", 102.0),
        "usdx_ask": dossier.get("usdx_at_t", 102.0) + 0.05,
        "macro_brief": dossier.get("macro_brief", "Macro calendar: Normal session conditions."),
        "macro_bias_prompt": dossier.get("macro_bias_prompt", "Directional filter: BEARISH_CONTINUATION"),
        "sentiment_brief": "Retail crowd positioning: 62% Long / 38% Short.",
        "telemetry_prompt": dossier.get("telemetry_prompt", ""),
        "tools_prompt": dossier.get("tools_prompt", ""),
        "active_exposure_prompt": "=== ACTIVE BROKER EXPOSURE ===\n• 0 open positions. Account flat.",
        "landmarks": dossier.get("landmarks")
    }

    screener_result = {
        "setup_type": trade_meta["setup_name"],
        "archetype_id": trade_meta["archetype_id"],
        "reason": f"Historical pre-screened setup: {trade_meta['archetype_id']} {trade_meta['direction']}",
        "signal_bar_time": str(t_target),
        "entry_ref": trade_meta["entry_price"],
        "sl_ref": trade_meta["stop_loss"],
        "phase": "EXECUTION_READY",
        "recommended_target_rr": trade_meta.get("target_rr", 3.5)
    }

    print("\n[2/3] Convening 3-Round Adversarial Multi-Agent Council...")
    t0 = time.time()
    report = convene_investment_council(
        symbol=clean_sym,
        mode="tactical",
        screener_result=screener_result,
        historical_dossier=council_dossier
    )
    dt_council = time.time() - t0

    if not report:
        print("[Error] Council failed to return a report.")
        return

    decision, parse_status = parse_council_decision_detailed(report)
    print(f"\n[3/3] Council Deliberation Complete in {dt_council:.1f}s.")
    print(f"Council Decision: {decision} (Parse Status: {parse_status})")

    # Evaluate council alignment with actual outcome
    actual_status = trade_meta["status"]
    actual_r = trade_meta["net_r"]

    print("\n" + "=" * 80)
    print("VERDICT & AUDIT COMPARISON:")
    print("=" * 80)
    if decision == "STAND_ASIDE":
        if actual_status == "LOSS":
            print(f"🛡️ PROTECTIVE VETO! The Council successfully detected the trap and ordered STAND_ASIDE.")
            print(f"Capital Saved: +${abs(trade_meta.get('risk_pts', 12.0) * 0.01 * 100):.2f} (+1.0R preserved)!")
        elif actual_status == "WIN":
            print(f"⚠️ DAMAGING STAND_ASIDE! The Council was overly cautious and missed a +{actual_r:.1f}R winner.")
        else:
            print(f"ℹ️ NEUTRAL STAND_ASIDE: Trade was a breakeven/expired in reality.")
    else:
        # Trade approved
        if actual_status == "WIN":
            print(f"🎯 APPROVED WINNER! The Council correctly validated the edge and approved the +{actual_r:.1f}R winner!")
        elif actual_status == "LOSS":
            print(f"❌ APPROVED LOSS: The Council approved a setup that failed and lost -1.0R in reality.")
        else:
            print(f"ℹ️ APPROVED BREAKEVEN / EXPIRED.")

    print("\nFULL MULTI-AGENT COUNCIL REPORT:")
    print("=" * 80)
    print(report)
    print("=" * 80)
    return


if __name__ == "__main__":
    # Test on Trade 88 (Nov 04, 2026 - Gold London Open - Actual LOSS -1.0R)
    trade_88 = {
        "date": "2026-11-04",
        "target_time": datetime.datetime(2026, 11, 4, 10, 0),
        "symbol": "XAUUSD_o",
        "session": "London_Post_Open",
        "archetype_id": "SETUP-ARCH-014",
        "direction": "SHORT",
        "setup_name": "BEARISH_H1_REVERSAL_ORIGIN_RETEST",
        "entry_price": 4026.09,
        "stop_loss": 4034.51,
        "risk_pts": 8.42,
        "target_rr": 3.5,
        "status": "LOSS",
        "net_r": -1.0
    }
    test_historical_trade(trade_88)
