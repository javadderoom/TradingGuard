"""
TradingGuard HITL - Autonomous Live Market Radar (Opportunity Scout)
Silently monitors live MT5 market feeds during London and NY killzones.
Detects prominent liquidity sweeps and Market Structure Shift (MSS) displacements.
Autonomously captures MTF charts, convenes the 6-Seat AI Investment Council,
and dispatches high-priority trade cards to Telegram with one-tap execution buttons.
"""

import time
import datetime
import re
import threading
from typing import Dict, Any, Optional, List, Tuple
import MetaTrader5 as mt5

from hitl.mt5_engine import MT5Engine
from hitl.telegram_client import TelegramClient
from hitl.council import convene_investment_council, assemble_council_intelligence
from hitl.tools.smc_tools import build_validated_order_plan
from hitl.capture import capture_multi_timeframe
from hitl.backtest.chart_renderer import render_candlestick_chart, create_mtf_grid_image, extract_chart_landmarks
from hitl.backtest.data_feed import _convert_records
from hitl.config import BASE_DIR, TELEGRAM_CHAT_ID

# Global storage for pending radar plans waiting for Seat #7 approval
PENDING_EXECUTION_PLANS: Dict[str, Dict[str, Any]] = {}


class LiveMarketRadar:
    def __init__(
        self,
        engine: MT5Engine,
        client: TelegramClient,
        target_symbols: Optional[List[str]] = None
    ):
        self.engine = engine
        self.client = client
        # Bitcoin/Crypto decommissioned from SMC Live Radar per 1-year empirical audit (-49.56R drag).
        # Crypto trades strictly through autonomous mathematical quant (LiveQuantBridge).
        self.target_symbols = target_symbols or ["GBPUSD", "XAUUSD", "NQ"]
        self.last_trigger_times: Dict[Tuple[str, str], float] = {}  # (symbol, "BUY"/"SELL") -> timestamp
        self.last_sweep_extremes: Dict[Tuple[str, str], float] = {} # (symbol, "BUY"/"SELL") -> extreme price
        self.cooldown_seconds: float = 1800.0 # 30 minutes between duplicate alerts per direction
        self._is_evaluating: bool = False

        # Autonomous Quant Strategy Bridge (Council & Snap Bypassed)
        from hitl.quant_engine.live_quant_bridge import LiveQuantBridge
        self.quant_bridge = LiveQuantBridge(self.engine, self.client)

    def is_killzone_active(self) -> Tuple[bool, str]:
        """
        Determines whether the market is currently inside institutional Killzones,
        dynamically resolving seasonal DST shifts across London, New York, and Tehran.
        """
        from hitl.backtest.session_clock import get_active_session_status
        is_active, label, sess_key = get_active_session_status()
        return is_active, label

    def scan_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Scans a single symbol for prominent liquidity sweeps and M1/M5 displacement.
        Returns detected setup details or None.
        """
        # Bitcoin/Crypto is permanently decommissioned from SMC scanning
        if "BTC" in symbol.upper() or "ETH" in symbol.upper():
            return None
        if not self.engine.ensure_connected():
            return None

        resolved = self.engine.resolve_symbol(symbol)
        if not resolved:
            return None

        # RULE-RISK-010: Zero Duplicate Exposure Guard
        # If an active position or pending order already exists for this symbol, suppress radar
        raw_pos = mt5.positions_get(symbol=resolved)
        raw_ord = mt5.orders_get(symbol=resolved)
        if raw_pos or raw_ord:
            return None

        # Fetch closed M5 bars (240 bars = 20 hours to capture Asian & London benchmarks)
        rates_5m = mt5.copy_rates_from_pos(resolved, mt5.TIMEFRAME_M5, 0, 240)
        rates_1h = mt5.copy_rates_from_pos(resolved, mt5.TIMEFRAME_H1, 0, 48)
        rates_1m = mt5.copy_rates_from_pos(resolved, mt5.TIMEFRAME_M1, 0, 60)
        rates_1d = mt5.copy_rates_from_pos(resolved, mt5.TIMEFRAME_D1, 0, 10)

        if rates_5m is None or len(rates_5m) < 60 or rates_1h is None or len(rates_1h) < 10:
            return None

        list_5m = _convert_records(rates_5m)
        list_1h = _convert_records(rates_1h)
        list_1m = _convert_records(rates_1m) if rates_1m is not None else []
        list_1d = _convert_records(rates_1d) if rates_1d is not None else []

        offset_sec = self.engine.get_broker_utc_offset() if hasattr(self.engine, 'get_broker_utc_offset') else 7200

        for b in list_5m:
            b['_utc_dt'] = datetime.datetime.fromtimestamp(b['time'] - offset_sec, datetime.timezone.utc)

        cur_dt = list_5m[-1]['_utc_dt']
        current_bid = list_5m[-1]['close']

        is_fx = "GBP" in symbol.upper() or "EUR" in symbol.upper()
        is_index = any(k in symbol.upper() for k in ("NQ", "NAS", "US100", "SPX", "YM", "US30"))
        pip_size = 0.00010 if is_fx else (1.0 if is_index else 0.10)
        min_sweep_pips = 1.0 if is_fx else (5.0 if is_index else 2.0)

        # Check Intermarket SMT Divergence for Gold vs Silver (SETUP-ARCH-005/007)
        smt_info = None
        if "XAU" in symbol.upper():
            try:
                res_silver = self.engine.resolve_symbol("XAGUSD")
                if res_silver:
                    rates_s = mt5.copy_rates_from_pos(res_silver, mt5.TIMEFRAME_M5, 0, 240)
                    if rates_s is not None and len(rates_s) >= 40:
                        list_5m_s = _convert_records(rates_s)
                        from hitl.backtest.metals_smt import detect_metals_smt_divergence
                        smt_info = detect_metals_smt_divergence(list_5m, list_5m_s, cur_dt.hour)
            except Exception as e:
                print(f"[LiveRadar] Metals SMT check error: {e}")

        # Execute institutional screener directly on closed bars
        from hitl.backtest.fast_screener import screen_ict_session
        from hitl.screener_gate import tehran_hour_from_bar_time

        try:
            screener_result = screen_ict_session(
                bars_5m=list_5m,
                bars_1h=list_1h,
                symbol=symbol,
                session_hour=tehran_hour_from_bar_time(list_5m[-1]["time"]),
                smt_info=smt_info,
                bars_1m=list_1m,
                bars_1d=list_1d,
                closed_bars_only=True
            )
        except Exception as e:
            print(f"[LiveRadar] screen_ict_session error for {symbol}: {e}")
            screener_result = None

        if not screener_result or not screener_result.get("has_setup"):
            return None

        side = screener_result.get("direction", "BUY")
        extreme_val = screener_result.get("sweep_extreme", list_5m[-2]["high"] if side == "SELL" else list_5m[-2]["low"])

        # Check Cooldown & Extreme Progression per (symbol, side)
        now_ts = time.time()
        last_t = self.last_trigger_times.get((symbol, side), 0.0)
        last_ext = self.last_sweep_extremes.get((symbol, side), 0.0)

        # Allow re-trigger only if cooldown elapsed OR new deeper extreme printed
        if now_ts - last_t < self.cooldown_seconds:
            if side == "SELL" and extreme_val <= last_ext + (min_sweep_pips * pip_size):
                return None
            if side == "BUY" and (last_ext != 0.0 and extreme_val >= last_ext - (min_sweep_pips * pip_size)):
                return None

        setup_type = screener_result.get("setup_type", f"{side}_SETUP")
        if smt_info and smt_info.get("has_smt"):
            smt_type = smt_info.get("smt_type", "")
            if "BEARISH" in smt_type and side == "SELL":
                setup_type = f"[SETUP-ARCH-007] Bearish Intermarket SMT Displacement ({setup_type})"
            elif "BULLISH" in smt_type and side == "BUY":
                setup_type = f"[SETUP-ARCH-005] Bullish Intermarket SMT Accumulation ({setup_type})"

        return {
            "symbol": symbol,
            "resolved_symbol": resolved,
            "side": side,
            "setup_type": setup_type,
            "archetype_id": screener_result.get("archetype_id"),
            "entry_ref": screener_result.get("entry_price"),
            "sl_ref": screener_result.get("sl_price"),
            "recommended_target_rr": screener_result.get("recommended_target_rr"),
            "recommended_be_rr": screener_result.get("recommended_be_rr"),
            "swept_target": screener_result.get("swept_target", setup_type),
            "sweep_extreme": extreme_val,
            "sweep_delta_pips": screener_result.get("sweep_delta_pips", 0.0),
            "current_price": current_bid,
            "timestamp_utc": cur_dt,
            "smt_info": smt_info,
            "screener_result": screener_result
        }

    def trigger_autonomous_pipeline(self, setup: Dict[str, Any]):
        """
        Executes streamlined autonomous workflow in background thread:
        1. Silently prepares 4-timeframe charts and merges into single 2x2 grid image.
        2. Convenes Tactical Council (Seats 1, 4, 5, 6) under pre-locked Tier 1 Macro.
        3. If Approved: Sends exactly ONE photo message with 5-line ticket and buttons.
        4. If Stand Aside: Sends a quiet 2-line flash note (zero chart clutter).
        """
        sym = setup["symbol"]
        side = setup.get("side", "BUY" if "BULLISH" in setup["setup_type"] else "SELL")
        is_fx = "GBP" in sym.upper() or "EUR" in sym.upper()
        sym_icon = "💷" if "GBP" in sym.upper() else ("💶" if "EUR" in sym.upper() else "🥇")
        pips_unit = "pips" if is_fx else "pts"

        chat_id = TELEGRAM_CHAT_ID
        if not chat_id:
            print("[LiveRadar] Missing TELEGRAM_CHAT_ID. Cannot alert.")
            return

        # Record cooldown per (symbol, side) IMMEDIATELY to prevent duplicate trigger loops
        self.last_trigger_times[(sym, side)] = time.time()
        self.last_sweep_extremes[(sym, side)] = setup["sweep_extreme"]

        print(f"[LiveRadar] 🚨 TRIGGERED: {sym} | {setup['setup_type']} | Sweep: {setup['swept_target']} (+{setup['sweep_delta_pips']} {pips_unit})")

        # 1. Silently Prepare 4-TF Candlestick Charts & Merged 2x2 Grid Image
        out_dir = BASE_DIR / "analysis_assets" / "mtf"
        out_dir.mkdir(parents=True, exist_ok=True)
        p_1d = out_dir / f"{sym}_1D.png"
        p_1h = out_dir / f"{sym}_1H.png"
        p_15m = out_dir / f"{sym}_15M.png"
        p_5m = out_dir / f"{sym}_5M.png"
        p_grid = out_dir / f"{sym}_MTF_GRID.png"

        r1d = r1h = r5m = None
        try:
            engine = MT5Engine()
            res = engine.resolve_symbol(sym)
            if engine.ensure_connected() and res:
                r1d = _convert_records(mt5.copy_rates_from_pos(res, mt5.TIMEFRAME_D1, 0, 90))
                r1h = _convert_records(mt5.copy_rates_from_pos(res, mt5.TIMEFRAME_H1, 0, 80))
                r15m = _convert_records(mt5.copy_rates_from_pos(res, mt5.TIMEFRAME_M15, 0, 60))
                r5m = _convert_records(mt5.copy_rates_from_pos(res, mt5.TIMEFRAME_M5, 0, 60))
                r5m_full = _convert_records(mt5.copy_rates_from_pos(res, mt5.TIMEFRAME_M5, 0, 200))
                landmarks = extract_chart_landmarks(sym, r1d, r5m_full)

                render_candlestick_chart(r1d, sym, "1D", p_1d)
                render_candlestick_chart(r1h, sym, "1H", p_1h, horizontal_levels=landmarks)
                render_candlestick_chart(r15m, sym, "15M", p_15m, horizontal_levels=landmarks)
                render_candlestick_chart(r5m, sym, "5M", p_5m, horizontal_levels=landmarks)

                # Combine into a single clean 2x2 grid image
                create_mtf_grid_image(p_1d, p_1h, p_15m, p_5m, p_grid)
        except Exception as e:
            print(f"[LiveRadar] Chart generation error: {e}")

        # Screener gate: use pre-screened setup or run screen_ict_session on full closed bars
        screener = setup.get("screener_result")
        if not screener and r5m_full and r1h:
            try:
                from hitl.backtest.fast_screener import screen_ict_session
                from hitl.screener_gate import tehran_hour_from_bar_time
                screener = screen_ict_session(
                    bars_5m=r5m_full,
                    bars_1h=r1h,
                    symbol=sym,
                    session_hour=tehran_hour_from_bar_time(r5m_full[-1]["time"]),
                    bars_1d=r1d,
                    closed_bars_only=True,
                )
            except Exception as e:
                print(f"[LiveRadar] Screener gate error: {e}")
                screener = None
        if not screener or not screener.get("has_setup"):
            veto = (screener or {}).get("reason", "live bars unavailable for screening")
            print(f"[LiveRadar] Screener veto for {sym}: {veto} (silent background log)")
            try:
                from hitl.council_decisions import log_council_decision
                log_council_decision(
                    symbol=sym,
                    decision="STAND_ASIDE",
                    reason=f"Screener veto (closed bars): {veto}",
                    full_report="",
                    plan=None,
                    sweep_target=setup.get("swept_target"),
                    sweep_extreme=setup.get("sweep_extreme"),
                    screener=screener,
                    parse_status="SCREENER_VETO",
                )
            except Exception as log_err:
                print(f"[LiveRadar] Decision logging error: {log_err}")
            return

        # 2. Convene Tactical Council (Tier 2 Execution Strike Team)
        try:
            dossier = assemble_council_intelligence(sym)
            if not dossier:
                print(f"[LiveRadar] Failed to assemble intelligence for {sym}")
                return

            report = convene_investment_council(sym, mode="tactical", screener_result=screener)
            if not report:
                print(f"[LiveRadar] Council failed to convene for {sym}")
                return

            print(f"[LiveRadar] Council deliberation received ({len(report)} chars). Evaluating order plan...")

            # Extract order plan from dossier landmarks & report
            landmarks = dossier.get("landmarks")
            macro_filter = dossier.get("macro_bias_data", {}).get("execution_filter", "")

            from hitl.council import parse_council_decision_detailed
            decision, parse_status = parse_council_decision_detailed(report)

            plan = None
            reason = ""
            if decision != "STAND_ASIDE" and landmarks:
                plan, reason = build_validated_order_plan(
                    decision=decision,
                    poi_selection="PROXIMAL_EDGE",
                    landmarks=landmarks,
                    macro_filter=macro_filter,
                    entry_ref=setup.get("entry_ref"),
                    sl_ref=setup.get("sl_ref"),
                    recommended_target_rr=setup.get("recommended_target_rr"),
                    archetype_id=setup.get("archetype_id")
                )

            # Record cooldown per (symbol, side)
            self.last_trigger_times[(sym, side)] = time.time()
            self.last_sweep_extremes[(sym, side)] = setup["sweep_extreme"]

            fmt = ".5f" if is_fx else ".2f"

            # 3. Streamlined Single-Message Telegram Dispatch (100% English)
            if plan and plan.get("entry") and plan.get("sl") and plan.get("tp"):
                from hitl.backtest.session_clock import get_active_session_status
                from hitl.backtest.evaluator import get_optimal_trade_management
                _, _, sess_key = get_active_session_status()
                target_rr_cap, breakeven_rr = get_optimal_trade_management(sym, sess_key, setup_arch_id=setup.get("archetype_id"))
                if setup.get("recommended_be_rr"):
                    breakeven_rr = setup["recommended_be_rr"]

                # Cap Take Profit target to empirical optimal ceiling if not using archetype calibrated RR
                initial_rr = plan.get("rr", 3.0)
                if not setup.get("recommended_target_rr") and initial_rr > target_rr_cap:
                    risk_dist = abs(plan["entry"] - plan["sl"])
                    if "BUY" in decision:
                        capped_tp = plan["entry"] + (risk_dist * target_rr_cap)
                    else:
                        capped_tp = plan["entry"] - (risk_dist * target_rr_cap)
                    plan["tp"] = round(capped_tp, 5 if is_fx else 2)
                    plan["rr"] = target_rr_cap

                plan_id = f"PLN-{sym}-{int(time.time())}"
                risk_usd = plan.get("risk_usd")
                if not risk_usd or risk_usd <= 0:
                    native_risk = self.engine.calculate_risk_usd(setup["resolved_symbol"], decision, plan["entry"], plan["sl"], 0.01)
                    risk_usd = native_risk if native_risk is not None else (plan["risk_pips"] * 0.1 if is_fx else plan["risk_pips"] * 1.0)
                order_lbl = decision.replace("_", " ")

                # Extract concise final verdict
                m_exec = re.search(r'(?i)Executive Summary & Critical Trigger[:\* ]+\s*(.+)', report)
                if m_exec:
                    clean_verdict = m_exec.group(1).strip().split('\n')[0].strip()
                    clean_verdict = re.sub(r'^[•\*\-\s]+', '', clean_verdict)
                else:
                    clean_verdict = f"Confirmed {decision.replace('_', ' ')} anchored at FVG proximal edge targeting opposing weak liquidity."

                risk_str = f"{plan['risk_pips']:.1f} {pips_unit} | ${risk_usd:.2f}"
                is_demo = self.engine.is_demo_account()

                be_str = f"🛡️ *Breakeven:* Auto-secured at `+{breakeven_rr:.1f}R`\n" if breakeven_rr else "🛡️ *Breakeven:* Off (Runner mode)\n"
                smt_str = f"🔗 *Intermarket SMT:* {setup['smt_info']['summary']}\n" if setup.get('smt_info') and setup['smt_info'].get('has_smt') else ""

                if is_demo:
                    # Autonomous Demo Execution: Council has free will, no approval needed
                    success, feedback, ticket = self.engine.place_limit_order(
                        symbol=setup["resolved_symbol"],
                        order_type_str=decision,
                        price=plan["entry"],
                        sl=plan["sl"],
                        tp=plan["tp"],
                        lot=0.01,
                        is_autonomous=True
                    )

                    if success and ticket:
                        try:
                            from hitl.watchdog import register_order_metadata
                            register_order_metadata(ticket, {
                                "symbol": sym,
                                "archetype_id": plan.get("archetype_id", setup.get("archetype_id")),
                                "be_rr": breakeven_rr,
                                "target_rr": plan.get("rr"),
                                "ttl_minutes": 60,
                                "created_at": time.time()
                            })
                        except Exception as e:
                            print(f"[LiveRadar] Failed to register order metadata: {e}")

                    PENDING_EXECUTION_PLANS[plan_id] = {
                        "symbol": setup["resolved_symbol"],
                        "clean_sym": sym,
                        "type": decision,
                        "entry": plan["entry"],
                        "sl": plan["sl"],
                        "tp": plan["tp"],
                        "lot": 0.01,
                        "rr": plan["rr"],
                        "breakeven_rr": breakeven_rr,
                        "session_key": sess_key,
                        "risk_usd": risk_usd,
                        "archetype_id": plan.get("archetype_id", setup.get("archetype_id", "DISCRETIONARY_SMC")),
                        "ticket": ticket if success else None,
                        "full_report": report,
                        "created_at": time.time()
                    }

                    if success:
                        auto_status = f"🚀 *[AUTONOMOUS DEMO EXECUTION · Ticket #{ticket}]*"
                        buttons = {
                            "inline_keyboard": [
                                [
                                    {"text": f"❌ Cancel Order #{ticket}", "callback_data": f"cancel_{ticket}"},
                                    {"text": "📜 View Deliberation", "callback_data": f"show_report_{plan_id}"}
                                ]
                            ]
                        }
                    else:
                        auto_status = f"⚠️ *[AUTONOMOUS DEMO ATTEMPT FAILED: {feedback}]*"
                        buttons = {
                            "inline_keyboard": [
                                [
                                    {"text": "📜 View Deliberation", "callback_data": f"show_report_{plan_id}"}
                                ]
                            ]
                        }

                    ticket_caption = (
                        f"{auto_status}\n"
                        f"🏛️ *Council Free-Will Order Placed in MT5 Demo*\n\n"
                        f"⚡ *{sym_icon} {sym} · {order_lbl}*\n"
                        f"📍 *Entry:* `{plan['entry']:{fmt}}`\n"
                        f"🛑 *SL:*    `{plan['sl']:{fmt}}` ({risk_str})\n"
                        f"🎯 *TP:*    `{plan['tp']:{fmt}}` (R:R: *1:{plan['rr']:.2f}* [Capped])\n"
                        f"{be_str}"
                        f"{smt_str}"
                        f"💡 *Hunt:*  `{setup['swept_target']}` (+{setup['sweep_delta_pips']} {pips_unit})\n"
                        f"⚖️ *Lot:*   `0.01`\n"
                        f"✅ *Final Verdict:* {clean_verdict}\n\n"
                        f"🛡️ *Velocity Guard Active:* Auto-cancels if adverse momentum triggers."
                    )
                else:
                    # Live Real Account: Strict Seat #7 Human Approval Required
                    PENDING_EXECUTION_PLANS[plan_id] = {
                        "symbol": setup["resolved_symbol"],
                        "clean_sym": sym,
                        "type": decision,
                        "entry": plan["entry"],
                        "sl": plan["sl"],
                        "tp": plan["tp"],
                        "lot": 0.01,
                        "rr": plan["rr"],
                        "breakeven_rr": breakeven_rr,
                        "session_key": sess_key,
                        "risk_usd": risk_usd,
                        "archetype_id": plan.get("archetype_id", setup.get("archetype_id", "DISCRETIONARY_SMC")),
                        "full_report": report,
                        "created_at": time.time()
                    }

                    buttons = {
                        "inline_keyboard": [
                            [
                                {"text": f"🚀 Approve & Place {decision.replace('_', ' ')}", "callback_data": f"exec_plan_{plan_id}"},
                                {"text": "🛡️ Veto / Stand Aside", "callback_data": f"veto_plan_{plan_id}"}
                            ],
                            [
                                {"text": "📜 View Full Deliberation", "callback_data": f"show_report_{plan_id}"}
                            ]
                        ]
                    }

                    trend_badge = ""
                    try:
                        from hitl.trend.trend_oracle import trend_oracle
                        fc = trend_oracle.get_forecast(symbol=sym, force_refresh=False)
                        day_bias = fc.get("horizons", {}).get("day", {}).get("bias", "")
                        day_conf = int(fc.get("horizons", {}).get("day", {}).get("confidence", 0.0) * 100)
                        tm = fc.get("trade_management", {})
                        if day_bias:
                            t_icon = "🟢" if day_bias == "BULLISH" else ("🔴" if day_bias == "BEARISH" else "🟡")
                            is_aligned = (setup['side'] == 'BUY' and day_bias == 'BULLISH') or (setup['side'] == 'SELL' and day_bias == 'BEARISH')
                            is_counter = (setup['side'] == 'BUY' and day_bias == 'BEARISH') or (setup['side'] == 'SELL' and day_bias == 'BULLISH')

                            if is_aligned:
                                pol = tm.get("aligned", {"tp_r": 3.5, "be_ratchet_r": 1.5})
                                regime_lbl = f"Trend-Aligned [TP: {pol['tp_r']:.1f}R | BE: {pol['be_ratchet_r']:.1f}R]"
                            elif is_counter:
                                pol = tm.get("counter", {"tp_r": 1.5, "be_ratchet_r": 1.0})
                                regime_lbl = f"Counter-Fade [TP: {pol['tp_r']:.1f}R | BE: {pol['be_ratchet_r']:.1f}R]"
                            else:
                                pol = tm.get("sideways", {"tp_r": 3.5, "be_ratchet_r": 1.0})
                                regime_lbl = f"Range Fade [TP: {pol['tp_r']:.1f}R | BE: {pol['be_ratchet_r']:.1f}R]"

                            trend_badge = f"🔮 *Trend Oracle:* {t_icon} {day_bias} (`{day_conf}%`) · _{regime_lbl}_\n"
                    except Exception:
                        pass

                    ticket_caption = (
                        f"⚡ *{sym_icon} {sym} · {order_lbl}*\n\n"
                        f"📍 *Entry:* `{plan['entry']:{fmt}}`\n"
                        f"🛑 *SL:*    `{plan['sl']:{fmt}}` ({risk_str})\n"
                        f"🎯 *TP:*    `{plan['tp']:{fmt}}` (R:R: *1:{plan['rr']:.2f}* [Capped])\n"
                        f"{be_str}"
                        f"{smt_str}"
                        f"{trend_badge}"
                        f"💡 *Hunt:*  `{setup['swept_target']}` (+{setup['sweep_delta_pips']} {pips_unit})\n"
                        f"⚖️ *Lot:*   `0.01`\n"
                        f"✅ *Final Verdict:* {clean_verdict}"
                    )

                # Send exactly ONE photo message with the combined 2x2 grid chart
                if p_grid.exists():
                    self.client.send_photo(chat_id, photo_path=str(p_grid), caption=ticket_caption, reply_markup=buttons)
                else:
                    self.client.send_message(chat_id, ticket_caption, reply_markup=buttons)

                # Persist decision to ledger for Review Council
                try:
                    from hitl.council_decisions import log_council_decision
                    log_council_decision(
                        symbol=sym,
                        decision=decision,
                        reason=clean_verdict,
                        full_report=report,
                        plan=plan,
                        sweep_target=setup.get("swept_target"),
                        sweep_extreme=setup.get("sweep_extreme"),
                        screener=screener,
                        parse_status=parse_status
                    )
                except Exception as log_err:
                    print(f"[LiveRadar] Decision logging error: {log_err}")

                exec_mode_str = "AUTONOMOUS DEMO" if is_demo else "HITL Approval"
                print(f"[LiveRadar] Dispatched Approved Order Card to Telegram ({exec_mode_str}): {sym} {decision}")

            else:
                # Quiet, zero-clutter 2-line flash note for Stand Aside (no charts sent)
                veto_reason = ""
                if plan is None and reason:
                    if "violates" in reason or "Macro" in reason:
                        veto_reason = f"Macro Filter ({macro_filter}) vetoes counter-trend execution."
                    elif "below mandatory" in reason:
                        veto_reason = "Risk-to-Reward ratio is below mandatory 1:3.0 institutional threshold."
                    elif "exceeds maximum permitted" in reason:
                        veto_reason = "Structural invalidation exceeds strict $12.00 maximum risk ceiling."
                    elif "POIs are at or" in reason:
                        veto_reason = "All Fair Value Gaps are beyond current market price (pending limit impossible without chasing)."
                    else:
                        veto_reason = reason.replace("PRE_FLIGHT_REJECTION: ", "").strip()

                if not veto_reason:
                    m_exec = re.search(r'(?i)Executive Summary & Critical Trigger[:\* ]+\s*(.+)', report)
                    if m_exec:
                        veto_reason = m_exec.group(1).strip().split('\n')[0].strip()
                        veto_reason = re.sub(r'^[•\*\-\s]+', '', veto_reason)
                    else:
                        veto_reason = "Setup vetoed due to structural invalidation or order flow asymmetry."

                cdo_line = ""
                m_cdo = re.search(r'(?i)Actionable [\'"]?IF-THEN[\'"]? Re-Activation Trigger[:\* ]+\s*(.+)', report)
                if m_cdo:
                    trigger_text = m_cdo.group(1).strip().split('\n')[0].strip()
                    trigger_text = re.sub(r'^[•\*\-\s]+', '', trigger_text)
                    if trigger_text and len(trigger_text) > 5:
                        cdo_line = f"\n🔭 *Next Trigger:* {trigger_text}"

                print(f"[LiveRadar] Council Stand Aside for {sym}: {veto_reason} (silent background log)")

                # Persist Stand Aside decision to ledger for Review Council (silent, zero Telegram clutter)
                try:
                    from hitl.council_decisions import log_council_decision
                    log_council_decision(
                        symbol=sym,
                        decision="STAND_ASIDE",
                        reason=veto_reason,
                        full_report=report,
                        plan=None,
                        sweep_target=setup.get("swept_target"),
                        sweep_extreme=setup.get("sweep_extreme"),
                        screener=screener,
                        parse_status=parse_status
                    )
                except Exception as log_err:
                    print(f"[LiveRadar] Decision logging error: {log_err}")

                print(f"[LiveRadar] Logged Stand Aside to ledger: {sym} | Reason: {veto_reason}")

        except Exception as e:
            print(f"[LiveRadar] Pipeline error for {sym}: {e}")

    def poll(self):
        """Called periodically by watchdog/bot loop (e.g. every 15-20 seconds)."""
        # 1. Pure Mathematical Quant Strategy Scanning (Council & Snap Bypassed)
        try:
            if hasattr(self, 'quant_bridge') and self.quant_bridge:
                self.quant_bridge.scan_all()
        except Exception as q_err:
            print(f"[LiveRadar] Quant bridge scan error: {q_err}")

        # 2. Institutional SMC Strategy Scanning (Council Deliberation)
        is_active, session_name = self.is_killzone_active()
        if not is_active:
            return

        if self._is_evaluating:
            return

        for sym in self.target_symbols:
            setup = self.scan_symbol(sym)
            if setup:
                self._is_evaluating = True
                def _worker():
                    try:
                        self.trigger_autonomous_pipeline(setup)
                    finally:
                        self._is_evaluating = False

                t = threading.Thread(target=_worker, daemon=True)
                t.start()
                break # Process one symbol at a time to prevent concurrency collisions
