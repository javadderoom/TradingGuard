"""
TradingGuard HITL - 2-Asset Forex Basket Backtester (EURUSD & GBPUSD)
Integrates:
1. Independent SMC Execution on Both Pairs (SETUP-ARCH-001..004):
   - Evaluates pure independent setups on EURUSD and GBPUSD simultaneously.
2. Intermarket SMT Divergence Engine (SETUP-ARCH-006):
   - Relative High/Low non-confirmation between Fiber and Cable.
3. Symbiotic Cross-Pair Barometer (The "Helper Pair" Dynamic):
   - When analyzing EURUSD, inspects GBPUSD structure/momentum as a leading predictive confirmation.
   - When analyzing GBPUSD, inspects EURUSD structure/momentum as a leading predictive confirmation.
4. Realistic Broker Bid/Ask Spread Simulation:
   - EURUSD: 1.8 pips (0.00018)
   - GBPUSD: 2.5 pips (0.00025)
5. 6-Seat AI Investment Council (Gemini 3.8 Flash via agy.exe, zero cost).
6. 12-Hour Forward M1 Replay with 75m TTL and Watchdog ATR Protection.
7. Counterfactual Opportunity Auditor & Shadow Portfolio (Blind vs Council).
8. Automated Retrospective Review Council Post-Mortem Audit.
"""

import sys
import time
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.data_feed import HistoricalDataFeed, _convert_records
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.forex_cross_pair import detect_forex_smt_divergence, analyze_cross_pair_symbiosis, format_symbiotic_prompt
from hitl.backtest.council_replay import convene_council_on_historical_dossier
from hitl.backtest.evaluator import evaluate_council_decision, get_default_broker_spread
from hitl.backtest.logger import BacktestLogger
from hitl.setup_registry import setup_registry
from hitl.review_council import convene_review_council
from hitl.counterfactual_auditor import counterfactual_auditor


