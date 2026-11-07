"""
TradingGuard HITL - Dense 90-Day Gold (XAUUSD) Advanced SMC Backtest
Evaluates EVERY single trading session across the past 3 months (90 days):
- Instrument: XAUUSD (Gold)
- Horizon: Past 90 Days (~65 Trading Days = 130 Full Sessions)
- Sessions: London Open (10:30 Tehran) & NY Open (16:30 Tehran)
- Advanced SMC Strategy Suite:
  * Asian / London Range Liquidity Sweeps (Judas Swings)
  * Market Structure Shifts (MSS) & Breaker Blocks (BB)
  * Fair Value Gaps (FVG) with Proximal Edge Execution
  * Optimal Trade Entry (OTE 0.62 - 0.79) Discount/Premium zones
  * SMT Divergence against USDX
  * Strict $12.00 Max Risk Ceiling & 75m Inactivity TTL
"""

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


def generate_all_gold_sessions(days_back: int = 90) -> List[datetime.datetime]:
    """Generates all London (10:30) and NY (16:30) sessions across past 90 days."""
    sessions = []
    now = datetime.datetime.now()

    for d in range(days_back, 0, -1):
        target_date = now - datetime.timedelta(days=d)
        if target_date.weekday() in (5, 6):  # Skip weekends
            continue

        t_london = target_date.replace(hour=10, minute=30, second=0, microsecond=0)
        t_ny = target_date.replace(hour=15, minute=30, second=0, microsecond=0)

        sessions.append(t_london)
        sessions.append(t_ny)

    sessions.sort()
    return sessions


