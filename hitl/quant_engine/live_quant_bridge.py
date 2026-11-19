"""
TradingGuard HITL - Live Quantitative Strategy Execution Bridge
Bridges ratified machine-discovered quant strategies into live market scanning.

Strict Operational Policy:
1. Pure Mathematical Execution: Zero Council deliberation and Zero SubQ Snap calls.
2. Account Risk Governor Gating: Strictly enforced via hitl/account_risk_manager.py.
3. Microstructure Precision: Spread buffers, dynamic ATR boundary scaling, and cooldown refractory filters.
"""

import time
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

from hitl.quant_engine.state_space import MathematicalStateSpace
from hitl.quant_engine.rule_engine import QuantRule
from hitl.account_risk_manager import risk_governor
from hitl.config import TELEGRAM_CHAT_ID

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DISCOVERY_DIR = BASE_DIR / "backtest_results" / "quant_discovery"


class LiveQuantBridge:
    """
    Executes live scanning and order placement for ratified quantitative rules.
    Operates without LLM or Vision Council intervention.
    """

    def __init__(self, engine: Any, client: Any):
        self.engine = engine
        self.client = client
        self.state_space = MathematicalStateSpace()
        self.rules_by_symbol: Dict[str, List[QuantRule]] = {}
        self.last_signal_times: Dict[Tuple[str, str], float] = {}
        self.last_signal_bars: Dict[Tuple[str, str], int] = {}
        self.target_symbols = ["XAUUSD", "NQ"]
        self.load_ratified_rules()

    def load_ratified_rules(self) -> None:
        """Loads verified annual multi-season ratified rules from discovery files (Gold and NQ only)."""
        try:
            # 1. BTCUSD: DECOMMISSIONED due to retail CFD turnover commission drag (-$3,268.75 on MT5).
            # 2. GBPUSD: DECOMMISSIONED from Quant (traded strictly under SMC where PF is 1.71 vs 0.91 in Quant).

            # 1. Nasdaq 100 (NQ - Mean Reversion & Volatility Breakout Buyers)
            nq_path = DISCOVERY_DIR / "annual_1year" / "nq" / "annual_ratified_strategies.json"
            if nq_path.exists():
                import json
                with open(nq_path, "r", encoding="utf-8") as f:
                    nq_data = json.load(f)
                # Deduplicated orthogonal rules: R14_011 (mean reversion) and R14_025 (vol compression)
                self.rules_by_symbol["NQ"] = [
                    QuantRule.from_dict(r["rule"]) for r in nq_data if r["rule"]["rule_id"] in ["R14_011", "R14_025"]
                ]

            # 2. XAUUSD (Gold - Dual-Direction Momentum & Orderflow)
            xau_path = DISCOVERY_DIR / "annual_1year" / "xauusd" / "annual_ratified_strategies.json"
            if xau_path.exists():
                import json
                with open(xau_path, "r", encoding="utf-8") as f:
                    xau_data = json.load(f)
                # Deduplicated orthogonal rules: R15_048 (velocity breakout), R14_058 (orderflow volume imbalance), R15_023 (autocorrelation momentum)
                self.rules_by_symbol["XAUUSD"] = [
                    QuantRule.from_dict(r["rule"]) for r in xau_data if r["rule"]["rule_id"] in ["R15_048", "R14_058", "R15_023"]
                ]
            else:
                legacy_xau = DISCOVERY_DIR / "xauusd" / "ratified_quant_strategies.json"
                if legacy_xau.exists():
                    import json
                    with open(legacy_xau, "r", encoding="utf-8") as f:
                        xau_data = json.load(f)
                    self.rules_by_symbol["XAUUSD"] = [
                        QuantRule.from_dict(r["rule"]) for r in xau_data if r["rule"]["rule_id"] in ["R2_020"]
                    ]

            total_rules = sum(len(r) for r in self.rules_by_symbol.values())
            print(f"[LiveQuantBridge] Loaded {total_rules} ratified quant rules across {len(self.rules_by_symbol)} symbols.")
        except Exception as e:
            print(f"[LiveQuantBridge] Error loading ratified rules: {e}")

    def _calculate_quant_lot(self, resolved_sym: str, order_type_str: str, entry: float, sl: float, target_risk_usd: float = 12.0) -> Tuple[float, float]:
        """Calculates optimal lot size clamped to broker limits targeting exact risk."""
        base_risk = self.engine.calculate_risk_usd(resolved_sym, order_type_str, entry, sl, 0.01)
        sym_info = mt5.symbol_info(resolved_sym)
        min_lot = getattr(sym_info, 'volume_min', 0.01) if sym_info else 0.01
        max_lot = getattr(sym_info, 'volume_max', 1.00) if sym_info else 1.00
        step_lot = getattr(sym_info, 'volume_step', 0.01) if sym_info else 0.01

        if base_risk and base_risk > 0:
            calc_lot = 0.01 * (target_risk_usd / base_risk)
            lot = max(min_lot, min(calc_lot, max_lot))
            lot = round(round(lot / step_lot) * step_lot, 2)
            # Recalculate true risk
            real_risk = self.engine.calculate_risk_usd(resolved_sym, order_type_str, entry, sl, lot)
            # If rounding pushed risk above ceiling, step down one increment
            while real_risk and real_risk > target_risk_usd and lot > min_lot:
                lot = round(lot - step_lot, 2)
                real_risk = self.engine.calculate_risk_usd(resolved_sym, order_type_str, entry, sl, lot)
            return lot, round(real_risk or target_risk_usd, 2)
        return min_lot, 10.0

    def scan_symbol(self, clean_sym: str) -> Optional[Dict[str, Any]]:
        """
        Fetches M5 bars, computes 33-dim state space, and evaluates predicates for clean_sym.
        """
        if clean_sym not in self.rules_by_symbol or not self.rules_by_symbol[clean_sym]:
            return None

        if not self.engine.ensure_connected():
            return None

        # 1. Gate strictly by session hours (Tehran 11:30 - 21:00)
        in_session, _ = self.engine.is_within_session_hours(clean_sym)
        if not in_session:
            return None

        resolved = self.engine.resolve_symbol(clean_sym)
        if not resolved:
            return None

        # 2. Duplicate Exposure Check: Stand aside if open position or pending order exists on symbol
        open_pos = self.engine.get_open_positions()
        pending_ords = self.engine.get_pending_orders()
        if any(p.get("symbol") == resolved for p in open_pos) or any(o.get("symbol") == resolved for o in pending_ords):
            return None

        # Fetch last 120 M5 bars (sufficient for 55-period velocity and 100-period z-score)
        rates = mt5.copy_rates_from_pos(resolved, mt5.TIMEFRAME_M5, 0, 120)
        if rates is None or len(rates) < 110:
            return None

        df_raw = pd.DataFrame(rates)
        try:
            st_df = self.state_space.transform(df_raw)
        except Exception as e:
            print(f"[LiveQuantBridge] State space calculation error for {clean_sym}: {e}")
            return None

        # Evaluate on the last closed bar to ensure zero lookahead bias
        closed_bar = st_df.iloc[-2]
        bar_time = int(closed_bar["time"])

        tick = mt5.symbol_info_tick(resolved)
        sym_info = mt5.symbol_info(resolved)
        if not tick or not sym_info:
            return None

        digits = sym_info.digits
        spread = tick.ask - tick.bid

        atr = float(closed_bar["atr_raw"])
        if atr <= 0:
            return None

        for rule in self.rules_by_symbol[clean_sym]:
            rule_key = (clean_sym, rule.rule_id)

            # Check cooldown against duplicate firing on same bar or refractory window
            last_time = self.last_signal_times.get(rule_key, 0.0)
            last_bar_time = self.last_signal_bars.get(rule_key, 0)
            if bar_time <= last_bar_time or (time.time() - last_time) < (rule.cooldown_bars * 300):
                continue

            # Evaluate predicates
            all_passed = True
            for pred in rule.predicates:
                try:
                    s_val = pred.evaluate(st_df)
                    if not s_val.iloc[-2]:
                        all_passed = False
                        break
                except Exception:
                    all_passed = False
                    break

            if not all_passed:
                continue

            # Signal Confirmed!
            is_buy = (rule.direction.upper() == "BUY")
            order_type_str = "BUY_LIMIT" if is_buy else "SELL_LIMIT"

            point = sym_info.point
            stops_level = getattr(sym_info, 'stops_level', 0) * point
            min_offset = max(stops_level, point)

            # Anchor limit entry right at market boundary (matching next-bar open fill physics)
            if is_buy:
                entry = round(tick.bid - min_offset, digits)
                sl = round(entry - (rule.sl_atr_mult * atr), digits)
                tp = round(entry + (rule.tp_atr_mult * atr), digits)
            else:
                entry = round(tick.ask + min_offset, digits)
                sl = round(entry + (rule.sl_atr_mult * atr), digits)
                tp = round(entry - (rule.tp_atr_mult * atr), digits)

            # Calculate dynamic lot size targeting firm $12.00 risk
            lot, risk_usd = self._calculate_quant_lot(resolved, order_type_str, entry, sl, target_risk_usd=12.0)

            # 3. Gate strictly via Account Profile & Prop Firm Risk Governor
            gov_ok, gov_msg, metrics = risk_governor.evaluate_order_feasibility(
                symbol=resolved,
                order_type_str=order_type_str,
                price=entry,
                sl=sl,
                tp=tp,
                lot=lot,
                risk_usd=risk_usd,
                engine=self.engine
            )

            if not gov_ok:
                print(f"[LiveQuantBridge] {clean_sym} {rule.rule_id} blocked by Risk Governor: {gov_msg[:80]}")
                continue

            # Record signal time to prevent double firing
            self.last_signal_times[rule_key] = time.time()
            self.last_signal_bars[rule_key] = bar_time

            rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 2.5
            sym_icon = "🪙" if "BTC" in clean_sym else ("💻" if "NQ" in clean_sym else ("💷" if "GBP" in clean_sym else "🥇"))

            signal_payload = {
                "symbol": clean_sym,
                "resolved_symbol": resolved,
                "rule_id": rule.rule_id,
                "direction": rule.direction,
                "order_type": order_type_str,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "lot": lot,
                "rr": round(rr, 2),
                "risk_usd": round(risk_usd, 2),
                "be_rr": getattr(rule, 'be_ratchet_r', 2.0),
                "ttl_minutes": getattr(rule, 'ttl_bars', 24) * 5,
                "predicates_str": ", ".join(str(p) for p in rule.predicates),
                "sym_icon": sym_icon,
                "digits": digits,
                "gov_metrics": metrics
            }

            self.dispatch_quant_order(signal_payload)
            return signal_payload

        return None

    def dispatch_quant_order(self, payload: Dict[str, Any]) -> None:
        """
        Dispatches verified quant order directly without Council or Snap intervention.
        """
        chat_id = TELEGRAM_CHAT_ID
        if not chat_id:
            return

        is_demo = self.engine.is_demo_account()
        sym = payload["symbol"]
        order_lbl = payload["order_type"].replace("_", " ")
        fmt = f".{payload['digits']}f"

        if is_demo:
            # Autonomous execution on Demo account
            success, feedback, ticket = self.engine.place_limit_order(
                symbol=payload["resolved_symbol"],
                order_type_str=payload["order_type"],
                price=payload["entry"],
                sl=payload["sl"],
                tp=payload["tp"],
                lot=payload["lot"],
                is_autonomous=True
            )

            if success:
                try:
                    from hitl.watchdog import register_order_metadata
                    register_order_metadata(ticket, {
                        "symbol": sym,
                        "archetype_id": f"QUANT_{payload['rule_id']}",
                        "be_rr": payload.get("be_rr", 2.0),
                        "target_rr": payload["rr"],
                        "ttl_minutes": payload.get("ttl_minutes", 120),
                        "created_at": time.time()
                    })
                except Exception:
                    pass
                card = (
                    f"🤖 *[AUTONOMOUS QUANT EXECUTION · Ticket #{ticket}]*\n"
                    f"⚡ *Pure Mathematical Execution (Council & Snap Bypassed)*\n\n"
                    f"📊 *{payload['sym_icon']} {sym} · {order_lbl}*\n"
                    f"📐 *Rule:* `{payload['rule_id']}`\n"
                    f"📍 *Entry:* `{payload['entry']:{fmt}}`\n"
                    f"🛑 *SL:*    `{payload['sl']:{fmt}}` (${payload['risk_usd']:.2f})\n"
                    f"🎯 *TP:*    `{payload['tp']:{fmt}}` (R:R: *1:{payload['rr']:.2f}*)\n"
                    f"⚖️ *Lot:*   `{payload['lot']}`\n\n"
                    f"🔬 *Predicates:* `{payload['predicates_str']}`\n"
                    f"🛡️ *Risk Governor:* `{risk_governor.mode}` "
                    f"(Open: {payload['gov_metrics']['open_trades']}/{payload['gov_metrics']['max_open_trades']} | "
                    f"Risk: {payload['gov_metrics']['projected_risk_pct']:.1f}%/{payload['gov_metrics']['max_concurrent_risk_pct']:.1f}%)\n\n"
                    f"🛡️ *Velocity Guard Active:* Auto-cancels on adverse momentum spike."
                )
                buttons = {
                    "inline_keyboard": [
                        [{"text": f"❌ Cancel Order #{ticket}", "callback_data": f"cancel_{ticket}"}]
                    ]
                }
                self.client.send_message(chat_id, card, reply_markup=buttons)
                print(f"[LiveQuantBridge] Placed Autonomous Quant Order #{ticket} on {sym} ({payload['rule_id']})")
            else:
                self.client.send_message(
                    chat_id,
                    f"⚠️ *[QUANT EXECUTION ATTEMPT FAILED]*\n"
                    f"Symbol: `{sym}` | Rule: `{payload['rule_id']}`\n"
                    f"Reason: {feedback}"
                )
        else:
            # Live Real Account: Immediate Action Card with Approve/Veto buttons
            from hitl.live_radar import PENDING_EXECUTION_PLANS
            plan_id = f"quant_{sym}_{int(time.time())}"
            PENDING_EXECUTION_PLANS[plan_id] = {
                "symbol": payload["resolved_symbol"],
                "clean_sym": sym,
                "type": payload["order_type"],
                "entry": payload["entry"],
                "sl": payload["sl"],
                "tp": payload["tp"],
                "lot": payload["lot"],
                "rr": payload["rr"],
                "risk_usd": payload["risk_usd"],
                "rule_id": payload["rule_id"],
                "is_quant": True,
                "created_at": time.time()
            }

            card = (
                f"🤖 *[QUANT STATISTICAL SIGNAL · ACTION REQUIRED]*\n"
                f"⚡ *Pure Mathematical Setup (Council & Snap Bypassed)*\n\n"
                f"📊 *{payload['sym_icon']} {sym} · {order_lbl}*\n"
                f"📐 *Rule:* `{payload['rule_id']}`\n"
                f"📍 *Entry:* `{payload['entry']:{fmt}}`\n"
                f"🛑 *SL:*    `{payload['sl']:{fmt}}` (${payload['risk_usd']:.2f})\n"
                f"🎯 *TP:*    `{payload['tp']:{fmt}}` (R:R: *1:{payload['rr']:.2f}*)\n"
                f"⚖️ *Lot:*   `{payload['lot']}`\n\n"
                f"🔬 *Predicates:* `{payload['predicates_str']}`\n"
                f"🛡️ *Risk Governor:* `{risk_governor.mode}` "
                f"(Open: {payload['gov_metrics']['open_trades']}/{payload['gov_metrics']['max_open_trades']} | "
                f"Risk: {payload['gov_metrics']['projected_risk_pct']:.1f}%/{payload['gov_metrics']['max_concurrent_risk_pct']:.1f}%)"
            )
            buttons = {
                "inline_keyboard": [
                    [
                        {"text": f"🚀 Approve & Place {order_lbl}", "callback_data": f"exec_plan_{plan_id}"},
                        {"text": "🛡️ Veto / Stand Aside", "callback_data": f"veto_plan_{plan_id}"}
                    ]
                ]
            }
            self.client.send_message(chat_id, card, reply_markup=buttons)

    def scan_all(self) -> None:
        """Iterates through target assets and evaluates mathematical signals."""
        for sym in self.target_symbols:
            try:
                self.scan_symbol(sym)
            except Exception as e:
                print(f"[LiveQuantBridge] Exception scanning {sym}: {e}")
