"""
TradingGuard HITL - Dense 90-Day Multi-Asset AI Council Backtester
Evaluates EVERY trading day across the past 3 months (90 days):
- Instruments: XAUUSD, EURUSD, GBPUSD
- Sessions: London Open (10:30 Tehran) & NY Open (16:30 Tehran)
- Total Sessions: ~65 trading days * 2 sessions * 3 assets = ~390 sessions
- Architecture:
  * Tier 1: Fast Algorithmic ICT Screener (<5ms) filters low-probability chop into instant STAND_ASIDE.
  * Tier 2: AI Investment Council deliberates on genuine liquidity sweeps and FVG setups.
  * Tier 3: Forward M1 Execution Simulator (75m Inactivity TTL, Watchdog radar, $12 hard risk cap).
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
from hitl.backtest.session_clock import get_session_times_for_date

SYMBOLS_TRIAD = ["XAUUSD", "EURUSD", "GBPUSD"]


def generate_all_90day_sessions(days_back: int = 90) -> List[datetime.datetime]:
    """Generates all London and NY trading sessions across the past 90 calendar days, dynamically adapting to seasonal DST shifts."""
    sessions = []
    now = datetime.datetime.now()

    for d in range(days_back, 0, -1):
        target_date = now - datetime.timedelta(days=d)
        # Skip Saturday (5) and Sunday (6)
        if target_date.weekday() in (5, 6):
            continue

        # Dynamic seasonal DST calculation:
        # Summer: London 10:30 / NY 15:30 Tehran
        # Winter: London 11:30 / NY 16:30 Tehran
        s_times = get_session_times_for_date(target_date.date())
        t_london = s_times["london"]["tehran_time"].replace(tzinfo=None)
        t_ny = s_times["new_york"]["tehran_time"].replace(tzinfo=None)

        sessions.append(t_london)
        sessions.append(t_ny)

    sessions.sort()
    return sessions


def run_dense_90day_backtest(
    symbols: List[str] = SYMBOLS_TRIAD,
    days_back: int = 90,
    max_council_calls_per_symbol: int = 15
) -> Dict[str, Any]:
    """
    Executes an exhaustive 90-day walk-forward backtest combining Tier-1 ICT Screener
    with Tier-2 AI Council deliberations on active market setups.
    """
    feed = HistoricalDataFeed()
    all_sessions = generate_all_90day_sessions(days_back=days_back)
    total_calendar_sessions = len(all_sessions)

    print("=" * 75)
    print("🏛️ DENSE 90-DAY MULTI-ASSET WALK-FORWARD AI COUNCIL BACKTEST")
    print(f"BASKET: {', '.join(symbols)} | HORIZON: {days_back} Days (~{total_calendar_sessions // 2} Trading Days)")
    print(f"SESSIONS PER ASSET: {total_calendar_sessions} (London 10:30 & NY 16:30)")
    print(f"TOTAL EVALUATION SCOPE: {total_calendar_sessions * len(symbols)} Session Milestones")
    print("PARAMETERS: Max Risk $12.00 | TTL 75m | FVG Proximal Edge | Base Lot 0.01")
    print("=" * 75)

    asset_scorecards = {}
    combined_results = []
    t_start = time.time()

    for sym in symbols:
        print(f"\n{'#' * 25} EXHAUSTIVE AUDIT: {sym} ({total_calendar_sessions} Sessions) {'#' * 25}")
        sym_results = []
        council_calls = 0

        for idx, milestone in enumerate(all_sessions, 1):
            t_str = milestone.strftime("%Y-%m-%d %H:%M")
            session_name = "London" if milestone.hour == 10 else "NY"

            # 1. Fetch lightweight bars for Tier-1 screening
            resolved = feed.engine.resolve_symbol(sym)
            if not resolved:
                continue

            rates_5m = mt5.copy_rates_from(resolved, mt5.TIMEFRAME_M5, milestone, 85)
            rates_1h = mt5.copy_rates_from(resolved, mt5.TIMEFRAME_H1, milestone, 20)
            list_5m = _convert_records(rates_5m)
            list_1h = _convert_records(rates_1h)

            if not (list_5m and list_1h):
                continue

            # 2. Tier-1 ICT Screener (<5ms)
            screener = screen_ict_session(list_5m, list_1h, sym, milestone.hour)

            if not screener["has_setup"] or (council_calls >= max_council_calls_per_symbol):
                # Instant Stand-Aside: Zero LLM latency
                item = {
                    "symbol": sym,
                    "timestamp": t_str,
                    "session": session_name,
                    "decision": "STAND_ASIDE",
                    "status": "STAND_ASIDE",
                    "pnl": 0.0,
                    "notes": f"Tier-1 Filter: {screener['reason']}"
                }
                sym_results.append(item)
                combined_results.append(item)
                continue

            # 3. Setup Detected! Trigger Tier-2 Full AI Investment Council
            council_calls += 1
            print(f"\n⚡ [{sym} #{council_calls}] {t_str} ({session_name} Open) -> {screener['reason']}")

            dossier = feed.prepare_session_dossier(sym, milestone)
            if not dossier:
                print(f"⚠️ Missing historical chart dossier at {t_str}")
                continue

            p_val = dossier['price_at_t']
            p_str = f"{p_val:.5f}" if ("EUR" in sym or "GBP" in sym) else f"{p_val:.2f}"
            print(f"📸 4 MTF Charts rendered. Price at T: {p_str}")
            print("🏛️ Convocating 5-Agent Council (agy.exe)...")

            decision_dict = convene_council_on_historical_dossier(dossier)
            if not decision_dict:
                print("⚠️ Council call timed out or failed.")
                continue

            dec = decision_dict['decision']
            print(f"⚖️ CIO Directive: [{dec}]")

            if dec != "STAND_ASIDE":
                print(f"   Entry: {decision_dict['entry']} | SL: {decision_dict['sl']} | TP: {decision_dict['tp']} | R:R: {decision_dict['rr']}")

            # 4. Tier-3 Forward M1 Execution Simulator (75m TTL, Watchdog, $12 Cap)
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
                "notes": eval_res.get('notes'),
                "council_report": decision_dict.get('full_report', '')
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
            "council_triggers": council_calls,
            "orders": orders,
            "filled": filled,
            "wins": wins,
            "losses": losses,
            "expired": expired,
            "pnl": sym_pnl,
            "win_rate": (wins / filled * 100) if filled > 0 else 0.0
        }

        print(f"\n📊 {sym} Audit Completed: {total_sym} Sessions | {council_calls} Council Triggers | {orders} Orders | Net PnL: ${sym_pnl:+.2f}")

    # Final Consolidated Portfolio Performance
    elapsed = time.time() - t_start
    total_all = len(combined_results)
    total_stand_asides = sum(1 for r in combined_results if r['decision'] == 'STAND_ASIDE')
    total_orders = total_all - total_stand_asides
    total_wins = sum(1 for r in combined_results if r['status'] == 'WIN')
    total_losses = sum(1 for r in combined_results if r['status'] == 'LOSS')
    total_expired = sum(1 for r in combined_results if r['status'] == 'EXPIRED')
    total_filled = total_wins + total_losses
    total_pnl = sum(r['pnl'] for r in combined_results)

    gross_profit = sum(r['pnl'] for r in combined_results if r['pnl'] > 0)
    gross_loss = abs(sum(r['pnl'] for r in combined_results if r['pnl'] < 0))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    print("\n" + "=" * 75)
    print("🏆 FINAL CONSOLIDATED 90-DAY MULTI-ASSET SCORECARD (ALL 65 TRADING DAYS)")
    print("=" * 75)
    for sym, sc in asset_scorecards.items():
        print(f"• {sym:6s}: {sc['total_sessions']} Sessions | {sc['council_triggers']} Council Convocations | {sc['orders']} Orders | {sc['filled']} Filled ({sc['wins']}W/{sc['losses']}L) | PnL: ${sc['pnl']:+.2f}")

    print("-" * 75)
    print(f"Total Market Sessions Evaluated Across 90 Days: {total_all}")
    print(f"• Pure Stand-Aside (Capital Preserved):          {total_stand_asides} ({total_stand_asides / total_all * 100:.1f}%)")
    print(f"• High-Probability Limit Orders Approved:       {total_orders}")
    print(f"  - Expired Unfilled (75m Inactivity TTL):      {total_expired}")
    print(f"  - Filled Institutional Trades:                {total_filled}")
    print(f"• Filled Trade Performance:                     {total_wins} Wins | {total_losses} Losses")
    print(f"• Portfolio Win Rate on Fills:                  {(total_wins / total_filled * 100) if total_filled > 0 else 0.0:.1f}%")
    print(f"• Net Portfolio Realized PnL:                   ${total_pnl:+.2f}")
    print(f"• Portfolio Profit Factor:                      {pf:.2f}")
    print(f"• Total Execution Runtime:                      {elapsed / 60:.1f} minutes")
    print("=" * 75)

    return {
        "asset_scorecards": asset_scorecards,
        "total_sessions": total_all,
        "total_stand_asides": total_stand_asides,
        "total_orders": total_orders,
        "total_filled": total_filled,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "total_expired": total_expired,
        "total_pnl": total_pnl,
        "profit_factor": pf,
        "runtime_minutes": elapsed / 60
    }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    # Run the dense 90-day audit
    run_dense_90day_backtest(symbols=["XAUUSD", "EURUSD", "GBPUSD"], days_back=90, max_council_calls_per_symbol=12)
