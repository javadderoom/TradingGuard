"""
TradingGuard HITL - MetaTrader 5 Execution & Risk Engine
Handles native order placement, mathematical risk enforcement ($12 cap),
pending order cancellation, and account queries.
"""

import os
import time
import datetime
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

        now = datetime.datetime.now()
        midnight = datetime.datetime(now.year, now.month, now.day, 0, 0, 0)
        deals = mt5.history_deals_get(midnight, now + datetime.timedelta(days=1))

        if not deals:
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
            if ct.profit < 0:
                consec_losses += 1
            else:
                break

        circuit_tripped = False
        reason = ""
        if daily_loss >= MAX_DAILY_LOSS_USD:
            circuit_tripped = True
            reason = f"سقف زیان روزانه (${daily_loss:.2f} >= ${MAX_DAILY_LOSS_USD:.2f}) پر شده است."
        elif consec_losses >= MAX_CONSECUTIVE_LOSSES:
            circuit_tripped = True
            reason = f"تعداد ضررهای متوالی امروز ({consec_losses} ترید) به حد مجاز رسیده است."

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
            return False, "اتصال به متاتریدر ۵ برقرار نشد.", {}

        # 1. Circuit Breaker Check (Daily loss ceiling & consecutive loss lock)
        perf = self.get_daily_performance()
        if perf["circuit_tripped"]:
            return False, (
                f"🚫 *سیستم در وضعیت قفل انضباطی (Circuit Breaker) است!*\n"
                f"دلیل: {perf['reason']}\n"
                f"جهت محافظت از سرمایه و پیشگیری از معامله احساسی، ثبت اردر جدید تا پایان روز مسدود می‌باشد."
            ), {}

        # 2. Cooldown Check (Post-trade pause - bypassed on Demo or for Council autonomous executions)
        in_cooldown, rem_min, cd_reason = self.get_cooldown_status()
        if in_cooldown and not self.is_demo_account() and not is_autonomous:
            return False, (
                f"⏳ *قفل آرامش ذهن (Cooldown) فعال است!*\n"
                f"تا پایان زمان وقفه (*{rem_min} دقیقه* باقی‌مانده) امکان ثبت اردر جدید وجود ندارد.\n"
                f"💡 *علت:* {cd_reason}\n"
                f"هدف: جلوگیری از ورودهای شتاب‌زده، انتقامی یا تصمیم‌گیری هیجانی."
            ), {}

        # 3. Session Hours Check (Tehran 11:30 - 21:00)
        in_session, session_msg = self.is_within_session_hours(symbol)
        if not in_session:
            return False, f"🚫 *عدم تایید اردر (سشن معاملاتی):*\n{session_msg}", {}

        # 4. High-Impact Macro News Danger Zone Check
        is_news_danger, news_ev = check_news_danger(symbol, window_minutes=20)
        if is_news_danger and news_ev:
            return False, (
                f"🚫 *توقف به دلیل اخبار با تاثیر بالا (News Radar)!*\n"
                f"📌 رویداد: `{news_ev['title']}` ({news_ev['country']})\n"
                f"⏰ زمان انتشار: ساعت `{news_ev['time_str']}` به وقت تهران ({news_ev['minutes_away']} دقیقه باقی‌مانده)\n"
                f"🛑 ورود اردر لیمیت در آستانه اخبار پرریسک به دلیل جهش اسپرد و اسلیپیج مسدود می‌باشد."
            ), {}

        resolved_sym = self.resolve_symbol(symbol)
        if not resolved_sym:
            return False, f"نماد `{symbol}` در بروکر پیدا نشد.", {}

        tick = mt5.symbol_info_tick(resolved_sym)
        if not tick:
            return False, f"دریافت قیمت لحظه‌ای برای `{resolved_sym}` ناموفق بود.", {}

        is_buy = "BUY" in order_type_str.upper()

        # Semantic Direction Validation
        if is_buy:
            if price >= tick.ask:
                return False, f"قیمت Buy Limit ({price}) باید پایین‌تر از قیمت لحظه‌ای فروش ({tick.ask}) باشد.", {}
            if sl >= price:
                return False, f"حد ضرر Buy Limit ({sl}) باید پایین‌تر از نقطه ورود ({price}) باشد.", {}
            if tp <= price:
                return False, f"حد سود Buy Limit ({tp}) باید بالاتر از نقطه ورود ({price}) باشد.", {}
        else: # SELL LIMIT
            if price <= tick.bid:
                return False, f"قیمت Sell Limit ({price}) باید بالاتر از قیمت لحظه‌ای خرید ({tick.bid}) باشد.", {}
            if sl <= price:
                return False, f"حد ضرر Sell Limit ({sl}) باید بالاتر از نقطه ورود ({price}) باشد.", {}
            if tp >= price:
                return False, f"حد سود Sell Limit ({tp}) باید پایین‌تر از نقطه ورود ({price}) باشد.", {}

        # Dollar Risk Validation ($12 Ceiling including Spread & Commission buffer)
        risk_usd = self.calculate_risk_usd(resolved_sym, order_type_str, price, sl, lot)
        if risk_usd is None:
            return False, "محاسبه مقدار ریسک با خطای بروکر مواجه شد.", {}

        reward_usd = self.calculate_risk_usd(resolved_sym, "SELL" if is_buy else "BUY", price, tp, lot) or 0.0

        # Estimate Spread Cost & Round-trip Commission buffer
        spread_cost = self.calculate_risk_usd(resolved_sym, "BUY", tick.ask, tick.bid, lot) or 0.0
        commission_est = round(0.10 * (lot / BASE_LOT), 2)
        friction_total = round(spread_cost + commission_est, 2)
        total_risk_usd = round(risk_usd + friction_total, 2)

        if total_risk_usd > MAX_RISK_USD:
            return False, (
                f"❌ *رد دستور به دلیل نقض سقف ریسک!*\n"
                f"ضرر حاصل از قیمت: *${risk_usd:.2f}*\n"
                f"هزینه اسپرد و کمیسیون: *${friction_total:.2f}*\n"
                f"مجموع ریسک معامله: *${total_risk_usd:.2f}* (سقف مجاز: *${MAX_RISK_USD:.2f}*)\n"
                f"💡 لطفاً حد ضرر را کمی بسته‌تر انتخاب کنید تا مجموع ریسک زیر ۱۲ دلار بماند."
            ), {}

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
            "rr": round(rr_ratio, 2)
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

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": sym,
            "volume": lot,
            "type": mt5_order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "type_filling": mt5.ORDER_FILLING_RETURN,
            "type_time": mt5.ORDER_TIME_GTC,
            "comment": "TradingGuard HITL",
        }

        result = mt5.order_send(request)
        if not result:
            return False, f"خطا در ارسال درخواست به بروکر: {mt5.last_error()}", None

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return False, f"بروکر درخواست را رد کرد: [{result.retcode}] {result.comment}", None

        return True, f"اردر لیمیت با تیکت #{result.order} ثبت شد.", result.order

    def cancel_order(self, ticket: int) -> Tuple[bool, str]:
        """Cancels a pending order by ticket ID."""
        if not self.ensure_connected():
            return False, "اتصال به متاتریدر برقرار نیست."

        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
        }
        result = mt5.order_send(request)
        if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
            comment = result.comment if result else str(mt5.last_error())
            return False, f"Order cancellation failed: {comment}"
        return True, f"Order #{ticket} cancelled successfully."

    def modify_position_sltp(self, ticket: int, sl: float, tp: float) -> Tuple[bool, str]:
        """Modifies Stop Loss and Take Profit of an active open position."""
        if not self.ensure_connected():
            return False, "MT5 connection failed"
        
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return False, f"Position #{ticket} not found"
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
