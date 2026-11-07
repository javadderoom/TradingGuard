"""
TradingGuard HITL - Complete Telegram Bot Service (Phases 1, 2 & 3)
Features:
- Background TradingView chart capture (/chart)
- Limit Order Placement with strict $12 Risk Cap (/buylimit, /selllimit)
- Automated Sharp Momentum Cancellation (ATR/Spread Watchdog)
- Stale Order TTL Reminder with interactive buttons
- Order & Position Management (/orders, /positions, /status, /cancel)
"""

import os
import sys
import time
import re
import threading
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure root workspace is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_PROXY,
    DEFAULT_SYMBOL,
    BASE_LOT,
    MAX_RISK_USD,
    MAX_DAILY_LOSS_USD,
    ASSETS_DIR,
    BASE_DIR
)
from hitl.telegram_client import TelegramClient
from hitl.capture import capture_tradingview, capture_multi_timeframe
from hitl.mt5_engine import MT5Engine
from hitl.watchdog import MarketWatchdog
from hitl.macro_calendar import get_upcoming_events
from hitl.council import convene_investment_council

# Persistent Mobile Bottom Menu (Reply Keyboard)
MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "💷 GBP Full Pack (Charts + Council)"}, {"text": "🥇 Gold Full Pack (Charts + Council)"}],
        [{"text": "🌅 Morning Briefing"}, {"text": "🔍 Review Council"}],
        [{"text": "📋 Pending Orders"}, {"text": "📊 Open Positions"}],
        [{"text": "🛡️ Account Status"}, {"text": "❓ Help & Syntax"}]
    ],
    "resize_keyboard": True,
    "is_persistent": True
}


def save_chat_id_to_env(chat_id: int | str):
    """Saves the authorized user's chat_id into .env for persistence."""
    env_path = BASE_DIR / ".env"
    lines = []
    found = False
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for idx, line in enumerate(lines):
            if line.startswith("TELEGRAM_CHAT_ID="):
                lines[idx] = f"TELEGRAM_CHAT_ID={chat_id}\n"
                found = True
                break
    if not found:
        lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"[Bot] Successfully paired and locked to Chat ID: {chat_id}")


def parse_order_command(text: str) -> dict | None:
    """Parses buy/sell limit commands with positional or named parameters."""
    text = text.strip()
    m_dir = re.search(r'(?i)\b(buy|sell)[ _]?limit\b', text)
    if not m_dir:
        return None
    direction = m_dir.group(1).upper() + '_LIMIT'

    # Check for explicit symbol (e.g. XAUUSD, EURUSD, GBPUSD, etc.)
    symbol = DEFAULT_SYMBOL
    sym_m = re.search(r'(?i)\b([A-Z]{6}(?:_o)?)\b', text)
    if sym_m:
        symbol = sym_m.group(1).upper()

    # Check for keyword format: sl=..., tp=...
    sl_m = re.search(r'(?i)\bsl\s*[:=]?\s*([0-9.]+)', text)
    tp_m = re.search(r'(?i)\btp\s*[:=]?\s*([0-9.]+)', text)

    if sl_m and tp_m:
        sl = float(sl_m.group(1))
        tp = float(tp_m.group(1))
        cleaned = re.sub(r'(?i)\b(buy|sell)[ _]?limit\b', '', text)
        cleaned = re.sub(r'(?i)\bsl\s*[:=]?\s*[0-9.]+', '', cleaned)
        cleaned = re.sub(r'(?i)\btp\s*[:=]?\s*[0-9.]+', '', cleaned)
        if sym_m:
            cleaned = cleaned.replace(sym_m.group(1), '')
        nums = re.findall(r'[0-9]+(?:\.[0-9]+)?', cleaned)
        if nums:
            return {'symbol': symbol, 'type': direction, 'entry': float(nums[0]), 'sl': sl, 'tp': tp}
    else:
        # Positional format: /buylimit [sym] entry sl tp
        cleaned = text
        if sym_m:
            cleaned = cleaned.replace(sym_m.group(1), '')
        nums = re.findall(r'[0-9]+(?:\.[0-9]+)?', cleaned)
        if len(nums) >= 3:
            return {'symbol': symbol, 'type': direction, 'entry': float(nums[0]), 'sl': float(nums[1]), 'tp': float(nums[2])}

    return None


