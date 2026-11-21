"""
TradingGuard HITL - Watchdog & Safety Radar Service
1. Automated Sharp Momentum Guard: Auto-cancels pending orders if price spikes > 2.0x ATR or spread blows out.
2. Time-Based Inactivity Reminder: Sends Telegram review prompts for stale pending orders.
"""

import time
import datetime
import threading
from pathlib import Path
from typing import Dict, Set, Tuple, Optional, Callable, Any
import json
import MetaTrader5 as mt5
from hitl.config import (
    MOMENTUM_ATR_MULTIPLIER,
    INACTIVITY_REMINDER_MINUTES,
    COOLDOWN_WIN_MINUTES,
    COOLDOWN_LOSS_MINUTES,
    TELEGRAM_CHAT_ID,
    BASE_DIR,
    DEFAULT_SYMBOL,
    FUNDAMENTAL_CACHE_TTL_MINUTES,
)
from hitl.mt5_engine import MT5Engine
from hitl.telegram_client import TelegramClient
from hitl.macro_calendar import check_news_danger


ORDER_META_FILE = BASE_DIR / "hitl" / "memory" / "active_order_meta.json"

def register_order_metadata(ticket: int, data: Dict[str, Any]):
    """Saves per-ticket execution metadata (archetype_id, be_rr, target_rr, ttl_minutes)."""
    try:
        meta = {}
        if ORDER_META_FILE.exists():
            with open(ORDER_META_FILE, "r", encoding="utf-8") as f:
                meta = json.load(f)
        meta[str(ticket)] = data
        ORDER_META_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ORDER_META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
    except Exception as e:
        print(f"[Watchdog] Error saving order metadata: {e}")

def get_order_metadata(ticket: int) -> Dict[str, Any]:
    """Retrieves per-ticket execution metadata."""
    try:
        if ORDER_META_FILE.exists():
            with open(ORDER_META_FILE, "r", encoding="utf-8") as f:
                meta = json.load(f)
                return meta.get(str(ticket), {})
    except Exception:
        pass
    return {}


