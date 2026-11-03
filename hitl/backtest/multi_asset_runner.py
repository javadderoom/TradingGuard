"""
TradingGuard HITL - Multi-Asset 3-Month AI Council Backtest Orchestrator
Backtests the optimized AI Council across 3 instruments:
- XAUUSD (Gold)
- EURUSD (Euro)
- GBPUSD (British Pound)

Parameters:
- Risk Ceiling: $17.00 per trade (0.01 lot)
- Inactivity TTL: 75 Minutes
- Entry Model: Proximal Edge / 50% Consequent Encroachment (C.E.)
- Horizon: Past 90 Days (3 Months)
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

SYMBOLS_TRIAD = ["XAUUSD", "EURUSD", "GBPUSD"]


def generate_3month_milestones(weeks_back: int = 12) -> List[datetime.datetime]:
    """Generates distributed London (10:30) and NY (16:30) session milestones across the past 3 months."""
    milestones = []
    now = datetime.datetime.now()

    # Step back week by week across 12 weeks (~90 days)
    for w in range(1, weeks_back + 1):
        # Sample Tuesday (weekday 1) and Thursday (weekday 3) of each week for optimal liquidity
        for target_weekday in (1, 3):
            days_offset = (w * 7) + (now.weekday() - target_weekday)
            dt = now - datetime.timedelta(days=days_offset)
            if dt.weekday() in (5, 6):
                continue
            
            # London Session: 10:30 Tehran
            t_london = dt.replace(hour=10, minute=30, second=0, microsecond=0)
            # NY Session: 15:30 Tehran (08:00 AM EDT)
            t_ny = dt.replace(hour=15, minute=30, second=0, microsecond=0)

            milestones.append(t_london)
            milestones.append(t_ny)

    milestones.sort()
    return milestones


def run_multi_asset_backtest(
    symbols: List[str] = SYMBOLS_TRIAD,
    sessions_per_symbol: int = 5
) -> Dict[str, Any]:
    """
    Executes a walk-forward multi-asset backtest on the optimized AI Council across the 3-month horizon.
    """
    feed = HistoricalDataFeed()
    milestones = generate_3month_milestones(weeks_back=12)
    # Evenly distribute milestones across the 3-month (12-week) span
    if len(milestones) > sessions_per_symbol:
        step = len(milestones) // sessions_per_symbol
        selected_milestones = [milestones[i * step] for i in range(sessions_per_symbol)]
    else:
        selected_milestones = milestones

    print("=" * 70)
    print("🏛️ MULTI-ASSET AI INVESTMENT COUNCIL BACKTEST (3-MONTH HORIZON)")
    print(f"BASKET: {', '.join(symbols)} | MAX RISK: $17.00 | TTL: 75m | BASE LOT: 0.01")
    print(f"Targeting {len(selected_milestones)} evenly spaced milestones per asset across past 90 days")
    print("=" * 70)

    asset_scorecards = {}
    combined_results = []

    for sym in symbols:
        print(f"\n{'#' * 25} TESTING ASSET: {sym} {'#' * 25}")
        sym_results = []

        for idx, milestone in enumerate(selected_milestones, 1):
            t_str = milestone.strftime("%Y-%m-%d %H:%M")
            session_name = "London Open" if milestone.hour == 10 else "NY Open"
            print(f"\n[{sym} Session {idx}/{len(selected_milestones)}] {t_str} Tehran ({session_name})")

            # 1. Historical MTF Dossier
            dossier = feed.prepare_session_dossier(sym, milestone)
            if not dossier:
                print(f"⚠️ Skipped {sym}: Missing historical rates.")
                continue

            p_val = dossier['price_at_t']
            p_str = f"{p_val:.5f}" if ("EUR" in sym or "GBP" in sym) else f"{p_val:.2f}"
            print(f"📸 4 MTF Charts rendered. Quote at T: {p_str}")

            # 2. Convene AI Council
            print("🏛️ Deliberating with 5-Agent Council (agy.exe)...")
            decision_dict = convene_council_on_historical_dossier(dossier)
            if not decision_dict:
                print("⚠️ Skipped: Council failed or timed out.")
                continue

            dec = decision_dict['decision']
            print(f"⚖️ CIO Directive: [{dec}]")
            if dec != "STAND_ASIDE":
                print(f"   Entry: {decision_dict['entry']} | SL: {decision_dict['sl']} | TP: {decision_dict['tp']} | R:R: {decision_dict['rr']}")
            
            # Print brief CIO synthesis from report
            full_rep = decision_dict.get('full_report', '')
            for line in full_rep.splitlines():
                if "Executive Summary" in line or "Critical Trigger" in line:
                    print(f"   📋 {line.strip()}")

            # 3. Evaluate Forward M1 Bars
            forward_m1 = feed.get_forward_m1_bars(sym, milestone, hours_forward=6)
            eval_res = evaluate_council_decision(decision_dict, forward_m1, sym)

            status = eval_res['status']
            pnl = eval_res['realized_pnl_usd']
            print(f"🎯 Execution Outcome: {status} (PnL: ${pnl:+.2f})")
            print(f"   Notes: {eval_res['notes']}")

            item = {
                "symbol": sym,
                "timestamp": t_str,
                "session": session_name,
                "decision": dec,
                "entry": decision_dict.get('entry'),
                "sl": decision_dict.get('sl'),
                "tp": decision_dict.get('tp'),
                "status": status,
                "pnl": pnl,
                "rr_realized": eval_res.get('rr_realized'),
                "notes": eval_res.get('notes')
            }
            sym_results.append(item)
            combined_results.append(item)

        # Asset summary
        total_sym = len(sym_results)
        stand_asides = sum(1 for r in sym_results if r['decision'] == 'STAND_ASIDE')
        orders = total_sym - stand_asides
        wins = sum(1 for r in sym_results if r['status'] == 'WIN')
        losses = sum(1 for r in sym_results if r['status'] == 'LOSS')
        expired = sum(1 for r in sym_results if r['status'] == 'EXPIRED')
        filled = wins + losses
        sym_pnl = sum(r['pnl'] for r in sym_results)

        asset_scorecards[sym] = {
            "total_sessions": total_sym,
            "stand_asides": stand_asides,
            "orders": orders,
            "filled": filled,
            "wins": wins,
            "losses": losses,
            "expired": expired,
            "pnl": sym_pnl,
            "win_rate": (wins / filled * 100) if filled > 0 else 0.0
        }

    # Consolidated Multi-Asset Portfolio Summary
    total_all = len(combined_results)
    total_stand_asides = sum(1 for r in combined_results if r['decision'] == 'STAND_ASIDE')
    total_orders = total_all - total_stand_asides
    total_wins = sum(1 for r in combined_results if r['status'] == 'WIN')
    total_losses = sum(1 for r in combined_results if r['status'] == 'LOSS')
    total_expired = sum(1 for r in combined_results if r['status'] == 'EXPIRED')
    total_watchdog = sum(1 for r in combined_results if r['status'] == 'CANCELLED_WATCHDOG')
    total_filled = total_wins + total_losses
    portfolio_pnl = sum(r['pnl'] for r in combined_results)
    portfolio_win_rate = (total_wins / total_filled * 100) if total_filled > 0 else 0.0

    gross_profit = sum(r['pnl'] for r in combined_results if r['pnl'] > 0)
    gross_loss = abs(sum(r['pnl'] for r in combined_results if r['pnl'] < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

    print("\n" + "=" * 70)
    print("🏆 CONSOLIDATED MULTI-ASSET PORTFOLIO SCORECARD (PAST 3 MONTHS)")
    print("=" * 70)
    for sym, sc in asset_scorecards.items():
        print(f"• {sym:<7}: {sc['total_sessions']} Sessions | {sc['stand_asides']} Stand-Aside | {sc['filled']} Filled ({sc['wins']}W/{sc['losses']}L) | PnL: ${sc['pnl']:+.2f}")
    
    print("-" * 70)
    print(f"Total Portfolio Sessions Evaluated: {total_all}")
    print(f"• Stand-Aside Directives:           {total_stand_asides} ({total_stand_asides/max(1, total_all)*100:.1f}%) [Preserved Capital]")
    print(f"• Total Limit Orders Approved:      {total_orders}")
    print(f"  - Expired Unfilled (75m TTL):     {total_expired}")
    print(f"  - Cancelled by Watchdog Radar:    {total_watchdog}")
    print(f"  - Filled Institutional Trades:    {total_filled}")
    print(f"• Trade Performance (Filled):       {total_wins} Wins | {total_losses} Losses")
    print(f"• Portfolio Win Rate on Fills:      {portfolio_win_rate:.1f}%")
    print(f"• Net Portfolio Realized PnL:       ${portfolio_pnl:+.2f}")
    print(f"• Portfolio Profit Factor:          {profit_factor:.2f}")
    print("=" * 70)

    return {
        "asset_scorecards": asset_scorecards,
        "combined_pnl": portfolio_pnl,
        "profit_factor": profit_factor,
        "win_rate": portfolio_win_rate,
        "total_filled": total_filled,
        "detailed_results": combined_results
    }


if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    # Run 4 sessions per symbol (12 total sessions across 3 months)
    run_multi_asset_backtest(symbols=["XAUUSD", "EURUSD", "GBPUSD"], sessions_per_symbol=4)