def _chart_worker(client: TelegramClient, chat_id: int | str, symbol: str):
    is_gbp = "GBP" in symbol.upper()
    is_euro = "EUR" in symbol.upper()
    if is_gbp:
        sym_name = "GBPUSD"
        sym_icon = "💷"
        pack_key = "gbp"
    elif is_euro:
        sym_name = "EURUSD"
        sym_icon = "💶"
        pack_key = "eur"
    else:
        sym_name = "XAUUSD"
        sym_icon = "🥇"
        pack_key = "gold"

    client.send_message(chat_id, f"📸 *Capturing 4-timeframe album for {sym_icon} {sym_name} (1D, 1H, 15M, 5M)...*")

    media_items = capture_multi_timeframe(sym_name)
    if not media_items:
        # Fallback to direct MT5 candlestick chart rendering
        try:
            from hitl.backtest.chart_renderer import render_candlestick_chart, create_mtf_grid_image, extract_chart_landmarks
            from hitl.backtest.data_feed import _convert_records
            import MetaTrader5 as mt5
            engine = MT5Engine()
            res_sym = engine.resolve_symbol(sym_name)
            if engine.ensure_connected() and res_sym:
                r1d = _convert_records(mt5.copy_rates_from_pos(res_sym, mt5.TIMEFRAME_D1, 0, 90))
                r1h = _convert_records(mt5.copy_rates_from_pos(res_sym, mt5.TIMEFRAME_H1, 0, 80))
                r15m = _convert_records(mt5.copy_rates_from_pos(res_sym, mt5.TIMEFRAME_M15, 0, 60))
                r5m = _convert_records(mt5.copy_rates_from_pos(res_sym, mt5.TIMEFRAME_M5, 0, 60))
                r5m_full = _convert_records(mt5.copy_rates_from_pos(res_sym, mt5.TIMEFRAME_M5, 0, 200))
                landmarks = extract_chart_landmarks(sym_name, r1d, r5m_full)
                
                out_dir = BASE_DIR / "analysis_assets" / "mtf"
                out_dir.mkdir(parents=True, exist_ok=True)
                
                p_1d = str(out_dir / f"{sym_name}_1D.png")
                p_1h = str(out_dir / f"{sym_name}_1H.png")
                p_15m = str(out_dir / f"{sym_name}_15M.png")
                p_5m = str(out_dir / f"{sym_name}_5M.png")
                p_grid = str(out_dir / f"{sym_name}_MTF_GRID.png")
                
                render_candlestick_chart(r1d, sym_name, "1D", p_1d)
                render_candlestick_chart(r1h, sym_name, "1H", p_1h, horizontal_levels=landmarks)
                render_candlestick_chart(r15m, sym_name, "15M", p_15m, horizontal_levels=landmarks)
                render_candlestick_chart(r5m, sym_name, "5M", p_5m, horizontal_levels=landmarks)
                create_mtf_grid_image(Path(p_1d), Path(p_1h), Path(p_15m), Path(p_5m), Path(p_grid))
                
                media_items = [
                    {"path": p_1d, "caption": f"{sym_icon} *{sym_name} · 1D (MT5 Live Feed)*\n📌 _Daily Macro Order Flow_"},
                    {"path": p_1h, "caption": f"{sym_icon} *{sym_name} · 1H (MT5 Live Feed)*\n📌 _Major Structure & Intraday Trend_"},
                    {"path": p_15m, "caption": f"{sym_icon} *{sym_name} · 15M (MT5 Live Feed)*\n📌 _Liquidity Sweeps & Key POIs_"},
                    {"path": p_5m, "caption": f"{sym_icon} *{sym_name} · 5M (MT5 Live Feed)*\n📌 _M5 Execution & Displacement FVG_"}
                ]
        except Exception as e:
            print(f"[Chart Worker] Fallback chart error: {e}")

    if media_items:
        # 1. Deliver 4-photo album immediately
        client.send_media_group(chat_id, media_items)

        # 2. Convene Tactical Council Silently (No raw transcript spam)
        try:
            report = convene_investment_council(sym_name, mode="tactical")
            if report:
                from hitl.live_radar import PENDING_EXECUTION_PLANS
                from hitl.council_decisions import log_council_decision

                from hitl.council import parse_council_decision
                decision = parse_council_decision(report)

                m_exec = re.search(r'(?i)Executive Summary & Critical Trigger[:\* ]+\s*(.+)', report)
                if m_exec:
                    clean_verdict = m_exec.group(1).strip().split('\n')[0].strip()
                    clean_verdict = re.sub(r'^[•\*\-\s]+', '', clean_verdict)
                else:
                    clean_verdict = "Council recommends standing aside pending higher-conviction liquidity sweep."

                plan_id = f"PLN-{sym_name}-{int(time.time())}"
                plan = None
                if decision != "STAND_ASIDE" and 'landmarks' in locals() and landmarks:
                    from hitl.tools.smc_tools import build_validated_order_plan
                    plan, _ = build_validated_order_plan(
                        decision=decision,
                        poi_selection="PROXIMAL_EDGE",
                        landmarks=landmarks
                    )

                engine = MT5Engine()
                is_demo = engine.is_demo_account()
                ticket = None
                auto_placed = False

                if plan and is_demo:
                    res_sym = engine.resolve_symbol(sym_name)
                    ok, fb, ticket = engine.place_limit_order(
                        symbol=res_sym,
                        order_type_str=decision,
                        price=plan['entry'],
                        sl=plan['sl'],
                        tp=plan['tp'],
                        lot=BASE_LOT,
                        is_autonomous=True
                    )
                    if ok:
                        auto_placed = True

                PENDING_EXECUTION_PLANS[plan_id] = {
                    "symbol": sym_name,
                    "clean_sym": sym_name,
                    "type": decision,
                    "plan": plan,
                    "ticket": ticket,
                    "full_report": report,
                    "created_at": time.time()
                }

                # Log decision to persistent ledger for Review Council audits
                log_council_decision(
                    symbol=sym_name,
                    decision=decision,
                    reason=clean_verdict,
                    full_report=report,
                    plan=plan
                )

                btn_row = [
                    {"text": f"📸 Refresh Charts", "callback_data": f"pack_{pack_key}"},
                    {"text": "📜 View Full Deliberation", "callback_data": f"show_report_{plan_id}"}
                ]
                if auto_placed and ticket:
                    buttons = {
                        "inline_keyboard": [
                            [{"text": f"❌ Cancel Order #{ticket}", "callback_data": f"cancel_{ticket}"}],
                            btn_row
                        ]
                    }
                else:
                    buttons = {"inline_keyboard": [btn_row]}

                auto_header = ""
                if auto_placed and ticket:
                    auto_header = f"🚀 *[AUTONOMOUS DEMO EXECUTION · Ticket #{ticket}]*\n"
                elif plan and not is_demo:
                    auto_header = f"🔒 *[LIVE ACCOUNT · Requires Manual Approval]*\n"

                summary_card = (
                    f"{auto_header}"
                    f"🏛️ *{sym_icon} {sym_name} · Council Assessment*\n\n"
                    f"⚖️ *Directive:* `{decision.replace('_', ' ')}`\n"
                    f"🛑 *Final Verdict:* {clean_verdict}"
                )
                client.send_message(chat_id, summary_card, reply_markup=buttons)
            else:
                client.send_message(chat_id, "⚠️ *Council deliberation unavailable.* Please retry in a few moments.")
        except Exception as e:
            print(f"[Council Worker] Error: {e}")
            client.send_message(chat_id, f"⚠️ *Error convening council:*\n`{e}`")
    else:
        client.send_message(chat_id, "❌ *Error capturing charts!* Please verify broker connection.")