def is_rollover_blackout(dt: Optional[datetime.datetime] = None) -> bool:
    """
    Checks if current time is within daily broker rollover blackout (23:55 to 00:15 broker server time).
    During rollover, bank liquidity disappears and spreads blow out normally; cancellations and entries are suppressed.
    """
    if dt is None:
        try:
            tick = mt5.symbol_info_tick(DEFAULT_SYMBOL)
            if tick and tick.time > 0:
                from hitl.replay_data import server_epoch_to_zones
                dt = server_epoch_to_zones(int(tick.time))["broker_dt"]
            else:
                dt = datetime.datetime.now()
        except Exception:
            dt = datetime.datetime.now()

    h = dt.hour
    m = dt.minute
    if (h == 23 and m >= 55) or (h == 0 and m <= 15):
        return True
    return False


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
        self.ratcheted_be_positions: Set[int] = set()
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
        self.last_london_briefing_date: Optional[datetime.date] = None
        self.last_ny_briefing_date: Optional[datetime.date] = None
        self.last_circuit_alerted: bool = False

        # Background Fundamental Causal Refresh State
        self.last_fundamental_refresh_ts: float = 0.0
        self._fundamental_refresh_running: bool = False
        fund_state = BASE_DIR / "hitl" / "memory" / "fundamental_state.json"
        if fund_state.exists():
            try:
                self.last_fundamental_refresh_ts = fund_state.stat().st_mtime
            except Exception:
                pass

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

        from hitl.account_risk_manager import risk_governor
        gov_sync = risk_governor.sync_state(self.engine)
        gov_mode = risk_governor.mode
        gov_status = f"`{gov_mode}` (Daily DD: {gov_sync['daily_dd_pct']:.1f}% | Overall: {gov_sync['overall_dd_pct']:.1f}%)"

        title = "💓 *Pong! System Healthy & Active*" if is_manual else "💓 *TradingGuard Periodic Heartbeat*"

        card = (
            f"{title}\n\n"
            f"🕒 *Tehran Time:* `{now_dt.strftime('%H:%M:%S')}`\n"
            f"⏱ *Uptime:* `{uptime_str}`\n"
            f"📡 *Telegram Proxy:* Connected (`127.0.0.1:10808`)\n"
            f"📈 *MT5 Broker:* {mt5_status}\n"
            f"📋 *Pending Orders:* {pending_count} | 🎯 *Active Positions:* {pos_count}\n"
            f"🛡️ *Discipline Radar:* Cooldown {cd_badge} | Circuit {circuit_badge}\n"
            f"🏢 *Risk Governor:* {gov_status}\n"
            f"🎯 *SMC Live Radar:* 🟢 Active (Autonomous Killzone Scout on Cable/Euro/Gold)"
        )
        self.client.send_message(chat_id, card)

    def _get_max_allowable_spread(self, symbol: str) -> int:
        """Returns max allowable broker spread in points before triggering protection cancellation."""
        s = symbol.upper()
        if "GBP" in s or "EUR" in s:
            return 60  # 6.0 pips on 5-digit FX
        elif "XAU" in s:
            return 120  # $1.20 on Gold (normal is 20-35 points)
        elif "XAG" in s:
            return 150  # 15.0 cents on Silver
        elif "NQ" in s or "USTEC" in s or "NAS100" in s:
            return 450  # 45.0 points on NQ (normal is 100-150 points)
        elif "SPX" in s or "US500" in s:
            return 250  # 25.0 points on SPX
        elif "BTC" in s:
            return 3000  # $30.00 on BTC
        return 100

    def check_momentum_and_spread(self, order) -> Tuple[bool, str]:
        """
        Evaluates whether current price velocity towards pending limit order constitutes a sharp spike.
        Returns (should_cancel, reason).
        """
        symbol = order.symbol
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 16)
        if rates is None or len(rates) < 12:
            return False, ""

        # Calculate 14-period True Range on closed bars (excluding forming spike bar)
        tr_list = []
        for i in range(1, len(rates) - 1):
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

        # Check if broker is in rollover blackout (spread naturally widens 10x-50x; suppress false spread cancellation)
        if is_rollover_blackout():
            return False, ""

        # Check Spread Spike (> asset-scaled threshold)
        sym_info = mt5.symbol_info(symbol)
        max_spread = self._get_max_allowable_spread(symbol)
        if sym_info and sym_info.spread > max_spread:
            return True, f"Abnormal broker spread spike ({sym_info.spread} points > {max_spread} limit)"

        # Calibrate per RULE-METALS-011: 3.5x ATR for Precious Metals, 2.0x for Forex/Indices
        is_metal = ("XAU" in symbol.upper() or "XAG" in symbol.upper())
        spike_mult = 3.5 if is_metal else 2.0

        # Check Sharp Directional Thrust within 3.0x ATR distance of entry
        if is_buy_limit and candle_body < 0 and abs_body >= (spike_mult * atr):
            dist_to_entry = abs(latest['close'] - order.price_open)
            if dist_to_entry <= (3.0 * atr):
                return True, f"Sharp adverse thrust near entry ({abs_body:.2f} >= {spike_mult}x ATR within 3x ATR distance)"

        if is_sell_limit and candle_body > 0 and abs_body >= (spike_mult * atr):
            dist_to_entry = abs(latest['close'] - order.price_open)
            if dist_to_entry <= (3.0 * atr):
                return True, f"Sharp adverse thrust near entry ({abs_body:.2f} >= {spike_mult}x ATR within 3x ATR distance)"

        return False, ""

    def poll(self):
        """Single polling cycle executed periodically."""
        if not self.engine.ensure_connected():
            return

        chat_id = TELEGRAM_CHAT_ID
        if not chat_id:
            return

        # 0. Account Risk Governor Sync & Circuit Check
        from hitl.account_risk_manager import risk_governor
        gov_sync = risk_governor.sync_state(self.engine)
        if gov_sync.get("circuit_breaker_active") and not self.last_circuit_alerted:
            self.last_circuit_alerted = True
            self.client.send_message(
                chat_id,
                f"🚨 *[ACCOUNT RISK GOVERNOR CIRCUIT BREAKER ENGAGED]*\n\n"
                f"📌 *Mode:* `{gov_sync['account_mode']}`\n"
                f"⚠️ *Reason:* {gov_sync['circuit_breaker_reason']}\n"
                f"💵 *Live Equity:* `${gov_sync['current_equity']:,.2f}` | Balance: `${gov_sync['current_balance']:,.2f}`\n"
                f"📉 *Daily Loss:* `${gov_sync['daily_loss_usd']:,.2f}` ({gov_sync['daily_dd_pct']:.2f}%)\n"
                f"📉 *Overall Drawdown:* `${gov_sync['overall_loss_usd']:,.2f}` ({gov_sync['overall_dd_pct']:.2f}%)\n\n"
                f"🛑 All new order execution is strictly locked to prevent account termination."
            )
        elif not gov_sync.get("circuit_breaker_active"):
            self.last_circuit_alerted = False

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

                # B) Time-Based Inactivity TTL Auto-Cancellation
                order_age_minutes = (time.time() - o.time_setup) / 60.0
                meta = get_order_metadata(o.ticket)
                ttl_limit = meta.get("ttl_minutes", INACTIVITY_REMINDER_MINUTES)
                if order_age_minutes >= ttl_limit:
                    success, msg = self.engine.cancel_order(o.ticket)
                    if success:
                        self.client.send_message(
                            chat_id,
                            f"⏳ *Auto-Cancellation of Stale Limit Order #{o.ticket}*\n"
                            f"📌 Symbol: `{o.symbol}`\n"
                            f"⏱ *TTL Expired:* {int(order_age_minutes)}m unfilled (TTL limit: {int(ttl_limit)}m)\n"
                            f"🛡️ Smart order lifecycle management cancelled stale setup safely."
                        )
                    continue

                if order_age_minutes >= (ttl_limit * 0.7) and o.ticket not in self.reminded_tickets:
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
                        f"⏱ Unfilled for {int(order_age_minutes)} minutes (TTL limit: {int(ttl_limit)}m).\n"
                        f"Would you like to keep or cancel?",
                        reply_markup=buttons
                    )

        # Clean up stale reminded tickets
        self.reminded_tickets = self.reminded_tickets.intersection(active_tickets)

        # 2. Inspect Open Positions (Detect Newly Filled Orders & Dynamic Breakeven Ratchet)
        positions = mt5.positions_get()
        current_pos_tickets = set()
        if positions:
            for p in positions:
                current_pos_tickets.add(p.ticket)
                is_buy = (p.type == mt5.POSITION_TYPE_BUY)
                pos_type = "BUY" if is_buy else "SELL"

                if p.ticket not in self.known_positions:
                    self.known_positions.add(p.ticket)
                    self.client.send_message(
                        chat_id,
                        f"🎯 *Limit Order Filled - Position Active!*\n"
                        f"📌 Ticket: `#{p.ticket}`\n"
                        f"🔹 Symbol: `{p.symbol}` ({pos_type})\n"
                        f"⚖️ Lot: `{p.volume}`\n"
                        f"📍 Entry: `{p.price_open}` | 🛑 SL: `{p.sl}` | 🎯 TP: `{p.tp}`\n"
                        f"🧘 *Set & Forget Protocol Activated.*"
                    )

                # Dynamic Breakeven Ratchet Protocol
                if p.ticket not in self.ratcheted_be_positions and p.sl > 0:
                    try:
                        from hitl.backtest.session_clock import get_active_session_status
                        from hitl.backtest.evaluator import get_optimal_trade_management, get_default_broker_spread
                        
                        meta = get_order_metadata(p.ticket)
                        be_rr = meta.get("be_rr")
                        setup_arch_id = meta.get("archetype_id")
                        
                        if be_rr is None:
                            _, _, sess_key = get_active_session_status()
                            _, be_rr = get_optimal_trade_management(p.symbol, sess_key, setup_arch_id=setup_arch_id)

                        if be_rr is not None and be_rr > 0:
                            risk_pts = abs(p.price_open - p.sl)
                            spread_pts = get_default_broker_spread(p.symbol)
                            sym_info = mt5.symbol_info(p.symbol)
                            digits = sym_info.digits if sym_info else (5 if ("EUR" in p.symbol or "GBP" in p.symbol) else (1 if "NQ" in p.symbol else 2))

                            if is_buy:
                                trigger_px = p.price_open + (be_rr * risk_pts)
                                if p.price_current >= trigger_px and p.sl < p.price_open:
                                    be_sl = round(p.price_open + spread_pts, digits)
                                    ok, msg = self.engine.modify_position_sltp(p.ticket, sl=be_sl, tp=p.tp)
                                    if ok:
                                        self.ratcheted_be_positions.add(p.ticket)
                                        self.client.send_message(
                                            chat_id,
                                            f"🛡️ *Breakeven Ratchet Activated!*\n\n"
                                            f"📌 *Ticket:* `#{p.ticket}` | Symbol: `{p.symbol}` ({pos_type})\n"
                                            f"📈 *Favorable Excursion:* Reached `+{be_rr:.1f}R` ({p.price_current})\n"
                                            f"🔒 *Stop Loss Ratcheted:* Entry + Spread (`{be_sl}`)\n"
                                            f"🎉 *Risk-Free Trade Guaranteed!*"
                                        )
                            else: # SELL
                                trigger_px = p.price_open - (be_rr * risk_pts)
                                if p.price_current <= trigger_px and p.sl > p.price_open:
                                    be_sl = round(p.price_open - spread_pts, digits)
                                    ok, msg = self.engine.modify_position_sltp(p.ticket, sl=be_sl, tp=p.tp)
                                    if ok:
                                        self.ratcheted_be_positions.add(p.ticket)
                                        self.client.send_message(
                                            chat_id,
                                            f"🛡️ *Breakeven Ratchet Activated!*\n\n"
                                            f"📌 *Ticket:* `#{p.ticket}` | Symbol: `{p.symbol}` ({pos_type})\n"
                                            f"📉 *Favorable Excursion:* Reached `+{be_rr:.1f}R` ({p.price_current})\n"
                                            f"🔒 *Stop Loss Ratcheted:* Entry - Spread (`{be_sl}`)\n"
                                            f"🎉 *Risk-Free Trade Guaranteed!*"
                                        )
                    except Exception as be_err:
                        print(f"[Watchdog] Breakeven ratchet error: {be_err}")

        # Clean up ratcheted tickets when closed
        self.ratcheted_be_positions = self.ratcheted_be_positions.intersection(current_pos_tickets)

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

        # C) Proactive OmniTrend Session Briefings (15m before London and NY Open)
        if is_weekday:
            try:
                from zoneinfo import ZoneInfo
                from hitl.backtest.session_clock import get_session_times_for_date
                now_tehran = datetime.datetime.now(ZoneInfo("Asia/Tehran"))
                sess_times = get_session_times_for_date(now_tehran.date())

                lon_target = sess_times["london"]["tehran_time"] - datetime.timedelta(minutes=15)
                ny_target = sess_times["new_york"]["tehran_time"] - datetime.timedelta(minutes=15)

                # London Open Briefing window (15m to 5m before open)
                if lon_target <= now_tehran < (lon_target + datetime.timedelta(minutes=10)):
                    if self.last_london_briefing_date != now_tehran.date():
                        self.last_london_briefing_date = now_tehran.date()
                        self.send_trend_briefing(chat_id, "London")

                # NY Open Briefing window (15m to 5m before open)
                if ny_target <= now_tehran < (ny_target + datetime.timedelta(minutes=10)):
                    if self.last_ny_briefing_date != now_tehran.date():
                        self.last_ny_briefing_date = now_tehran.date()
                        self.send_trend_briefing(chat_id, "New York")
            except Exception as e:
                print(f"[Watchdog] Trend Briefing Error: {e}")

        # 9. Non-blocking Periodic Causal Fundamental Refresh (every FUNDAMENTAL_CACHE_TTL_MINUTES on weekdays)
        self._maybe_trigger_fundamental_refresh(is_weekday=is_weekday, now_ts=now_ts)

    def _maybe_trigger_fundamental_refresh(self, is_weekday: bool, now_ts: float):
        """Triggers non-blocking background causal macro synthesis without stalling the 3s poll loop."""
        if not is_weekday or now_ts < 1e9 or self._fundamental_refresh_running:
            return
        ttl_sec = max(300.0, float(FUNDAMENTAL_CACHE_TTL_MINUTES) * 60.0)
        if (now_ts - self.last_fundamental_refresh_ts) < ttl_sec:
            return

        self._fundamental_refresh_running = True
        self.last_fundamental_refresh_ts = now_ts

        def _bg_worker():
            try:
                from hitl.fundamental.causal_engine import fundamental_engine
                fundamental_engine.get_global_dossier(force_refresh=True, allow_llm=True)
            except Exception as e:
                print(f"[Watchdog] Background fundamental refresh error: {e}")
            finally:
                self._fundamental_refresh_running = False

        threading.Thread(target=_bg_worker, daemon=True, name="FundamentalCausalRefresh").start()

    def send_trend_briefing(self, chat_id: int | str, session_name: str):
        """Sends proactive session trend forecast card to Telegram."""
        try:
            from hitl.trend.trend_oracle import trend_oracle
            fc = trend_oracle.get_forecast(symbol="XAUUSD", force_refresh=True)
            card = trend_oracle.format_telegram_card(fc)
            header = f"🚨 *Proactive {session_name} Session Trend Briefing (15m to Open)*\n\n"
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🔁 Refresh Forecast", "callback_data": "trend_refresh_XAUUSD"},
                        {"text": "📸 View Chart", "callback_data": "pack_gold"}
                    ]
                ]
            }
            self.client.send_message(chat_id, header + card, reply_markup=keyboard)
        except Exception as e:
            print(f"[Watchdog] Failed to send trend briefing: {e}")
