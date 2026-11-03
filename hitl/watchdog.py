"""
TradingGuard HITL - Watchdog & Safety Radar Service
1. Automated Sharp Momentum Guard: Auto-cancels pending orders if price spikes > 2.0x ATR or spread blows out.
2. Time-Based Inactivity Reminder: Sends Telegram review prompts for stale pending orders.
"""

import time
import datetime
from typing import Dict, Set, Tuple, Optional, Callable
import MetaTrader5 as mt5
from hitl.config import (
    MOMENTUM_ATR_MULTIPLIER,
    INACTIVITY_REMINDER_MINUTES,
    COOLDOWN_WIN_MINUTES,
    COOLDOWN_LOSS_MINUTES,
    TELEGRAM_CHAT_ID
)
from hitl.mt5_engine import MT5Engine
from hitl.telegram_client import TelegramClient
from hitl.macro_calendar import check_news_danger


class MarketWatchdog:
    def __init__(
        self,
        engine: MT5Engine,
        client: TelegramClient,
        on_auto_dispatch: Optional[Callable[[str], None]] = None
    ):
        self.engine = engine
        self.client = client
        self.on_auto_dispatch = on_auto_dispatch
        self.last_auto_dispatch_hour: int = -1
        self.start_time: float = time.time()
        self.last_heartbeat_time: float = time.time()
        self.reminded_tickets: Set[int] = set()
        self.warned_news_events: Set[str] = set()
        self.known_positions: Set[int] = set()
        if self.engine.ensure_connected():
            curr_pos = mt5.positions_get()
            if curr_pos:
                self.known_positions = {p.ticket for p in curr_pos}

        # Autonomous SMC Opportunity Radar
        from hitl.live_radar import LiveMarketRadar
        self.radar = LiveMarketRadar(self.engine, self.client)
        self.last_radar_poll: float = 0.0

        # Closed-Loop Review State
        self.last_post_mortem_date: Optional[datetime.date] = None
        self.last_morning_briefing_date: Optional[datetime.date] = None

    def send_heartbeat(self, chat_id: int | str, is_manual: bool = False):
        """Sends an operational system health check card."""
        now_dt = datetime.datetime.now()
        uptime_sec = int(time.time() - self.start_time)
        hrs, rem = divmod(uptime_sec, 3600)
        mins, secs = divmod(rem, 60)
        uptime_str = f"{hrs}h {mins}m {secs}s"

        acc = self.engine.get_account_summary()
        mt5_status = f"🟢 Connected (`{acc['login']}` - ${acc['balance']:.2f})" if acc else "🔴 Disconnected"

        pending_count = len(self.engine.get_pending_orders())
        pos_count = len(self.engine.get_open_positions())

        in_cd, cd_min, _ = self.engine.get_cooldown_status()
        cd_badge = f"⏳ Active ({cd_min}m left)" if in_cd else "🟢 Idle"

        perf = self.engine.get_daily_performance()
        circuit_badge = "⛔ TRIPPED" if perf["circuit_tripped"] else f"🟢 Safe (${perf['realized_pnl']:+.2f})"

        title = "💓 *Pong! System Healthy & Active*" if is_manual else "💓 *TradingGuard Periodic Heartbeat*"

        card = (
            f"{title}\n\n"
            f"🕒 *Tehran Time:* `{now_dt.strftime('%H:%M:%S')}`\n"
            f"⏱ *Uptime:* `{uptime_str}`\n"
            f"📡 *Telegram Proxy:* Connected (`127.0.0.1:10808`)\n"
            f"📈 *MT5 Broker:* {mt5_status}\n"
            f"📋 *Pending Orders:* {pending_count} | 🎯 *Active Positions:* {pos_count}\n"
            f"🛡️ *Discipline Radar:* Cooldown {cd_badge} | Circuit {circuit_badge}\n"
            f"🎯 *SMC Live Radar:* 🟢 Active (Autonomous Killzone Scout on Cable/Euro/Gold)"
        )
        self.client.send_message(chat_id, card)

    def check_momentum_and_spread(self, order) -> Tuple[bool, str]:
        """
        Evaluates whether current price velocity towards pending limit order constitutes a sharp spike.
        Returns (should_cancel, reason).
        """
        symbol = order.symbol
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 15)
        if rates is None or len(rates) < 10:
            return False, ""

        # Calculate 14-period True Range
        tr_list = []
        for i in range(1, len(rates)):
            hl = rates[i]['high'] - rates[i]['low']
            hc = abs(rates[i]['high'] - rates[i-1]['close'])
            lc = abs(rates[i]['low'] - rates[i-1]['close'])
            tr_list.append(max(hl, hc, lc))

        atr = sum(tr_list) / len(tr_list) if tr_list else 1.0
        latest = rates[-1]
        candle_body = latest['close'] - latest['open']
        abs_body = abs(candle_body)

        is_buy_limit = (order.type == mt5.ORDER_TYPE_BUY_LIMIT)
        is_sell_limit = (order.type == mt5.ORDER_TYPE_SELL_LIMIT)

        # Check Spread Spike (> 3x normal)
        sym_info = mt5.symbol_info(symbol)
        if sym_info and sym_info.spread > 50: # Spread > 50 points (e.g. 5.0 pips)
            return True, f"جهش غیرعادی اسپرد بروکر ({sym_info.spread} پوینت)"

        # Check Sharp Directional Thrust
        # For Buy Limit: adverse move is aggressive red candle plunging downwards
        if is_buy_limit and candle_body < 0 and abs_body >= (MOMENTUM_ATR_MULTIPLIER * atr):
            return True, f"کندل نزولی پرقدرت شتابان ({abs_body:.2f} > {MOMENTUM_ATR_MULTIPLIER}x ATR)"

        # For Sell Limit: adverse move is aggressive green candle surging upwards
        if is_sell_limit and candle_body > 0 and abs_body >= (MOMENTUM_ATR_MULTIPLIER * atr):
            return True, f"کندل صعودی پرقدرت شتابان ({abs_body:.2f} > {MOMENTUM_ATR_MULTIPLIER}x ATR)"

        return False, ""

    def poll(self):
        """Single polling cycle executed periodically."""
        if not self.engine.ensure_connected():
            return

        chat_id = TELEGRAM_CHAT_ID
        if not chat_id:
            return

        # 1. Inspect Pending Orders
        orders = mt5.orders_get()
        active_tickets = set()

        if orders:
            for o in orders:
                active_tickets.add(o.ticket)
                # A) Automated Momentum Check
                should_cancel, reason = self.check_momentum_and_spread(o)
                if should_cancel:
                    success, msg = self.engine.cancel_order(o.ticket)
                    if success:
                        self.client.send_message(
                            chat_id,
                            f"🛑 *Auto-Cancellation of Limit Order #{o.ticket}*\n"
                            f"📌 Symbol: `{o.symbol}`\n"
                            f"⚡ *Reason:* Sharp adverse momentum spike towards entry ({reason})\n"
                            f"🛡️ Smart guard prevented trade against high velocity order flow."
                        )
                    continue

                # B) Time-Based Inactivity Reminder (TTL)
                order_age_minutes = (time.time() - o.time_setup) / 60.0
                if order_age_minutes >= INACTIVITY_REMINDER_MINUTES and o.ticket not in self.reminded_tickets:
                    self.reminded_tickets.add(o.ticket)
                    order_type_str = "Buy Limit" if o.type == mt5.ORDER_TYPE_BUY_LIMIT else "Sell Limit"
                    buttons = {
                        "inline_keyboard": [
                            [
                                {"text": f"❌ Cancel Order #{o.ticket}", "callback_data": f"cancel_{o.ticket}"},
                                {"text": f"👁 Keep Order", "callback_data": f"keep_{o.ticket}"}
                            ]
                        ]
                    }
                    self.client.send_message(
                        chat_id,
                        f"⏳ *Stale Limit Order Reminder*\n"
                        f"📌 Ticket: `#{o.ticket}` ({order_type_str})\n"
                        f"🔹 Entry: `{o.price_open}`\n"
                        f"⏱ Unfilled for {int(order_age_minutes)} minutes.\n"
                        f"Would you like to keep or cancel?",
                        reply_markup=buttons
                    )

        # Clean up stale reminded tickets
        self.reminded_tickets = self.reminded_tickets.intersection(active_tickets)

        # 2. Inspect Open Positions (Detect Newly Filled Orders)
        positions = mt5.positions_get()
        current_pos_tickets = set()
        if positions:
            for p in positions:
                current_pos_tickets.add(p.ticket)
                if p.ticket not in self.known_positions:
                    self.known_positions.add(p.ticket)
                    pos_type = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
                    self.client.send_message(
                        chat_id,
                        f"🎯 *Limit Order Filled - Position Active!*\n"
                        f"📌 Ticket: `#{p.ticket}`\n"
                        f"🔹 Symbol: `{p.symbol}` ({pos_type})\n"
                        f"⚖️ Lot: `{p.volume}`\n"
                        f"📍 Entry: `{p.price_open}` | 🛑 SL: `{p.sl}` | 🎯 TP: `{p.tp}`\n"
                        f"🧘 *Set & Forget Protocol Activated.*"
                    )

        # 3. Detect Closed Positions (Position was in known_positions but now gone!)
        closed_tickets = self.known_positions - current_pos_tickets
        for closed_ticket in closed_tickets:
            # Query deals for closed position
            deals = mt5.history_deals_get(position=closed_ticket)
            sym = "UNKNOWN"
            net_profit = 0.0
            if deals:
                net_profit = sum(d.profit + d.commission + d.swap + d.fee for d in deals)
                sym = deals[0].symbol if deals else "XAUUSD"

            is_win = (net_profit >= 0)
            cd_mins = COOLDOWN_WIN_MINUTES if is_win else COOLDOWN_LOSS_MINUTES
            cd_reason = "Profit consolidation & discipline lock" if is_win else "Mental clarity & revenge trading defense"
            self.engine.set_cooldown(cd_mins, cd_reason)

            if is_win:
                self.client.send_message(
                    chat_id,
                    f"🎉 *Position Closed in Profit!*\n\n"
                    f"📌 *Ticket:* `#{closed_ticket}` | Symbol: `{sym}`\n"
                    f"💰 *Net Realized Profit:* *+${net_profit:.2f}*\n"
                    f"⏱ *Cooldown Active:* {cd_mins}m mandatory pause to consolidate gains.\n"
                    f"Good job! ☕"
                )
            else:
                self.client.send_message(
                    chat_id,
                    f"🛑 *Position Closed at Stop Loss.*\n\n"
                    f"📌 *Ticket:* `#{closed_ticket}` | Symbol: `{sym}`\n"
                    f"💸 *Realized Loss:* *-${abs(net_profit):.2f}*\n"
                    f"⏱ *Cooldown Active:* {cd_mins}m pause to eliminate emotional tilt.\n"
                    f"🧘 System paused to reset perspective."
                )

            # Check daily circuit breaker after closure
            perf = self.engine.get_daily_performance()
            if perf["circuit_tripped"]:
                self.client.send_message(
                    chat_id,
                    f"⛔ *Daily Circuit Breaker TRIPPED!*\n"
                    f"Reason: {perf['reason']}\n"
                    f"Trading locked until next market session."
                )

        self.known_positions = current_pos_tickets

        # 4. Periodic Heartbeat (Every 60 minutes during session hours)
        now_ts = time.time()
        now_dt = datetime.datetime.now()
        is_weekday = (now_dt.weekday() < 5) # Monday = 0 ... Friday = 4
        in_session = (11 <= now_dt.hour <= 20)
        if is_weekday and in_session and (now_ts - self.last_heartbeat_time >= 3600):
            self.last_heartbeat_time = now_ts
            self.send_heartbeat(chat_id, is_manual=False)

        # 6. Proactive High-Impact News Radar for Active Pending Orders
        if active_tickets and orders:
            for o in orders:
                is_danger, news_ev = check_news_danger(o.symbol, window_minutes=15)
                if is_danger and news_ev:
                    news_key = f"{o.ticket}_{news_ev['title']}_{news_ev['date_str']}"
                    if news_key not in self.warned_news_events:
                        self.warned_news_events.add(news_key)
                        btn = {"inline_keyboard": [[{"text": f"❌ Cancel Order #{o.ticket}", "callback_data": f"cancel_{o.ticket}"}]]}
                        self.client.send_message(
                            chat_id,
                            f"⚠️ *Fundamental News Risk Detected!*\n\n"
                            f"📌 *Event:* `{news_ev['title']}` ({news_ev['country']})\n"
                            f"⏰ *Release Time:* `{news_ev['time_str']}` Tehran ({news_ev['minutes_away']}m away)\n"
                            f"📋 *Active Order:* Ticket `#{o.ticket}` on `{o.symbol}`\n\n"
                            f"🛑 *Discipline Recommendation:* High-impact events can trigger severe spread blowout and slippage. Cancel order to preserve capital if preferred.",
                            reply_markup=btn
                        )

        # 7. Autonomous SMC Live Opportunity Radar (Polls every 15 seconds)
        now_ts = time.time()
        if now_ts - self.last_radar_poll >= 15.0:
            self.last_radar_poll = now_ts
            self.radar.poll()

        # 8. Automated Closed-Loop Session Reviews
        # A) End-of-Session Post-Mortem at 21:00 Tehran (Mon-Fri)
        if is_weekday and now_dt.hour == 21 and now_dt.minute == 0:
            if self.last_post_mortem_date != now_dt.date():
                self.last_post_mortem_date = now_dt.date()
                try:
                    from hitl.review_engine import run_session_post_mortem
                    run_session_post_mortem(self.engine, self.client, chat_id)
                except Exception as e:
                    print(f"[Watchdog] Post-Mortem Error: {e}")

        # B) Pre-Market Morning Briefing at 10:30 Tehran (Mon-Fri)
        if is_weekday and now_dt.hour == 10 and now_dt.minute == 30:
            if self.last_morning_briefing_date != now_dt.date():
                self.last_morning_briefing_date = now_dt.date()
                try:
                    from hitl.review_engine import run_morning_briefing
                    run_morning_briefing(self.engine, self.client, chat_id)
                except Exception as e:
                    print(f"[Watchdog] Morning Briefing Error: {e}")
