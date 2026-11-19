"""
TradingGuard HITL - MetaTrader 5 Execution & Risk Engine
Handles native order placement, mathematical risk enforcement ($12 cap),
pending order cancellation, and account queries.
"""

import os
import time
import datetime
import threading
from typing import Optional, Dict, Any, List, Tuple
import MetaTrader5 as mt5
from hitl.config import (
    MAX_RISK_USD,
    BASE_LOT,
    DEFAULT_SYMBOL,
    MAX_DAILY_LOSS_USD,
    MAX_CONSECUTIVE_LOSSES,
    SESSION_START_HOUR,
    SESSION_START_MINUTE,
    SESSION_END_HOUR,
    SESSION_END_MINUTE
)
from hitl.macro_calendar import check_news_danger

_MT5_LOCK = threading.RLock()


class MT5Engine:
    def __init__(self):
        self._connected = False
        self.cooldown_until: float = 0.0
        self.cooldown_reason: str = ""

    def set_cooldown(self, minutes: int, reason: str = ""):
        """Sets an operational cooldown window in minutes."""
        self.cooldown_until = time.time() + (minutes * 60)
        self.cooldown_reason = reason

    def get_cooldown_status(self) -> Tuple[bool, int, str]:
        """Returns (is_active, remaining_minutes, reason)."""
        now = time.time()
        if now < self.cooldown_until:
            rem = int((self.cooldown_until - now) / 60) + 1
            return True, rem, self.cooldown_reason
        return False, 0, ""

    def is_within_session_hours(self, symbol: str) -> Tuple[bool, str]:
        """
        Validates if current time is within active trading session (11:30 - 21:00 Tehran).
        Crypto (BTCUSD) is allowed 24/7.
        Forex and Commodities (Gold) are restricted on weekends and off-session hours.
        """
        now = datetime.datetime.now()
        is_crypto = any(c in symbol.upper() for c in ["BTC", "ETH"])

        if not is_crypto:
            if now.weekday() in (5, 6):
                return False, "Forex and Gold markets are closed on weekends."

            from hitl.backtest.session_clock import get_active_session_status
            is_active, label, sess_key = get_active_session_status()
            if not is_active:
                return False, f"Outside authorized institutional trading session ({label}). Trading during low-liquidity off-hours is prohibited."

        return True, ""

    def ensure_connected(self) -> bool:
        """Initializes connection to the running MT5 terminal if not already connected."""
        if not self._connected:
            terminal_path = r"C:\Program Files\LiteFinance MT5 Terminal\terminal64.exe"
            init_ok = mt5.initialize(path=terminal_path) if os.path.exists(terminal_path) else mt5.initialize()
            if not init_ok:
                print(f"[MT5Engine] Initialization failed: {mt5.last_error()}")
                self._connected = False
                return False
            self._connected = True
        return True

    def get_broker_utc_offset(self) -> int:
        """
        Calculates broker server timezone offset relative to true UTC in seconds.
        E.g., if LiteFinance MT5 is EET (UTC+2), returns 7200.
        """
        if not self.ensure_connected():
            return 7200
        try:
            for sym in ["XAUUSD_o", "GBPUSD_o", "EURUSD_o", "XAUUSD", "GBPUSD"]:
                t = mt5.symbol_info_tick(sym)
                if t and t.time > 0:
                    utc_now = datetime.datetime.now(datetime.timezone.utc).timestamp()
                    return int(round((t.time - utc_now) / 3600.0) * 3600)
        except Exception:
            pass
        return 7200

    def is_demo_account(self) -> bool:
        """Returns True if the connected account is a demo account."""
        if not self.ensure_connected():
            return False
        acc = mt5.account_info()
        if not acc:
            return False
        return acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO or getattr(acc, 'trade_mode', 1) == 0

    def get_account_summary(self) -> Optional[Dict[str, Any]]:
        if not self.ensure_connected():
            return None
        acc = mt5.account_info()
        if not acc:
            return None
        return {
            "login": acc.login,
            "server": acc.server,
            "trade_mode": "DEMO" if acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else "REAL",
            "currency": acc.currency,
            "balance": acc.balance,
            "equity": acc.equity,
            "margin_free": acc.margin_free,
            "profit": acc.profit
        }

    def resolve_symbol(self, symbol: Optional[str] = None) -> Optional[str]:
        """Resolves symbol name, matching broker postfixes like _o."""
        if not self.ensure_connected():
            return None
        sym = symbol or DEFAULT_SYMBOL
        info = mt5.symbol_info(sym)
        if info:
            if not info.visible:
                mt5.symbol_select(sym, True)
            return sym

        # Try appending _o or stripping
        candidates = [sym, f"{sym}_o", sym.replace("_o", "")]
        for c in candidates:
            info = mt5.symbol_info(c)
            if info:
                if not info.visible:
                    mt5.symbol_select(c, True)
                return c
        return None

    def calculate_risk_usd(self, symbol: str, order_type_str: str, entry: float, sl: float, lot: float) -> Optional[float]:
        """Calculates expected dollar loss using native MT5 calculation."""
        if not self.ensure_connected():
            return None

        # Determine direction for calc profit
        is_buy = "BUY" in order_type_str.upper()
        calc_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL

        loss = mt5.order_calc_profit(calc_type, symbol, lot, entry, sl)
        if loss is not None:
            return abs(float(loss))
        return None

    def get_daily_performance(self) -> Dict[str, Any]:
        """Calculates realized PnL, daily loss, and consecutive losses for today."""
        if not self.ensure_connected():
            return {
                "realized_pnl": 0.0,
                "daily_loss": 0.0,
                "consecutive_losses": 0,
                "circuit_tripped": False,
                "reason": ""
            }

        # Resolve broker server time to anchor today's midnight in server time
        server_now = None
        s_tick = mt5.symbol_info_tick(DEFAULT_SYMBOL)
        if s_tick and hasattr(s_tick, 'time') and isinstance(s_tick.time, (int, float)) and s_tick.time > 0:
            server_now = datetime.datetime.fromtimestamp(s_tick.time)
        else:
            server_now = datetime.datetime.now()

        midnight = datetime.datetime(server_now.year, server_now.month, server_now.day, 0, 0, 0)
        deals = mt5.history_deals_get(midnight, server_now + datetime.timedelta(days=1))

        if not deals or not isinstance(deals, (list, tuple)):
            return {
                "realized_pnl": 0.0,
                "daily_loss": 0.0,
                "consecutive_losses": 0,
                "circuit_tripped": False,
                "reason": ""
            }

        total_pnl = sum(d.profit + d.commission + d.swap + d.fee for d in deals)
        daily_loss = abs(total_pnl) if total_pnl < 0 else 0.0

        # Calculate consecutive losses from closed trades
        closed_trades = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
        closed_trades.sort(key=lambda x: x.time, reverse=True)

        consec_losses = 0
        for ct in closed_trades:
            net_ct_pnl = ct.profit + ct.commission + ct.swap + ct.fee
            if net_ct_pnl < 0:
                consec_losses += 1
            else:
                break

        circuit_tripped = False
        reason = ""
        if daily_loss >= MAX_DAILY_LOSS_USD:
            circuit_tripped = True
            reason = f"Daily loss ceiling reached (${daily_loss:.2f} >= ${MAX_DAILY_LOSS_USD:.2f})."
        elif consec_losses >= MAX_CONSECUTIVE_LOSSES:
            circuit_tripped = True
            reason = f"Maximum consecutive losses reached today ({consec_losses} trades)."

        return {
            "realized_pnl": round(total_pnl, 2),
            "daily_loss": round(daily_loss, 2),
            "consecutive_losses": consec_losses,
            "circuit_tripped": circuit_tripped,
            "reason": reason
        }

    def validate_limit_order(
        self,
        symbol: str,
        order_type_str: str,
        price: float,
        sl: float,
        tp: float,
        lot: float = BASE_LOT,
        is_autonomous: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates price sanity, direction constraints, discipline locks, and strict $12 risk cap.
        Returns (is_valid, error_message, details_dict).
        """
        if not self.ensure_connected():
            return False, "Failed to connect to MetaTrader 5.", {}

        # 1. Circuit Breaker Check (Daily loss ceiling & consecutive loss lock)
        perf = self.get_daily_performance()
        if perf["circuit_tripped"]:
            return False, (
                f"🚫 *System in Circuit Breaker Discipline Lock!*\n"
                f"Reason: {perf['reason']}\n"
                f"To protect capital and prevent emotional trading, new orders are locked for the remainder of the session."
            ), {}

        # 2. Cooldown Check (Post-trade pause - bypassed on Demo or for Council autonomous executions)
        in_cooldown, rem_min, cd_reason = self.get_cooldown_status()
        if in_cooldown and not self.is_demo_account() and not is_autonomous:
            return False, (
                f"⏳ *Mindfulness Cooldown Active!*\n"
                f"New order placement is locked for *{rem_min} minutes*.\n"
                f"💡 *Reason:* {cd_reason}\n"
                f"Purpose: Prevent revenge trading, impulsive entries, and emotional decisions."
            ), {}

        # 3. Session Hours Check (Tehran 11:30 - 21:00)
        in_session, session_msg = self.is_within_session_hours(symbol)
        if not in_session:
            return False, f"🚫 *Session Hour Rejection:*\n{session_msg}", {}

        # 4. High-Impact Macro News Danger Zone Check
        is_news_danger, news_ev = check_news_danger(symbol, window_minutes=20)
        if is_news_danger and news_ev:
            return False, (
                f"🚫 *High-Impact Macro News Danger Zone Active!*\n"
                f"📌 Event: `{news_ev['title']}` ({news_ev['country']})\n"
                f"⏰ Release Time: `{news_ev['time_str']}` Tehran ({news_ev['minutes_away']}m away)\n"
                f"🛑 Pending orders prohibited during high-risk news releases due to spread blowouts and slippage."
            ), {}

        resolved_sym = self.resolve_symbol(symbol)
        if not resolved_sym:
            return False, f"Symbol `{symbol}` not found on broker.", {}

        tick = mt5.symbol_info_tick(resolved_sym)
        if not tick:
            return False, f"Failed to retrieve live market quote for `{resolved_sym}`.", {}

        is_buy = "BUY" in order_type_str.upper()

        # Semantic Direction Validation
        if is_buy:
            if price >= tick.ask:
                return False, f"Buy Limit price ({price}) must be below current Ask ({tick.ask}).", {}
            if sl >= price:
                return False, f"Buy Limit Stop Loss ({sl}) must be below Entry price ({price}).", {}
            if tp <= price:
                return False, f"Buy Limit Take Profit ({tp}) must be above Entry price ({price}).", {}
        else: # SELL LIMIT
            if price <= tick.bid:
                return False, f"Sell Limit price ({price}) must be above current Bid ({tick.bid}).", {}
            if sl <= price:
                return False, f"Sell Limit Stop Loss ({sl}) must be above Entry price ({price}).", {}
            if tp >= price:
                return False, f"Sell Limit Take Profit ({tp}) must be below Entry price ({price}).", {}

        # Dollar Risk Validation ($12 Ceiling including Spread & Commission buffer)
        risk_usd = self.calculate_risk_usd(resolved_sym, order_type_str, price, sl, lot)
        if risk_usd is None:
            return False, "Broker risk calculation returned an error.", {}

        reward_usd = self.calculate_risk_usd(resolved_sym, "SELL" if is_buy else "BUY", price, tp, lot) or 0.0

        # Estimate Spread Cost & Round-trip Commission buffer
        spread_cost = self.calculate_risk_usd(resolved_sym, "BUY", tick.ask, tick.bid, lot) or 0.0
        commission_est = round(0.10 * (lot / BASE_LOT), 2)
        friction_total = round(spread_cost + commission_est, 2)
        total_risk_usd = round(risk_usd + friction_total, 2)

        if total_risk_usd > MAX_RISK_USD:
            return False, (
                f"❌ *Order Rejected: Max Dollar Risk Violation!*\n"
                f"Structural Stop Loss: *${risk_usd:.2f}*\n"
                f"Friction (Spread & Commission): *${friction_total:.2f}*\n"
                f"Total Projected Risk: *${total_risk_usd:.2f}* (Max Allowed: *${MAX_RISK_USD:.2f}*)\n"
                f"💡 Please refine Stop Loss distance to keep total risk strictly under ${MAX_RISK_USD:.2f}."
            ), {}

        # 6. Account Profile & Prop Firm Risk Governor Validation
        from hitl.account_risk_manager import risk_governor
        gov_ok, gov_msg, gov_metrics = risk_governor.evaluate_order_feasibility(
            symbol=resolved_sym,
            order_type_str=order_type_str,
            price=price,
            sl=sl,
            tp=tp,
            lot=lot,
            risk_usd=total_risk_usd,
            engine=self
        )
        if not gov_ok:
            return False, gov_msg, {}

        rr_ratio = (reward_usd / total_risk_usd) if total_risk_usd > 0 else 0.0
        details = {
            "symbol": resolved_sym,
            "type": "BUY_LIMIT" if is_buy else "SELL_LIMIT",
            "entry": price,
            "sl": sl,
            "tp": tp,
            "lot": lot,
            "price_risk_usd": round(risk_usd, 2),
            "friction_usd": friction_total,
            "risk_usd": total_risk_usd,
            "reward_usd": round(reward_usd, 2),
            "rr": round(rr_ratio, 2),
            "account_governor": gov_metrics
        }
        return True, "", details

    def place_limit_order(
        self,
        symbol: str,
        order_type_str: str,
        price: float,
        sl: float,
        tp: float,
        lot: float = BASE_LOT,
        is_autonomous: bool = False
    ) -> Tuple[bool, str, Optional[int]]:
        """Executes pending limit order in MT5 with hard SL and TP."""
        valid, msg, details = self.validate_limit_order(symbol, order_type_str, price, sl, tp, lot, is_autonomous=is_autonomous)
        if not valid:
            return False, msg, None

        sym = details["symbol"]
        is_buy = "BUY" in details["type"]
        mt5_order_type = mt5.ORDER_TYPE_BUY_LIMIT if is_buy else mt5.ORDER_TYPE_SELL_LIMIT

        sym_info = mt5.symbol_info(sym)
        if not sym_info:
            return False, f"Failed to retrieve symbol info for {sym}.", None

        # Snap price, SL, TP to broker digits and tick size
        digits = getattr(sym_info, "digits", 2)
        tick_size = getattr(sym_info, "trade_tick_size", 0.0) or 0.0
        if tick_size > 0:
            snapped_price = round(round(price / tick_size) * tick_size, digits)
            snapped_sl = round(round(sl / tick_size) * tick_size, digits)
            snapped_tp = round(round(tp / tick_size) * tick_size, digits)
        else:
            snapped_price = round(price, digits)
            snapped_sl = round(sl, digits)
            snapped_tp = round(tp, digits)

        # Dynamic filling_mode resolution: RETURN (4) -> IOC (2) -> FOK (1)
        filling_mode = getattr(sym_info, "filling_mode", 0)
        if (filling_mode & 4) != 0:
            resolved_filling = mt5.ORDER_FILLING_RETURN
        elif (filling_mode & 2) != 0:
            resolved_filling = mt5.ORDER_FILLING_IOC
        elif (filling_mode & 1) != 0:
            resolved_filling = mt5.ORDER_FILLING_FOK
        else:
            resolved_filling = mt5.ORDER_FILLING_RETURN

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": sym,
            "volume": lot,
            "type": mt5_order_type,
            "price": snapped_price,
            "sl": snapped_sl,
            "tp": snapped_tp,
            "type_filling": resolved_filling,
            "type_time": mt5.ORDER_TIME_GTC,
            "comment": "TradingGuard HITL",
        }

        with _MT5_LOCK:
            result = mt5.order_send(request)
            if not result:
                return False, f"Broker request dispatch error: {mt5.last_error()}", None

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return False, f"Broker rejected order: [{result.retcode}] {result.comment}", None

            return True, f"Limit order successfully placed with ticket #{result.order}.", result.order

    def cancel_order(self, ticket: int) -> Tuple[bool, str]:
        """Cancels a pending order by ticket ID."""
        if not self.ensure_connected():
            return False, "MT5 connection is not active."

        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
        }
        with _MT5_LOCK:
            result = mt5.order_send(request)
            if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
                comment = result.comment if result else str(mt5.last_error())
                return False, f"Order cancellation failed: {comment}"
            return True, f"Order #{ticket} cancelled successfully."

    def modify_position_sltp(self, ticket: int, sl: float, tp: float) -> Tuple[bool, str]:
        """Modifies Stop Loss and Take Profit of an active open position."""
        if not self.ensure_connected():
            return False, "MT5 connection is not active."
        
        with _MT5_LOCK:
            pos = mt5.positions_get(ticket=ticket)
            if not pos:
                return False, f"Position #{ticket} not found."
            p = pos[0]

            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "symbol": p.symbol,
                "sl": float(sl),
                "tp": float(tp),
            }
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                return True, f"Position #{ticket} SL/TP updated successfully."
            err = res.comment if res else str(mt5.last_error())
            return False, f"Failed to modify position #{ticket}: {err}"

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """Retrieves all active pending orders."""
        if not self.ensure_connected():
            return []
        orders = mt5.orders_get()
        if not orders:
            return []
        res = []
        for o in orders:
            is_buy = o.type in [mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP]
            res.append({
                "ticket": o.ticket,
                "symbol": o.symbol,
                "type": "BUY LIMIT" if o.type == mt5.ORDER_TYPE_BUY_LIMIT else "SELL LIMIT" if o.type == mt5.ORDER_TYPE_SELL_LIMIT else str(o.type),
                "volume": o.volume_current,
                "price_open": o.price_open,
                "sl": o.sl,
                "tp": o.tp,
                "time_setup": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(o.time_setup))
            })
        return res

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Retrieves all currently filled open positions."""
        if not self.ensure_connected():
            return []
        positions = mt5.positions_get()
        if not positions:
            return []
        res = []
        for p in positions:
            res.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "price_current": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit
            })
        return res
