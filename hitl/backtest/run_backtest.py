"""
TradingGuard HITL - Master AI Investment Council Backtest Runner
Orchestrates end-to-end historical walk-forward simulations:
1. Slices rates at historical session milestones (London & NY Opens).
2. Renders high-fidelity dark-mode MTF charts (1D, 1H, 15M, 5M).
3. Invokes the Antigravity AI Council via agy.exe with zero lookahead.
4. Simulates M1 forward execution, 45m TTLs, Watchdog radar, and hard $12 SL/TPs.
5. Emits an institutional performance score card.
"""

import sys
import datetime
from pathlib import Path
from typing import List, Dict, Any

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.data_feed import HistoricalDataFeed
from hitl.backtest.council_replay import convene_council_on_historical_dossier
from hitl.backtest.evaluator import evaluate_council_decision


from hitl.backtest.session_clock import get_session_times_for_date


def generate_session_milestones(days_back: int = 10) -> List[datetime.datetime]:
    """Generates London and New York session timestamps for weekdays, dynamically adapting to seasonal DST shifts."""
    milestones = []
    now = datetime.datetime.now()
    
    for d in range(1, days_back + 1):
        dt = now - datetime.timedelta(days=d)
        # Skip Saturday (5) and Sunday (6)
        if dt.weekday() in (5, 6):
            continue
        # Dynamic seasonal DST calculation:
        # Summer: London 10:30 / NY 15:30 Tehran
        # Winter: London 11:30 / NY 16:30 Tehran
        s_times = get_session_times_for_date(dt.date())
        t_london = s_times["london"]["tehran_time"].replace(tzinfo=None)
        t_ny = s_times["new_york"]["tehran_time"].replace(tzinfo=None)
        
        milestones.append(t_ny)
        milestones.append(t_london)

    # Return chronological order
    milestones.sort()
    return milestones


def run_council_backtest(
    symbol: str = "XAUUSD",
    max_sessions: int = 5
) -> Dict[str, Any]:
    """Runs the walk-forward backtest across selected historical sessions."""
    feed = HistoricalDataFeed()
    milestones = generate_session_milestones(days_back=12)
    
    # Pick the most recent N sessions
    selected = milestones[-max_sessions:]

    print("=" * 65)
    print(f"🏛️ STARTING AI COUNCIL BACKTEST: {symbol}")
    print(f"Targeting {len(selected)} historical session milestones (London & NY)")
    print("Zero lookahead • High-Fidelity PIL MTF charts • Real M1 evaluation")
    print("=" * 65)

    results = []

    for idx, milestone in enumerate(selected, 1):
        t_str = milestone.strftime("%Y-%m-%d %H:%M")
        print(f"\n--- [Session {idx}/{len(selected)}] {symbol} @ {t_str} Tehran ---")

        # 1. Prepare Historical Dossier
        dossier = feed.prepare_session_dossier(symbol, milestone)
        if not dossier:
            print("⚠️ Skipped: Incomplete historical data.")
            continue

        print(f"📸 4 MTF Charts rendered. Price at milestone: {dossier['price_at_t']:.2f}")

        # 2. Convene AI Investment Council
        print("🏛️ Convening 5-Agent Council via native Antigravity (agy.exe)...")
        decision_dict = convene_council_on_historical_dossier(dossier)
        if not decision_dict:
            print("⚠️ Skipped: Council deliberation failed or timed out.")
            continue

        dec = decision_dict['decision']
        print(f"⚖️ CIO Directive: [{dec}]")
        if dec != "STAND_ASIDE":
            print(f"   Entry: {decision_dict['entry']} | SL: {decision_dict['sl']} | TP: {decision_dict['tp']} | R:R: {decision_dict['rr']}")

        # 3. Evaluate Forward M1 Execution
        forward_m1 = feed.get_forward_m1_bars(symbol, milestone, hours_forward=6)
        print(f"⏩ Replaying {len(forward_m1)} forward M1 bars (TTL 45m, ATR Radar, SL/TP)...")
        eval_res = evaluate_council_decision(decision_dict, forward_m1, symbol)

        status = eval_res['status']
        pnl = eval_res['realized_pnl_usd']
        print(f"🎯 Execution Outcome: {status} (PnL: ${pnl:+.2f})")
        print(f"   Notes: {eval_res['notes']}")

        results.append({
            "timestamp": t_str,
            "decision": dec,
            "entry": decision_dict.get('entry'),
            "sl": decision_dict.get('sl'),
            "tp": decision_dict.get('tp'),
            "status": status,
            "pnl": pnl,
            "rr_realized": eval_res.get('rr_realized'),
            "notes": eval_res.get('notes')
        })

    # Summary Statistics
    total = len(results)
    if total == 0:
        print("\nNo sessions completed.")
        return {}

    stand_asides = sum(1 for r in results if r['decision'] == 'STAND_ASIDE')
    orders = total - stand_asides
    wins = sum(1 for r in results if r['status'] == 'WIN')
    losses = sum(1 for r in results if r['status'] == 'LOSS')
    expired = sum(1 for r in results if r['status'] == 'EXPIRED')
    watchdog_cancels = sum(1 for r in results if r['status'] == 'CANCELLED_WATCHDOG')
    filled_trades = wins + losses
    
    total_pnl = sum(r['pnl'] for r in results)
    win_rate = (wins / filled_trades * 100) if filled_trades > 0 else 0.0
    
    gross_profit = sum(r['pnl'] for r in results if r['pnl'] > 0)
    gross_loss = abs(sum(r['pnl'] for r in results if r['pnl'] < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

    print("\n" + "=" * 65)
    print(f"📊 ANTIGRAVITY AI COUNCIL BACKTEST SCORECARD ({symbol})")
    print("=" * 65)
    print(f"Total Sessions Evaluated:   {total}")
    print(f"• Stand-Aside Directives:   {stand_asides} ({stand_asides/total*100:.1f}%) [Capital Preserved]")
    print(f"• Limit Orders Approved:    {orders}")
    print(f"  - Expired Unfilled (45m): {expired}")
    print(f"  - Cancelled by Watchdog:  {watchdog_cancels}")
    print(f"  - Filled Executions:      {filled_trades}")
    print(f"• Trade Outcomes (Filled):  {wins} Wins | {losses} Losses")
    print(f"• Win Rate on Filled:       {win_rate:.1f}%")
    print(f"• Total Realized PnL:       ${total_pnl:+.2f}")
    print(f"• Profit Factor:            {profit_factor:.2f}")
    print("=" * 65)

    return {
        "total_sessions": total,
        "stand_asides": stand_asides,
        "orders_approved": orders,
        "filled_trades": filled_trades,
        "wins": wins,
        "losses": losses,
        "expired": expired,
        "watchdog_cancels": watchdog_cancels,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "profit_factor": profit_factor,
        "detailed_results": results
    }


if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    # Run pilot test of 3 sessions to verify the complete pipeline
    run_council_backtest(symbol="XAUUSD", max_sessions=3)