def generate_basket_checkpoints(
    days_back: int = 60,
    start_date: Optional[datetime.date] = None,
    trading_days: Optional[int] = None,
    session_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Generates London, NY Open, and NY Silver Bullet checkpoints across trading days."""
    sessions = []
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

    if start_date and trading_days:
        cur = start_date
        t_days = []
        while len(t_days) < trading_days:
            if cur.weekday() not in (5, 6):
                t_days.append(cur)
            cur += datetime.timedelta(days=1)

        for td in t_days:
            for h, m, label in checkpoints:
                if session_filter and session_filter.lower() not in label.lower():
                    continue
                dt = datetime.datetime(td.year, td.month, td.day, h, m, 0)
                sessions.append({
                    "datetime": dt,
                    "label": label,
                    "hour": h,
                    "date_str": td.strftime("%Y-%m-%d")
                })
    else:
        now = datetime.datetime.now()
        for d in range(days_back, 0, -1):
            target_date = now - datetime.timedelta(days=d)
            if target_date.weekday() in (5, 6):
                continue

            for h, m, label in checkpoints:
                if session_filter and session_filter.lower() not in label.lower():
                    continue
                dt = target_date.replace(hour=h, minute=m, second=0, microsecond=0)
                sessions.append({
                    "datetime": dt,
                    "label": label,
                    "hour": h,
                    "date_str": target_date.strftime("%Y-%m-%d")
                })

    sessions.sort(key=lambda s: s["datetime"])
    return sessions


def run_forex_basket_backtest(
    days_back: int = 60,
    start_date_str: Optional[str] = None,
    trading_days: Optional[int] = None,
    max_council_triggers: int = 40,
    run_name: str = "forex_basket_eur_gbp_audit",
    session_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes the 2-Asset EURUSD & GBPUSD basket backtest with cross-pair symbiosis.
    Supports either relative days_back or explicit segmented date range (start_date + trading_days).
    """
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    feed = HistoricalDataFeed()
    logger = BacktestLogger(run_name=run_name)

    start_date = datetime.date.fromisoformat(start_date_str) if start_date_str else None
    all_checkpoints = generate_basket_checkpoints(
        days_back=days_back,
        start_date=start_date,
        trading_days=trading_days,
        session_filter=session_filter
    )
    total_checkpoints = len(all_checkpoints)

    seg_info = f"SEGMENT: {start_date_str} ({trading_days} Trading Days)" if start_date_str else f"HORIZON: {days_back} Days"

    print("=" * 85)
    print("🏛️ TRADINGGUARD HITL - 2-ASSET FOREX BASKET BACKTEST (EURUSD & GBPUSD)")
    print(f"ASSETS: EURUSD (Fiber) & GBPUSD (Cable) | {seg_info}")
    print(f"TOTAL CHECKPOINTS: {total_checkpoints} Dual-Asset Session Milestones")
    print("SYMBIOTIC RADAR: Cross-Pair Leading Barometer & Relative Velocity Active")
    print("SMT RADAR: Relative High/Low Intermarket SMT Engine Active (SETUP-ARCH-006)")
    print("INDEPENDENT TRADES: Fully Preserved (SETUP-ARCH-001..004 on Both Pairs)")
    print("EXECUTION REALISM: True Bid/Ask Spread (EUR 1.8 pips | GBP 2.5 pips) | 12h Forward Replay")
    print("RISK CEILING: Strict $12.00 Max Risk per Trade | 0.01 Base Lot | 75m TTL")
    print("=" * 85)

    res_eur = feed.engine.resolve_symbol("EURUSD")
    res_gbp = feed.engine.resolve_symbol("GBPUSD")

    if not (res_eur and res_gbp):
        print(f"❌ Error: MT5 symbol resolution failed. EUR: {res_eur}, GBP: {res_gbp}")
        return {}

    session_records = []
    council_triggers = 0
    executed_trades_for_review = []
    stand_asides_for_review = []
    approved_orders_for_csv = []
    active_orders_per_asset = {"EURUSD": {}, "GBPUSD": {}}
    t_start = time.time()

    for idx, cp in enumerate(all_checkpoints, 1):
        milestone = cp["datetime"]
        label = cp["label"]
        date_str = cp["date_str"]
        t_str = milestone.strftime("%Y-%m-%d %H:%M")

        # 1. Fetch lightweight 5M & 1H bars for both FX pairs (<2ms)
        rates_5m_eur = _convert_records(mt5.copy_rates_from(res_eur, mt5.TIMEFRAME_M5, milestone, 85))
        rates_1h_eur = _convert_records(mt5.copy_rates_from(res_eur, mt5.TIMEFRAME_H1, milestone, 20))

        rates_5m_gbp = _convert_records(mt5.copy_rates_from(res_gbp, mt5.TIMEFRAME_M5, milestone, 85))
        rates_1h_gbp = _convert_records(mt5.copy_rates_from(res_gbp, mt5.TIMEFRAME_H1, milestone, 20))

        if not (rates_5m_eur and rates_1h_eur and rates_5m_gbp and rates_1h_gbp):
            continue

        price_eur = rates_5m_eur[-1]['close']
        price_gbp = rates_5m_gbp[-1]['close']

        # 2. Intermarket SMT Divergence & Cross-Pair Symbiosis Computation
        smt_info = detect_forex_smt_divergence(rates_5m_eur, rates_5m_gbp, milestone.hour)
        symbiosis_eur = analyze_cross_pair_symbiosis(rates_5m_eur, rates_5m_gbp, "EURUSD", "GBPUSD", smt_info)
        symbiosis_gbp = analyze_cross_pair_symbiosis(rates_5m_gbp, rates_5m_eur, "GBPUSD", "EURUSD", smt_info)

        # 3. Screen both FX pairs independently (Supports ARCH-001..004 AND SMT ARCH-006)
        screener_eur = screen_ict_session(rates_5m_eur, rates_1h_eur, "EURUSD", milestone.hour, smt_info=smt_info)
        screener_gbp = screen_ict_session(rates_5m_gbp, rates_1h_gbp, "GBPUSD", milestone.hour, smt_info=smt_info)

        # Evaluate candidate opportunities
        candidates = []
        if screener_eur["has_setup"]:
            candidates.append(("EURUSD", screener_eur, price_eur, symbiosis_eur, "GBPUSD"))
        if screener_gbp["has_setup"]:
            candidates.append(("GBPUSD", screener_gbp, price_gbp, symbiosis_gbp, "EURUSD"))

        # If neither pair triggered a setup, record stand aside
        if not candidates:
            notes = "Both pairs: Mid-range chop / no ratified setup."
            if smt_info.get("has_smt"):
                notes += f" Note: {smt_info.get('smt_type')} active but no structural POI mitigation."
            session_records.append({
                "symbol": "BASKET",
                "timestamp": t_str,
                "session": label,
                "price_at_t": f"EUR:{price_eur:.5f} GBP:{price_gbp:.5f}",
                "decision": "STAND_ASIDE",
                "entry": None, "sl": None, "tp": None, "rr": None,
                "status": "STAND_ASIDE",
                "realized_pnl_usd": 0.0,
                "fill_minute": None, "exit_minute": None,
                "notes": notes,
                "cdo_trigger": "Filtered: No ratified setup",
                "smt_active": smt_info.get("has_smt", False),
                "smt_type": smt_info.get("smt_type", "NONE")
            })
            continue

        # Process setups found on one or both FX pairs
        for sym, screener, curr_p, symbiosis_data, helper_sym in candidates:
            if council_triggers >= max_council_triggers:
                break

            window_key = (date_str, label.split()[0])
            if active_orders_per_asset[sym].get(window_key, False):
                continue

            council_triggers += 1
            arch_id = screener.get("archetype_id", "SETUP-ARCH-001")

            print(f"\n⚡ [{sym} Setup #{council_triggers}/{max_council_triggers}] {t_str} ({label})")
            print(f"   Reason: {screener['reason']}")
            print(f"   🤝 Symbiotic Helper ({helper_sym}): [{symbiosis_data['confluence']}] -> {symbiosis_data['narrative'][:85]}...")
            if smt_info.get("has_smt"):
                print(f"   🔗 Intermarket SMT: {smt_info['summary'][:85]}...")

            # Prepare MTF Chart Dossier
            dossier = feed.prepare_session_dossier(sym, milestone)
            if not dossier:
                print("   ⚠️ Missing historical chart dossier.")
                continue

            # Inject Screener Candidate Setup directly into Telemetry
            cand_entry = screener.get('entry_ref', curr_p)
            cand_sl = screener.get('sl_ref')
            cand_block = (
                f"\n=== SCREENER HIGH-PROBABILITY CANDIDATE SETUP ===\n"
                f"• Screener Archetype: [{arch_id}] {screener.get('setup_type', 'N/A')}\n"
                f"• Technical Trigger: {screener['reason']}\n"
                f"• Screener Proximal Entry Reference: {cand_entry:.5f}\n"
            )
            if cand_sl:
                cand_block += f"• Screener Structural SL Reference: {cand_sl:.5f}\n"
            cand_block += (
                f"• Alpha Execution Directive: This setup has passed pre-screening for institutional edge.\n"
                f"  The Council's primary mandate is ALPHA CAPTURE WITH CONTROLLED RISK.\n"
                f"  If risk <= $12 and R:R >= 1:3.0, APPROVE [BUY LIMIT] or [SELL LIMIT] anchored at the PROXIMAL edge.\n"
                f"  Do NOT invent bureaucratic reasons to stand aside when valid displacement/sweep is present.\n"
                f"================================================\n"
            )

            # Inject Symbiotic Cross-Pair Barometer directly into AI Council Telemetry
            symbiosis_prompt_block = format_symbiotic_prompt(symbiosis_data)
            dossier["telemetry_prompt"] = cand_block + "\n\n" + symbiosis_prompt_block + "\n\n" + dossier.get("telemetry_prompt", "")

            # Convocate 6-Seat AI Investment Council
            print(f"🏛️ Convocating 6-Seat Council for {sym} (Gemini 3.8 Flash with Playbook Memory & Symbiotic Context)...")
            res = convene_council_on_historical_dossier(dossier)
            if not res:
                print("   ⚠️ Council call timed out or failed.")
                continue

            dec = res['decision']
            full_rep = res.get('full_report', '')
            print(f"   ⚖️ CIO Directive: [{dec}]")

            # Extract CDO Memo
            cdo_memo = "N/A"
            for line in full_rep.splitlines():
                if "Actionable 'IF-THEN'" in line or "Developing Setup" in line:
                    cdo_memo = line.strip().replace("• **Actionable 'IF-THEN' Re-Activation Trigger:**", "").strip()
                    print(f"   📋 CDO Watchlist: {cdo_memo}")
                    break

            if dec != "STAND_ASIDE":
                entry_val = res.get('entry')
                sl_val = res.get('sl')
                tp_val = res.get('tp')
                print(f"   Entry: {entry_val:.5f} | SL: {sl_val:.5f} | TP: {tp_val:.5f} | R:R: {res.get('rr')}")
                active_orders_per_asset[sym][window_key] = True

                broker_dt = dossier.get("broker_time", milestone)
                sym_code = "GBP" if "GBP" in sym.upper() else "EUR"
                order_id = f"ORD-{broker_dt.strftime('%m%d')}-{broker_dt.strftime('%H%M')}-{sym_code}"
                approved_orders_for_csv.append({
                    "id": order_id,
                    "symbol": "AUTO",
                    "type": dec,
                    "trigger_time": broker_dt.strftime("%Y.%m.%d %H:%M:00"),
                    "entry": round(entry_val, 5),
                    "sl": round(sl_val, 5),
                    "tp": round(tp_val, 5),
                    "lot": 0.01,
                    "ttl": 360
                })

            # 4. Forward M1 Execution Simulator (12 Hours with Realistic Broker Bid/Ask Spread)
            forward_m1 = feed.get_forward_m1_bars(sym, milestone, hours_forward=12)
            eval_res = evaluate_council_decision(res, forward_m1, sym)

            status = eval_res['status']
            pnl = eval_res['realized_pnl_usd']
            print(f"   🎯 Outcome: {status} (Realized PnL: ${pnl:+.2f})")
            print(f"   Notes: {eval_res['notes']}")

            # Post-mortem counterfactual replay for review council
            if dec == "STAND_ASIDE" and forward_m1:
                audit_res = counterfactual_auditor.replay_missed_opportunity(
                    screener_result=screener,
                    dossier=dossier,
                    forward_m1_bars=forward_m1,
                    symbol=sym
                )
                stand_asides_for_review.append(audit_res)
                print(f"   🔍 Missed Opp Replay: {audit_res['verdict']} (${audit_res['counterfactual_pnl_usd']:+.2f})")
                print(f"      {audit_res['summary']}")

            elif dec != "STAND_ASIDE":
                executed_trades_for_review.append({
                    "timestamp": f"{t_str} ({label})",
                    "symbol": sym,
                    "decision": dec,
                    "entry": res.get("entry"),
                    "sl": res.get("sl"),
                    "tp": res.get("tp"),
                    "status": status,
                    "realized_pnl": pnl,
                    "notes": eval_res.get("notes")
                })

            record = {
                "symbol": sym,
                "timestamp": t_str,
                "session": label,
                "price_at_t": f"{curr_p:.5f}",
                "decision": dec,
                "entry": res.get("entry"),
                "sl": res.get("sl"),
                "tp": res.get("tp"),
                "rr": res.get("rr"),
                "status": status,
                "realized_pnl_usd": pnl,
                "fill_minute": eval_res.get("fill_minute"),
                "exit_minute": eval_res.get("exit_minute"),
                "target_optimization": eval_res.get("target_optimization", {}),
                "notes": eval_res.get("notes"),
                "cdo_trigger": cdo_memo,
                "council_debate": full_rep,
                "smt_active": smt_info.get("has_smt", False),
                "smt_type": smt_info.get("smt_type", "NONE"),
                "archetype_id": arch_id,
                "symbiosis_confluence": symbiosis_data.get("confluence", "NONE")
            }
            session_records.append(record)

    # 5. Compile Segmented and Consolidated Scorecard
    elapsed = time.time() - t_start

    def _calc_stats(recs: List[Dict[str, Any]]) -> Dict[str, Any]:
        tot = len(recs)
        sa = sum(1 for r in recs if r.get('decision') == 'STAND_ASIDE')
        orders = tot - sa
        wins = sum(1 for r in recs if r.get('status') == 'WIN')
        losses = sum(1 for r in recs if r.get('status') == 'LOSS')
        expired = sum(1 for r in recs if r.get('status') == 'EXPIRED')
        cancels = sum(1 for r in recs if r.get('status') == 'CANCELLED_WATCHDOG')
        filled = wins + losses
        net_pnl = sum(r.get('realized_pnl_usd', 0.0) for r in recs)
        g_profit = sum(r.get('realized_pnl_usd', 0.0) for r in recs if r.get('realized_pnl_usd', 0.0) > 0)
        g_loss = abs(sum(r.get('realized_pnl_usd', 0.0) for r in recs if r.get('realized_pnl_usd', 0.0) < 0))
        pf = (g_profit / g_loss) if g_loss > 0 else (99.0 if g_profit > 0 else 0.0)
        wr = (wins / filled * 100) if filled > 0 else 0.0
        return {
            "total_sessions": tot,
            "stand_asides": sa,
            "orders_approved": orders,
            "expired_unfilled": expired,
            "watchdog_cancelled": cancels,
            "filled_trades": filled,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(wr, 1),
            "gross_profit_usd": round(g_profit, 2),
            "gross_loss_usd": round(g_loss, 2),
            "net_pnl_usd": round(net_pnl, 2),
            "profit_factor": round(pf, 2)
        }

    eur_recs = [r for r in session_records if r.get('symbol') == 'EURUSD']
    gbp_recs = [r for r in session_records if r.get('symbol') == 'GBPUSD']
    smt_recs = [r for r in session_records if r.get('smt_active') and r.get('decision') != 'STAND_ASIDE']
    independent_recs = [r for r in session_records if not r.get('smt_active') and r.get('decision') != 'STAND_ASIDE']
    all_traded_recs = [r for r in session_records if r.get('symbol') in ('EURUSD', 'GBPUSD')]

    stats_eur = _calc_stats(eur_recs)
    stats_gbp = _calc_stats(gbp_recs)
    stats_smt = _calc_stats(smt_recs)
    stats_ind = _calc_stats(independent_recs)
    stats_basket = _calc_stats(all_traded_recs)

    # Compile Shadow Portfolio Audit (Blind Execution vs Council Filtering)
    shadow_sc = counterfactual_auditor.generate_shadow_portfolio_scorecard(
        executed_trades=executed_trades_for_review,
        stand_aside_audits=stand_asides_for_review
    )

    scorecard = {
        "days_back": days_back,
        "runtime_seconds": round(elapsed, 1),
        "council_triggers": council_triggers,
        "eurusd_performance": stats_eur,
        "gbpusd_performance": stats_gbp,
        "smt_trades_performance": stats_smt,
        "independent_smc_performance": stats_ind,
        "consolidated_basket": stats_basket,
        "shadow_portfolio": shadow_sc
    }

    # 6. Persist to Disk via BacktestLogger
    metadata = {
        "engine": "TradingGuard 2-Asset Forex Basket (EURUSD + GBPUSD) + Symbiotic Leading Barometer",
        "days_back": days_back,
        "spread_simulated": True,
        "spreads": {"EURUSD": "1.8 pips", "GBPUSD": "2.5 pips"},
        "max_risk_ceiling_usd": 12.00,
        "inactivity_ttl_minutes": 75,
        "hours_forward_simulation": 12,
        "windows": "London (10:00-11:00), NY Open (15:00-16:00), NY Silver Bullet (17:30-18:00)",
        "watchdog_enabled": True,
        "llm_model": "gemini-3.8-flash-low",
        "cost": "$0.00"
    }
    paths = logger.log_run(metadata, session_records, scorecard)

    # Persist approved orders to orders_schedule.csv for MT5 Strategy Tester
    if approved_orders_for_csv:
        csv_lines = ["ID,Symbol,Type,TriggerTime,Entry,SL,TP,Lot,TTL\n"]
        for o in approved_orders_for_csv:
            csv_lines.append(f"{o['id']},{o['symbol']},{o['type']},{o['trigger_time']},{o['entry']:.5f},{o['sl']:.5f},{o['tp']:.5f},{o['lot']:.2f},{o['ttl']}\n")
        
        common_path = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\Common\Files\orders_schedule.csv")
        local_path = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB\MQL5\Files\orders_schedule.csv")
        try:
            common_path.write_text("".join(csv_lines), encoding="utf-8")
            local_path.write_text("".join(csv_lines), encoding="utf-8")
            print(f"\n📝 Written {len(approved_orders_for_csv)} approved order(s) to Common\\Files and MQL5\\Files.")
        except Exception as e:
            print(f"⚠️ Warning: Failed writing to orders_schedule.csv: {e}")
    else:
        print("\n📝 Zero orders approved by Council (all stood aside); orders_schedule.csv left pristine.")

    print("\n" + "=" * 85)
    print("🏆 FINAL 2-ASSET FOREX BASKET SCORECARD (REALISTIC SPREAD & SYMBIOSIS)")
    print("=" * 85)
    print(f"Total Market Checkpoints Evaluated ({days_back} Days): {total_checkpoints}")
    print(f"Total High-Probability Council Deliberations:        {council_triggers}")
    print(f"Execution Horizon:                                    12-Hour Forward M1 Replay")
    print(f"Spread Deductions:                                    EURUSD 1.8 pips | GBPUSD 2.5 pips")
    print("-" * 85)
    print(f"💶 EURUSD (FIBER) PERFORMANCE:")
    print(f"   • Limit Orders Approved:   {stats_eur['orders_approved']}")
    print(f"   • Filled Trades:           {stats_eur['filled_trades']} ({stats_eur['wins']} Wins | {stats_eur['losses']} Losses)")
    print(f"   • Win Rate on Fills:       {stats_eur['win_rate_pct']}%")
    print(f"   • Net Realized Profit:     ${stats_eur['net_pnl_usd']:+.2f}")
    print(f"   • Profit Factor:           {stats_eur['profit_factor']}")
    print("-" * 85)
    print(f"💷 GBPUSD (CABLE) PERFORMANCE:")
    print(f"   • Limit Orders Approved:   {stats_gbp['orders_approved']}")
    print(f"   • Filled Trades:           {stats_gbp['filled_trades']} ({stats_gbp['wins']} Wins | {stats_gbp['losses']} Losses)")
    print(f"   • Win Rate on Fills:       {stats_gbp['win_rate_pct']}%")
    print(f"   • Net Realized Profit:     ${stats_gbp['net_pnl_usd']:+.2f}")
    print(f"   • Profit Factor:           {stats_gbp['profit_factor']}")
    print("-" * 85)
    print(f"🔗 INTERMARKET SMT TRADES (SETUP-ARCH-006):")
    print(f"   • Filled Trades:           {stats_smt['filled_trades']} ({stats_smt['wins']} Wins | {stats_smt['losses']} Losses)")
    print(f"   • Win Rate on SMT:         {stats_smt['win_rate_pct']}%")
    print(f"   • Net Realized Profit:     ${stats_smt['net_pnl_usd']:+.2f}")
    print(f"   • Profit Factor:           {stats_smt['profit_factor']}")
    print("-" * 85)
    print(f"🏛️ INDEPENDENT SMC TRADES (SETUP-ARCH-001..004):")
    print(f"   • Filled Trades:           {stats_ind['filled_trades']} ({stats_ind['wins']} Wins | {stats_ind['losses']} Losses)")
    print(f"   • Win Rate on Indep:       {stats_ind['win_rate_pct']}%")
    print(f"   • Net Realized Profit:     ${stats_ind['net_pnl_usd']:+.2f}")
    print(f"   • Profit Factor:           {stats_ind['profit_factor']}")
    print("-" * 85)
    print(f"🏆 CONSOLIDATED BASKET TOTAL:")
    print(f"   • Total Filled Trades:     {stats_basket['filled_trades']} ({stats_basket['wins']} Wins | {stats_basket['losses']} Losses)")
    print(f"   • Basket Win Rate:         {stats_basket['win_rate_pct']}%")
    print(f"   • Basket Net PnL:          ${stats_basket['net_pnl_usd']:+.2f}")
    print(f"   • Basket Profit Factor:    {stats_basket['profit_factor']}")
    print(f"   • Total Runtime:           {elapsed / 60:.1f} minutes")
    print("=" * 85)
    print("\n" + counterfactual_auditor.format_shadow_portfolio_markdown(shadow_sc))
    print("=" * 85)

    # 7. Retrospective Review Council Post-Mortem Hearing
    if executed_trades_for_review or stand_asides_for_review:
        print("\n🏛️ Convening Retrospective Review Council to Audit Forex Basket Run...")
        rev_res = convene_review_council(
            executed_trades=executed_trades_for_review,
            stand_aside_audits=stand_asides_for_review,
            symbol="EURUSD & GBPUSD"
        )
        if rev_res:
            print("✅ Review Council Completed! Institutional Playbook calibrated.")
            print(f"   Ratified Rules: {len(rev_res['ratified_rules'])}")

    return scorecard


if __name__ == "__main__":
    import sys
    import argparse
    sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description="TradingGuard HITL 2-Asset Forex Basket Runner")
    parser.add_argument("--start-date", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--trading-days", type=int, default=None, help="Number of trading days forward")
    parser.add_argument("--days-back", type=int, default=60, help="Days back from today if start-date is omitted")
    parser.add_argument("--max-triggers", type=int, default=40, help="Maximum council triggers")
    parser.add_argument("--run-name", type=str, default="forex_basket_eur_gbp_audit", help="Run identifier for logs")
    parser.add_argument("--session", type=str, default=None, help="Filter session by label (e.g. London)")

    args = parser.parse_args()

    run_forex_basket_backtest(
        days_back=args.days_back,
        start_date_str=args.start_date,
        trading_days=args.trading_days,
        max_council_triggers=args.max_triggers,
        run_name=args.run_name,
        session_filter=args.session
    )