def _council_worker(client: TelegramClient, chat_id: int | str, symbol: str):
    is_gbp = "GBP" in symbol.upper()
    is_euro = "EUR" in symbol.upper()
    if is_gbp:
        sym_name = "GBPUSD"
        sym_icon = "💷"
        pack_key = "gbp"
    elif is_euro:
        sym_name = "EURUSD"
        sym_icon = "💶"
        pack_key = "eur"
    else:
        sym_name = "XAUUSD"
        sym_icon = "🥇"
        pack_key = "gold"

    try:
        report = convene_investment_council(sym_name, mode="tactical")
        if report:
            from hitl.live_radar import PENDING_EXECUTION_PLANS
            from hitl.council_decisions import log_council_decision
            from hitl.council import assemble_council_intelligence

            from hitl.council import parse_council_decision
            decision = parse_council_decision(report)

            m_exec = re.search(r'(?i)Executive Summary & Critical Trigger[:\* ]+\s*(.+)', report)
            if m_exec:
                clean_verdict = m_exec.group(1).strip().split('\n')[0].strip()
                clean_verdict = re.sub(r'^[•\*\-\s]+', '', clean_verdict)
            else:
                clean_verdict = "Council recommends standing aside pending higher-conviction liquidity sweep."

            plan_id = f"PLN-{sym_name}-{int(time.time())}"
            plan = None
            if decision != "STAND_ASIDE":
                dossier = assemble_council_intelligence(sym_name)
                landmarks = dossier.get("landmarks") if dossier else None
                if landmarks:
                    from hitl.tools.smc_tools import build_validated_order_plan
                    plan, _ = build_validated_order_plan(
                        decision=decision,
                        poi_selection="PROXIMAL_EDGE",
                        landmarks=landmarks
                    )

            engine = MT5Engine()
            is_demo = engine.is_demo_account()
            ticket = None
            auto_placed = False

            if plan and is_demo:
                res_sym = engine.resolve_symbol(sym_name)
                ok, fb, ticket = engine.place_limit_order(
                    symbol=res_sym,
                    order_type_str=decision,
                    price=plan['entry'],
                    sl=plan['sl'],
                    tp=plan['tp'],
                    lot=BASE_LOT,
                    is_autonomous=True
                )
                if ok:
                    auto_placed = True

            PENDING_EXECUTION_PLANS[plan_id] = {
                "symbol": sym_name,
                "clean_sym": sym_name,
                "type": decision,
                "plan": plan,
                "ticket": ticket,
                "full_report": report,
                "created_at": time.time()
            }

            log_council_decision(
                symbol=sym_name,
                decision=decision,
                reason=clean_verdict,
                full_report=report,
                plan=plan
            )

            btn_row = [
                {"text": f"📸 Refresh {sym_name} Charts", "callback_data": f"pack_{pack_key}"},
                {"text": "📜 View Full Deliberation", "callback_data": f"show_report_{plan_id}"}
            ]
            if auto_placed and ticket:
                action_buttons = {
                    "inline_keyboard": [
                        [{"text": f"❌ Cancel Order #{ticket}", "callback_data": f"cancel_{ticket}"}],
                        btn_row
                    ]
                }
            else:
                action_buttons = {"inline_keyboard": [btn_row]}

            auto_header = ""
            if auto_placed and ticket:
                auto_header = f"🚀 *[AUTONOMOUS DEMO EXECUTION · Ticket #{ticket}]*\n"
            elif plan and not is_demo:
                auto_header = f"🔒 *[LIVE ACCOUNT · Requires Manual Approval]*\n"

            summary_card = (
                f"{auto_header}"
                f"🏛️ *{sym_icon} {sym_name} · Council Assessment*\n\n"
                f"⚖️ *Directive:* `{decision.replace('_', ' ')}`\n"
                f"🛑 *Final Verdict:* {clean_verdict}"
            )
            client.send_message(chat_id, summary_card, reply_markup=action_buttons)
        else:
            client.send_message(chat_id, f"⚠️ *Council convening error for {sym_icon} {sym_name}.*")
    except Exception as e:
        print(f"[Council Worker] Error: {e}")
        client.send_message(chat_id, f"⚠️ *Error convening council:*\n`{e}`")


