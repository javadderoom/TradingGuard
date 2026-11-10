"""
TradingGuard HITL - OmniTrend Oracle Core Service
Orchestrates on-chart microstructure, off-chart macro intelligence, and SubQ Snap
classification into unified multi-horizon trend predictions with persistent state caching.
"""

import os
import sys
import json
import time
import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.trend.on_chart_microstructure import extract_on_chart_microstructure
from hitl.trend.off_chart_macro import extract_off_chart_macro
from hitl.trend.snap_trend_classifier import SnapTrendClassifier

STATE_DIR = BASE_DIR / "hitl" / "memory"
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "trend_regime_state.json"

CACHE_TTL_SECONDS = 900  # 15 minutes
TZ_TEHRAN = ZoneInfo("Asia/Tehran")


class TrendOracle:
    """
    Central Multi-Horizon Trend & Regime Prediction Service for TradingGuard.
    """

    def __init__(self, classifier: Optional[SnapTrendClassifier] = None):
        self.classifier = classifier or SnapTrendClassifier()
        self._cached_forecast: Optional[Dict[str, Any]] = None
        self._last_update_ts: float = 0.0

    def get_forecast(
        self,
        symbol: str = "XAUUSD",
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Retrieves the multi-horizon trend prediction.
        Returns from cache if fresher than CACHE_TTL_SECONDS unless force_refresh is True.
        """
        now = time.time()
        if not force_refresh and self._cached_forecast and (now - self._last_update_ts < CACHE_TTL_SECONDS):
            return self._cached_forecast

        # Check disk cache if in-memory cache is empty
        if not force_refresh and not self._cached_forecast and STATE_FILE.exists():
            try:
                mtime = STATE_FILE.stat().st_mtime
                if now - mtime < CACHE_TTL_SECONDS:
                    with open(STATE_FILE, "r", encoding="utf-8") as f:
                        self._cached_forecast = json.load(f)
                        self._last_update_ts = mtime
                        return self._cached_forecast
            except Exception as e:
                print(f"[TrendOracle] Disk cache read warning: {e}")

        # Fresh execution
        t0 = time.perf_counter()
        on_chart = extract_on_chart_microstructure(symbol=symbol)
        off_chart = extract_off_chart_macro(symbol=symbol)
        forecast = self.classifier.classify_trend(on_chart, off_chart)

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        # Merge metadata
        forecast["symbol"] = symbol
        forecast["latency_ms"] = elapsed_ms
        forecast["generated_at_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        forecast["generated_at_tehran"] = datetime.datetime.now(TZ_TEHRAN).strftime("%Y-%m-%d %H:%M:%S Tehran")
        forecast["on_chart_telemetry"] = on_chart
        forecast["off_chart_telemetry"] = off_chart

        # Update cache & persist to disk
        self._cached_forecast = forecast
        self._last_update_ts = now
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(forecast, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TrendOracle] Failed to persist state to {STATE_FILE}: {e}")

        return forecast

    def format_telegram_card(self, forecast: Dict[str, Any]) -> str:
        """
        Formats forecast into a rich, readable Telegram card for @TradingGuard2Bot.
        """
        sym = forecast.get("symbol", "XAUUSD")
        horizons = forecast.get("horizons", {})
        on_chart = forecast.get("on_chart_telemetry", {})
        off_chart = forecast.get("off_chart_telemetry", {})

        curr_p = on_chart.get("current_price", 0.0)

        # Session Horizon
        sess = horizons.get("session", {})
        sess_bias = sess.get("bias", "NEUTRAL")
        sess_icon = "🟢" if sess_bias == "BULLISH" else ("🔴" if sess_bias == "BEARISH" else "🟡")
        sess_conf = int(sess.get("confidence", 0.0) * 100)
        sess_arch = sess.get("session_archetype", "N/A").replace("_", " ")
        sess_range = sess.get("expected_range", {})

        # Day Horizon
        day = horizons.get("day", {})
        day_bias = day.get("bias", "NEUTRAL")
        day_icon = "🟢" if day_bias == "BULLISH" else ("🔴" if day_bias == "BEARISH" else "🟡")
        day_conf = int(day.get("confidence", 0.0) * 100)
        daily_dol = day.get("daily_dol", {})
        dol_target = daily_dol.get("target", 0.0)
        dol_type = daily_dol.get("type", "N/A").replace("_", " ")
        inval = day.get("invalidation", 0.0)

        # Week Horizon
        week = horizons.get("week", {})
        week_bias = week.get("bias", "NEUTRAL")
        week_icon = "🟢" if week_bias == "BULLISH" else ("🔴" if week_bias == "BEARISH" else "🟡")
        week_conf = int(week.get("confidence", 0.0) * 100)
        week_target = week.get("macro_target", 0.0)
        week_prof = week.get("weekly_profile", "N/A").replace("_", " ")

        # Off-chart macro badges
        sentiment = off_chart.get("retail_sentiment", {})
        retail_l = sentiment.get("retail_long_pct", 50.0)
        retail_s = sentiment.get("retail_short_pct", 50.0)
        catalysts = off_chart.get("catalysts", {})
        sess_risk = catalysts.get("session_risk", "LOW")
        risk_badge = "🔴 High Danger" if sess_risk in ("HIGH", "CRITICAL") else ("🟡 Moderate" if sess_risk == "MEDIUM" else "🟢 Low Risk")

        smt = on_chart.get("smt_divergence", {})
        smt_badge = f"⚡ *SMT:* {smt.get('type')}" if smt.get("has_smt") else "🔹 *SMT:* Neutral"

        card = (
            f"🔮 *OmniTrend Oracle — {sym} Multi-Horizon Forecast*\n"
            f"⏱ *Generated:* `{forecast.get('generated_at_tehran', '')}`\n"
            f"💲 *Current Price:* `${curr_p:.2f}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ *1. SESSION HORIZON (Next 2–6h)*\n"
            f"• Bias: {sess_icon} *{sess_bias}* (Conf: `{sess_conf}%`)\n"
            f"• Archetype: `{sess_arch}`\n"
            f"• Expected Range: `${sess_range.get('low', 0):.2f}` – `${sess_range.get('high', 0):.2f}`\n"
            f"• Catalyst Risk: {risk_badge}\n\n"
            f"📅 *2. DAILY HORIZON (24 Hours)*\n"
            f"• Bias: {day_icon} *{day_bias}* (Conf: `{day_conf}%`)\n"
            f"• Draw on Liquidity (DOL): *${dol_target:.2f}* ({dol_type})\n"
            f"• Invalidation Level: `${inval:.2f}`\n\n"
            f"🗓️ *3. WEEKLY HORIZON (5 Days)*\n"
            f"• Bias: {week_icon} *{week_bias}* (Conf: `{week_conf}%`)\n"
            f"• Weekly Profile: `{week_prof}`\n"
            f"• Macro Target: *${week_target:.2f}*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *OFF-CHART & MACRO INTELLIGENCE:*\n"
            f"• Retail Sentiment: `{retail_l}% Long` / `{retail_s}% Short`\n"
            f"• {smt_badge}\n\n"
            f"💡 *Institutional Synthesis:*\n"
            f"_{forecast.get('synthesis_rationale', '')}_\n\n"
            f"🛡️ _Advisory Mode: Informational trend guidance. Screener trades are not blocked._"
        )
        return card

    def format_cli_summary(self, forecast: Dict[str, Any]) -> str:
        """Formats clean terminal diagnostics."""
        horizons = forecast.get("horizons", {})
        sess = horizons.get("session", {})
        day = horizons.get("day", {})
        week = horizons.get("week", {})
        dol = day.get("daily_dol", {})
        return (
            f"\n=======================================================\n"
            f"🔮 OMNITREND ORACLE: {forecast.get('symbol')} MULTI-HORIZON FORECAST\n"
            f"=======================================================\n"
            f"SESSION (2-6h) : {sess.get('bias')} ({int(sess.get('confidence',0)*100)}%) | Archetype: {sess.get('session_archetype')}\n"
            f"DAILY   (24h)  : {day.get('bias')} ({int(day.get('confidence',0)*100)}%) | DOL: {dol.get('target')} ({dol.get('type')})\n"
            f"WEEKLY  (5d)   : {week.get('bias')} ({int(week.get('confidence',0)*100)}%) | Target: {week.get('macro_target')} | Profile: {week.get('weekly_profile')}\n"
            f"Latency        : {forecast.get('latency_ms')} ms\n"
            f"Rationale      : {forecast.get('synthesis_rationale')}\n"
            f"======================================================="
        )


# Global singleton instance
trend_oracle = TrendOracle()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OmniTrend Oracle Diagnostics")
    parser.add_argument("--symbol", default="XAUUSD", help="Target symbol")
    parser.add_argument("--refresh", action="store_true", help="Force fresh prediction")
    args = parser.parse_args()

    fc = trend_oracle.get_forecast(symbol=args.symbol, force_refresh=args.refresh)
    print(trend_oracle.format_cli_summary(fc))
