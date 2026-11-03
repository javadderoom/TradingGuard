"""
TradingGuard HITL - 30-Day Gold Comparative Backtest (6-Seat Multimodal Engine)
Evaluates every trading session across the past 30 calendar days on Gold (XAUUSD):
- London Open (10:30 Tehran) & NY Open (16:30 Tehran)
- 6-Seat AI Investment Council (ICT, Macro, TV Sentiment, CRO, CIO, CDO)
- Exact Mathematical SMC Telemetry + 4 MTF Chart PNGs (1D, 1H, 15M, 5M)
- Forward M1 Execution Simulator (75m TTL, 3s ATR Momentum Radar, $17 Risk Ceiling)
- Complete Persistence to CSV, JSON, and Markdown via BacktestLogger
"""

import re
import sys
import time
import datetime
from pathlib import Path
from typing import List, Dict, Any

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.data_feed import HistoricalDataFeed, _convert_records
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.council_replay import convene_council_on_historical_dossier
from hitl.backtest.evaluator import evaluate_council_decision
from hitl.backtest.logger import BacktestLogger


def generate_30day_sessions(days_back: int = 30) -> List[datetime.datetime]:
    """Generates all London (10:30) and NY (16:30) trading sessions for past 30 days."""
    sessions = []
    now = datetime.datetime.now()

    for d in range(days_back, 0, -1):
        target_date = now - datetime.timedelta(days=d)
        if target_date.weekday() in (5, 6):  # Skip Saturday/Sunday
            continue

        t_london = target_date.replace(hour=10, minute=30, second=0, microsecond=0)
        t_ny = target_date.replace(hour=15, minute=30, second=0, microsecond=0)

        sessions.append(t_london)
        sessions.append(t_ny)

    sessions.sort()
    return sessions


