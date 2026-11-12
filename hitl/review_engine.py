"""
TradingGuard HITL - Closed-Loop Institutional Review Engine
1. Decision Audit (شورای بازبینی - Decision Audit):
   - Audits past Council decisions (Stand Asides and Placed Orders) against real MT5 market outcomes.
   - Evaluates whether Stand Asides were protective (saved capital) or flawed (missed winners).
   - Evaluates whether order plans were filled, reached TP, or stopped out.
   - Records factual audit summaries to `hitl/memory/council_playbook.json`.
   - Dispatches a concise, high-density Decision Audit Card to Telegram.

   NOTE (Pack 5): this is a DETERMINISTIC audit — no LLM is involved.

2. Pre-Market Morning Briefing (Scheduled pre-London):
   - Runs a real deterministic analysis of the previous trading day (OHLC range, net change,
     SMC Killzone screener detections + M1 evaluation, and yesterday's logged bot decisions).
   - Never recycles stale multi-day-old boilerplate lessons.
   - Analyzes live overnight Asian Range benchmarks (00:00 - 07:00 UTC, DST-corrected).
   - Resolves London/NY Killzone times dynamically via `hitl/backtest/session_clock.py`.
   - Fetches Tier 1 Macro Fundamental bias and scheduled high-impact news windows.
"""

import datetime
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo
import MetaTrader5 as mt5

from hitl.config import BASE_DIR, TELEGRAM_CHAT_ID, MAX_DAILY_LOSS_USD
from hitl.mt5_engine import MT5Engine
from hitl.telegram_client import TelegramClient
from hitl.council_memory import CouncilMemory
from hitl.council_decisions import (
    get_unreviewed_decisions,
    audit_decision_outcome,
    _load_log,
    _save_log,
)
from hitl.macro_calendar import get_upcoming_events
from hitl.macro_bias import calculate_htf_fundamental_bias
from hitl.backtest.data_feed import _convert_records
from hitl.backtest.session_clock import get_session_times_for_date
from hitl.replay_data import server_epoch_to_zones

TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_UTC = datetime.timezone.utc
TZ_ATHENS = ZoneInfo("Europe/Athens")
PORTFOLIO_SYMBOLS = ["XAUUSD", "GBPUSD", "NQ"]


def _previous_trading_date(ref_date: datetime.date) -> datetime.date:
    """Returns the most recent weekday strictly before `ref_date`."""
    d = ref_date - datetime.timedelta(days=1)
    while d.weekday() in (5, 6):
        d -= datetime.timedelta(days=1)
    return d


def _symbol_icon(sym: str) -> str:
    s = sym.upper()
    if "XAU" in s:
        return "🥇"
    if "GBP" in s:
        return "💷"
    if "BTC" in s:
        return "₿"
    if "NQ" in s or "NAS" in s:
        return "📊"
    if "EUR" in s:
        return "💶"
    return "📈"