def handle_council_command(client: TelegramClient, chat_id: int | str, symbol: str = "XAUUSD"):
    """Spawns background worker to convene the 5-member investment council."""
    t = threading.Thread(target=_council_worker, args=(client, chat_id, symbol), daemon=True)
    t.start()


def handle_chart_command(client: TelegramClient, chat_id: int | str, symbol: str = "XAUUSD"):
    """Spawns background worker to capture charts and invoke Antigravity AI without blocking bot polling."""
    t = threading.Thread(target=_chart_worker, args=(client, chat_id, symbol), daemon=True)
    t.start()


def handle_orders_command(client: TelegramClient, engine: MT5Engine, chat_id: int | str):
    """Lists all active pending orders with inline cancellation buttons."""
    orders = engine.get_pending_orders()
    if not orders:
        client.send_message(chat_id, "📭 No active pending limit orders found.")
        return

    text = f"📋 *Active Pending Orders ({len(orders)} active):*\n\n"
    keyboard = []
    for o in orders:
        text += (
            f"🔹 *Ticket #{o['ticket']}* | {o['type']}\n"
            f"   Symbol: `{o['symbol']}` | Lot: `{o['volume']}`\n"
            f"   Entry: `{o['price_open']}` | SL: `{o['sl']}` | TP: `{o['tp']}`\n\n"
        )
        keyboard.append([{"text": f"❌ Cancel #{o['ticket']}", "callback_data": f"cancel_{o['ticket']}"}])

    client.send_message(chat_id, text, reply_markup={"inline_keyboard": keyboard})


def handle_positions_command(client: TelegramClient, engine: MT5Engine, chat_id: int | str):
    """Lists currently open filled positions."""
    positions = engine.get_open_positions()
    if not positions:
        client.send_message(chat_id, "📭 No open positions at this moment.")
        return

    text = f"📊 *Open Positions ({len(positions)} active):*\n\n"
    for p in positions:
        pnl_icon = "🟢" if p['profit'] >= 0 else "🔴"
        text += (
            f"{pnl_icon} *Ticket #{p['ticket']}* | {p['type']} `{p['symbol']}`\n"
            f"   Lot: `{p['volume']}` | Net PnL: *${p['profit']:.2f}*\n"
            f"   Entry: `{p['price_open']}` | Current: `{p['price_current']}`\n"
            f"   SL: `{p['sl']}` | TP: `{p['tp']}`\n\n"
        )
    client.send_message(chat_id, text)


