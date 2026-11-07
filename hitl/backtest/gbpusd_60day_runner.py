"""
TradingGuard HITL - Dense 60-Day GBPUSD AI Council Backtester (Expanded Windows)
Evaluates EVERY trading day across the past 2 months (60 calendar days / ~44 trading days)
with EXPANDED STRATEGIC KILLZONE WINDOWS:
1. London Killzone (10:00, 10:30, 11:00 Tehran / 02:30, 03:00, 03:30 NY)
2. NY Open Killzone (15:00, 15:30, 16:00 Tehran / 07:30, 08:00, 08:30 NY)
3. NY Silver Bullet Window (17:30, 18:00 Tehran / 10:00, 10:30 NY - Post News & Equity Open)
4. Extended 12-Hour Forward M1 Holding Window (Allows institutional cable swings to mature)
5. Gated by Ratified Setup Registry (SETUP-ARCH-001 to 004)
6. 6-Seat AI Investment Council (Gemini 3.8 Flash via agy.exe) with Active Playbook Memory
7. Automated Retrospective Review Council post-mortem audit
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
from hitl.backtest.evaluator import evaluate_council_decision, summarize_pnl
from hitl.backtest.logger import BacktestLogger
from hitl.setup_registry import setup_registry
from hitl.review_council import convene_review_council


def generate_expanded_60day_sessions(days_back: int = 60) -> List[Dict[str, Any]]:
    """
    Generates all strategic session checkpoints across the past 60 calendar days:
    - London Killzone (10:00, 10:30, 11:00)
    - NY Open Killzone (15:00, 15:30, 16:00)
    - NY Silver Bullet (17:30, 18:00)
    """
    sessions = []
    now = datetime.datetime.now()

    checkpoints = [
        (10, 0, "London Pre-Open"),
        (10, 30, "London Open"),
        (11, 0, "London Post-Open"),
        (15, 0, "NY Pre-Open"),
        (15, 30, "NY Open"),
        (16, 0, "NY Post-Open"),
        (17, 30, "NY Silver Bullet Open"),
        (18, 0, "NY Silver Bullet Mid")
    ]

    for d in range(days_back, 0, -1):
        target_date = now - datetime.timedelta(days=d)
        if target_date.weekday() in (5, 6):
            continue

        for h, m, label in checkpoints:
            dt = target_date.replace(hour=h, minute=m, second=0, microsecond=0)
            sessions.append({
                "datetime": dt,
                "label": label,
                "hour": h,
                "date_str": target_date.strftime("%Y-%m-%d")
            })

    sessions.sort(key=lambda s: s["datetime"])
    return sessions


def run_expanded_gbpusd_60day_backtest(
    days_back: int = 60,
    max_council_triggers: int = 20
) -> Dict[str, Any]:
    """
    Executes the dense 60-day (2-month) walk-forward backtest on GBPUSD.
    """
    symbol = "GBPUSD"
    feed = HistoricalDataFeed()
    logger = BacktestLogger(run_name="60day_gbpusd_expanded_audit")

    all_checkpoints = generate_expanded_60day_sessions(days_back=days_back)
    total_checkpoints = len(all_checkpoints)

    print("=" * 80)
    print("🏛️ TRADINGGUARD HITL - DENSE 60-DAY (2-MONTH) GBPUSD EXPANDED BACKTEST")
    print(f"ASSET: {symbol} | HORIZON: {days_back} Days (~{total_checkpoints // 8} Trading Days)")
    print(f"TOTAL CHECKPOINTS: {total_checkpoints} Across London, NY Open & NY Silver Bullet Windows")
    print("GOVERNANCE: Strict $12.00 Max Risk | 75m TTL | 12h M1 Hold | Base Lot 0.01")
    print("REGISTRY GATE: Only Ratified SMC Archetypes (SETUP-ARCH-001..004) Trigger Council")
    print("=" * 80)

    resolved = feed.engine.resolve_symbol(symbol)
    if not resolved:
        print(f"❌ Error: Could not resolve {symbol} in MT5.")
        return {}

    session_records = []
    council_triggers = 0
    executed_trades_for_review = []
    stand_asides_for_review = []
    active_orders_per_day = {}
    t_start = time.time()

    for idx, cp in enumerate(all_checkpoints, 1):
        milestone = cp["datetime"]
        label = cp["label"]
        date_str = cp["date_str"]
        t_str = milestone.strftime("%Y-%m-%d %H:%M")

        # 1. Fetch lightweight bars for Tier-1 screening (<1ms)
        rates_5m = mt5.copy_rates_from(resolved, mt5.TIMEFRAME_M5, milestone, 85)
        rates_1h = mt5.copy_rates_from(resolved, mt5.TIMEFRAME_H1, milestone, 20)
        list_5m = _convert_records(rates_5m)
        list_1h = _convert_records(rates_1h)

        if not (list_5m and list_1h):
            continue

        screener = screen_ict_session(list_5m, list_1h, symbol, milestone.hour)
        price_at_t = list_5m[-1]['close']

        # Prevent duplicate entries in the same session window on the same date
        has_active_order_in_window = active_orders_per_day.get((date_str, label.split()[0]), False)

        if not screener["has_setup"] or (council_triggers >= max_council_triggers) or has_active_order_in_window:
            record = {
                "symbol": symbol,
                "timestamp": t_str,
                "session": label,
                "price_at_t": f"{price_at_t:.5f}",
                "decision": "STAND_ASIDE",
                "entry": None, "sl": None, "tp": None, "rr": None,
                "status": "STAND_ASIDE",
                "realized_pnl_usd": 0.0,
                "fill_minute": None, "exit_minute": None,
                "notes": f"Tier-1 Screener: {screener['reason']}" if not has_active_order_in_window else "Window order active",
                "cdo_trigger": "Filtered: Mid-range chop / low volatility"
            }
            session_records.append(record)
            continue

        # 2. SMC Setup Detected & Ratified -> Convene 6-Seat Council with Telemetry + Charts + Memory
        council_triggers += 1
        arch_id = screener.get("archetype_id", "SETUP-ARCH-001")
        print(f"\n⚡ [GBPUSD Setup #{council_triggers}/{max_council_triggers}] {t_str} ({label}) -> {screener['reason']}")

        dossier = feed.prepare_session_dossier(symbol, milestone)
        if not dossier:
            print("⚠️ Missing historical chart dossier.")
            continue

        print(f"📸 4 MTF Charts rendered. Quote at T: {dossier['price_at_t']:.5f}")
        print("🏛️ Convocating 6-Seat Council (Gemini 3.8 Flash with Playbook Memory)...")

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
            print(f"   Entry: {res['entry']:.5f} | SL: {res['sl']:.5f} | TP: {res['tp']:.5f} | R:R: {res['rr']}")
            active_orders_per_day[(date_str, label.split()[0])] = True

        # 3. Forward M1 Execution Simulator (Extended to 12 Hours for Cable Swings)
        forward_m1 = feed.get_forward_m1_bars(symbol, milestone, hours_forward=12)
        eval_res = evaluate_council_decision(res, forward_m1, symbol)

        status = eval_res['status']
        pnl = eval_res['realized_pnl_usd']
        print(f"🎯 Execution Outcome: {status} (PnL: ${pnl:+.2f})")
        print(f"   Notes: {eval_res['notes']}")

        # Track Counterfactual Excursion for Stand-Asides
        if dec == "STAND_ASIDE" and forward_m1:
            open_p = forward_m1[0]['open']
            fwd_4h = forward_m1[:240]
            max_h = max(b['high'] for b in fwd_4h)
            min_l = min(b['low'] for b in fwd_4h)
            close_4h = fwd_4h[-1]['close']
            gain_pips = (max_h - open_p) * 10000
            dd_pips = (open_p - min_l) * 10000
            close_delta_pips = (close_4h - open_p) * 10000

            verdict = "CHOP"
            if gain_pips >= 25.0 and dd_pips < 12.0:
                verdict = "MISSED_BULLISH_WINNER"
            elif dd_pips >= 25.0 and gain_pips < 12.0:
                verdict = "MISSED_BEARISH_WINNER"
            elif gain_pips < 8.0 and dd_pips >= 18.0:
                verdict = "PROTECTIVE_VETO"

            audit_item = {
                "timestamp": f"{t_str} ({label})",
                "symbol": symbol,
                "discussed_setup": screener['reason'],
                "cio_decision": dec,
                "forward_4h_mfe": round(gain_pips, 1),
                "forward_4h_mae": round(dd_pips, 1),
                "forward_4h_close_change": round(close_delta_pips, 1),
                "verdict": verdict,
                "lesson": f"Forward 4H: +{gain_pips:.1f} pips max / -{dd_pips:.1f} pips dd. CDO: {cdo_memo[:60]}"
            }
            stand_asides_for_review.append(audit_item)

        elif dec != "STAND_ASIDE":
            trade_item = {
                "timestamp": f"{t_str} ({label})",
                "symbol": symbol,
                "decision": dec,
                "entry": res.get("entry"),
                "sl": res.get("sl"),
                "tp": res.get("tp"),
                "status": status,
                "realized_pnl": pnl,
                "notes": eval_res.get("notes")
            }
            executed_trades_for_review.append(trade_item)

        record = {
            "symbol": symbol,
            "timestamp": t_str,
            "session": label,
            "price_at_t": f"{dossier['price_at_t']:.5f}",
            "decision": dec,
            "entry": res.get("entry"),
            "sl": res.get("sl"),
            "tp": res.get("tp"),
            "rr": res.get("rr"),
            "status": status,
            "realized_pnl_usd": pnl,
            # Pack 6: persist the evaluator's realised flag so the ledger
            # itself records that OPEN_AT_END PnL is floating, not cash.
            "is_realized": eval_res.get("is_realized", status != "OPEN_AT_END"),
            "fill_minute": eval_res.get("fill_minute"),
            "exit_minute": eval_res.get("exit_minute"),
            "notes": eval_res.get("notes"),
            "cdo_trigger": cdo_memo,
            "council_debate": full_rep
        }
        session_records.append(record)

    # 4. Compile Scorecard
    elapsed = time.time() - t_start
    total_eval = len(session_records)
    stand_asides = sum(1 for r in session_records if r['decision'] == 'STAND_ASIDE')
    orders = total_eval - stand_asides
    wins = sum(1 for r in session_records if r['status'] == 'WIN')
    losses = sum(1 for r in session_records if r['status'] == 'LOSS')
    expired = sum(1 for r in session_records if r['status'] == 'EXPIRED')
    watchdog_cancels = sum(1 for r in session_records if r['status'] == 'CANCELLED_WATCHDOG')
    filled = wins + losses
    # Pack 6: net/gross/PF are REALISED only (see eurusd_90day_runner).
    pnl_summary = summarize_pnl(session_records)
    net_pnl = pnl_summary["realized_net_usd"]
    gross_profit = pnl_summary["realized_gross_profit_usd"]
    gross_loss = pnl_summary["realized_gross_loss_usd"]
    pf = pnl_summary["realized_profit_factor"]
    win_rate = (wins / filled * 100) if filled > 0 else 0.0

    scorecard = {
        "symbol": symbol,
        "days_back": days_back,
        "total_sessions": total_eval,
        "stand_asides": stand_asides,
        "council_triggers": council_triggers,
        "orders_approved": orders,
        "expired_unfilled": expired,
        "watchdog_cancelled": watchdog_cancels,
        "filled_trades": filled,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 2),
        "gross_profit_usd": round(gross_profit, 2),
        "gross_loss_usd": round(gross_loss, 2),
        "net_pnl_usd": round(net_pnl, 2),
        "profit_factor": round(pf, 2),
        "unrealized_pnl_usd": pnl_summary["unrealized_net_usd"],
        "open_at_end_trades": pnl_summary["open_trades"],
        "runtime_seconds": round(elapsed, 1)
    }

    # 5. Persist to Disk via BacktestLogger
    metadata = {
        "engine": "TradingGuard 6-Seat AI Council + Ratified Archetypes Gate + 12h Hold Window",
        "symbol": symbol,
        "days_back": days_back,
        "max_risk_ceiling_usd": 12.00,
        "inactivity_ttl_minutes": 75,
        "hours_forward_simulation": 12,
        "windows": "London (10:00-11:00), NY Open (15:00-16:00), NY Silver Bullet (17:30-18:00)",
        "watchdog_enabled": True,
        "llm_model": "gemini-3.8-flash-low",
        "cost": "$0.00"
    }
    paths = logger.log_run(metadata, session_records, scorecard)

    print("\n" + "=" * 80)
    print("🏆 FINAL DENSE 60-DAY GBPUSD EXPANDED SCORECARD")
    print("=" * 80)
    print(f"Total Market Checkpoints Evaluated (60 Days): {total_eval}")
    print(f"• Pure Stand-Asides (Capital Preserved):       {stand_asides} ({stand_asides / total_eval * 100:.1f}%)")
    print(f"• High-Probability Setups Debated:            {council_triggers}")
    print(f"• Limit Orders Approved by CIO:               {orders}")
    print(f"  - Expired Unfilled (75m TTL):               {expired}")
    print(f"  - Cancelled by Momentum Watchdog:           {watchdog_cancels}")
    print(f"  - Filled Executions:                        {filled}")
    print(f"• Performance on Fills:                       {wins} Wins | {losses} Losses")
    print(f"• Win Rate on Fills:                          {win_rate:.1f}%")
    print(f"• Net Realized Profit:                        ${net_pnl:+.2f}")
    print(f"• Unrealised PnL (open at end, NOT counted):    ${pnl_summary['unrealized_net_usd']:+.2f} ({pnl_summary['open_trades']} open)")
    print(f"• Profit Factor:                              {pf:.2f}")
    print(f"• Total Execution Time:                       {elapsed / 60:.1f} minutes")
    print("=" * 80)

    # 6. Convene Retrospective Review Council on GBPUSD Data
    if executed_trades_for_review or stand_asides_for_review:
        print("\n🏛️ Convening Retrospective Review Council to Audit GBPUSD 60-Day Run...")
        rev_res = convene_review_council(
            executed_trades=executed_trades_for_review,
            stand_aside_audits=stand_asides_for_review,
            symbol="GBPUSD"
        )
        if rev_res:
            print("✅ Review Council Completed! Playbook calibrated.")
            print(f"   Proposed Rules (pending human approval): {len(rev_res['proposed_rules'])}")

    return scorecard


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    run_expanded_gbpusd_60day_backtest(days_back=60, max_council_triggers=20)