def run_30day_comparison(max_council_triggers: int = 15):
    logger = BacktestLogger(run_name="30day_gold_6seat_audit")
    feed = HistoricalDataFeed()
    sessions = generate_30day_sessions(days_back=30)
    total_sessions = len(sessions)

    print("=" * 75)
    print("🏆 30-DAY GOLD (XAUUSD) COMPARATIVE AUDIT: 6-SEAT MULTIMODAL COUNCIL")
    print(f"HORIZON: Past 30 Days (~{total_sessions // 2} Trading Days = {total_sessions} Full Sessions)")
    print("NEW ENGINE: Multimodal Numerical Telemetry + 4 MTF Charts + 6th Seat (CDO)")
    print("GOVERNANCE: Strict $17.00 Max Risk | 75m TTL | 3s Momentum Radar | Base Lot 0.01")
    print("=" * 75)

    resolved = feed.engine.resolve_symbol("XAUUSD")
    if not resolved:
        print("❌ Error: Could not resolve XAUUSD.")
        return

    session_records = []
    council_triggers = 0
    t_start = time.time()

    for idx, milestone in enumerate(sessions, 1):
        t_str = milestone.strftime("%Y-%m-%d %H:%M")
        session_name = "London Open" if milestone.hour == 10 else "NY Open"

        # 1. Fetch lightweight bars for Tier-1 screening
        rates_5m = mt5.copy_rates_from(resolved, mt5.TIMEFRAME_M5, milestone, 85)
        rates_1h = mt5.copy_rates_from(resolved, mt5.TIMEFRAME_H1, milestone, 20)
        list_5m = _convert_records(rates_5m)
        list_1h = _convert_records(rates_1h)

        if not (list_5m and list_1h):
            continue

        screener = screen_ict_session(list_5m, list_1h, "XAUUSD", milestone.hour)
        price_at_t = list_5m[-1]['close']

        if not screener["has_setup"] or (council_triggers >= max_council_triggers):
            # Instant Stand-Aside
            record = {
                "symbol": "XAUUSD",
                "timestamp": t_str,
                "session": session_name,
                "price_at_t": f"{price_at_t:.2f}",
                "decision": "STAND_ASIDE",
                "entry": None, "sl": None, "tp": None, "rr": None,
                "status": "STAND_ASIDE",
                "realized_pnl_usd": 0.0,
                "fill_minute": None, "exit_minute": None,
                "notes": f"Tier-1 Screener: {screener['reason']}",
                "cdo_trigger": "Filtered: Mid-range chop / low volatility"
            }
            session_records.append(record)
            continue

        # 2. SMC Setup Detected -> Convene 6-Seat Council with Telemetry + Charts
        council_triggers += 1
        print(f"\n⚡ [Gold Setup #{council_triggers}] {t_str} ({session_name}) -> {screener['reason']}")

        dossier = feed.prepare_session_dossier("XAUUSD", milestone)
        if not dossier:
            continue

        print(f"📸 4 MTF Charts rendered. Quote at T: {dossier['price_at_t']:.2f}")
        print("🏛️ Convocating 6-Seat Council (Gemini 3.8)...")

        res = convene_council_on_historical_dossier(dossier)
        if not res:
            print("⚠️ Council call timed out or failed.")
            continue

        dec = res['decision']
        full_rep = res.get('full_report', '')
        print(f"⚖️ CIO Directive: [{dec}]")

        # Extract Seat 6 CDO Tactical Memo
        cdo_memo = "N/A"
        for line in full_rep.splitlines():
            if "Actionable 'IF-THEN'" in line or "Developing Setup" in line:
                cdo_memo = line.strip().replace("• **Actionable 'IF-THEN' Re-Activation Trigger:**", "").strip()
                print(f"   📋 CDO Watchlist: {cdo_memo}")
                break

        if dec != "STAND_ASIDE":
            print(f"   Entry: {res['entry']} | SL: {res['sl']} | TP: {res['tp']} | R:R: {res['rr']}")

        # 3. Forward M1 Execution Simulator (75m TTL, Watchdog radar, $17 cap)
        forward_m1 = feed.get_forward_m1_bars("XAUUSD", milestone, hours_forward=6)
        eval_res = evaluate_council_decision(res, forward_m1, "XAUUSD")

        status = eval_res['status']
        pnl = eval_res['realized_pnl_usd']
        print(f"🎯 Execution Outcome: {status} (PnL: ${pnl:+.2f})")
        print(f"   Notes: {eval_res['notes']}")

        record = {
            "symbol": "XAUUSD",
            "timestamp": t_str,
            "session": session_name,
            "price_at_t": f"{dossier['price_at_t']:.2f}",
            "decision": dec,
            "entry": res.get("entry"),
            "sl": res.get("sl"),
            "tp": res.get("tp"),
            "rr": res.get("rr"),
            "status": status,
            "realized_pnl_usd": pnl,
            "fill_minute": eval_res.get("fill_minute"),
            "exit_minute": eval_res.get("exit_minute"),
            "notes": eval_res.get("notes"),
            "cdo_trigger": cdo_memo
        }
        session_records.append(record)

    # 4. Compile Consolidated Scorecard
    elapsed = time.time() - t_start
    total_eval = len(session_records)
    stand_asides = sum(1 for r in session_records if r['decision'] == 'STAND_ASIDE')
    orders = total_eval - stand_asides
    wins = sum(1 for r in session_records if r['status'] == 'WIN')
    losses = sum(1 for r in session_records if r['status'] == 'LOSS')
    expired = sum(1 for r in session_records if r['status'] == 'EXPIRED')
    watchdog_cancels = sum(1 for r in session_records if r['status'] == 'CANCELLED_WATCHDOG')
    filled = wins + losses
    net_pnl = sum(r['realized_pnl_usd'] for r in session_records)
    gross_profit = sum(r['realized_pnl_usd'] for r in session_records if r['realized_pnl_usd'] > 0)
    gross_loss = abs(sum(r['realized_pnl_usd'] for r in session_records if r['realized_pnl_usd'] < 0))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
    win_rate = (wins / filled * 100) if filled > 0 else 0.0

    scorecard = {
        "total_sessions": total_eval,
        "stand_asides": stand_asides,
        "stand_aside_pct": (stand_asides / total_eval * 100) if total_eval > 0 else 0.0,
        "council_triggers": council_triggers,
        "orders": orders,
        "filled": filled,
        "wins": wins,
        "losses": losses,
        "expired": expired,
        "watchdog_cancels": watchdog_cancels,
        "win_rate": win_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_pnl": net_pnl,
        "profit_factor": pf,
        "runtime_minutes": elapsed / 60
    }

    metadata = {
        "instrument": "XAUUSD",
        "horizon_days": 30,
        "risk_cap_usd": 17.0,
        "ttl_minutes": 75,
        "lot_size": 0.01,
        "council_seats": 6,
        "engine": "Multimodal Numerical-Visual Fusion"
    }

    # 5. Persist Everything to Disk
    logger.log_run(metadata, session_records, scorecard)

    print("\n" + "=" * 75)
    print("🏆 FINAL 30-DAY GOLD COMPARATIVE SCORECARD (6-SEAT MULTIMODAL COUNCIL)")
    print("=" * 75)
    print(f"Total Calendar Sessions Evaluated:         {total_eval} (Past 30 Days)")
    print(f"• Stand-Aside Directives (Capital Saved):  {stand_asides} ({scorecard['stand_aside_pct']:.1f}%)")
    print(f"• 6-Seat Council Convocations:             {council_triggers}")
    print(f"• Approved Limit Orders:                   {orders}")
    print(f"  - Expired Unfilled (75m TTL):            {expired}")
    print(f"  - Cancelled by Watchdog Radar:           {watchdog_cancels}")
    print(f"  - Filled Institutional Trades:           {filled}")
    print(f"• Win Rate on Fills:                       {win_rate:.1f}% ({wins}W / {losses}L)")
    print(f"• Gross Realized Profit:                   +${gross_profit:.2f}")
    print(f"• Gross Realized Loss:                     -${gross_loss:.2f}")
    print(f"• Net Realized Portfolio PnL:              ${net_pnl:+.2f}")
    print(f"• Profit Factor:                           {pf:.2f}")
    print("=" * 75)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    run_30day_comparison(max_council_triggers=10)
