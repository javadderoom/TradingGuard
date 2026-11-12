"""
TradingGuard HITL - SubQ Snap Multi-Horizon Trend Classifier
Combines on-chart microstructure vectors and off-chart macro/sentiment intelligence
using Subquadratic SubQ Snap (or deterministic quantitative matrix fallback) to produce
probabilistic directional forecasts across Session, Day, and Week horizons.
"""

import sys
import json
import time
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.config import SNAP_API_KEY, SNAP_API_URL, SNAP_MODEL


class SnapTrendClassifier:
    """
    Subquadratic Multimodal Trend Classifier.
    """

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None):
        self.api_key = SNAP_API_KEY if api_key is None else api_key
        self.api_url = SNAP_API_URL if api_url is None else api_url
        self.model = SNAP_MODEL or "subq-snap-1.1"

    def classify_trend(
        self,
        on_chart: Dict[str, Any],
        off_chart: Dict[str, Any],
        timeout: int = 12
    ) -> Dict[str, Any]:
        """
        Classifies trend across Session, Day, and Week horizons.
        Uses SubQ Snap when configured, otherwise applies the deterministic quantitative matrix.
        """
        if self.api_key and self.api_url:
            try:
                res = self._call_snap_api(on_chart, off_chart, timeout=timeout)
                if res and "horizons" in res:
                    return res
            except Exception as e:
                print(f"[SnapTrendClassifier] API call failed: {e}. Falling back to deterministic engine.")

        # Deterministic Quantitative Matrix Fallback
        return self._evaluate_deterministic_matrix(on_chart, off_chart)

    def _call_snap_api(
        self,
        on_chart: Dict[str, Any],
        off_chart: Dict[str, Any],
        timeout: int
    ) -> Optional[Dict[str, Any]]:
        """Invokes SubQ Snap classification endpoint using the official state+questions schema."""
        sym = on_chart.get("symbol", "XAUUSD")
        is_forex = "GBP" in sym.upper() or "EUR" in sym.upper()
        is_index = "NQ" in sym.upper() or "NAS" in sym.upper() or "USTEC" in sym.upper() or "US100" in sym.upper() or "SPX" in sym.upper()
        decimals = 5 if is_forex else 2

        state_str = (
            f"=== ASSET: {sym} ===\n"
            f"Timestamp: {on_chart.get('timestamp_utc')}\n"
            f"Current Price: {on_chart.get('current_price')}\n\n"
            f"--- On-Chart Microstructure ---\n"
            f"Daily Range: Low {on_chart['daily_structure']['daily_low']} - High {on_chart['daily_structure']['daily_high']} (ADR 14: {on_chart['daily_structure']['adr_14']}, Utilized: {on_chart['daily_structure']['adr_utilization_pct']}%)\n"
            f"Previous Day: Low {on_chart['daily_structure']['pdl']} - High {on_chart['daily_structure']['pdh']} (Swept PDH: {on_chart['daily_structure']['has_swept_pdh']}, Swept PDL: {on_chart['daily_structure']['has_swept_pdl']})\n"
            f"Weekly Context: Open {on_chart['weekly_structure']['cwo']} (Relation: {on_chart['weekly_structure']['relation_to_weekly_open']})\n"
            f"Asian Range: {on_chart['session_ranges'].get('asian_low', 'N/A')} - {on_chart['session_ranges'].get('asian_high', 'N/A')} | London Range: {on_chart['session_ranges'].get('london_low', 'Pending')} - {on_chart['session_ranges'].get('london_high', 'Pending')}\n"
            f"H1 Structure Regime: {on_chart['htf_trend'].get('h1_regime', 'N/A')} | SMT Divergence: {on_chart['smt_divergence'].get('type', 'NONE')} ({on_chart['smt_divergence'].get('note', '')})\n"
            f"Primary Draw on Liquidity: {on_chart['draw_on_liquidity'].get('type', 'N/A')} at {on_chart['draw_on_liquidity'].get('target_price', 'N/A')}\n\n"
            f"--- Off-Chart Macro & Sentiment ---\n"
            f"Retail Crowd Positioning: {off_chart.get('retail_sentiment', {}).get('retail_long_pct', 50)}% Long / {off_chart.get('retail_sentiment', {}).get('retail_short_pct', 50)}% Short (Contrarian: {off_chart.get('retail_sentiment', {}).get('contrarian_bias', 'NEUTRAL')})\n"
            f"Catalyst Danger Score: Session={off_chart.get('catalysts', {}).get('session_risk', 'LOW')} | Day={off_chart.get('catalysts', {}).get('day_risk', 'LOW')}\n"
            f"Active Session: {off_chart.get('session_context', {}).get('session_label', 'Active')}"
        )

        questions = {
            "session_horizon": {
                "type": "choice",
                "instructions": "Determine the high-probability institutional directional bias for the upcoming 2-6 hour session.",
                "criteria": {
                    "BULLISH_EXPANSION": "Session order flow is bullish; expected to sweep Asian low or expand higher into overhead BSL.",
                    "BEARISH_EXPANSION": "Session order flow is bearish; expected to sweep Asian high or expand lower into underlying SSL.",
                    "RANGE_BOUND_CHOP": "Session is trapped in equilibrium consolidation or high catalyst danger whipsaw."
                }
            },
            "day_horizon": {
                "type": "choice",
                "instructions": f"Determine the daily candle archetype and directional close for {sym} over the next 24 hours.",
                "criteria": {
                    "BULLISH_DAY": "Daily candle is expected to close green with higher highs, targeting upper Draw on Liquidity.",
                    "BEARISH_DAY": "Daily candle is expected to close red with lower lows, targeting lower Draw on Liquidity.",
                    "CONSOLIDATION_DAY": "Inside day or balanced equilibrium; lack of directional expansion conviction."
                }
            },
            "weekly_profile": {
                "type": "choice",
                "instructions": "Identify the multi-day weekly ICT expansion profile.",
                "criteria": {
                    "TUESDAY_LOW_OF_WEEK": "Classic ICT bullish profile where the low of the week establishes on Tuesday during European/NY flow.",
                    "TUESDAY_HIGH_OF_WEEK": "Classic ICT bearish profile where the high of the week establishes on Tuesday during European/NY flow.",
                    "MID_WEEK_REVERSAL": "Wednesday/Thursday expansion reversal against the early week probe.",
                    "NEUTRAL_CHOP": "Weekly balance without clear macro displacement."
                }
            }
        }

        request_body = {
            "model": self.model,
            "state": state_str,
            "questions": questions
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        req = urllib.request.Request(
            self.api_url,
            data=json.dumps(request_body).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                answers = data.get("answers", {})

                # Parse session choice
                sess_obj = answers.get("session_horizon", {})
                sess_raw = sess_obj.get("choice", "RANGE_BOUND_CHOP")
                sess_bias = "BULLISH" if "BULLISH" in sess_raw else ("BEARISH" if "BEARISH" in sess_raw else "RANGE_CHOP")
                sess_conf = sess_obj.get("confidence", 0.70)

                # Parse day choice
                day_obj = answers.get("day_horizon", {})
                day_raw = day_obj.get("choice", "CONSOLIDATION_DAY")
                day_bias = "BULLISH" if "BULLISH" in day_raw else ("BEARISH" if "BEARISH" in day_raw else "CONSOLIDATION")
                day_conf = day_obj.get("confidence", 0.75)

                # Parse week choice
                week_obj = answers.get("weekly_profile", {})
                week_raw = week_obj.get("choice", "NEUTRAL_CHOP")
                week_bias = "BULLISH" if "LOW_OF_WEEK" in week_raw else ("BEARISH" if "HIGH_OF_WEEK" in week_raw else "NEUTRAL")
                week_conf = week_obj.get("confidence", 0.68)

                # Synthesize with numerical levels from on_chart
                dol = on_chart.get("draw_on_liquidity", {})
                daily_st = on_chart.get("daily_structure", {})
                default_band = 0.0050 if is_forex else (150.0 if is_index else 15.0)
                pdl = daily_st.get("pdl", on_chart["current_price"] - default_band)
                pdh = daily_st.get("pdh", on_chart["current_price"] + default_band)

                target_p = dol.get("target_price", pdl if day_bias == "BEARISH" else pdh)
                inval_p = daily_st.get("daily_high", pdh) if day_bias == "BEARISH" else daily_st.get("daily_low", pdl)
                expected_range, key_trigger = self._compute_session_expected_range(
                    on_chart=on_chart,
                    sess_bias=sess_bias,
                    sess_arch=sess_raw,
                    target_p=target_p,
                    is_forex=is_forex,
                    is_index=is_index,
                    decimals=decimals,
                )

                if is_forex:
                    tm_policy = {
                        "aligned": {"tp_r": 2.0, "be_ratchet_r": 1.0, "mode": "FOREX_TREND_EXPANSION", "note": "Forex Trend Expansion: 2.0R TP with 1.0R BE protection"},
                        "counter": {"tp_r": 2.5, "be_ratchet_r": 1.0, "mode": "PREMIER_MEAN_REVERSION_FADE", "note": "Judas Sweep Fade: 2.5R TP with 1.0R BE ratchet (Premier Edge)"},
                        "sideways": {"tp_r": 2.5, "be_ratchet_r": 0.8, "mode": "FOREX_RANGE_BOUNDARY_FADE", "note": "Forex Range Fade: 2.5R TP with 0.8R BE protection"}
                    }
                elif is_index:
                    tm_policy = {
                        "aligned": {"tp_r": 3.5, "be_ratchet_r": 1.0, "mode": "INDEX_TREND_EXPANSION", "note": "Index Trend Expansion: 3.5R TP with early 1.0R BE protection"},
                        "counter": {"tp_r": 3.0, "be_ratchet_r": 0.8, "mode": "INDEX_MEAN_REVERSION_FADE", "note": "Judas Sweep Fade: 3.0R TP with fast 0.8R BE ratchet (Premier Edge)"},
                        "sideways": {"tp_r": 3.0, "be_ratchet_r": 0.8, "mode": "INDEX_RANGE_BOUNDARY_FADE", "note": "Index Range Boundary Fade: 3.0R TP with 0.8R BE protection"}
                    }
                else:
                    tm_policy = {
                        "aligned": {"tp_r": 3.5, "be_ratchet_r": 1.5, "mode": "TREND_EXPANSION", "note": "Target Distal DOL with 1.5R BE protection"},
                        "counter": {"tp_r": 1.5, "be_ratchet_r": 1.0, "mode": "COUNTER_TREND_SCALP", "note": "Defensive Scalp: 1.5R TP with fast 1.0R BE ratchet"},
                        "sideways": {"tp_r": 3.5, "be_ratchet_r": 1.0, "mode": "EQUILIBRIUM_BOUNDARY_FADE", "note": "Range Fade: 3.5R Boundary Target with early 1.0R BE protection"}
                    }

                return {
                    "symbol": sym,
                    "horizons": {
                        "session": {
                            "bias": sess_bias,
                            "confidence": round(sess_conf, 2),
                            "session_archetype": sess_raw,
                            "expected_range": expected_range,
                            "key_trigger": key_trigger,
                            "catalyst_danger": off_chart["catalysts"]["session_risk"]
                        },
                        "day": {
                            "bias": day_bias,
                            "confidence": round(day_conf, 2),
                            "daily_dol": {
                                "target": round(target_p, decimals),
                                "type": dol.get("type", "LIQUIDITY_TARGET"),
                                "rationale": f"SubQ Snap classified {day_raw} targeting {dol.get('type')}"
                            },
                            "invalidation": round(inval_p, decimals),
                            "candle_archetype": day_raw
                        },
                        "week": {
                            "bias": week_bias,
                            "confidence": round(week_conf, 2),
                            "macro_target": round(on_chart["weekly_structure"]["pwl" if week_bias == "BEARISH" else "pwh"], decimals),
                            "weekly_profile": week_raw
                        }
                    },
                    "trade_management": tm_policy,
                    "synthesis_rationale": (
                        f"SubQ Snap 1.1 Multimodal Classification: Evaluated on-chart MTF state vs off-chart macro catalysts for {sym}. "
                        f"Session bias rated {sess_bias} (confidence {int(sess_conf*100)}%), Daily horizon aligned with {day_raw} toward {target_p:.{decimals}f}. "
                        f"Weekly profile: {week_raw}."
                    ),
                    "source": "subq-snap-1.1"
                }
        return None
        return None

    def _build_prompt(self, on_chart: Dict[str, Any], off_chart: Dict[str, Any]) -> str:
        """Constructs high-density structured prompt for SubQ Snap."""
        sym = on_chart.get("symbol", "XAUUSD")
        return (
            f"Analyze the following institutional state vector for {sym} and forecast the trend:\n\n"
            f"=== ON-CHART MICROSTRUCTURE ===\n"
            f"{json.dumps(on_chart, indent=2)}\n\n"
            f"=== OFF-CHART MACRO & SENTIMENT ===\n"
            f"{json.dumps(off_chart, indent=2)}\n\n"
            "Produce strict JSON output formatted as:\n"
            "{\n"
            f'  "symbol": "{sym}",\n'
            '  "horizons": {\n'
            '    "session": {"bias": "BULLISH"|"BEARISH"|"RANGE_CHOP", "confidence": float, "session_archetype": str, "expected_range": {"high": float, "low": float}, "key_trigger": float, "catalyst_danger": str},\n'
            '    "day": {"bias": "BULLISH"|"BEARISH"|"CONSOLIDATION", "confidence": float, "daily_dol": {"target": float, "type": str, "rationale": str}, "invalidation": float, "candle_archetype": str},\n'
            '    "week": {"bias": "BULLISH"|"BEARISH"|"NEUTRAL", "confidence": float, "macro_target": float, "weekly_profile": str}\n'
            "  },\n"
            '  "synthesis_rationale": str\n'
            "}"
        )

    def _compute_session_expected_range(
        self,
        on_chart: Dict[str, Any],
        sess_bias: str,
        sess_arch: str,
        target_p: float,
        is_forex: bool,
        is_index: bool,
        decimals: int
    ) -> Tuple[Dict[str, float], float]:
        """
        Anchors session expected_range and key_trigger around current_price,
        daily structure extremes, remaining ADR capacity, and session liquidity
        so directional ranges stay skewed toward the predicted move rather than
        anchoring blindly on stale Asian boundaries.
        """
        curr_p = float(on_chart.get("current_price", 0.0))
        daily_st = on_chart.get("daily_structure", {})
        sess_rng = on_chart.get("session_ranges", {})

        default_band = 0.0050 if is_forex else (150.0 if is_index else 15.0)
        default_adr = 0.0080 if is_forex else (300.0 if is_index else 25.0)
        default_asian = 0.0030 if is_forex else (100.0 if is_index else 10.0)

        pdh = float(daily_st.get("pdh", curr_p + default_band))
        pdl = float(daily_st.get("pdl", curr_p - default_band))
        asian_high = float(sess_rng.get("asian_high", pdh))
        asian_low = float(sess_rng.get("asian_low", pdl))
        asian_range = float(sess_rng.get("asian_range", max(0.0, asian_high - asian_low) or default_asian))

        daily_high = float(daily_st.get("daily_high", max(curr_p, asian_high)))
        daily_low = float(daily_st.get("daily_low", min(curr_p, asian_low)))
        daily_range = float(daily_st.get("daily_range", max(0.0, daily_high - daily_low)))
        adr_14 = float(daily_st.get("adr_14", default_adr))
        remaining_adr = max(0.0, adr_14 - daily_range)

        sweep_buf = 0.00025 if is_forex else (25.0 if is_index else 2.5)
        exp_buf = 0.0010 if is_forex else (80.0 if is_index else 10.0)
        pullback_floor = 0.0015 if is_forex else (60.0 if is_index else 6.0)
        max_reach = max(exp_buf * 1.5, adr_14)

        if sess_bias == "BEARISH":
            down_step = max(exp_buf, 0.65 * remaining_adr)
            raw_low = min(curr_p, daily_low) - down_step
            if (curr_p - max_reach) <= target_p < curr_p:
                raw_low = min(raw_low, target_p)
            downside_room = max(exp_buf, curr_p - raw_low)
            max_pullback = min(max(pullback_floor, 0.20 * adr_14), 0.60 * downside_room)
            struct_ceiling = max(asian_high, daily_high, curr_p) + sweep_buf
            raw_high = min(struct_ceiling, curr_p + max_pullback)
            key_trig = asian_high if curr_p >= asian_low else min(raw_high, asian_low)
        elif sess_bias == "BULLISH":
            up_step = max(exp_buf, 0.65 * remaining_adr)
            raw_high = max(curr_p, daily_high) + up_step
            if curr_p < target_p <= (curr_p + max_reach):
                raw_high = max(raw_high, target_p)
            upside_room = max(exp_buf, raw_high - curr_p)
            max_pullback = min(max(pullback_floor, 0.20 * adr_14), 0.60 * upside_room)
            struct_floor = min(asian_low, daily_low, curr_p) - sweep_buf
            raw_low = max(struct_floor, curr_p - max_pullback)
            key_trig = asian_low if curr_p <= asian_high else max(raw_low, asian_high)
        elif sess_arch == "CATALYST_WHIPSAW_RISK":
            whip_band = max(pullback_floor, asian_range * 1.5)
            raw_high = curr_p + whip_band
            raw_low = curr_p - whip_band
            key_trig = curr_p
        else:
            raw_high = max(asian_high, curr_p + sweep_buf)
            raw_low = min(asian_low, curr_p - sweep_buf)
            key_trig = (raw_high + raw_low) / 2.0

        return (
            {"high": round(raw_high, decimals), "low": round(raw_low, decimals)},
            round(key_trig, decimals),
        )

    def _evaluate_deterministic_matrix(
        self,
        on_chart: Dict[str, Any],
        off_chart: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Deterministic Quantitative Institutional Rule Matrix.
        Guarantees zero-failure, authentic institutional logic matching ICT & Macro fundamentals.
        """
        sym = on_chart.get("symbol", "XAUUSD")
        is_forex = "GBP" in sym.upper() or "EUR" in sym.upper()
        is_index = "NQ" in sym.upper() or "NAS" in sym.upper() or "USTEC" in sym.upper() or "US100" in sym.upper() or "SPX" in sym.upper()
        decimals = 5 if is_forex else 2

        curr_p = on_chart.get("current_price", 0.0)
        daily_st = on_chart.get("daily_structure", {})
        weekly_st = on_chart.get("weekly_structure", {})
        dol = on_chart.get("draw_on_liquidity", {})
        htf = on_chart.get("htf_trend", {})
        smt = on_chart.get("smt_divergence", {})
        sess = on_chart.get("session_ranges", {})

        sentiment = off_chart.get("retail_sentiment", {})
        catalysts = off_chart.get("catalysts", {})

        default_band = 0.0050 if is_forex else (150.0 if is_index else 15.0)
        pdh = daily_st.get("pdh", curr_p + default_band)
        pdl = daily_st.get("pdl", curr_p - default_band)
        pdc = daily_st.get("pdc", curr_p)
        cwo = weekly_st.get("cwo", curr_p)
        pwh = weekly_st.get("pwh", curr_p + (default_band * 2))
        pwl = weekly_st.get("pwl", curr_p - (default_band * 2))
        adr_14 = daily_st.get("adr_14", 0.0080 if is_forex else (300.0 if is_index else 25.0))
        adr_util = daily_st.get("adr_utilization_pct", 20.0)

        has_swept_pdh = daily_st.get("has_swept_pdh", False)
        has_swept_pdl = daily_st.get("has_swept_pdl", False)

        h1_regime = htf.get("h1_regime", "CONSOLIDATION_RANGE")
        retail_long_pct = sentiment.get("retail_long_pct", 50.0)
        session_danger = catalysts.get("session_risk", "LOW")

        # --- 1. DAILY HORIZON CALCULATION (Calibrated Institutional Scoring) ---
        score_day = 0.0

        # Feature A: SFP at Daily Extremes
        if has_swept_pdh and curr_p < pdh:
            score_day -= 2.5  # SFP at highs
        elif has_swept_pdl and curr_p > pdl:
            score_day += 2.5  # SFP at lows

        # Feature B: Damped Previous Day Close (PDC) Relation
        noise_buffer = 0.05 * max(0.0030 if is_forex else (50.0 if is_index else 10.0), adr_14)
        if curr_p > pdc + noise_buffer:
            score_day += 0.5
        elif curr_p < pdc - noise_buffer:
            score_day -= 0.5

        # Feature C: H1 Structural Displacement Regime
        if h1_regime == "BULLISH_EXPANSION":
            score_day += 1.8
        elif h1_regime == "BEARISH_EXPANSION":
            score_day -= 1.8

        # Feature D: Institutional SMT Divergence
        if smt.get("type") == "BULLISH_SMT":
            score_day += 1.5
        elif smt.get("type") == "BEARISH_SMT":
            score_day -= 1.5

        # Feature E: Retail Contrarian Sentiment Positioning
        if retail_long_pct >= 70.0:
            score_day -= 1.5  # Institutional flush of retail longs
        elif retail_long_pct <= 30.0:
            score_day += 1.5  # Institutional short squeeze

        # Feature F: Weekly Range Premium / Discount Exhaustion
        if pwh > pwl:
            w_pct = (curr_p - pwl) / (pwh - pwl)
            if w_pct >= 0.85:
                score_day -= 1.0  # Resistance / exhaustion at weekly highs
            elif w_pct <= 0.15:
                score_day += 1.0  # Support / exhaustion at weekly lows

        # Calibrated Thresholding: Selective High-Conviction Gating & ADR Cap
        if adr_util >= 55.0:
            # Range exhaustion: > 55% of ADR consumed prior to main expansion
            day_bias = "CONSOLIDATION"
            day_conf = 0.65
            candle_arch = "ADR_EXHAUSTED_ROTATION"
            target_p = round(pdc, decimals)
            dol_type = "MEAN_REVERSION"
            inval_p = round(pdh if curr_p < pdc else pdl, decimals)
            day_rationale = f"ADR utilization at {adr_util}%; high probability of session equilibrium rotation."
        elif score_day >= 1.5:
            day_bias = "BULLISH"
            day_conf = min(0.92, round(0.65 + (score_day * 0.04), 2))
            candle_arch = "EXPANSION_UP_DAY"
            target_p = round(dol.get("target_price") or pdh, decimals)
            dol_type = "BUY_SIDE_LIQUIDITY"
            inval_p = round(daily_st.get("daily_low") or pdl, decimals)
            day_rationale = f"High-conviction bullish displacement (score +{score_day:.1f}); targeting overhead BSL."
        elif score_day <= -1.5:
            day_bias = "BEARISH"
            day_conf = min(0.92, round(0.65 + (abs(score_day) * 0.04), 2))
            candle_arch = "EXPANSION_DOWN_DAY"
            target_p = round(dol.get("target_price") or pdl, decimals)
            dol_type = "SELL_SIDE_LIQUIDITY"
            inval_p = round(daily_st.get("daily_high") or pdh, decimals)
            day_rationale = f"High-conviction bearish displacement (score {score_day:.1f}); targeting underlying SSL."
        else:
            day_bias = "CONSOLIDATION"
            day_conf = 0.60
            candle_arch = "INSIDE_DOJI_DAY"
            target_p = round(pdc, decimals)
            dol_type = "MEAN_REVERSION"
            inval_p = round(pdh, decimals)
            day_rationale = "Balanced forces / lack of structural displacement; range-bound equilibrium."

        # --- 2. SESSION HORIZON CALCULATION ---
        asian_high = sess.get("asian_high", pdh)
        asian_low = sess.get("asian_low", pdl)
        judas_offset = 0.0002 if is_forex else (20.0 if is_index else 2.0)

        if session_danger == "CRITICAL":
            sess_bias = "RANGE_CHOP"
            sess_conf = 0.55
            sess_arch = "CATALYST_WHIPSAW_RISK"
        elif day_bias == "BULLISH":
            # If bullish, Judas swing sweeps Asian low then expands up
            sess_bias = "BULLISH"
            sess_conf = day_conf
            sess_arch = "JUDAS_SWEEP_EXPANSION" if curr_p <= asian_low + judas_offset else "UNILATERAL_EXPANSION"
        elif day_bias == "BEARISH":
            # If bearish, Judas swing sweeps Asian high then expands down
            sess_bias = "BEARISH"
            sess_conf = day_conf
            sess_arch = "JUDAS_SWEEP_EXPANSION" if curr_p >= asian_high - judas_offset else "UNILATERAL_EXPANSION"
        else:
            sess_bias = "RANGE_CHOP"
            sess_conf = 0.58
            sess_arch = "RANGE_BOUND_CONSOLIDATION"

        expected_range, key_trig = self._compute_session_expected_range(
            on_chart=on_chart,
            sess_bias=sess_bias,
            sess_arch=sess_arch,
            target_p=target_p,
            is_forex=is_forex,
            is_index=is_index,
            decimals=decimals,
        )
        exp_high = expected_range["high"]
        exp_low = expected_range["low"]

        # --- 3. WEEKLY HORIZON CALCULATION ---
        if curr_p > cwo and day_bias == "BULLISH":
            week_bias = "BULLISH"
            week_conf = 0.76
            week_target = round(pwh, decimals)
            week_profile = "TUESDAY_LOW_OF_WEEK_EXPANSION"
        elif curr_p < cwo and day_bias == "BEARISH":
            week_bias = "BEARISH"
            week_conf = 0.78
            week_target = round(pwl, decimals)
            week_profile = "TUESDAY_HIGH_OF_WEEK_EXPANSION"
        else:
            week_bias = "NEUTRAL"
            week_conf = 0.62
            week_target = round(cwo, decimals)
            week_profile = "MID_WEEK_EQUILIBRIUM"

        synthesis = (
            f"Synthesizing on-chart MTF state with off-chart macro intelligence for {sym}: "
            f"Daily bias is {day_bias} (Conf: {int(day_conf*100)}%) with primary DOL targeting {dol_type} at {target_p:.{decimals}f}. "
            f"Session posture reflects {sess_arch} ({sess_bias}) with anticipated boundary [{exp_low:.{decimals}f} - {exp_high:.{decimals}f}]. "
            f"Weekly context aligns with {week_profile} toward {week_target:.{decimals}f}."
        )

        if is_forex:
            tm_policy = {
                "aligned": {"tp_r": 2.0, "be_ratchet_r": 1.0, "mode": "FOREX_TREND_EXPANSION", "note": "Forex Trend Expansion: 2.0R TP with 1.0R BE protection"},
                "counter": {"tp_r": 2.5, "be_ratchet_r": 1.0, "mode": "PREMIER_MEAN_REVERSION_FADE", "note": "Judas Sweep Fade: 2.5R TP with 1.0R BE ratchet (Premier Edge)"},
                "sideways": {"tp_r": 2.5, "be_ratchet_r": 0.8, "mode": "FOREX_RANGE_BOUNDARY_FADE", "note": "Forex Range Fade: 2.5R TP with 0.8R BE protection"}
            }
        elif is_index:
            tm_policy = {
                "aligned": {"tp_r": 3.5, "be_ratchet_r": 1.0, "mode": "INDEX_TREND_EXPANSION", "note": "Index Trend Expansion: 3.5R TP with early 1.0R BE protection"},
                "counter": {"tp_r": 3.0, "be_ratchet_r": 0.8, "mode": "INDEX_MEAN_REVERSION_FADE", "note": "Judas Sweep Fade: 3.0R TP with fast 0.8R BE ratchet (Premier Edge)"},
                "sideways": {"tp_r": 3.0, "be_ratchet_r": 0.8, "mode": "INDEX_RANGE_BOUNDARY_FADE", "note": "Index Range Boundary Fade: 3.0R TP with 0.8R BE protection"}
            }
        else:
            tm_policy = {
                "aligned": {"tp_r": 3.5, "be_ratchet_r": 1.5, "mode": "TREND_EXPANSION", "note": "Target Distal DOL with 1.5R BE protection"},
                "counter": {"tp_r": 1.5, "be_ratchet_r": 1.0, "mode": "COUNTER_TREND_SCALP", "note": "Defensive Scalp: 1.5R TP with fast 1.0R BE ratchet"},
                "sideways": {"tp_r": 3.5, "be_ratchet_r": 1.0, "mode": "EQUILIBRIUM_BOUNDARY_FADE", "note": "Range Fade: 3.5R Boundary Target with early 1.0R BE protection"}
            }

        return {
            "symbol": sym,
            "horizons": {
                "session": {
                    "bias": sess_bias,
                    "confidence": sess_conf,
                    "session_archetype": sess_arch,
                    "expected_range": {"high": exp_high, "low": exp_low},
                    "key_trigger": key_trig,
                    "catalyst_danger": session_danger
                },
                "day": {
                    "bias": day_bias,
                    "confidence": day_conf,
                    "daily_dol": {
                        "target": target_p,
                        "type": dol_type,
                        "rationale": day_rationale
                    },
                    "invalidation": inval_p,
                    "candle_archetype": candle_arch
                },
                "week": {
                    "bias": week_bias,
                    "confidence": week_conf,
                    "macro_target": week_target,
                    "weekly_profile": week_profile
                }
            },
            "trade_management": tm_policy,
            "synthesis_rationale": synthesis
        }
