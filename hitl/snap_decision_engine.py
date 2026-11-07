"""
TradingGuard HITL - SubQ Snap Decision Engine
An isolated, high-speed multimodal decision module powered by Subquadratic SubQ Snap (subq-snap-1.1).
Replaces slow, non-deterministic generative LLM debate parsing with typed, bounded classifications.
"""

import os
import sys
import json
import time
import base64
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.config import SNAP_API_KEY, SNAP_API_URL, SNAP_MODEL, MAX_RISK_USD
from hitl.council_memory import memory_engine
from hitl.sentiment_feed import format_sentiment_summary


def _encode_image_base64(image_path: Path, max_bytes: int = 2 * 1024 * 1024) -> Optional[Dict[str, str]]:
    """Encodes a PNG or JPEG file into a raw base64 string for SubQ Snap."""
    if not image_path.exists():
        return None
    try:
        data = image_path.read_bytes()
        if len(data) > max_bytes:
            # Over limit, omit to avoid exceeding request boundaries
            return None
        mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        b64_str = base64.b64encode(data).decode("utf-8")
        return {"mediaType": mime, "base64": b64_str}
    except Exception as e:
        print(f"[SubQ Snap] Failed to encode image {image_path}: {e}")
        return None


class SnapDecisionEngine:
    """
    Subquadratic SubQ Snap Decision Model Integration.
    Evaluates pre-screened trade opportunities against active playbook rules and MTF charts,
    returning typed decisions (BUY_LIMIT, SELL_LIMIT, STAND_ASIDE) and confidence metrics in ~1-2 seconds.
    """

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None):
        self.api_key = api_key or SNAP_API_KEY
        self.api_url = api_url or SNAP_API_URL
        self.model = SNAP_MODEL

        if not self.api_key:
            print("[SubQ Snap] Warning: SNAP_API_KEY is not set.")

    def evaluate_candidate(
        self,
        symbol: str,
        session_label: str,
        screener_setup: Dict[str, Any],
        mtf_state: Dict[str, Any],
        current_quote: Dict[str, float],
        chart_paths: Optional[List[Path]] = None,
        timeout: int = 15
    ) -> Dict[str, Any]:
        """
        Evaluates a pre-screened trading candidate through SubQ Snap.
        """
        if not self.api_key:
            return {
                "decision": "STAND_ASIDE",
                "confidence": 0.0,
                "probabilities": {},
                "primary_driver": "API_KEY_MISSING",
                "latency_ms": 0.0,
                "error": "Missing SNAP_API_KEY"
            }

        start_t = time.perf_counter()

        # 1. Gather Playbook Rules
        playbook_text = memory_engine.get_playbook_prompt_section(symbol)

        # 2. Gather Retail Sentiment
        sentiment_text = format_sentiment_summary(symbol)

        # 3. Assemble Structured State Context
        arch_id = screener_setup.get("archetype_id", "UNKNOWN")
        setup_type = screener_setup.get("setup_type", "NONE")
        proposed_dir = screener_setup.get("direction", "NONE")
        entry_p = screener_setup.get("entry_price", 0.0)
        sl_p = screener_setup.get("sl_price", 0.0)
        tp_p = screener_setup.get("target_price") or screener_setup.get("dol_target", 0.0)
        risk_pts = abs(entry_p - sl_p) if (entry_p and sl_p) else 0.0

        # Archetype Category Classification (Reversal vs. Continuation)
        is_continuation = arch_id in (
            "SETUP-ARCH-003",
            "SETUP-ARCH-004",
            "SETUP-ARCH-010",
            "SETUP-ARCH-013"
        ) or "FVG_EXPANSION" in setup_type or "MOMENTUM" in setup_type

        mode_desc = "TREND_CONTINUATION_FVG" if is_continuation else "LIQUIDITY_RAID_REVERSAL"
        req_desc = "Internal FVG Imbalance Retest (External swing sweep not required)" if is_continuation else "External Liquidity Sweep (PDH/PDL or Session Extreme sweep required)"

        state_lines = [
            f"=== TRADING OPPORTUNITY CANDIDATE ===",
            f"Asset: {symbol}",
            f"Session: {session_label}",
            f"Current Bid/Ask: {current_quote.get('bid', 0.0)} / {current_quote.get('ask', 0.0)} (Spread: {current_quote.get('spread', 0.0)})",
            f"Firm Maximum Dollar Risk: ${MAX_RISK_USD:.2f} per 0.01 lot",
            "",
            f"=== QUANTITATIVE ICT PRE-SCREENER TELEMETRY ===",
            f"Archetype Detected: {arch_id} ({setup_type})",
            f"Archetype Classification: {mode_desc}",
            f"Liquidity Mechanism: {req_desc}",
            f"Proposed Direction: {proposed_dir}",
            f"Proposed Order: Entry={entry_p}, SL={sl_p}, TP/Target={tp_p}",
            f"Calculated Stop Distance: {risk_pts:.4f}",
            "",
            f"=== MULTI-TIMEFRAME STRUCTURE (MTF) ===",
            f"H1 Structural State: {mtf_state.get('h1_state', 'NEUTRAL')}",
            f"Daily Inside Day: {mtf_state.get('is_inside_day', False)}",
            f"Mid-Range Equilibrium Compression: {mtf_state.get('in_mid_equilibrium', False)}",
            f"Prior Day High/Low: {mtf_state.get('pdh')} / {mtf_state.get('pdl')}",
            f"External Target (DOL): {mtf_state.get('dol_external')}",
            "",
            sentiment_text,
            "",
            playbook_text
        ]
        state_str = "\n".join(state_lines)

        # 4. Prepare Images (Up to 4 MTF Charts)
        images_payload = []
        if chart_paths:
            for p in chart_paths[:4]:
                enc = _encode_image_base64(Path(p))
                if enc:
                    images_payload.append(enc)

        # 5. Define Structured Decisions API Questions (Archetype-Aware Routing)
        if is_continuation:
            decision_instructions = (
                f"Determine institutional execution for a Trend-Continuation / FVG-Expansion candidate ({arch_id}). "
                "Evaluate based on HTF directional momentum, energetic displacement leaving an unfilled Fair Value Gap (FVG), "
                "clear draw on liquidity (DOL), and absence of adverse macro resistance. Note: Continuation setups "
                "do NOT require sweeping external swing extremes; they enter on internal imbalance/FVG retests."
            )
            buy_criteria = (
                "Market is in clear bullish displacement or markup phase, price retests an unfilled bullish FVG/imbalance, "
                "HTF draw on liquidity is higher, stop loss is well-protected below displacement base and within "
                f"${MAX_RISK_USD:.2f}, and zero firm risk rules are violated."
            )
            sell_criteria = (
                "Market is in clear bearish displacement or markdown phase, price retests an unfilled bearish FVG/imbalance, "
                "HTF draw on liquidity is lower, stop loss is well-protected above displacement peak and within "
                f"${MAX_RISK_USD:.2f}, and zero firm risk rules are violated."
            )
            stand_aside_criteria = (
                "Price is trapped in low-volume consolidation, displacement candle lacks energetic volume, FVG is already completely filled, "
                "trade fades the higher-timeframe trend, or firm risk ceiling is exceeded."
            )
            veto_criteria = {
                "NO_VETO": "Zero rules violated. Displacement momentum, FVG clarity, and risk parameters fully pass.",
                "MACRO_DISALIGNMENT": "Violates RULE-CORE-002: Fades dominant Higher-Timeframe trend.",
                "WEAK_DISPLACEMENT": "Violates RULE-CORE-004: Lack of energetic displacement candle body close through FVG.",
                "INCOMPLETE_FVG": "Fair value gap is already fully closed or lacks clear imbalance boundary.",
                "MID_RANGE_CHOP": "Inside day or mid-range equilibrium chop without clear draw on liquidity.",
                "EXCESSIVE_RISK": f"Stop loss distance exceeds firm's ${MAX_RISK_USD:.2f} risk ceiling."
            }
            conviction_criteria = {
                "A_PLUS_PRIME": "High-velocity institutional expansion with strong FVG imbalance and unreached HTF draw on liquidity.",
                "STANDARD_VALID": "Standard valid trend continuation FVG retest conforming to rules.",
                "MARGINAL_CHOP": "Marginal continuation with fading momentum, overlapping candles, or low edge."
            }
        else:
            decision_instructions = (
                f"Determine institutional execution for a Liquidity-Raid / Structure-Reversal candidate ({arch_id}). "
                "Evaluate strictly based on prominent liquidity sweep (SSL/BSL/PDH/PDL), energetic rejection, double market structure shift (MSS), "
                "and institutional breaker block formation."
            )
            buy_criteria = (
                "Price swept key sell-side liquidity (SSL) or PDL, energetically displaced upward creating "
                "a confirmed 5M FVG/MSS, aligns with dominant macro structure, stop loss satisfies the "
                f"${MAX_RISK_USD:.2f} ceiling, and zero active firm rules are violated."
            )
            sell_criteria = (
                "Price swept key buy-side liquidity (BSL) or PDH, energetically displaced downward creating "
                "a confirmed 5M FVG/MSS, aligns with dominant macro structure, stop loss satisfies the "
                f"${MAX_RISK_USD:.2f} ceiling, and zero active firm rules are violated."
            )
            stand_aside_criteria = (
                "Market is trapped in mid-range equilibrium, sweep is unconfirmed, displacement is weak, "
                "macro structure is violated, inside-day compression exists, or any active firm playbook "
                "rule dictates standing aside."
            )
            veto_criteria = {
                "NO_VETO": "Zero rules violated. Liquidity sweep, displacement, and risk parameters fully pass.",
                "MACRO_DISALIGNMENT": "Violates RULE-CORE-002: Fades dominant Higher-Timeframe trend.",
                "UNCONFIRMED_SWEEP": "Violates RULE-CORE-003: No prominent liquidity pool swept prior to trigger.",
                "WEAK_DISPLACEMENT": "Violates RULE-CORE-004: Lack of energetic displacement candle body close.",
                "MID_RANGE_CHOP": "Inside day or mid-range equilibrium chop without clear draw on liquidity.",
                "EXCESSIVE_RISK": f"Stop loss distance exceeds firm's ${MAX_RISK_USD:.2f} risk ceiling."
            }
            conviction_criteria = {
                "A_PLUS_PRIME": "Prime institutional reversal setup with clean liquidity pool sweep and explosive displacement.",
                "STANDARD_VALID": "Standard valid institutional reversal conforming to rules.",
                "MARGINAL_CHOP": "Marginal setup with conflicting signals, weak displacement, or low edge."
            }

        questions = {
            "decision": {
                "type": "choice",
                "instructions": decision_instructions,
                "criteria": {
                    "BUY_LIMIT": buy_criteria,
                    "SELL_LIMIT": sell_criteria,
                    "STAND_ASIDE": stand_aside_criteria
                }
            },
            "veto_check": {
                "type": "choice",
                "instructions": "Identify if any firm risk or structural veto condition is triggered.",
                "criteria": veto_criteria
            },
            "conviction": {
                "type": "choice",
                "instructions": "Rate institutional conviction tier for this trading setup.",
                "criteria": conviction_criteria
            }
        }

        request_body = {
            "model": self.model,
            "state": state_str,
            "questions": questions
        }
        if images_payload:
            request_body["images"] = images_payload

        # 6. Execute SubQ Snap Request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            req = urllib.request.Request(
                self.api_url,
                data=json.dumps(request_body).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status_code = resp.status
                resp_text = resp.read().decode("utf-8")

            elapsed_ms = (time.perf_counter() - start_t) * 1000.0

            if status_code == 200:
                data = json.loads(resp_text)
                answers = data.get("answers", {})

                # Extract typed decision
                dec_obj = answers.get("decision", {})
                decision = dec_obj.get("choice", "STAND_ASIDE")
                confidence = dec_obj.get("confidence", 0.0)
                probabilities = dec_obj.get("probabilities", {})

                # Extract veto/driver
                veto_obj = answers.get("veto_check", {})
                primary_driver = veto_obj.get("choice", "NO_VETO")

                # Extract conviction tier
                conv_obj = answers.get("conviction", {})
                conviction_tier = conv_obj.get("choice", "MARGINAL_CHOP")

                return {
                    "decision": decision,
                    "confidence": round(confidence, 3),
                    "probabilities": {k: round(v, 4) for k, v in probabilities.items()},
                    "primary_driver": primary_driver,
                    "conviction_tier": conviction_tier,
                    "latency_ms": round(elapsed_ms, 1),
                    "input_tokens": data.get("usage", {}).get("input_tokens", 0),
                    "source": "subq-snap-1.1",
                    "raw_answers": answers
                }
            else:
                return {
                    "decision": "STAND_ASIDE",
                    "confidence": 0.0,
                    "probabilities": {},
                    "primary_driver": f"HTTP_ERROR_{status_code}",
                    "latency_ms": round((time.perf_counter() - start_t) * 1000.0, 1),
                    "error": resp_text
                }

        except urllib.error.HTTPError as e:
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            error_body = e.read().decode("utf-8", errors="replace")
            print(f"[SubQ Snap API 422/Error]: {error_body}")
            return {
                "decision": "STAND_ASIDE",
                "confidence": 0.0,
                "probabilities": {},
                "primary_driver": f"HTTP_ERROR_{e.code}",
                "latency_ms": round(elapsed_ms, 1),
                "error": error_body
            }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            return {
                "decision": "STAND_ASIDE",
                "confidence": 0.0,
                "probabilities": {},
                "primary_driver": "EXCEPTION",
                "latency_ms": round(elapsed_ms, 1),
                "error": str(e)
            }


# Singleton export
snap_engine = SnapDecisionEngine()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("--- Testing SubQ Snap Decision Engine ---")
    mock_setup = {
        "archetype_id": "SETUP-ARCH-010",
        "setup_type": "BEARISH_PROMINENT_SWEEP_MSS",
        "direction": "SHORT",
        "entry_price": 4076.57,
        "sl_price": 4082.61,
        "target_price": 4055.00
    }
    mock_mtf = {
        "h1_state": "BEARISH_MSS",
        "is_inside_day": False,
        "in_mid_equilibrium": False,
        "pdh": 4082.00,
        "pdl": 4020.00,
        "dol_external": 4020.00
    }
    mock_quote = {"bid": 4076.50, "ask": 4076.70, "spread": 0.20}

    res = snap_engine.evaluate_candidate(
        symbol="XAUUSD",
        session_label="NY Open (NFP)",
        screener_setup=mock_setup,
        mtf_state=mock_mtf,
        current_quote=mock_quote
    )
    print("\nDecision Result:")
    print(json.dumps(res, indent=2))
