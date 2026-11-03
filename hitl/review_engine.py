"""
TradingGuard HITL - Closed-Loop Institutional Review Engine
1. Review Council (شورای بازبینی - Decision Audit):
   - Audits past Council decisions (Stand Asides and Placed Orders) against real MT5 market outcomes.
   - Evaluates whether Stand Asides were protective (saved capital) or flawed (missed winners).
   - Evaluates whether order plans were filled, reached TP, or stopped out.
   - Synthesizes institutional corrections and persists them to `hitl/memory/council_playbook.json`.
   - Dispatches a concise, high-density Decision Audit Card to Telegram.

2. Pre-Market Morning Briefing (10:30 Tehran / 07:00 UTC):
   - Injects prior day's lessons learned and active calibration rules.
   - Analyzes live overnight Asian Range benchmarks (High, Low, Midpoint) for Cable, Euro, and Gold.
   - Fetches today's Tier 1 Macro Fundamental bias and scheduled high-impact news windows.
   - Dispatches the Morning Operational Card to Telegram prior to London open.
"""

import time
import datetime
from typing import Dict, Any, List, Optional
import MetaTrader5 as mt5

from hitl.config import BASE_DIR, TELEGRAM_CHAT_ID, MAX_DAILY_LOSS_USD
from hitl.mt5_engine import MT5Engine
from hitl.telegram_client import TelegramClient
from hitl.council_memory import CouncilMemory
from hitl.council_decisions import (
    get_unreviewed_decisions,
    audit_decision_outcome,
    _load_log,
    _save_log
)
from hitl.macro_calendar import get_upcoming_events
from hitl.macro_bias import calculate_htf_fundamental_bias
from hitl.backtest.data_feed import _convert_records


def convene_review_council(
    engine: MT5Engine,
    client: TelegramClient,
    chat_id: Optional[int | str] = None
) -> Dict[str, Any]:
    """
    Convenes the Institutional Review Council (شورای بازبینی).
    Audits previous Council decisions and their real-world outcomes.
    Dispatches a concise, high-impact Telegram card without lengthy debate transcripts.
    """
    target_chat = chat_id or TELEGRAM_CHAT_ID
    now_dt = datetime.datetime.now()

    # 1. Fetch recent decisions to audit
    all_decisions = _load_log()
    today_str = now_dt.strftime("%Y-%m-%d")
    
    # Prioritize today's decisions, or fallback to the last 5 decisions
    recent_decisions = [d for d in all_decisions if d.get("date_str") == today_str]
    if not recent_decisions:
        recent_decisions = all_decisions[-5:] if all_decisions else []

    if not recent_decisions:
        card = (
            f"🏛️ *TRADINGGUARD REVIEW COUNCIL (DECISION AUDIT)*\n"
            f"📅 *Date:* `{now_dt.strftime('%A, %b %d, %Y')}`\n\n"
            f"📭 _No recent Council decisions recorded in the ledger yet._\n"
            f"Decisions are automatically logged when live setups trigger during killzones."
        )
        if target_chat and client:
            client.send_message(target_chat, card)
        return {"status": "NO_DECISIONS", "count": 0}

    # 2. Audit each decision against MT5 price trajectory
    audit_results = []
    missed_winners = 0
    protective_vetoes = 0
    accurate_entries = 0
    neutral_count = 0

    for d in recent_decisions:
        audit = audit_decision_outcome(d, engine)
        verdict = audit.get("verdict", "AUDITED")
        summary = audit.get("summary", "")

        if "MISSED WINNER" in verdict:
            missed_winners += 1
        elif "PROTECTIVE VETO" in verdict or "ACCURATE VETO" in verdict:
            protective_vetoes += 1
        elif "WIN" in verdict or "ACCURATE" in verdict:
            accurate_entries += 1
        else:
            neutral_count += 1

        d["reviewed"] = True
        d["review_verdict"] = verdict
        d["review_notes"] = summary

        audit_results.append({
            "record": d,
            "audit": audit
        })

    # Save updated reviewed status
    _save_log(all_decisions)

    # 3. Formulate Institutional Synthesis & Lesson for Tomorrow
    memory = CouncilMemory()
    if missed_winners > 0:
        synthesis = (
            f"Detected {missed_winners} missed winning setup(s) due to overly rigid directional filters. "
            f"Directive: Authorize selective counter-trend entries on prominent Asian/session extremes when M5 displacement MSS is confirmed."
        )
    elif protective_vetoes > 0 and missed_winners == 0:
        synthesis = (
            f"High-fidelity capital preservation: {protective_vetoes} veto(es) successfully protected capital from adverse moves or chop. "
            f"Directive: Continue enforcing strict MSS confirmation before capital allocation."
        )
    elif accurate_entries > 0:
        synthesis = (
            f"Execution fidelity verified: Limit orders achieved favorable asymmetry. "
            f"Directive: Maintain structural stop buffers pinned to M5 protected swings."
        )
    else:
        synthesis = (
            "Market exhibited equilibrium chop. Council discipline successfully avoided overtrading in dead zones."
        )

    # Save to Council Memory Playbook
    memory.record_counterfactual_audit(
        symbol="MULTI",
        session_time=now_dt.strftime("%Y-%m-%d %H:%M"),
        discussed_setup=f"Review Council Audit: {len(audit_results)} decisions evaluated",
        cio_decision="REVIEW_COUNCIL_AUDIT",
        forward_4h_max_gain=0.0,
        forward_4h_max_dd=0.0,
        forward_4h_close_change=0.0,
        verdict="AUDIT_SYNTHESIS",
        lesson=synthesis
    )

    # 4. Format Concise, High-Impact Telegram Card
    audit_items_text = []
    for idx, item in enumerate(audit_results, 1):
        rec = item["record"]
        aud = item["audit"]
        sym = rec["symbol"]
        icon = "🥇" if "XAU" in sym else ("💷" if "GBP" in sym else "💶")
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
        f"📅 *Session Date:* `{now_dt.strftime('%A, %b %d, %Y')}`\n\n"
        f"🔍 *Past Decisions vs. Actual Market Outcomes ({len(audit_results)} evaluated):*\n\n"
        f"{all_audits_str}\n\n"
        f"🎯 *Key Adjustment for Next Decision Council:*\n"
        f"_{synthesis}_\n\n"
        f"🛡️ *Playbook updated in institutional memory.*"
    )

    if target_chat and client:
        client.send_message(target_chat, card)

    return {
        "status": "COMPLETED",
        "decisions_audited": len(audit_results),
        "missed_winners": missed_winners,
        "protective_vetoes": protective_vetoes,
        "synthesis": synthesis,
        "timestamp": now_dt.isoformat()
    }