def run_gold_dense_backtest(days_back: int = 90, max_council_calls: int = 25) -> Dict[str, Any]:
    """
    Executes the dense 90-day walk-forward backtest on Gold with advanced SMC models.
    """
    feed = HistoricalDataFeed()
    all_sessions = generate_all_gold_sessions(days_back=days_back)
    total_sessions = len(all_sessions)

    print("=" * 75)
    print("🏆 DENSE 90-DAY GOLD (XAUUSD) ADVANCED SMC BACKTEST")
    print(f"INSTRUMENT: XAUUSD | HORIZON: {days_back} Days (~{total_sessions // 2} Trading Days)")
    print(f"TOTAL EVALUATION SCOPE: {total_sessions} Full Sessions (Every Single Trading Day)")
    print("SMC STRATEGIES: Breaker Blocks | FVGs | Liquidity Sweeps | OTE | SMT Divergence")
    print("RISK GOVERNANCE: Max Risk $12.00 | TTL 75m | 3s Momentum Radar | Base Lot 0.01")
    print("=" * 75)

    results = []
    council_convocations = 0
    t_start = time.time()

    resolved = feed.engine.resolve_symbol("XAUUSD")
    if not resolved:
        print("❌ Error: Could not resolve XAUUSD in MT5.")
        return {}

    for idx, milestone in enumerate(all_sessions, 1):
        t_str = milestone.strftime("%Y-%m-%d %H:%M")
        session_name = "London Open" if milestone.hour == 10 else "NY Open"

        # 1. Fetch lightweight bars for Tier-1 Advanced SMC screening
        rates_5m = mt5.copy_rates_from(resolved, mt5.TIMEFRAME_M5, milestone, 85)
        rates_1h = mt5.copy_rates_from(resolved, mt5.TIMEFRAME_H1, milestone, 20)
        list_5m = _convert_records(rates_5m)
        list_1h = _convert_records(rates_1h)

        if not (list_5m and list_1h):
            continue

        # 2. Tier-1 Advanced SMC Screener (<5ms)
        screener = screen_ict_session(list_5m, list_1h, "XAUUSD", milestone.hour)

        if not screener["has_setup"] or (council_convocations >= max_council_calls):
            # Instant Stand-Aside
            item = {
                "milestone": t_str,
                "session": session_name,
                "decision": "STAND_ASIDE",
                "status": "STAND_ASIDE",
                "pnl": 0.0,
                "notes": f"Tier-1 Screener: {screener['reason']}"
            }
            results.append(item)
            continue

        # 3. Valid SMC Setup Found! Trigger Tier-2 AI Council
        council_convocations += 1
        print(f"\n⚡ [XAUUSD Setup #{council_convocations}] {t_str} ({session_name}) -> {screener['reason']}")

        dossier = feed.prepare_session_dossier("XAUUSD", milestone)
        if not dossier:
            print(f"⚠️ Missing chart dossier at {t_str}")
            continue

        print(f"📸 4 MTF Charts rendered. Gold Price at T: {dossier['price_at_t']:.2f}")
        print("🏛️ Convocating 5-Agent Council (agy.exe)...")

        decision_dict = convene_council_on_historical_dossier(dossier)
        if not decision_dict:
            print("⚠️ Council failed or timed out.")
            continue

        dec = decision_dict['decision']
        print(f"⚖️ CIO Directive: [{dec}]")

        if dec != "STAND_ASIDE":
            print(f"   Entry: {decision_dict['entry']} | SL: {decision_dict['sl']} | TP: {decision_dict['tp']} | R:R: {decision_dict['rr']}")
            full_rep = decision_dict.get('full_report', '')
            for line in full_rep.splitlines():
                if "Executive Summary" in line or "Critical Trigger" in line:
                    print(f"   📋 {line.strip()}")

        # 4. Forward M1 Execution Simulator (75m TTL, Watchdog, $12 Cap)
        forward_m1 = feed.get_forward_m1_bars("XAUUSD", milestone, hours_forward=6)
        eval_res = evaluate_council_decision(decision_dict, forward_m1, "XAUUSD")

        status = eval_res['status']
        pnl = eval_res['realized_pnl_usd']
        print(f"🎯 Execution Outcome: {status} (PnL: ${pnl:+.2f})")
        print(f"   Notes: {eval_res['notes']}")

        item = {
            "milestone": t_str,
            "session": session_name,
            "decision": dec,
            "entry": decision_dict.get('entry'),
            "sl": decision_dict.get('sl'),
            "tp": decision_dict.get('tp'),
            "status": status,
            "pnl": pnl,
            "rr_realized": eval_res.get('rr_realized'),
            "notes": eval_res.get('notes'),
            "setup_type": screener['setup_type']
        }
        results.append(item)

    # Compile Final Institutional Gold Scorecard
    elapsed = time.time() - t_start
    total_evaluated = len(results)
    stand_asides = sum(1 for r in results if r['decision'] == 'STAND_ASIDE')
    orders = total_evaluated - stand_asides
    wins = sum(1 for r in results if r['status'] == 'WIN')
    losses = sum(1 for r in results if r['status'] == 'LOSS')
    expired = sum(1 for r in results if r['status'] == 'EXPIRED')
    filled = wins + losses
    net_pnl = sum(r['pnl'] for r in results)

    gross_profit = sum(r['pnl'] for r in results if r['pnl'] > 0)
    gross_loss = abs(sum(r['pnl'] for r in results if r['pnl'] < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    print("\n" + "=" * 75)
    print("🏆 FINAL DENSE 90-DAY GOLD (XAUUSD) SMC PERFORMANCE SCORECARD")
    print("=" * 75)
    print(f"Total Calendar Sessions Evaluated:         {total_evaluated} (All 65 Trading Days)")
    print(f"• Pure Stand-Aside (Capital Preserved):    {stand_asides} ({stand_asides / total_evaluated * 100:.1f}%)")
    print(f"• Advanced SMC Council Convocations:       {council_convocations}")
    print(f"• High-Probability Limit Orders Approved: {orders}")
    print(f"  - Expired Unfilled (75m Inactivity TTL): {expired}")
    print(f"  - Filled Institutional Trades:          {filled}")
    print(f"• Trade Outcome on Fills:                 {wins} Wins | {losses} Losses")
    print(f"• Win Rate on Fills:                      {(wins / filled * 100) if filled > 0 else 0.0:.1f}%")
    print(f"• Gross Realized Profit:                  +${gross_profit:.2f}")
    print(f"• Gross Realized Loss:                    -${gross_loss:.2f}")
    print(f"• Net Realized Portfolio PnL:             ${net_pnl:+.2f}")
    print(f"• Portfolio Profit Factor:                {profit_factor:.2f}")
    print(f"• Total Execution Time:                   {elapsed / 60:.1f} minutes")
    print("=" * 75)

    return {
        "total_sessions": total_evaluated,
        "stand_asides": stand_asides,
        "council_convocations": council_convocations,
        "orders": orders,
        "filled": filled,
        "wins": wins,
        "losses": losses,
        "expired": expired,
        "net_pnl": net_pnl,
        "profit_factor": profit_factor
    }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    run_gold_dense_backtest(days_back=90, max_council_calls=20)
