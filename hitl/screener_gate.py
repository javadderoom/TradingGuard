"""
TradingGuard HITL - Live Screener Gate (Pack 5)

The live HITL bot used to convene the AI council on any Telegram /council
tap (or any radar trigger) with no screener check, so live decisions were
*less* filtered than the backtested ones — the backtests at least ran
screen_ict_session() first. This module is the single live gate:

    run_screener_gate(symbol) -> screen_ict_session() result dict

It fetches the same live MT5 bars the council would use, runs the screener
with the Pack 4 closed-bars default (signal on the last *closed* bar only,
entry on the next bar), and returns the screener's dict unchanged
(has_setup, reason, setup_type, archetype_id, entry_ref, sl_ref,
signal_bar_time, closed_bars_only).

Callers must NOT convene the council when has_setup is False — including
when the gate itself fails (MT5 down / too few bars): fail closed, log a
STAND_ASIDE with the gate's reason, and tell the user. The council prompt
then only ever asserts pre-screening when it is true (see
convene_investment_council(..., screener_result=...)).

session_hour is the Tehran hour of the signal bar: the screener's session
windows are keyed on it (9-11 Asian, 14-16 London, otherwise NY AM).
"""

import datetime
from typing import Dict, Any, Optional, List

import MetaTrader5 as mt5

from hitl.mt5_engine import MT5Engine
from hitl.backtest.data_feed import _convert_records

TEHRAN_OFFSET = datetime.timedelta(hours=3, minutes=30)


def tehran_hour_from_bar_time(bar_time: Any) -> int:
    """Tehran hour of a bar time (epoch int/float, or a datetime)."""
    if isinstance(bar_time, datetime.datetime):
        dt = bar_time
    else:
        dt = datetime.datetime.fromtimestamp(int(bar_time), tz=datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return (dt + TEHRAN_OFFSET).hour


def fetch_live_bars(symbol: str) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """Fetches the live MT5 bars the screener needs. Returns None on failure."""
    engine = MT5Engine()
    resolved = engine.resolve_symbol(symbol)
    if not engine.ensure_connected() or not resolved:
        return None
    try:
        r1d = mt5.copy_rates_from_pos(resolved, mt5.TIMEFRAME_D1, 0, 90)
        r1h = mt5.copy_rates_from_pos(resolved, mt5.TIMEFRAME_H1, 0, 80)
        r5m = mt5.copy_rates_from_pos(resolved, mt5.TIMEFRAME_M5, 0, 120)
    except Exception as e:
        print(f"[ScreenerGate] MT5 bar fetch error for {symbol}: {e}")
        return None
    if r5m is None or len(r5m) < 40 or r1h is None or len(r1h) < 10:
        return None
    return {
        "bars_5m": _convert_records(r5m),
        "bars_1h": _convert_records(r1h),
        "bars_1d": _convert_records(r1d) if r1d is not None else None,
    }


def run_screener_gate(symbol: str) -> Dict[str, Any]:
    """
    Runs screen_ict_session() (closed-bars only) on live bars for `symbol`.
    Returns the screener result dict. On any fetch/insufficiency failure it
    returns has_setup=False with setup_type SCREENER_ERROR — callers treat
    that exactly like a veto: do not convene the council.
    """
    from hitl.backtest.fast_screener import screen_ict_session

    bars = fetch_live_bars(symbol)
    if not bars:
        return {
            "has_setup": False,
            "reason": "Screener unavailable: live MT5 bars could not be fetched (or too few bars)",
            "setup_type": "SCREENER_ERROR",
            "closed_bars_only": True,
            "signal_bar_time": None,
        }
    session_hour = tehran_hour_from_bar_time(bars["bars_5m"][-1]["time"])
    try:
        result = screen_ict_session(
            bars_5m=bars["bars_5m"],
            bars_1h=bars["bars_1h"],
            symbol=symbol,
            session_hour=session_hour,
            bars_1d=bars["bars_1d"],
            closed_bars_only=True,
        )
    except Exception as e:
        print(f"[ScreenerGate] screen_ict_session error for {symbol}: {e}")
        return {
            "has_setup": False,
            "reason": f"Screener error: {e}",
            "setup_type": "SCREENER_ERROR",
            "closed_bars_only": True,
            "signal_bar_time": None,
        }
    return result


def format_screener_veto(symbol: str, result: Dict[str, Any]) -> str:
    """One-line Telegram-safe explanation of why the screener vetoed."""
    return (
        f"🛡️ *{symbol} · STAND ASIDE (Screener Gate)*\n\n"
        f"No setup passed the ICT screener (closed bars only).\n"
        f"🛑 *Reason:* {result.get('reason', 'No setup')}\n\n"
        f"The council was not convened — live decisions are now gated by "
        f"the same screener the backtests use."
    )