def _scan_day_smc_setups(
    res_sym: str,
    sym: str,
    target_date: datetime.date,
    m5_bars: List[Dict[str, Any]],
    m1_bars: List[Dict[str, Any]],
    h1_bars: List[Dict[str, Any]],
    d1_bars: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Runs deterministic closed-bar SMC screening across London Open & NY Open
    on `target_date` and evaluates fills via `evaluate_council_decision`.
    """
    from bisect import bisect_right
    from hitl.backtest.fast_screener import screen_ict_session
    from hitl.backtest.evaluator import evaluate_council_decision
    import hitl.backtest.chart_renderer as chart_renderer

    stimes = get_session_times_for_date(target_date)
    lon_start = stimes["london"]["utc_time"]
    lon_end = lon_start + datetime.timedelta(hours=3)
    ny_start = stimes["new_york"]["utc_time"]
    ny_end = ny_start + datetime.timedelta(hours=3)

    h1_times = [b["time"] for b in h1_bars]
    d1_times = [b["time"] for b in d1_bars]

    # Pre-attach true UTC dt without mutating caller lists permanently
    for coll in (h1_bars, d1_bars):
        for b in coll:
            if "dt" not in b:
                b["dt"] = server_epoch_to_zones(b["time"])["utc_dt"]

    signals_found: List[Dict[str, Any]] = []
    seen_waves = set()
    orig_offset_fn = getattr(chart_renderer, "get_broker_utc_offset_seconds", None)

    try:
        for i, b in enumerate(m5_bars):
            z = server_epoch_to_zones(b["time"])
            utc_dt = z["utc_dt"]
            if utc_dt.date() != target_date:
                continue

            in_lon = lon_start <= utc_dt < lon_end
            in_ny = ny_start <= utc_dt < ny_end
            if not (in_lon or in_ny):
                continue

            hist_m5 = []
            for hb in m5_bars[max(0, i - 120) : i + 1]:
                hb_copy = dict(hb)
                hb_copy["dt"] = server_epoch_to_zones(hb["time"])["utc_dt"]
                hist_m5.append(hb_copy)
            if len(hist_m5) < 40:
                continue

            h1_idx = bisect_right(h1_times, b["time"])
            hist_h1 = h1_bars[max(0, h1_idx - 60) : h1_idx]
            d1_idx = bisect_right(d1_times, b["time"])
            hist_d1 = d1_bars[max(0, d1_idx - 15) : d1_idx]
            if len(hist_h1) < 10:
                continue

            if orig_offset_fn is not None:
                chart_renderer.get_broker_utc_offset_seconds = lambda off=z["offset_sec"]: off

            res = screen_ict_session(
                bars_5m=hist_m5,
                bars_1h=hist_h1,
                symbol=res_sym,
                session_hour=z["teh_dt"].hour,
                bars_1d=hist_d1 if hist_d1 else None,
                closed_bars_only=True,
            )

            if not (res.get("has_setup") and res.get("entry_ref") and res.get("sl_ref")):
                continue

            arch_id = res.get("archetype_id", "SETUP-ARCH-001")
            direction = "LONG" if "BULLISH" in res.get("setup_type", "").upper() else "SHORT"
            entry_p = float(res["entry_ref"])
            sl_p = float(res["sl_ref"])
            wave_key = (arch_id, direction, round(entry_p, 2))
            if wave_key in seen_waves:
                continue
            seen_waves.add(wave_key)

            sig_time = int(res.get("signal_bar_time") or hist_m5[-2]["time"])
            target_rr = float(res.get("recommended_target_rr") or 2.0)
            be_rr = res.get("recommended_be_rr", 1.2)
            risk_pts = abs(entry_p - sl_p)
            if risk_pts <= 0:
                continue
            tp_p = (entry_p + target_rr * risk_pts) if direction == "LONG" else (entry_p - target_rr * risk_pts)

            fwd_m1 = [m for m in m1_bars if m["time"] >= sig_time + 300]
            outcome_str = "UNFILLED"
            if fwd_m1:
                ev = evaluate_council_decision(
                    {
                        "decision": "BUY_LIMIT" if direction == "LONG" else "SELL_LIMIT",
                        "entry": entry_p,
                        "sl": sl_p,
                        "tp": tp_p,
                        "lot": 0.01,
                    },
                    fwd_m1,
                    symbol=res_sym,
                    breakeven_rr=be_rr,
                    target_rr_cap=7.5 if arch_id == "SETUP-ARCH-013" else 3.5,
                    max_risk_usd=20.0,
                )
                rr_val = ev.get("rr_realized")
                if rr_val is not None:
                    outcome_str = f"{ev['status']} ({rr_val:+.2f}R)"
                else:
                    outcome_str = ev.get("status", "EXPIRED")

            signals_found.append({
                "archetype": arch_id,
                "direction": direction,
                "time_tehran": server_epoch_to_zones(sig_time)["tehran_str"],
                "entry": round(entry_p, 5 if "GBP" in sym else 2),
                "outcome": outcome_str,
            })
    finally:
        if orig_offset_fn is not None:
            chart_renderer.get_broker_utc_offset_seconds = orig_offset_fn

    return signals_found


def analyze_previous_trading_day(
    engine: MT5Engine,
    target_date: datetime.date,
    symbols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Performs a factual analysis of `target_date` using real MT5 bars + SMC scan
    plus live decision log entries recorded strictly on `target_date`.
    """
    target_symbols = symbols or PORTFOLIO_SYMBOLS
    date_str = target_date.strftime("%Y-%m-%d")

    all_decisions = _load_log()
    day_decisions = [d for d in all_decisions if d.get("date_str") == date_str]
    stand_aside = sum(1 for d in day_decisions if d.get("decision") == "STAND_ASIDE")
    approved = sum(1 for d in day_decisions if d.get("decision") in ("BUY_LIMIT", "SELL_LIMIT"))
    missed_win = sum(1 for d in day_decisions if "MISSED WINNER" in str(d.get("review_verdict", "")))
    prot_veto = sum(
        1 for d in day_decisions
        if "PROTECTIVE VETO" in str(d.get("review_verdict", "")) or "ACCURATE VETO" in str(d.get("review_verdict", ""))
    )

    market_recap: List[Dict[str, Any]] = []
    if engine and engine.ensure_connected():
        # Fetch range in Europe/Athens server time covering target_date (+1d buffer before for MTF)
        start_dt = datetime.datetime.combine(target_date - datetime.timedelta(days=5), datetime.time(0, 0), tzinfo=TZ_UTC)
        end_dt = datetime.datetime.combine(target_date + datetime.timedelta(days=1), datetime.time(23, 59), tzinfo=TZ_UTC)

        for sym in target_symbols:
            res_sym = engine.resolve_symbol(sym)
            if not res_sym:
                continue
            r_m5 = mt5.copy_rates_range(res_sym, mt5.TIMEFRAME_M5, start_dt, end_dt)
            r_m1 = mt5.copy_rates_range(res_sym, mt5.TIMEFRAME_M1, start_dt, end_dt)
            r_h1 = mt5.copy_rates_from_pos(res_sym, mt5.TIMEFRAME_H1, 0, 200)
            r_d1 = mt5.copy_rates_from_pos(res_sym, mt5.TIMEFRAME_D1, 0, 40)

            if r_m5 is None or len(r_m5) == 0:
                continue

            m5_list = _convert_records(r_m5)
            m1_list = _convert_records(r_m1) if r_m1 is not None and len(r_m1) > 0 else []
            h1_list = _convert_records(r_h1) if r_h1 is not None and len(r_h1) > 0 else []
            d1_list = _convert_records(r_d1) if r_d1 is not None and len(r_d1) > 0 else []

            day_bars = [b for b in m5_list if server_epoch_to_zones(b["time"])["utc_dt"].date() == target_date]
            if not day_bars:
                continue

            day_open = float(day_bars[0]["open"])
            day_close = float(day_bars[-1]["close"])
            day_high = max(float(b["high"]) for b in day_bars)
            day_low = min(float(b["low"]) for b in day_bars)
            diff = day_close - day_open
            rng = day_high - day_low
            direction = "BULLISH" if diff > 0 else ("BEARISH" if diff < 0 else "FLAT")

            smc_signals = _scan_day_smc_setups(res_sym, sym, target_date, m5_list, m1_list, h1_list, d1_list)

            market_recap.append({
                "symbol": sym,
                "open": day_open,
                "high": day_high,
                "low": day_low,
                "close": day_close,
                "range_pts": round(rng, 5 if "GBP" in sym else 2),
                "change_pts": round(diff, 5 if "GBP" in sym else 2),
                "direction": direction,
                "smc_signals": smc_signals,
            })

    return {
        "date_str": date_str,
        "market_recap": market_recap,
        "live_decisions": {
            "total": len(day_decisions),
            "approved": approved,
            "stand_aside": stand_aside,
            "missed_winners": missed_win,
            "protective_vetoes": prot_veto,
        },
    }


def audit_past_decisions(
    engine: MT5Engine,
    client: TelegramClient,
    chat_id: Optional[int | str] = None,
) -> Dict[str, Any]:
    """
    Deterministic audit of recent Council decisions (شورای بازبینی).
    Strict date filtering: audits today's decisions or yesterday's trading day
    (never reaches back arbitrarily across stale weeks).
    """
    target_chat = chat_id or TELEGRAM_CHAT_ID
    now_dt = datetime.datetime.now(TZ_TEHRAN)
    today_str = now_dt.strftime("%Y-%m-%d")
    prev_str = _previous_trading_date(now_dt.date()).strftime("%Y-%m-%d")

    all_decisions = _load_log()
    recent_decisions = [d for d in all_decisions if d.get("date_str") == today_str]
    audit_target_str = today_str
    if not recent_decisions:
        recent_decisions = [d for d in all_decisions if d.get("date_str") == prev_str]
        audit_target_str = prev_str

    if not recent_decisions:
        card = (
            f"🏛️ *TRADINGGUARD REVIEW COUNCIL (DECISION AUDIT)*\n"
            f"📅 *Date:* `{now_dt.strftime('%A, %b %d, %Y')}`\n\n"
            f"📭 _No live Council decisions logged on `{today_str}` or `{prev_str}`._"
        )
        if target_chat and client:
            client.send_message(target_chat, card)
        return {"status": "NO_DECISIONS", "count": 0}

    audit_results = []
    missed_winners = 0
    protective_vetoes = 0
    accurate_entries = 0
    missed_by_symbol: Dict[str, int] = {}

    for d in recent_decisions:
        audit = audit_decision_outcome(d, engine)
        verdict = audit.get("verdict", "AUDITED")
        summary = audit.get("summary", "")

        if "MISSED WINNER" in verdict:
            missed_winners += 1
            sym = d.get("symbol", "UNKNOWN")
            missed_by_symbol[sym] = missed_by_symbol.get(sym, 0) + 1
        elif "PROTECTIVE VETO" in verdict or "ACCURATE VETO" in verdict:
            protective_vetoes += 1
        elif "WIN" in verdict or "ACCURATE" in verdict:
            accurate_entries += 1

        d["reviewed"] = True
        d["review_verdict"] = verdict
        d["review_notes"] = summary
        audit_results.append({"record": d, "audit": audit})

    _save_log(all_decisions)

    # Factual, unvarnished synthesis without hardcoded unauthorized rule flips
    parts = [f"Audited {len(audit_results)} decision(s) for `{audit_target_str}`:"]
    if accurate_entries:
        parts.append(f"{accurate_entries} accurate/winning execution(s)")
    if protective_vetoes:
        parts.append(f"{protective_vetoes} protective veto(es)")
    if missed_winners:
        breakdown = ", ".join(f"{s}: {c}" for s, c in sorted(missed_by_symbol.items()))
        parts.append(f"{missed_winners} counterfactual expansion(s) ({breakdown}) — inspect screener clock/gates before modifying ratified rules")
    if not (accurate_entries or protective_vetoes or missed_winners):
        parts.append("all outcomes neutral/unfilled")
    synthesis = " | ".join(parts)

    memory = CouncilMemory()
    memory.record_counterfactual_audit(
        symbol="MULTI",
        session_time=now_dt.strftime("%Y-%m-%d %H:%M"),
        discussed_setup=f"Review Council Audit ({audit_target_str}): {len(audit_results)} decisions evaluated",
        cio_decision="REVIEW_COUNCIL_AUDIT",
        forward_4h_max_gain=0.0,
        forward_4h_max_dd=0.0,
        forward_4h_close_change=0.0,
        verdict="AUDIT_SYNTHESIS",
        lesson=synthesis,
    )

    audit_items_text = []
    for idx, item in enumerate(audit_results, 1):
        rec = item["record"]
        aud = item["audit"]
        sym = rec["symbol"]
        icon = _symbol_icon(sym)
        time_str = rec.get("time_str", "")
        dec_type = rec["decision"].replace("_", " ")
        reason = rec.get("reason", "N/A")
        verdict_str = aud.get("verdict", "AUDITED")
        summary_str = aud.get("summary", "")

        audit_items_text.append(
            f"*{idx}. {time_str}* | {icon} *{sym} · [{dec_type}]*\n"
            f"   • *Reason Given:* _{reason}_\n"
            f"   • *Outcome:* {summary_str}\n"
            f"   • *Audit Verdict:* *{verdict_str}*"
        )

    all_audits_str = "\n\n".join(audit_items_text)

    card = (
        f"🏛️ *TRADINGGUARD REVIEW COUNCIL (DECISION AUDIT)*\n"
        f"📅 *Audited Date:* `{audit_target_str}`\n\n"
        f"🔍 *Past Decisions vs. Actual Market Outcomes ({len(audit_results)} evaluated):*\n\n"
        f"{all_audits_str}\n\n"
        f"📊 *Factual Summary:*\n"
        f"_{synthesis}_"
    )

    if target_chat and client:
        client.send_message(target_chat, card)

    return {
        "status": "COMPLETED",
        "decisions_audited": len(audit_results),
        "missed_winners": missed_winners,
        "protective_vetoes": protective_vetoes,
        "synthesis": synthesis,
        "timestamp": now_dt.isoformat(),
    }


def run_session_post_mortem(
    engine: MT5Engine,
    client: TelegramClient,
    chat_id: Optional[int | str] = None,
) -> Dict[str, Any]:
    """Alias for end-of-session decision audit."""
    return audit_past_decisions(engine, client, chat_id)


def run_morning_briefing(
    engine: MT5Engine,
    client: TelegramClient,
    chat_id: Optional[int | str] = None,
) -> Dict[str, Any]:
    """
    Executes automated Pre-Market Morning Briefing.
    Performs an authentic deterministic analysis of the previous trading day
    plus DST-accurate overnight Asian benchmarks and session open times.
    """
    target_chat = chat_id or TELEGRAM_CHAT_ID
    now_tehran = datetime.datetime.now(TZ_TEHRAN)
    prev_date = _previous_trading_date(now_tehran.date())

    # 1. Actual Past-Day Analysis (Real Market Bars + Screener Scan + Live Bot Log)
    past_recap = analyze_previous_trading_day(engine, prev_date, symbols=PORTFOLIO_SYMBOLS)
    recap_lines: List[str] = []
    for item in past_recap.get("market_recap", []):
        sym = item["symbol"]
        icon = _symbol_icon(sym)
        is_fx = "GBP" in sym or "EUR" in sym
        fmt = ".5f" if is_fx else ".2f"
        scale = 10000.0 if is_fx else 1.0
        unit = "pips" if is_fx else "pts"
        chg_scaled = item["change_pts"] * scale
        rng_scaled = item["range_pts"] * scale
        line = (
            f"• {icon} *{sym}:* `{item['direction']}` ({chg_scaled:+.1f} {unit} | "
            f"PDL `{item['low']:{fmt}}` – PDH `{item['high']:{fmt}}`, Rng {rng_scaled:.1f} {unit})"
        )
        sigs = item.get("smc_signals", [])
        if sigs:
            sig_txt = ", ".join(
                f"{s.get('archetype', 'SMC')} {s.get('direction', '')} @{s.get('time_tehran', 'N/A')} -> {s.get('outcome', 'N/A')}"
                for s in sigs
            )
            line += f"\n   _SMC Scan:_ {sig_txt}"
        else:
            line += "\n   _SMC Scan:_ No ratified triggers in London/NY Open."
        recap_lines.append(line)

    if not recap_lines:
        recap_lines.append("• _MT5 bar history unavailable for yesterday's market recap._")

    ld = past_recap.get("live_decisions", {})
    recap_lines.append(
        f"• 🤖 *Yesterday's Bot Log ({past_recap['date_str']}):* "
        f"`{ld.get('total', 0)}` event(s) | Approved: `{ld.get('approved', 0)}` | "
        f"Stand Aside: `{ld.get('stand_aside', 0)}`"
    )
    past_recap_text = "\n".join(recap_lines)

    # 2. Extract overnight Asian Range benchmarks (00:00 - 07:00 UTC) with true broker offset conversion
    benchmarks: Dict[str, Any] = {}
    if engine and engine.ensure_connected():
        for sym in PORTFOLIO_SYMBOLS:
            res_sym = engine.resolve_symbol(sym)
            if not res_sym:
                continue
            r5m = mt5.copy_rates_from_pos(res_sym, mt5.TIMEFRAME_M5, 0, 180)
            if r5m is not None and len(r5m) > 0:
                list_5m = _convert_records(r5m)
                cur_utc_date = server_epoch_to_zones(list_5m[-1]["time"])["utc_dt"].date()
                asian_bars = []
                for b in list_5m:
                    utc_dt = server_epoch_to_zones(b["time"])["utc_dt"]
                    if utc_dt.date() == cur_utc_date and utc_dt.hour < 7:
                        asian_bars.append(b)
                if asian_bars:
                    a_high = max(b["high"] for b in asian_bars)
                    a_low = min(b["low"] for b in asian_bars)
                    a_eq = (a_high + a_low) / 2.0
                    s_info = mt5.symbol_info(res_sym)
                    benchmarks[sym] = {
                        "high": a_high,
                        "low": a_low,
                        "eq": a_eq,
                        "current": list_5m[-1]["close"],
                        "spread_pts": s_info.spread if s_info else 0,
                    }

    bench_lines = []
    for sym in PORTFOLIO_SYMBOLS:
        b = benchmarks.get(sym)
        icon = _symbol_icon(sym)
        is_fx = "GBP" in sym or "EUR" in sym
        fmt = ".5f" if is_fx else ".2f"
        unit = "pips" if is_fx else "pts"
        if b:
            denom = 0.00010 if is_fx else 1.0
            range_size = (b["high"] - b["low"]) / denom
            bench_lines.append(
                f"• {icon} *{sym}:*\n"
                f"   High: `{b['high']:{fmt}}` | Low: `{b['low']:{fmt}}` (Range: *{range_size:.1f} {unit}*)\n"
                f"   Current: `{b['current']:{fmt}}` | Eq: `{b['eq']:{fmt}}`"
            )
        else:
            bench_lines.append(f"• {icon} *{sym}:* _Awaiting Asian Range Calculation_")
    bench_text = "\n".join(bench_lines)

    # 3. Macro Bias & High-Impact Events Preview
    macro_gold = calculate_htf_fundamental_bias("XAUUSD")
    macro_filter = macro_gold.get("execution_filter", "SELECTIVE_BI_DIRECTIONAL")
    usdx_mom = macro_gold.get("usdx_metrics", {}).get("momentum_5d_pct", 0.0)

    events = get_upcoming_events("XAUUSD", hours_ahead=12)
    news_lines = []
    if events:
        for ev in events[:3]:
            badge = "🔴" if ev["impact"] == "High" else "🟡"
            news_lines.append(f"• {badge} `{ev['time_str']} Tehran` | {ev['title']} ({ev['country']})")
    else:
        news_lines.append("• 🟢 _No high-impact economic releases scheduled during London Killzone._")
    news_text = "\n".join(news_lines)

    today_sessions = get_session_times_for_date(now_tehran.date())
    lon_tehran_str = today_sessions["london"]["tehran_str"]
    ny_tehran_str = today_sessions["new_york"]["tehran_str"]

    card = (
        f"🌅 *TRADINGGUARD PRE-MARKET BRIEFING*\n"
        f"🕒 *Tehran Time:* `{now_tehran.strftime('%H:%M:%S')} ({now_tehran.strftime('%A, %b %d')})`\n"
        f"🎯 *Pre-London Strategic Outlook*\n\n"
        f"📊 *Past Trading Day Analysis ({past_recap['date_str']}):*\n"
        f"{past_recap_text}\n\n"
        f"🎯 *Overnight Asian Benchmarks (00:00 - 07:00 UTC):*\n"
        f"{bench_text}\n\n"
        f"🌐 *Macro Stance & USDX Context:*\n"
        f"• Directional Stance: *[{macro_filter}]*\n"
        f"• USDX 5D Momentum: `{usdx_mom:+.2f}%`\n\n"
        f"📅 *Today's Key Economic Windows:*\n"
        f"{news_text}\n\n"
        f"🚀 *London Open activates at {lon_tehran_str} | NY Open at {ny_tehran_str}.*"
    )

    if target_chat and client:
        client.send_message(target_chat, card)

    return {
        "status": "COMPLETED",
        "past_day": past_recap,
        "benchmarks": benchmarks,
        "macro_filter": macro_filter,
        "timestamp": now_tehran.isoformat(),
    }