def handle_news_command(client: TelegramClient, chat_id: int | str, symbol: str = "XAUUSD"):
    """Displays today's and upcoming high-impact economic calendar events in Tehran local time."""
    events = get_upcoming_events(symbol, hours_ahead=24)
    if not events:
        client.send_message(
            chat_id,
            f"📅 *Economic Calendar (Next 24h - {symbol}):*\n\n"
            f"📭 No high or medium-impact events scheduled for this window."
        )
        return

    text = f"📅 *Upcoming High/Med Impact Events ({symbol}):*\n\n"
    for e in events:
        badge = "🔴 High Impact" if e["impact"] == "High" else "🟡 Medium Impact"
        away_str = f"in {e['minutes_away']}m" if e["minutes_away"] > 0 else f"{abs(e['minutes_away'])}m ago"
        text += (
            f"🔹 *{e['time_str']} Tehran* | `{e['country']}` [{badge}]\n"
            f"   📌 *Event:* {e['title']}\n"
            f"   ⏱ Timing: _{away_str}_\n"
            f"   📊 Forecast: `{e['forecast']}` | Previous: `{e['previous']}`\n\n"
        )
    client.send_message(chat_id, text)


def handle_status_command(client: TelegramClient, engine: MT5Engine, chat_id: int | str):
    """Reports overall account and system operational status."""
    acc = engine.get_account_summary()
    if not acc:
        client.send_message(chat_id, "⚠️ *Status:* Unable to connect to MetaTrader 5.")
        return

    pending_count = len(engine.get_pending_orders())
    pos_count = len(engine.get_open_positions())
    perf = engine.get_daily_performance()

    if perf["circuit_tripped"]:
        breaker_badge = f"⛔ *TRIPPED (Blocked):* {perf['reason']}"
    else:
        pnl_val = perf['realized_pnl']
        sign = "+" if pnl_val >= 0 else "-"
        breaker_badge = f"🟢 *SAFE:* Realized Today `{sign}${abs(pnl_val):.2f}` (Daily Loss Cap: `${MAX_DAILY_LOSS_USD:.2f}`)"

    in_session, session_msg = engine.is_within_session_hours("XAUUSD")
    session_badge = "🟢 *Active Session* (11:30 - 21:00 Tehran)" if in_session else "🌙 *Outside Trading Hours*"

    in_cd, rem_min, cd_reason = engine.get_cooldown_status()
    cd_badge = f"⏳ *Active* ({rem_min}m remaining)" if in_cd else "🟢 *Idle* (No Restrictions)"

    text = (
        f"🛡️ *TradingGuard HITL System Status*\n\n"
        f"👤 *Account:* `{acc['login']}` ({acc['server']})\n"
        f"💵 *Balance:* `${acc['balance']:.2f}`\n"
        f"📈 *Live Equity:* `${acc['equity']:.2f}`\n"
        f"💰 *Floating PnL:* `${acc['profit']:.2f}`\n\n"
        f"📋 *Pending Limit Orders:* {pending_count}\n"
        f"🎯 *Active Positions:* {pos_count}\n"
        f"⚖️ *Per-Trade Risk Cap:* `${MAX_RISK_USD:.2f}` (Lot: {BASE_LOT})\n"
        f"🛡️ *Daily Circuit Breaker:* {breaker_badge}\n"
        f"⏰ *Trading Session:* {session_badge}\n"
        f"⏱ *Cooldown Status:* {cd_badge}\n"
        f"📡 *Telegram Proxy:* Connected"
    )
    client.send_message(chat_id, text)


