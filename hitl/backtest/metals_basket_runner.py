"""
TradingGuard HITL - 2-Asset Precious Metals Basket Backtester (Gold & Silver)
Simultaneously evaluates Gold (XAUUSD) and Silver (XAGUSD) across strategic session killzones:
1. Intermarket SMT Divergence Radar: Real-time non-confirmation analysis between Gold and Silver.
2. Gated by Ratified Archetypes: Including SETUP-ARCH-005 (Precious Metals Intermarket SMT).
3. Contract Physics Enforcement:
   - Gold: 0.01 lot = $1.00/pt. Max SL = $12.00.
   - Silver: 0.01 lot = 50 oz contract -> $50.00/pt ($0.50/cent). Max SL = 0.34 pts ($12.00).
4. Realistic Broker Bid/Ask Spread Simulation:
   - Gold: $0.15 spread penalty on BUY fills and SHORT stops/TPs.
   - Silver: $0.030 spread penalty (3.0 cents).
5. 6-Seat AI Investment Council (Gemini 3.8 Flash via agy.exe, zero cost).
6. 12-Hour Forward M1 Execution Simulator with Watchdog ATR protection.
7. Automated Retrospective Review Council Post-Mortem Audit.
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
from hitl.backtest.metals_smt import detect_metals_smt_divergence
from hitl.backtest.council_replay import convene_council_on_historical_dossier
from hitl.backtest.evaluator import evaluate_council_decision, get_default_broker_spread, get_optimal_trade_management, summarize_pnl
from hitl.backtest.logger import BacktestLogger
from hitl.setup_registry import setup_registry
from hitl.review_council import convene_review_council
from hitl.counterfactual_auditor import counterfactual_auditor
from hitl.backtest.session_clock import get_session_times_for_date


def generate_basket_checkpoints(
    days_back: Optional[int] = None,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    session_filter: Optional[str] = None,
    include_pre_session: bool = False
) -> List[Dict[str, Any]]:
    """Generates dynamic DST-aware London, NY Open, and NY Silver Bullet checkpoints.
    Accounts for Tehran permanent UTC+3:30 (no DST) vs London/NY seasonal DST shifts.
    Disallows pre-session checkpoints by default per User Mandate.
    """
    sessions = []
    now = datetime.datetime.now()

    target_dates = []
    if start_date and end_date:
        cur = start_date
        while cur <= end_date:
            if cur.weekday() not in (5, 6):
                target_dates.append(cur)
            cur += datetime.timedelta(days=1)
    else:
        d_back = days_back or 45
        for d in range(d_back, 0, -1):
            target_date = (now - datetime.timedelta(days=d)).date()
            if target_date.weekday() not in (5, 6):
                target_dates.append(target_date)

    for cur in target_dates:
        st = get_session_times_for_date(cur)
        lon_dt = st["london"]["tehran_time"]
        ny_dt = st["new_york"]["tehran_time"]

        # Build dynamic milestones for this specific calendar date
        day_checkpoints = []

        if include_pre_session:
            # 30m prior to London Open
            pre_lon = lon_dt - datetime.timedelta(minutes=30)
            day_checkpoints.append((pre_lon.hour, pre_lon.minute, "London Pre-Open"))

        # Prime London volume killzones
        day_checkpoints.append((lon_dt.hour, lon_dt.minute, "London Open"))
        lon_post = lon_dt + datetime.timedelta(minutes=30)
        day_checkpoints.append((lon_post.hour, lon_post.minute, "London Post-Open"))

        if include_pre_session:
            # 30m prior to NY Forex Open
            pre_ny = ny_dt - datetime.timedelta(minutes=30)
            day_checkpoints.append((pre_ny.hour, pre_ny.minute, "NY Pre-Open"))

        # Prime NY volume killzones
        day_checkpoints.append((ny_dt.hour, ny_dt.minute, "NY Open"))
        ny_post = ny_dt + datetime.timedelta(minutes=30)
        day_checkpoints.append((ny_post.hour, ny_post.minute, "NY Post-Open"))

        # NY Silver Bullet (10:00 - 11:00 NY local time -> 2h to 2.5h after NY Open)
        sb_open = ny_dt + datetime.timedelta(hours=2)
        sb_mid = ny_dt + datetime.timedelta(hours=2, minutes=30)
        day_checkpoints.append((sb_open.hour, sb_open.minute, "NY Silver Bullet Open"))
        day_checkpoints.append((sb_mid.hour, sb_mid.minute, "NY Silver Bullet Mid"))

        for h, m, label in day_checkpoints:
            if session_filter and session_filter.lower() not in label.lower():
                continue
            dt = datetime.datetime.combine(cur, datetime.time(h, m, 0))
            sessions.append({
                "datetime": dt,
                "label": label,
                "hour": h,
                "date_str": cur.strftime("%Y-%m-%d")
            })

    sessions.sort(key=lambda s: s["datetime"])
    return sessions


def run_metals_basket_backtest(
    days_back: Optional[int] = None,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    max_council_triggers: int = 24,
    session_filter: Optional[str] = None,
    include_pre_session: bool = False
) -> Dict[str, Any]:
    """
    Executes the 2-Asset Gold & Silver basket backtest.
    """
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    feed = HistoricalDataFeed()
    logger = BacktestLogger(run_name="metals_basket_xau_xag_audit")

    all_checkpoints = generate_basket_checkpoints(
        days_back=days_back,
        start_date=start_date,
        end_date=end_date,
        session_filter=session_filter,
        include_pre_session=include_pre_session
    )
    total_checkpoints = len(all_checkpoints)

    print("=" * 85)
    print("🏛️ TRADINGGUARD HITL - 2-ASSET PRECIOUS METALS BASKET BACKTEST (GOLD & SILVER)")
    if start_date and end_date:
        print(f"ASSETS: Gold (XAUUSD) & Silver (XAGUSD) | WINDOW: {start_date} to {end_date} ({total_checkpoints // 8} Trading Days)")
    else:
        print(f"ASSETS: Gold (XAUUSD) & Silver (XAGUSD) | HORIZON: {days_back} Days (~{total_checkpoints // 8} Trading Days)")
    print(f"TOTAL CHECKPOINTS: {total_checkpoints} Dual-Asset Session Milestones")
    print("INTERMARKET RADAR: Relative High/Low SMT Divergence Engine Active")
    print("EXECUTION REALISM: True Bid/Ask Spread (Gold $0.15 | Silver $0.030) | 12h Forward M1 Hold")
    print("RISK CEILING: Strict $12.00 Max Risk per Trade | 0.01 Base Lot | 75m TTL")
    print("GOVERNANCE: Gated strictly by Review Council Ratified Archetypes (SETUP-ARCH-001..005)")
    print("=" * 85)

    res_gold = feed.engine.resolve_symbol("XAUUSD")
    res_silver = feed.engine.resolve_symbol("XAGUSD")

    if not (res_gold and res_silver):
        print(f"❌ Error: MT5 symbol resolution failed. Gold: {res_gold}, Silver: {res_silver}")
        return {}

    session_records = []
    council_triggers = 0
    executed_trades_for_review = []
    stand_asides_for_review = []
    active_orders_per_asset = {"XAUUSD": {}, "XAGUSD": {}}
    t_start = time.time()

    for idx, cp in enumerate(all_checkpoints, 1):
        milestone = cp["datetime"]
        label = cp["label"]
        date_str = cp["date_str"]
        t_str = milestone.strftime("%Y-%m-%d %H:%M")

        # 1. Fetch lightweight 5M, 1H & Daily bars for both metals (<3ms)
        rates_5m_g = _convert_records(mt5.copy_rates_from(res_gold, mt5.TIMEFRAME_M5, milestone, 85))
        rates_1h_g = _convert_records(mt5.copy_rates_from(res_gold, mt5.TIMEFRAME_H1, milestone, 20))
        rates_1d_g = _convert_records(mt5.copy_rates_from(res_gold, mt5.TIMEFRAME_D1, milestone, 5))

        rates_5m_s = _convert_records(mt5.copy_rates_from(res_silver, mt5.TIMEFRAME_M5, milestone, 85))
        rates_1h_s = _convert_records(mt5.copy_rates_from(res_silver, mt5.TIMEFRAME_H1, milestone, 20))
        rates_1d_s = _convert_records(mt5.copy_rates_from(res_silver, mt5.TIMEFRAME_D1, milestone, 5))

        if not (rates_5m_g and rates_1h_g and rates_5m_s and rates_1h_s):
            continue

        price_g = rates_5m_g[-1]['close']
        price_s = rates_5m_s[-1]['close']

        # 2. Intermarket SMT Divergence Computation
        smt_info = detect_metals_smt_divergence(rates_5m_g, rates_5m_s, milestone.hour)

        # 3. Screen both metals independently with SMT Confluence & Daily Regime Gates
        screener_g = screen_ict_session(rates_5m_g, rates_1h_g, "XAUUSD", milestone.hour, smt_info=smt_info, bars_1d=rates_1d_g)
        screener_s = screen_ict_session(rates_5m_s, rates_1h_s, "XAGUSD", milestone.hour, smt_info=smt_info, bars_1d=rates_1d_s)

        # Evaluate candidate opportunities (Silver execution is strictly BANNED by User Mandate)
        candidates = []
        if screener_g["has_setup"]:
            candidates.append(("XAUUSD", screener_g, price_g))
        # XAGUSD execution is disabled - Silver serves strictly as SMT correlation radar for Gold.

        # If neither metal triggered a setup, record stand aside
        if not candidates:
            # Stand aside for basket
            notes = "Both metals: Mid-range chop / no ratified setup."
            if smt_info.get("has_smt"):
                notes += f" Note: {smt_info.get('smt_type')} active but no structural POI mitigation."
            session_records.append({
                "symbol": "BASKET",
                "timestamp": t_str,
                "session": label,
                "price_at_t": f"G:{price_g:.2f} S:{price_s:.3f}",
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

        # Process setups found on one or both metals
        for sym, screener, curr_p in candidates:
            if council_triggers >= max_council_triggers:
                break

            window_key = (date_str, label.split()[0])
            if active_orders_per_asset[sym].get(window_key, False):
                continue

            council_triggers += 1
            arch_id = screener.get("archetype_id", "SETUP-ARCH-001")
            fmt = ".2f" if sym == "XAUUSD" else ".3f"

            print(f"\n⚡ [{sym} Setup #{council_triggers}/{max_council_triggers}] {t_str} ({label})")
            print(f"   Reason: {screener['reason']}")
            if smt_info.get("has_smt"):
                print(f"   🔗 Intermarket SMT: {smt_info['summary']}")

            # Prepare MTF Chart Dossier
            dossier = feed.prepare_session_dossier(sym, milestone)
            if not dossier:
                print("   ⚠️ Missing historical chart dossier.")
                continue

            # Inject Screener Candidate Setup directly into Telemetry
            cand_entry = screener.get('entry_ref', price_g if sym == "XAUUSD" else price_s)
            cand_sl = screener.get('sl_ref')
            mtf_info = screener.get("mtf_info", {})
            mtf_phase = screener.get("phase", "UNKNOWN")
            rec_target_rr = screener.get("recommended_target_rr", 3.0)
            rec_be_rr = screener.get("recommended_be_rr")
            phase_summary = screener.get("phase_summary", "")
            dol_target = screener.get("dol_target", "N/A")
            h1_state = mtf_info.get("h1_state", "NEUTRAL")

            mtf_block = (
                f"\n=== MULTI-TIMEFRAME (MTF) STRUCTURAL NARRATIVE ===\n"
                f"• MTF Phase: {mtf_phase}\n"
                f"• 1H Market Structure State: {h1_state}\n"
                f"• Draw on Liquidity (DOL): {dol_target}\n"
                f"• Target Strategy: {'BIG EXPANSION TARGET (4.5R)' if mtf_phase == 'PRO_EXPANSION' else ('SCALED RETRACEMENT TARGET (2.2R)' if mtf_phase == 'HTF_RETRACEMENT' else 'BALANCED RANGE TARGET (2.5R)')}\n"
                f"• Breakeven Defense: {'Runner Mode (No early BE choke)' if rec_be_rr is None else f'Fast Breakeven Ratchet at {rec_be_rr}R'}\n"
                f"• Structural Summary: {phase_summary}\n"
                f"================================================\n"
            )
            cand_block = (
                f"\n=== SCREENER HIGH-PROBABILITY CANDIDATE SETUP ===\n"
                f"• Screener Archetype: [{arch_id}] {screener.get('setup_type', 'N/A')}\n"
                f"• Technical Trigger: {screener['reason']}\n"
                f"• Recommended Proximal Entry: {cand_entry:{fmt}}\n"
            )
            if cand_sl:
                risk_val = abs(cand_entry - cand_sl) * (1.0 if sym == 'XAUUSD' else 50.0)
                cand_block += f"• Structural SL Reference: {cand_sl:{fmt}} (Risk: ${risk_val:.2f})\n"
            cand_block += (
                f"• Target Strategy: Aim for {rec_target_rr}R Take Profit ({'BIG EXPANSION RUNNER' if mtf_phase == 'PRO_EXPANSION' else 'SCALED RETRACEMENT'}).\n"
                f"• Alpha Execution Directive: This setup has passed algorithmic MTF pre-screening.\n"
                f"  The Council's primary mandate is ALPHA CAPTURE WITH CONTROLLED RISK.\n"
                f"  If risk <= $12 and R:R >= 1:2.0, APPROVE [BUY LIMIT] or [SELL LIMIT].\n"
                f"  Do NOT invent bureaucratic reasons to stand aside when valid displacement/sweep is present.\n"
                f"================================================\n"
            )
            dossier["telemetry_prompt"] = mtf_block + cand_block + dossier.get("telemetry_prompt", "")

            # Inject SMT Divergence Context directly into AI Council Telemetry
            if smt_info.get("has_smt"):
                smt_header = (
                    f"\n=== PRECIOUS METALS INTERMARKET SMT RADAR ===\n"
                    f"• Intermarket State: {smt_info['smt_type']}\n"
                    f"• Intelligence: {smt_info['summary']}\n"
                    f"• SMT Partner Quote: {'Silver: ' + f'{price_s:.3f}' if sym == 'XAUUSD' else 'Gold: ' + f'{price_g:.2f}'}\n"
                    f"==============================================\n"
                )
                dossier["telemetry_prompt"] = smt_header + dossier.get("telemetry_prompt", "")

            # Convocate 6-Seat AI Investment Council
            print(f"🏛️ Convocating 6-Seat Council for {sym} (Gemini 3.8 Flash with Playbook Memory)...")
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
                print(f"   Entry: {entry_val:{fmt}} | SL: {sl_val:{fmt}} | TP: {tp_val:{fmt}} | R:R: {res.get('rr')}")
                active_orders_per_asset[sym][window_key] = True

            # 4. Forward M1 Execution Simulator with Dynamic Empirical Policy
            forward_m1 = feed.get_forward_m1_bars(sym, milestone, hours_forward=12)
            opt_tgt, opt_be = get_optimal_trade_management(sym, label)
            if screener.get("recommended_target_rr"):
                opt_tgt = screener["recommended_target_rr"]
            if "recommended_be_rr" in screener:
                opt_be = screener["recommended_be_rr"]

            eval_res = evaluate_council_decision(
                res,
                forward_m1,
                sym,
                breakeven_rr=opt_be if opt_be is not None else 999.0,
                target_rr_cap=opt_tgt
            )

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
                "price_at_t": f"{curr_p:{fmt}}",
                "decision": dec,
                "entry": res.get("entry"),
                "sl": res.get("sl"),
                "tp": res.get("tp"),
                "rr": res.get("rr"),
                "status": status,
                "realized_pnl_usd": pnl,
                # Pack 6: persist the evaluator's realised flag so the
                # ledger itself records OPEN_AT_END PnL as floating.
                "is_realized": eval_res.get("is_realized", status != "OPEN_AT_END"),
                "fill_minute": eval_res.get("fill_minute"),
                "exit_minute": eval_res.get("exit_minute"),
                "notes": eval_res.get("notes"),
                "cdo_trigger": cdo_memo,
                "council_debate": full_rep,
                "smt_active": smt_info.get("has_smt", False),
                "smt_type": smt_info.get("smt_type", "NONE"),
                "archetype_id": arch_id
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
        breakevens = sum(1 for r in recs if r.get('status') == 'BREAKEVEN')
        expired = sum(1 for r in recs if r.get('status') == 'EXPIRED')
        cancels = sum(1 for r in recs if r.get('status') == 'CANCELLED_WATCHDOG')
        filled = wins + losses + breakevens
        # Pack 6: net/gross/PF are REALISED only. OPEN_AT_END floating
        # PnL used to be summed here (worst file in this runner's own
        # history: closed -$37.60 reported as +$8.05); it is now
        # reported separately as unrealised.
        pnl_summary = summarize_pnl(recs)
        net_pnl = pnl_summary["realized_net_usd"]
        g_profit = pnl_summary["realized_gross_profit_usd"]
        g_loss = pnl_summary["realized_gross_loss_usd"]
        pf = pnl_summary["realized_profit_factor"]
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
            "breakevens": breakevens,
            "win_rate_pct": round(wr, 1),
            "gross_profit_usd": round(g_profit, 2),
            "gross_loss_usd": round(g_loss, 2),
            "net_pnl_usd": round(net_pnl, 2),
            "profit_factor": round(pf, 2),
            "unrealized_pnl_usd": pnl_summary["unrealized_net_usd"],
            "open_at_end_trades": pnl_summary["open_trades"]
        }

    gold_recs = [r for r in session_records if r.get('symbol') == 'XAUUSD']
    silver_recs = [r for r in session_records if r.get('symbol') == 'XAGUSD']
    smt_recs = [r for r in session_records if r.get('smt_active') and r.get('decision') != 'STAND_ASIDE']
    all_traded_recs = [r for r in session_records if r.get('symbol') in ('XAUUSD', 'XAGUSD')]

    stats_gold = _calc_stats(gold_recs)
    stats_silver = _calc_stats(silver_recs)
    stats_smt = _calc_stats(smt_recs)
    stats_basket = _calc_stats(all_traded_recs)

    # 5. Compile Shadow Portfolio Audit (Blind Execution vs Council Filtering)
    shadow_sc = counterfactual_auditor.generate_shadow_portfolio_scorecard(
        executed_trades=executed_trades_for_review,
        stand_aside_audits=stand_asides_for_review
    )

    scorecard = {
        "days_back": days_back,
        "runtime_seconds": round(elapsed, 1),
        "council_triggers": council_triggers,
        "gold_performance": stats_gold,
        "silver_performance": stats_silver,
        "smt_trades_performance": stats_smt,
        "consolidated_basket": stats_basket,
        "shadow_portfolio": shadow_sc
    }

    # 6. Persist to Disk via BacktestLogger
    metadata = {
        "engine": "TradingGuard 2-Asset Metals Basket (XAUUSD + XAGUSD) + SMT Radar",
        "days_back": days_back,
        "spread_simulated": True,
        "spreads": {"XAUUSD": "$0.15", "XAGUSD": "$0.030 (3.0 cents)"},
        "max_risk_ceiling_usd": 12.00,
        "inactivity_ttl_minutes": 75,
        "hours_forward_simulation": 12,
        "windows": "London (10:00-11:00), NY Open (15:00-16:00), NY Silver Bullet (17:30-18:00)",
        "watchdog_enabled": True,
        "llm_model": "gemini-3.8-flash-low",
        "cost": "$0.00"
    }
    paths = logger.log_run(metadata, session_records, scorecard)

    print("\n" + "=" * 85)
    print("🏆 FINAL 2-ASSET PRECIOUS METALS BASKET SCORECARD (REALISTIC SPREAD SIMULATED)")
    print("=" * 85)
    print(f"Total Market Checkpoints Evaluated ({days_back} Days): {total_checkpoints}")
    print(f"Total High-Probability Council Deliberations:        {council_triggers}")
    print(f"Execution Horizon:                                    12-Hour Forward M1 Replay")
    print(f"Spread Deductions:                                    Gold $0.15 | Silver $0.030")
    print("-" * 85)
    print(f"🥇 GOLD (XAUUSD) PERFORMANCE:")
    print(f"   • Limit Orders Approved:   {stats_gold['orders_approved']}")
    print(f"   • Filled Trades:           {stats_gold['filled_trades']} ({stats_gold['wins']} Wins | {stats_gold['losses']} Losses | {stats_gold.get('breakevens', 0)} BE)")
    print(f"   • Win Rate on Fills:       {stats_gold['win_rate_pct']}%")
    print(f"   • Net Realized Profit:     ${stats_gold['net_pnl_usd']:+.2f}")
    print(f"   • Profit Factor:           {stats_gold['profit_factor']}")
    print("-" * 85)
    print(f"🥈 SILVER (XAGUSD) PERFORMANCE:")
    print(f"   • Limit Orders Approved:   {stats_silver['orders_approved']}")
    print(f"   • Filled Trades:           {stats_silver['filled_trades']} ({stats_silver['wins']} Wins | {stats_silver['losses']} Losses | {stats_silver.get('breakevens', 0)} BE)")
    print(f"   • Win Rate on Fills:       {stats_silver['win_rate_pct']}%")
    print(f"   • Net Realized Profit:     ${stats_silver['net_pnl_usd']:+.2f}")
    print(f"   • Profit Factor:           {stats_silver['profit_factor']}")
    print("-" * 85)
    print(f"🔗 INTERMARKET SMT SUB-SET TRADES (SETUP-ARCH-005):")
    print(f"   • Filled Trades:           {stats_smt['filled_trades']} ({stats_smt['wins']} Wins | {stats_smt['losses']} Losses | {stats_smt.get('breakevens', 0)} BE)")
    print(f"   • Win Rate on SMT:         {stats_smt['win_rate_pct']}%")
    print(f"   • Net Realized Profit:     ${stats_smt['net_pnl_usd']:+.2f}")
    print(f"   • Profit Factor:           {stats_smt['profit_factor']}")
    print("-" * 85)
    print(f"🏛️ CONSOLIDATED BASKET TOTAL:")
    print(f"   • Total Filled Trades:     {stats_basket['filled_trades']} ({stats_basket['wins']} Wins | {stats_basket['losses']} Losses | {stats_basket.get('breakevens', 0)} BE)")
    print(f"   • Basket Win Rate:         {stats_basket['win_rate_pct']}%")
    print(f"   • Basket Net PnL:          ${stats_basket['net_pnl_usd']:+.2f}")
    print(f"   • Basket Profit Factor:    {stats_basket['profit_factor']}")
    print(f"   • Total Runtime:           {elapsed / 60:.1f} minutes")
    print("=" * 85)
    print("\n" + counterfactual_auditor.format_shadow_portfolio_markdown(shadow_sc))
    print("=" * 85)

    # 7. Retrospective Review Council Post-Mortem Hearing
    if executed_trades_for_review or stand_asides_for_review:
        print("\n🏛️ Convening Retrospective Review Council to Audit Metals Basket Run...")
        rev_res = convene_review_council(
            executed_trades=executed_trades_for_review,
            stand_aside_audits=stand_asides_for_review,
            symbol="XAUUSD & XAGUSD"
        )
        if rev_res:
            print("✅ Review Council Completed! Institutional Playbook calibrated.")
            print(f"   Proposed Rules (pending human approval): {len(rev_res['proposed_rules'])}")

    return scorecard


if __name__ == "__main__":
    import sys
    import argparse
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="2-Asset Precious Metals Basket Backtester")
    parser.add_argument("--start", type=str, default="2026-10-26", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2026-10-30", help="End date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=None, help="Days back (optional)")
    parser.add_argument("--max_triggers", type=int, default=24, help="Max council triggers")
    parser.add_argument("--session", type=str, default=None, help="Filter session by label (e.g. London)")
    parser.add_argument("--include_pre", action="store_true", default=False, help="Include pre-session checkpoints")
    args = parser.parse_args()

    s_date = datetime.date.fromisoformat(args.start) if args.start else None
    e_date = datetime.date.fromisoformat(args.end) if args.end else None

    run_metals_basket_backtest(
        days_back=args.days,
        start_date=s_date,
        end_date=e_date,
        max_council_triggers=args.max_triggers,
        session_filter=args.session,
        include_pre_session=args.include_pre
    )