def run_session_post_mortem(
    engine: MT5Engine,
    client: TelegramClient,
    chat_id: Optional[int | str] = None
) -> Dict[str, Any]:
    """Alias for end-of-session review council."""
    return convene_review_council(engine, client, chat_id)


def run_morning_briefing(
    engine: MT5Engine,
    client: TelegramClient,
    chat_id: Optional[int | str] = None
) -> Dict[str, Any]:
    """
    Executes automated Pre-Market Morning Briefing (10:30 Tehran / 07:00 UTC).
    Analyzes overnight Asian ranges, injects prior day lessons, and previews macro news.
    """
    target_chat = chat_id or TELEGRAM_CHAT_ID
    now_dt = datetime.datetime.now()

    # 1. Retrieve yesterday's carry-forward lesson
    memory = CouncilMemory()
    recent_audits = memory.data.get("counterfactual_audits", [])
    yesterday_lesson = recent_audits[-1]["lesson"] if recent_audits else "Maintain strict discipline and honor structural stop buffers."

    # 2. Extract overnight Asian Range benchmarks for primary assets
    benchmarks = {}
    symbols = ["XAUUSD", "GBPUSD", "EURUSD"]
    
    if engine.ensure_connected():
        for sym in symbols:
            res_sym = engine.resolve_symbol(sym)
            if not res_sym:
                continue
            r5m = mt5.copy_rates_from_pos(res_sym, mt5.TIMEFRAME_M5, 0, 120)
            if r5m is not None and len(r5m) > 0:
                list_5m = _convert_records(r5m)
                cur_date = datetime.datetime.fromtimestamp(list_5m[-1]['time'], datetime.timezone.utc).date()
                asian_bars = [
                    b for b in list_5m
                    if datetime.datetime.fromtimestamp(b['time'], datetime.timezone.utc).date() == cur_date
                    and datetime.datetime.fromtimestamp(b['time'], datetime.timezone.utc).hour < 7
                ]
                if asian_bars:
                    a_high = max(b['high'] for b in asian_bars)
                    a_low = min(b['low'] for b in asian_bars)
                    a_eq = (a_high + a_low) / 2.0
                    benchmarks[sym] = {
                        "high": a_high,
                        "low": a_low,
                        "eq": a_eq,
                        "current": list_5m[-1]['close'],
                        "spread_pts": mt5.symbol_info(res_sym).spread if mt5.symbol_info(res_sym) else 0
                    }

    # Format Asian benchmark lines
    bench_lines = []
    for sym in symbols:
        b = benchmarks.get(sym)
        icon = "🥇" if "XAU" in sym else ("💷" if "GBP" in sym else "💶")
        is_fx = "GBP" in sym or "EUR" in sym
        fmt = ".5f" if is_fx else ".2f"
        unit = "pips" if is_fx else "pts"
        if b:
            range_size = (b["high"] - b["low"]) / (0.00010 if is_fx else 0.10)
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

    card = (
        f"🌅 *TRADINGGUARD PRE-MARKET BRIEFING*\n"
        f"🕒 *Tehran Time:* `{now_dt.strftime('%H:%M:%S')} ({now_dt.strftime('%A, %b %d')})`\n"
        f"🎯 *Pre-London Strategic Outlook*\n\n"
        f"🧠 *Yesterday's Carry-Forward Lesson:*\n"
        f"_{yesterday_lesson}_\n\n"
        f"🎯 *Overnight Asian Benchmarks (00:00 - 07:00 UTC):*\n"
        f"{bench_text}\n\n"
        f"🌐 *Macro Stance & USDX Context:*\n"
        f"• Directional Stance: *[{macro_filter}]*\n"
        f"• USDX 5D Momentum: `{usdx_mom:+.2f}%`\n"
        f"• *Directive:* Authorize pro-trend expansions; selective counter-trend permitted strictly on Asian sweep purges.\n\n"
        f"📅 *Today's Key Economic Windows:*\n"
        f"{news_text}\n\n"
        f"🚀 *London Killzone activates at 11:00 Tehran. Stay disciplined!*"
    )

    if target_chat and client:
        client.send_message(target_chat, card)

    return {
        "status": "COMPLETED",
        "benchmarks": benchmarks,
        "macro_filter": macro_filter,
        "timestamp": now_dt.isoformat()
    }