def run_bot():
    token = TELEGRAM_BOT_TOKEN
    proxy = TELEGRAM_PROXY

    if not token:
        print("[Bot Error] TELEGRAM_BOT_TOKEN is not set.")
        sys.exit(1)

    client = TelegramClient(token=token, proxy=proxy)
    me = None
    for attempt in range(1, 6):
        me = client.get_me()
        if me and me.get("ok"):
            break
        print(f"[Bot] Connection attempt {attempt}/5 failed. Retrying in 2s...")
        time.sleep(2)

    if not me or not me.get("ok"):
        print("[Bot Error] Failed to connect to Telegram Bot API after 5 attempts. Check Token or Proxy.")
        sys.exit(1)

    bot_username = me["result"]["username"]
    print("=" * 50)
    print(f"TradingGuard HITL System Online: @{bot_username}")
    print(f"Proxy configured: {proxy}")
    print("=" * 50)

    engine = MT5Engine()
    watchdog = MarketWatchdog(
        engine,
        client,
        on_auto_dispatch=lambda sym: handle_chart_command(client, authorized_chat_id, sym)
    )

    authorized_chat_id = TELEGRAM_CHAT_ID
    offset = None
    last_watchdog_poll = 0.0

    while True:
        try:
            # 1. Run Market Watchdog Loop Every 3 Seconds
            now = time.time()
            if now - last_watchdog_poll >= 3.0:
                watchdog.poll()
                last_watchdog_poll = now

            # 2. Poll Telegram Updates (short timeout so watchdog stays responsive)
            updates = client.get_updates(offset=offset, timeout=3)
            for upd in updates:
                offset = upd["update_id"] + 1

                # Handle Text Messages
                if "message" in upd and "text" in upd["message"]:
                    msg = upd["message"]
                    sender_id = msg["chat"]["id"]
                    text = msg["text"].strip()

                    # First-time pairing logic
                    if not authorized_chat_id:
                        if text == "/start":
                            save_chat_id_to_env(sender_id)
                            authorized_chat_id = str(sender_id)
                            client.send_message(
                                sender_id,
                                "✅ *TradingGuard HITL System Paired Successfully!*\n\n"
                                "Core Commands:\n"
                                "📸 `/chart` : Multi-timeframe institutional chart analysis\n"
                                "⚡ `/buylimit 3865 3858 3885` : Place Buy Limit order on Gold\n"
                                "⚡ `/selllimit 3885 3892 3865` : Place Sell Limit order on Gold\n"
                                "📋 `/orders` : Active pending orders with instant cancellation\n"
                                "📊 `/positions` : Current live open positions\n"
                                "🛡️ `/status` : Account balance, floating PnL, and risk shield"
                            )
                            continue
                        else:
                            client.send_message(sender_id, "⚠️ Please send `/start` first to pair your account.")
                            continue

                    # Strict whitelist authorization check
                    if str(sender_id) != str(authorized_chat_id):
                        print(f"[Security] Rejected unauthorized user ID: {sender_id}")
                        continue

                    # A) Check if message is a Limit Order Command
                    order_spec = parse_order_command(text)
                    if order_spec:
                        # Attempt to place limit order
                        success, feedback, ticket = engine.place_limit_order(
                            symbol=order_spec['symbol'],
                            order_type_str=order_spec['type'],
                            price=order_spec['entry'],
                            sl=order_spec['sl'],
                            tp=order_spec['tp'],
                            lot=BASE_LOT
                        )
                        if success:
                            # Re-fetch details for card
                            _, _, details = engine.validate_limit_order(
                                symbol=order_spec['symbol'],
                                order_type_str=order_spec['type'],
                                price=order_spec['entry'],
                                sl=order_spec['sl'],
                                tp=order_spec['tp'],
                                lot=BASE_LOT
                            )
                            order_label = "BUY LIMIT" if "BUY" in order_spec['type'] else "SELL LIMIT"
                            card = (
                                f"✅ *Limit Order Placed Successfully!*\n\n"
                                f"📌 *Ticket:* `#{ticket}`\n"
                                f"🔹 *Type:* `{order_label}`\n"
                                f"📍 *Entry:* `{details.get('entry')}`\n"
                                f"🛑 *SL:* `{details.get('sl')}`\n"
                                f"   • Price Risk: `${details.get('price_risk_usd')}` | Friction: `${details.get('friction_usd')}`\n"
                                f"   • Total Risk: *${details.get('risk_usd')}*\n"
                                f"🎯 *TP:* `{details.get('tp')}` (Target Reward: *${details.get('reward_usd')}*)\n"
                                f"⚖️ *R:R Ratio:* `1:{details.get('rr')}` | Lot: `{BASE_LOT}`\n\n"
                                f"🛡️ *Velocity Guard Active:* Order will auto-cancel if adverse momentum spike triggers."
                            )
                            buttons = {
                                "inline_keyboard": [
                                    [{"text": f"❌ Cancel Order #{ticket}", "callback_data": f"cancel_{ticket}"}]
                                ]
                            }
                            client.send_message(sender_id, card, reply_markup=buttons)
                        else:
                            # Send rejection or failure message
                            client.send_message(sender_id, f"⚠️ *Order Placement Rejected:*\n{feedback}")
                        continue

                    # B) Standard Command Dispatcher
                    # 1. Council Only (Without recapturing charts)
                    if any(k in text.lower() for k in ["/council", "council", "شورا", "مجلس"]) and not any(k in text.lower() for k in ["چارت", "پکیج", "کامل"]):
                        if any(k in text.lower() for k in ["💷", "پوند", "gbp"]):
                            handle_council_command(client, sender_id, "GBPUSD")
                        elif any(k in text.lower() for k in ["💶", "یورو", "eur"]):
                            handle_council_command(client, sender_id, "EURUSD")
                        else:
                            handle_council_command(client, sender_id, "XAUUSD")
                    # 2. Complete Analysis Package (4-Timeframe Charts + Council Deliberation)
                    elif any(k in text.lower() for k in ["💷", "پوند", "gbp"]):
                        handle_chart_command(client, sender_id, "GBPUSD")
                    elif any(k in text.lower() for k in ["💶", "یورو", "eur"]):
                        handle_chart_command(client, sender_id, "EURUSD")
                    elif any(k in text.lower() for k in ["🥇", "طلا", "gold", "/gold", "/chart", "چارت", "پکیج"]):
                        handle_chart_command(client, sender_id, "XAUUSD")
                    elif any(k in text.lower() for k in ["/review", "review", "/audit", "audit", "بازبینی", "شورای بازبینی", "review council", "/postmortem", "postmortem", "post-mortem", "جلسه بازبینی"]):
                        from hitl.review_engine import convene_review_council
                        convene_review_council(engine, client, sender_id)
                    elif any(k in text.lower() for k in ["/briefing", "briefing", "morning", "صبحگاهی", "شروع روز", "morning briefing"]):
                        from hitl.review_engine import run_morning_briefing
                        run_morning_briefing(engine, client, sender_id)
                    elif any(k in text for k in ["📋", "اردر", "/orders", "orders"]):
                        handle_orders_command(client, engine, sender_id)
                    elif any(k in text for k in ["📊", "پوزیشن", "/positions", "positions"]):
                        handle_positions_command(client, engine, sender_id)
                    elif any(k in text for k in ["🛡️", "وضعیت", "/status", "status"]):
                        handle_status_command(client, engine, sender_id)
                    elif text.startswith("/cancel"):
                        parts = text.split()
                        if len(parts) >= 2 and parts[1].isdigit():
                            t = int(parts[1])
                            confirm_buttons = {
                                "inline_keyboard": [
                                    [
                                        {"text": f"✅ Yes, Cancel Order #{t}", "callback_data": f"confirm_cancel_{t}"},
                                        {"text": "🔙 Keep Order", "callback_data": f"keep_{t}"}
                                    ]
                                ]
                            }
                            client.send_message(
                                sender_id,
                                f"⚠️ *Cancel Order Confirmation*\nAre you sure you want to cancel limit order `#{t}`?",
                                reply_markup=confirm_buttons
                            )
                        else:
                            handle_orders_command(client, engine, sender_id)
                    elif any(k in text.lower() for k in ["/ping", "ping", "/health", "health", "heartbeat", "پینگ"]):
                        watchdog.send_heartbeat(sender_id, is_manual=True)
                    elif any(k in text.lower() for k in ["/news", "news", "تقویم", "اخبار"]):
                        handle_news_command(client, sender_id, "XAUUSD")
                    elif any(k in text for k in ["❓", "راهنما", "/help", "/start", "help"]):
                        client.send_message(
                            sender_id,
                            "🛡️ *TradingGuard HITL Autonomous Guidance & Execution System*\n\n"
                            "📸 *Full Analysis Packages (Charts + Council):*\n"
                            "• Tap `🥇 Gold Full Pack` : 4-timeframe dossier + 6-Seat Council\n"
                            "• Tap `💷 GBP Full Pack`  : 4-timeframe dossier + 6-Seat Council\n"
                            "• Tap `💶 EUR Full Pack`  : 4-timeframe dossier + 6-Seat Council\n\n"
                            "🏛️ *Council On-Demand (No Chart Re-Capture):*\n"
                            "• Tap `🏛️ GBP Council Only` or command `/council`\n\n"
                            "⚡ *Direct Limit Order Syntax:*\n"
                            "`/buylimit 3865 3858 3885`\n"
                            "`/selllimit 3885 3892 3865`\n"
                            "or named:\n"
                            "`Buy Limit 3865 SL=3858 TP=3885`\n\n"
                            "💡 *Risk Cap:* Strict $12.00 maximum risk ceiling including friction.",
                            reply_markup=MAIN_KEYBOARD
                        )
                    else:
                        client.send_message(
                            sender_id,
                            f"Unknown command: `{text}`\nUse the bottom buttons or /help for guidance.",
                            reply_markup=MAIN_KEYBOARD
                        )

                # Handle Inline Button Clicks
                elif "callback_query" in upd:
                    cb = upd["callback_query"]
                    sender_id = cb["message"]["chat"]["id"]
                    data = cb.get("data", "")
                    client.answer_callback_query(cb["id"])

                    if str(sender_id) == str(authorized_chat_id):
                        if data in ["cmd_chart", "pack_gold"]:
                            handle_chart_command(client, sender_id, "XAUUSD")
                        elif data == "pack_eur":
                            handle_chart_command(client, sender_id, "EURUSD")
                        elif data == "pack_gbp":
                            handle_chart_command(client, sender_id, "GBPUSD")
                        elif data in ["council_gold", "council_xauusd"]:
                            handle_council_command(client, sender_id, "XAUUSD")
                        elif data in ["council_eur", "council_eurusd"]:
                            handle_council_command(client, sender_id, "EURUSD")
                        elif data in ["council_gbp", "council_gbpusd"]:
                            handle_council_command(client, sender_id, "GBPUSD")
                        elif data.startswith("cancel_"):
                            ticket_str = data.split("_")[1]
                            if ticket_str.isdigit():
                                confirm_buttons = {
                                    "inline_keyboard": [
                                        [
                                            {"text": f"✅ Yes, Cancel Order #{ticket_str}", "callback_data": f"confirm_cancel_{ticket_str}"},
                                            {"text": "🔙 Keep Order", "callback_data": f"keep_{ticket_str}"}
                                        ]
                                    ]
                                }
                                client.send_message(
                                    sender_id,
                                    f"⚠️ *Cancel Order Confirmation*\nAre you sure you want to cancel limit order `#{ticket_str}`?",
                                    reply_markup=confirm_buttons
                                )
                        elif data.startswith("confirm_cancel_"):
                            ticket_str = data.split("_")[2]
                            if ticket_str.isdigit():
                                ok, res_msg = engine.cancel_order(int(ticket_str))
                                client.send_message(sender_id, f"🗑️ {res_msg}")
                        elif data.startswith("keep_"):
                            ticket_str = data.split("_")[1]
                            client.send_message(sender_id, f"👁 Order #{ticket_str} retained and active.")
                        elif data.startswith("exec_plan_"):
                            from hitl.live_radar import PENDING_EXECUTION_PLANS
                            plan_id = data.replace("exec_plan_", "")
                            plan = PENDING_EXECUTION_PLANS.get(plan_id)
                            if not plan:
                                client.send_message(sender_id, "⚠️ This order plan has expired or was already executed.")
                            else:
                                success, feedback, ticket = engine.place_limit_order(
                                    symbol=plan['symbol'],
                                    order_type_str=plan['type'],
                                    price=plan['entry'],
                                    sl=plan['sl'],
                                    tp=plan['tp'],
                                    lot=plan['lot']
                                )
                                if success:
                                    del PENDING_EXECUTION_PLANS[plan_id]
                                    order_label = plan['type'].replace('_', ' ')
                                    fmt = ".5f" if "GBP" in plan['symbol'] or "EUR" in plan['symbol'] else ".2f"
                                    client.send_message(
                                        sender_id,
                                        f"🚀 *Order Approved & Placed in MetaTrader 5!*\n\n"
                                        f"📌 *Ticket:* `#{ticket}`\n"
                                        f"🔹 *Type:* `{order_label}`\n"
                                        f"📍 *Entry:* `{plan['entry']:{fmt}}`\n"
                                        f"🛑 *SL:*    `{plan['sl']:{fmt}}`\n"
                                        f"🎯 *TP:*    `{plan['tp']:{fmt}}` (R:R: *1:{plan['rr']:.2f}*)\n"
                                        f"⚖️ *Lot:*   `{plan['lot']}`\n\n"
                                        f"🛡️ *Velocity Guard Activated:*\n"
                                        f"Order will be auto-cancelled if price exhibits adverse momentum before fill."
                                    )
                                else:
                                    client.send_message(sender_id, f"⚠️ *MetaTrader 5 Placement Error:*\n`{feedback}`")
                        elif data.startswith("veto_plan_"):
                            from hitl.live_radar import PENDING_EXECUTION_PLANS
                            plan_id = data.replace("veto_plan_", "")
                            if plan_id in PENDING_EXECUTION_PLANS:
                                del PENDING_EXECUTION_PLANS[plan_id]
                            client.send_message(
                                sender_id,
                                "🛡️ *Order Vetoed by Seat #7 (Lead Human Partner).*\nCapital preserved. No order was placed."
                            )
                        elif data.startswith("show_report_"):
                            from hitl.live_radar import PENDING_EXECUTION_PLANS
                            plan_id = data.replace("show_report_", "")
                            plan = PENDING_EXECUTION_PLANS.get(plan_id)
                            if plan and plan.get("full_report"):
                                client.send_message(
                                    sender_id,
                                    f"🏛️ *Full Council Deliberation:*\n\n{plan['full_report']}"
                                )
                            else:
                                client.send_message(
                                    sender_id,
                                    "⚠️ Deliberation text is no longer available or has expired."
                                )

        except KeyboardInterrupt:
            print("\n[Bot] Shutting down gracefully...")
            break
        except Exception as e:
            print(f"[Bot] Polling loop exception: {e}")
            time.sleep(2)


if __name__ == '__main__':
    run_bot()
