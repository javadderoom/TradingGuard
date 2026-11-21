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

    # Determine Catalyst Risk Score (-5m to +60m around High-Impact release = CRITICAL)
    if any(-5 <= e["minutes_away"] <= 60 for e in high_impact_session):
        session_catalyst_risk = "CRITICAL"
    elif high_impact_session:
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

    # 4. Evidence-Grounded Causal Fundamental Intelligence (cached; non-blocking fallback)
    fundamental_causal: Dict[str, Any] = {}
    try:
        from hitl.fundamental.causal_engine import fundamental_engine

        fund_view = fundamental_engine.get_asset_view(symbol, force_refresh=False, allow_llm=False)
        diag = fund_view.get("diagnostics", {}) or {}
        reg = fund_view.get("global_macro_regime", {}) or {}
        fundamental_causal = {
            "global_regime": reg.get("label", "N/A"),
            "dominant_theme": reg.get("dominant_theme", ""),
            "asset_bias": fund_view.get("bias", "NEUTRAL"),
            "asset_score": int(fund_view.get("score", 0) or 0),
            "confidence": float(fund_view.get("confidence", 0.0) or 0.0),
            "dominant_driver": fund_view.get("dominant_driver", ""),
            "dominant_mechanism": fund_view.get("dominant_mechanism", ""),
            "causal_chains": (fund_view.get("causal_chains") or [])[:3],
            "rates_tape": {
                "nom_10y": diag.get("nom_10y_level"),
                "nom_10y_5d_bps": diag.get("nom_10y_5d_bps"),
                "real_10y": diag.get("real_10y_level"),
                "real_10y_5d_bps": diag.get("real_10y_5d_bps"),
                "dxy_level": diag.get("dxy_level"),
                "dxy_5d_pct": diag.get("dxy_5d_pct"),
                "vix_level": diag.get("vix_level"),
                "bond_equity_co_selloff": diag.get("bond_equity_co_selloff"),
            },
            "cot_positioning": fund_view.get("cot"),
            "analysis_source": fund_view.get("analysis_source", "fundamental_engine"),
        }
    except Exception as e:
        fundamental_causal = {"error": str(e), "asset_bias": "NEUTRAL", "asset_score": 0, "confidence": 0.0}

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
        },
        "fundamental_causal": fundamental_causal,
    }
