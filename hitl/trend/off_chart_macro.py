"""
TradingGuard HITL - Off-Chart Macro & Sentiment Intelligence
Synthesizes macroeconomic catalyst calendars, high-impact red folder news,
and retail sentiment positioning to determine institutional flow headwinds/tailwinds.
"""

import sys
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.macro_calendar import get_upcoming_events
from hitl.sentiment_feed import fetch_tradingview_ideas

TZ_UTC = datetime.timezone.utc
TZ_TEHRAN = ZoneInfo("Asia/Tehran")


def extract_off_chart_macro(symbol: str = "XAUUSD") -> Dict[str, Any]:
    """
    Extracts structured off-chart intelligence (economic catalysts + retail sentiment) for any supported asset.
    """
    now_utc = datetime.datetime.now(TZ_UTC)
    now_tehran = now_utc.astimezone(TZ_TEHRAN)

    # 1. Economic Calendar Analysis
    # Check events in next 6 hours (session impact), 24 hours (day impact), and 72 hours (week impact)
    events_session = get_upcoming_events(symbol=symbol, hours_ahead=6)
    events_day = get_upcoming_events(symbol=symbol, hours_ahead=24)
    events_week = get_upcoming_events(symbol=symbol, hours_ahead=72)

    # Filter to high impact
    high_impact_session = [e for e in events_session if e.get("impact") == "High"]
    high_impact_day = [e for e in events_day if e.get("impact") == "High"]
    high_impact_week = [e for e in events_week if e.get("impact") == "High"]

    # Determine Catalyst Risk Score
    if high_impact_session:
        nearest_mins = min(e["minutes_away"] for e in high_impact_session)
        if 0 <= nearest_mins <= 60:
            session_catalyst_risk = "CRITICAL"
        else:
            session_catalyst_risk = "HIGH"
    elif any(e.get("impact") == "Medium" for e in events_session):
        session_catalyst_risk = "MEDIUM"
    else:
        session_catalyst_risk = "LOW"

    day_catalyst_risk = "HIGH" if len(high_impact_day) >= 2 else ("MEDIUM" if high_impact_day else "LOW")
    week_catalyst_risk = "HIGH" if len(high_impact_week) >= 3 else ("MEDIUM" if high_impact_week else "LOW")

    # 2. Retail Sentiment & Contrarian Positioning
    ideas = fetch_tradingview_ideas(symbol=symbol)
    retail_long_pct = 50.0
    retail_short_pct = 50.0
    sample_size = len(ideas) if ideas else 0
    contrarian_bias = "NEUTRAL"

    if ideas:
        bulls = sum(1 for i in ideas if i.get("sentiment") == "BULLISH")
        bears = sum(1 for i in ideas if i.get("sentiment") == "BEARISH")
        total = bulls + bears
        if total > 0:
            retail_long_pct = round((bulls / total) * 100.0, 1)
            retail_short_pct = round((bears / total) * 100.0, 1)

            # Contrarian Institutional Logic:
            # When retail is overwhelmingly long (>65%), Smart Money hunts resting sell-side stops below the market.
            # When retail is overwhelmingly short (>65%), Smart Money hunts resting buy-side stops above the market.
            if retail_long_pct >= 65.0:
                contrarian_bias = "INSTITUTIONAL_SHORT_HUNT"
            elif retail_short_pct >= 65.0:
                contrarian_bias = "INSTITUTIONAL_LONG_HUNT"
            else:
                contrarian_bias = "BALANCED"

    # 3. Session Timing Context
    from hitl.backtest.session_clock import get_active_session_status
    is_active, session_label, session_key = get_active_session_status()

    return {
        "symbol": symbol,
        "timestamp_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "timestamp_tehran": now_tehran.strftime("%Y-%m-%d %H:%M:%S Tehran"),
        "session_context": {
            "is_active_killzone": is_active,
            "session_label": session_label,
            "session_key": session_key
        },
        "catalysts": {
            "session_risk": session_catalyst_risk,
            "day_risk": day_catalyst_risk,
            "week_risk": week_catalyst_risk,
            "upcoming_high_impact_session": high_impact_session,
            "upcoming_high_impact_day_count": len(high_impact_day),
            "upcoming_high_impact_week_count": len(high_impact_week)
        },
        "retail_sentiment": {
            "sample_size": sample_size,
            "retail_long_pct": retail_long_pct,
            "retail_short_pct": retail_short_pct,
            "contrarian_bias": contrarian_bias,
            "interpretation": (
                f"Retail crowd is {retail_long_pct}% LONG. Institutional liquidity hunt favors "
                + ("flushing Sell-Side Liquidity." if retail_long_pct >= 65 else ("squeezing Buy-Side Liquidity." if retail_short_pct >= 65 else "two-sided structural expansion."))
            )
        }
    }
