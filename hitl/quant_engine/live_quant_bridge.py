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
        self.target_symbols = ["BTCUSD", "NQ", "GBPUSD", "XAUUSD"]
        self.load_ratified_rules()

    def load_ratified_rules(self) -> None:
        """Loads verified annual multi-season ratified rules from discovery files."""
        try:
            # 1. BTCUSD
            btc_path = DISCOVERY_DIR / "annual_1year" / "btcusd" / "annual_ratified_strategies.json"
            if btc_path.exists():
                import json
                with open(btc_path, "r", encoding="utf-8") as f:
                    btc_data = json.load(f)
                self.rules_by_symbol["BTCUSD"] = [
                    QuantRule.from_dict(r["rule"]) for r in btc_data if r["rule"]["rule_id"] in ["R14_015", "R14_010"]
                ]

            # 2. Nasdaq 100 (NQ)
            nq_path = DISCOVERY_DIR / "annual_1year" / "nq" / "annual_ratified_strategies.json"
            if nq_path.exists():
                import json
                with open(nq_path, "r", encoding="utf-8") as f:
                    nq_data = json.load(f)
                self.rules_by_symbol["NQ"] = [
                    QuantRule.from_dict(r["rule"]) for r in nq_data if r["rule"]["rule_id"] in ["R14_041", "R14_031"]
                ]

            # 3. GBPUSD (Cable)
            gbp_path = DISCOVERY_DIR / "annual_1year" / "gbpusd" / "annual_ratified_strategies.json"
            if gbp_path.exists():
                import json
                with open(gbp_path, "r", encoding="utf-8") as f:
                    gbp_data = json.load(f)
                self.rules_by_symbol["GBPUSD"] = [
                    QuantRule.from_dict(r["rule"]) for r in gbp_data if r["rule"]["rule_id"] in ["R14_027", "R12_019"]
                ]

            # 4. XAUUSD (Gold)
            xau_path = DISCOVERY_DIR / "xauusd" / "ratified_quant_strategies.json"
            if xau_path.exists():
                import json
                with open(xau_path, "r", encoding="utf-8") as f:
                    xau_data = json.load(f)
                self.rules_by_symbol["XAUUSD"] = [
                    QuantRule.from_dict(r["rule"]) for r in xau_data if r["rule"]["rule_id"] in ["R2_020"]
                ]

            total_rules = sum(len(r) for r in self.rules_by_symbol.values())
            print(f"[LiveQuantBridge] Loaded {total_rules} ratified quant rules across {len(self.rules_by_symbol)} symbols.")
        except Exception as e:
            print(f"[LiveQuantBridge] Error loading ratified rules: {e}")

    def scan_symbol(self, clean_sym: str) -> Optional[Dict[str, Any]]:
        """
        Fetches M5 bars, computes 33-dim state space, and evaluates predicates for clean_sym.
        """
        if clean_sym not in self.rules_by_symbol or not self.rules_by_symbol[clean_sym]:
            return None

        if not self.engine.ensure_connected():
            return None

        resolved = self.engine.resolve_symbol(clean_sym)
        if not resolved:
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
            min_offset = max(getattr(sym_info, 'stops_level', 0) * point, point * 3, 0.5 * spread)

            # Anchor limit entry close to market to ensure fill on proximal touch
            if is_buy:
                # Proximal entry: strictly below ask to form valid BUY LIMIT
                entry = round(tick.ask - min_offset, digits)
                if entry >= tick.ask:
                    entry = round(tick.ask - (point * 3), digits)
                sl = round(entry - (rule.sl_atr_mult * atr), digits)
                tp = round(entry + (rule.tp_atr_mult * atr), digits)
            else:
                # Proximal entry: strictly above bid to form valid SELL LIMIT
                entry = round(tick.bid + min_offset, digits)
                if entry <= tick.bid:
                    entry = round(tick.bid + (point * 3), digits)
                sl = round(entry + (rule.sl_atr_mult * atr), digits)
                tp = round(entry - (rule.tp_atr_mult * atr), digits)

            # Risk USD check
            risk_usd = self.engine.calculate_risk_usd(resolved, order_type_str, entry, sl, 0.01)
            if risk_usd is None or risk_usd <= 0:
                risk_usd = 10.0

            # 1. Gate strictly via Account Profile & Prop Firm Risk Governor
            gov_ok, gov_msg, metrics = risk_governor.evaluate_order_feasibility(
                symbol=resolved,
                order_type_str=order_type_str,
                price=entry,
                sl=sl,
                tp=tp,
                lot=0.01,
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
                "lot": 0.01,
                "rr": round(rr, 2),
                "risk_usd": round(risk_usd, 2),
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
