"""
TradingGuard Fundamental Engine - Layer 3 Multi-Order Causal Synthesis Engine
Synthesizes quantitative sovereign curves, cross-asset tape, CFTC positioning, and live news
to trace 2nd- and 3rd-order transmission mechanisms, verify narratives against live prices,
and score all major traded assets with deterministic quantitative fallback.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hitl.config import BASE_DIR, FUNDAMENTAL_CACHE_TTL_MINUTES, FUNDAMENTAL_LLM_MODEL
from hitl.fundamental.cot_feed import fetch_cot_positioning
from hitl.fundamental.governor import normalize_fundamental_symbol
from hitl.fundamental.http_utils import read_json_cache, write_json_atomic
from hitl.fundamental.market_tape import collect_full_market_tape
from hitl.fundamental.news_aggregator import fetch_global_macro_events
from hitl.macro_calendar import get_recent_released_events, get_upcoming_events

CORE_ASSETS: List[str] = [
    "XAUUSD",
    "XAGUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "NQ",
    "SPX",
    "HK50",
    "BTCUSD",
    "ETHUSD",
    "USCRUDE",
]

VALID_BIASES = ("STRONG_BEARISH", "BEARISH", "NEUTRAL", "BULLISH", "STRONG_BULLISH")
VALID_TAPE_TAGS = ("CONFIRMED_BY_TAPE", "PARTIAL", "CONTRADICTED_BY_TAPE")

STATE_FILE = BASE_DIR / "hitl" / "memory" / "fundamental_state.json"
HISTORY_LOG_FILE = BASE_DIR / "hitl" / "memory" / "fundamental_history_log.jsonl"

_ENGINE_LOCK = threading.Lock()


def _find_agy_binary() -> str:
    found = shutil.which("agy")
    if found:
        return found
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local_app_data, "agy", "bin", "agy.exe"),
        r"C:\Users\Javad\AppData\Local\agy\bin\agy.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "agy"


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _score_to_bias(score: float) -> str:
    if score >= 55:
        return "STRONG_BULLISH"
    if score >= 20:
        return "BULLISH"
    if score <= -55:
        return "STRONG_BEARISH"
    if score <= -20:
        return "BEARISH"
    return "NEUTRAL"


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """Extracts the outer JSON object cleanly from LLM stdout."""
    if not text:
        return None
    # Strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE).replace("```", "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = cleaned[start : end + 1]
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


import logging

logger = logging.getLogger(__name__)


def _run_agy_json(prompt_text: str, model: Optional[str] = None, timeout: int = 210) -> Optional[Dict[str, Any]]:
    """Invokes local Google Antigravity CLI cleanly using temp-file piping."""
    agy_bin = _find_agy_binary()
    chosen_model = model or FUNDAMENTAL_LLM_MODEL or "gemini-3.8-flash-high"
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as tf:
            tf.write(prompt_text)
            temp_name = tf.name

        cmd = [
            agy_bin,
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
            "--model",
            chosen_model,
            "-p",
            f"@{temp_name}",
        ]
        proc = subprocess.run(
            cmd,
            cwd=tempfile.gettempdir(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if proc.returncode != 0:
            err_msg = (proc.stderr or proc.stdout or "").strip()[:300]
            logger.warning(f"[CausalEngine] agy returned code {proc.returncode}: {err_msg}")
            print(f"[CausalEngine] agy non-zero exit ({proc.returncode}): {err_msg}")
            return None
        lines = [ln for ln in proc.stdout.splitlines() if not ln.startswith("jetski:")]
        parsed = _extract_json_block("\n".join(lines))
        if parsed is None:
            raw_preview = "\n".join(lines).strip()[:300]
            logger.warning(f"[CausalEngine] agy output lacked valid JSON: {raw_preview}")
            print(f"[CausalEngine] agy JSON parse miss: {raw_preview}")
        return parsed
    except subprocess.TimeoutExpired:
        logger.warning(f"[CausalEngine] agy synthesis timed out after {timeout}s")
        print(f"[CausalEngine] agy synthesis timed out after {timeout}s")
        return None
    except Exception as e:
        logger.warning(f"[CausalEngine] agy invocation exception: {e}")
        print(f"[CausalEngine] agy invocation exception: {e}")
        return None
    finally:
        if temp_name and os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except Exception:
                pass


class FundamentalCausalEngine:
    """
    Universal Multi-Asset Causal Macro Intelligence Engine.
    Combines sovereign yield curves, cross-asset tape, CFTC positioning, and live global news
    into tape-verified 2nd/3rd-order transmission chains and per-asset directional scores.
    """

    def __init__(self, ttl_minutes: Optional[int] = None):
        self.ttl_seconds = float((ttl_minutes or FUNDAMENTAL_CACHE_TTL_MINUTES) * 60)
        self._mem_dossier: Optional[Dict[str, Any]] = None
        self._mem_ts: float = 0.0

    def _build_llm_prompt(
        self,
        tape: Dict[str, Any],
        cot: Dict[str, Any],
        news_bundle: Dict[str, Any],
        target_symbols: Optional[List[str]] = None,
    ) -> str:
        assets_target = target_symbols or CORE_ASSETS
        diag = tape.get("diagnostics", {})
        ust = tape.get("treasury_curves", {})
        yf = tape.get("yahoo_tape", {})
        mt5_tape = tape.get("mt5_tape", {})

        # Compact quantitative tape summary
        rate_lines = [
            f"As-of Date: {ust.get('as_of_date', 'N/A')}",
            f"US 3M: {ust.get('nom_3m', {}).get('latest', 'N/A')}% ({ust.get('nom_3m', {}).get('chg_5d_bps', 'N/A')} bps 5D)",
            f"US 2Y: {ust.get('nom_2y', {}).get('latest', 'N/A')}% ({ust.get('nom_2y', {}).get('chg_5d_bps', 'N/A')} bps 5D)",
            f"US 10Y Official: {ust.get('nom_10y', {}).get('latest', 'N/A')}% ({ust.get('nom_10y', {}).get('chg_5d_bps', 'N/A')} bps 5D, {ust.get('nom_10y', {}).get('chg_20d_bps', 'N/A')} bps 20D) | Intraday YF ^TNX: {yf.get('US10Y_YF', {}).get('latest', 'N/A')}% ({yf.get('US10Y_YF', {}).get('chg_1d_bps', 'N/A')} bps 1D)",
            f"US 30Y: {ust.get('nom_30y', {}).get('latest', 'N/A')}% ({ust.get('nom_30y', {}).get('chg_5d_bps', 'N/A')} bps 5D)",
            f"US 10Y REAL YIELD (TIPS): {diag.get('real_10y_level', 'N/A')}% ({diag.get('real_10y_5d_bps', 'N/A')} bps 5D, {ust.get('real_10y', {}).get('chg_20d_bps', 'N/A')} bps 20D)",
            f"US 10Y BREAKEVEN INFLATION: {diag.get('breakeven_10y_level', 'N/A')}% ({diag.get('breakeven_5d_bps', 'N/A')} bps 5D)",
            f"2s10s Curve Slope: {diag.get('slope_2s10s', 'N/A')}% | Dominant Rate Driver Flag: {diag.get('rate_impulse_driver')}",
        ]

        asset_lines = []
        all_keys = [
            ("DXY/USDX", "USDX", "DXY_YF"),
            ("TLT (20Y Bond ETF)", None, "TLT"),
            ("HYG (High Yield Credit)", None, "HYG"),
            ("SHY (1-3Y Treasury)", None, "SHY"),
            ("VIX", "VIX", "VIX_YF"),
            ("SPX", "SPX", None),
            ("NQ (Nasdaq 100)", "NQ", None),
            ("FDAX (Germany)", "FDAX", None),
            ("HK50 (Hang Seng)", "HK50", "HSI_YF"),
            ("CSI300 (Mainland China)", None, "CSI300"),
            ("USD/CNH (Offshore Yuan)", None, "USDCNH"),
            ("NI225 (Japan)", "NI225", None),
            ("USCRUDE (WTI)", "USCRUDE", "WTI_YF"),
            ("UKBRENT (Brent)", "UKBRENT", None),
            ("COPPER (HG=F)", None, "COPPER"),
            ("XAUUSD (Gold)", "XAUUSD", "GOLD_YF"),
            ("XAGUSD (Silver)", "XAGUSD", None),
            ("EURUSD", "EURUSD", None),
            ("GBPUSD", "GBPUSD", None),
            ("USDJPY", "USDJPY", None),
            ("BTCUSD", "BTCUSD", "BTC_YF"),
            ("ETHUSD", "ETHUSD", None),
        ]
        for label, mk, yk in all_keys:
            rec = mt5_tape.get(mk) if mk and mk in mt5_tape else (yf.get(yk) if yk and yk in yf else None)
            if rec:
                asset_lines.append(
                    f"- {label}: {rec['latest']} | 1D: {rec['chg_1d_pct']:+.2f}% | 5D: {rec['chg_5d_pct']:+.2f}% | 20D: {rec['chg_20d_pct']:+.2f}%"
                )

        diag_flags = (
            f"Universal Cross-Asset Regime Flags:\n"
            f"- Bond-Equity Co-Selloff (Cash/Reserve Liquidation Flag): {diag.get('bond_equity_co_selloff')} (SPX 5D={diag.get('spx_5d_pct')}%, NQ 5D={diag.get('nq_5d_pct')}%, TLT 5D={diag.get('tlt_5d_pct')}%)\n"
            f"- Credit Stress (HYG vs SHY 5D): {diag.get('credit_stress_5d_pct')}%\n"
            f"- Asia/China Stress Flag: {diag.get('asia_china_stress')} (CSI300 5D={diag.get('csi300_5d_pct')}%, HK50 5D={diag.get('hk50_5d_pct')}%, USD/CNH 5D={diag.get('usdcnh_5d_pct')}%)\n"
            f"- Energy Impulse: 5D={diag.get('oil_5d_pct')}%, 20D={diag.get('oil_20d_pct')}%\n"
            f"- Copper vs Gold 5D Spread: {diag.get('copper_gold_5d_diff')}%\n"
            f"- G7 FX Strength Ranking (5D%): {diag.get('fx_strength_ranking_5d')}"
        )

        cot_lines = []
        for csym, cdata in (cot.get("assets") or {}).items():
            cot_lines.append(
                f"- {csym} ({cdata['report_date']} | {cdata['participant']}): Net {cdata['net_contracts']:+,} (WoW {cdata['net_change_wow']:+,}), Long%={cdata['long_pct']}%, Flag={cdata['crowding_flag']} [{cdata['note']}]"
            )

        ev_lines = []
        for ev in (news_bundle.get("events") or [])[:18]:
            raw_s = str(ev.get("summary") or "").strip()
            summ = f" — {raw_s[:90]}" if raw_s else ""
            ev_lines.append(f"- [{ev['published_utc']} | {ev['source']}] {ev['title']}{summ}")

        recent_cal_lines = [
            f"- [{r['date_str']} {r['time_str']} Tehran | {r['country']} {r['impact']}] {r['title']} (Fcst={r['forecast']}, Prev={r['previous']}, {r['minutes_ago']}m ago)"
            for r in (news_bundle.get("recent_releases") or [])[:6]
        ]
        upcoming_cal_lines = [
            f"- [{u['date_str']} {u['time_str']} Tehran | {u['country']} {u['impact']}] {u['title']} (Fcst={u['forecast']}, Prev={u['previous']}, in {u['minutes_away']}m)"
            for u in (news_bundle.get("upcoming_calendar") or [])[:8]
        ]

        prompt = f"""CRITICAL: Do NOT invoke any tools, file reads, shell commands, or web searches. All verified live data is provided below. Return ONLY the single valid JSON object in one immediate turn.

You are the Chief Global Macro & Cross-Asset Causal Strategist at a tier-1 institutional macro fund.
Analyze ONLY the live quantitative tape, institutional CFTC positioning, central bank / economic calendar releases, and live news headlines below.

STRICT ANALYTICAL RULES:
1. ZERO 1ST-ORDER STEREOTYPES OR HARDCODED STORIES: Never assume naive rules like "war = gold up", "stocks down = bonds up", or "rate hike = USD up". Identify the ACTUAL 2nd- and 3rd-order transmission mechanisms active right now:
   - E.g. War/oil shock -> inflation fears -> central bank stays hawkish -> real yields surge -> USD rallies & Gold falls; OR
   - Equity/Asia stress -> liquidity/reserve crunch -> sovereigns/funds sell US Treasuries -> bond prices drop & USD cash squeeze lifts USD -> Gold falls despite risk-off; OR
   - Tech/equity rout -> safe-haven flight INTO Treasuries -> yields drop sharply & Fed cut bets surge -> check which path the LIVE TAPE is ACTUALLY printing right now!
2. MANDATORY TAPE VERIFICATION: Every causal chain you output MUST cite exact live figures from Layer 1 below and assign:
   - "CONFIRMED_BY_TAPE" if the actual yield/DXY/bond/equity/asset numbers match the chain,
   - "PARTIAL" if evidence is mixed across horizons (e.g. 20D trend vs 1D reversal),
   - "CONTRADICTED_BY_TAPE" if headlines say one story while actual prices/yields are moving the opposite way. Never promote a contradicted story over what the tape proves.
3. COMPETING FORCES & INVALIDATION: For every single asset in {assets_target}, weigh BOTH active bullish tailwinds AND active bearish headwinds, state the dominant mechanism, and give a specific measurable macro invalidation trigger.
4. KEEP JSON CONCISE & COMPACT: Output 3-4 active causal chains (max 3 short steps each, <=15 words per step) and for each of the {len(assets_target)} assets keep forces to 1-2 short bullets (<=12 words each) so the full JSON completes cleanly and fast.
5. OUTPUT STRICT VALID JSON ONLY (no markdown fences, no commentary outside JSON).

=== LAYER 1A: US TREASURY NOMINAL & TIPS REAL YIELD CURVES ===
{chr(10).join(rate_lines)}

=== LAYER 1B: LIVE CROSS-ASSET MARKET TAPE (1D / 5D / 20D) ===
{chr(10).join(asset_lines)}

=== LAYER 1C: {diag_flags}

=== LAYER 1D: OFFICIAL CFTC COT INSTITUTIONAL POSITIONING ===
{chr(10).join(cot_lines) if cot_lines else "COT unavailable."}

=== LAYER 2A: LIVE GLOBAL MACRO, CENTRAL BANK & GEOPOLITICAL NEWS (LAST 48H) ===
{chr(10).join(ev_lines) if ev_lines else "No live headlines fetched."}

=== LAYER 2B: RECENTLY RELEASED SCHEDULED ECONOMIC PRINTS (PAST 12H) ===
{chr(10).join(recent_cal_lines) if recent_cal_lines else "None in past 12h."}

=== LAYER 2C: UPCOMING HIGH/MEDIUM ECONOMIC CATALYSTS (NEXT 72H) ===
{chr(10).join(upcoming_cal_lines) if upcoming_cal_lines else "None in next 72h."}

REQUIRED OUTPUT JSON SCHEMA:
{{
  "global_macro_regime": {{
    "label": "SHORT_MACHINE_READABLE_REGIME_NAME",
    "summary": "2-3 sentence synthesis of the dominant global macro regime verified by yields, dollar, equities, and news.",
    "dominant_theme": "One crisp headline naming the primary macro transmission force active now",
    "dollar_regime": "BULLISH_LIQUIDITY_SQUEEZE | BULLISH_YIELD_DRIVEN | NEUTRAL_RANGE | BEARISH_EASING | MIXED",
    "rates_regime": "REAL_YIELD_SURGE | INFLATION_REPRICING | FLIGHT_TO_SAFETY_DROP | RANGE_BOUND",
    "risk_regime": "RISK_ON | RISK_OFF_FLIGHT_TO_QUALITY | LIQUIDITY_CRUNCH_CO_SELLOFF | ROTATION"
  }},
  "causal_chains": [
    {{
      "chain_id": "CHAIN-1",
      "event": "Triggering real-world event or release from Layer 2/1",
      "transmission_steps": [
        "Step 1: trigger...",
        "Step 2: intermediate rate/bond/liquidity/reserve mechanism...",
        "Step 3: final transmission onto asset flows..."
      ],
      "tape_verification": "CONFIRMED_BY_TAPE | PARTIAL | CONTRADICTED_BY_TAPE",
      "tape_evidence": "Exact numbers from Layer 1 proving or contradicting this chain",
      "affected_assets": {{
        "XAUUSD": "BEARISH",
        "NQ": "BEARISH"
      }},
      "horizon": "INTRADAY | SWING_1_5D | MACRO_1_4W",
      "confidence": 0.85
    }}
  ],
  "assets": {{
    "SYMBOL": {{
      "bias": "STRONG_BULLISH | BULLISH | NEUTRAL | BEARISH | STRONG_BEARISH",
      "score": -100_to_100_integer,
      "confidence": 0.0_to_1.0_float,
      "horizon_bias": {{
        "intraday": "BULLISH | BEARISH | NEUTRAL",
        "swing_1_5d": "BULLISH | BEARISH | NEUTRAL",
        "macro_1_4w": "BULLISH | BEARISH | NEUTRAL"
      }},
      "dominant_driver": "Primary macro driver label",
      "dominant_mechanism": "Explicit A -> B -> C causal link driving this asset right now",
      "bullish_forces": ["Specific tailwind + evidence"],
      "bearish_forces": ["Specific headwind + evidence"],
      "invalidation_trigger": "Measurable macro/tape condition that flips this view",
      "execution_posture": "BUY_DIPS_ALIGNED | SELL_RALLIES_ALIGNED | TWO_WAY_SELECTIVE | DEFENSIVE_REDUCED_SIZE"
    }}
  }}
}}

Ensure `"assets"` contains complete entries for ALL {len(assets_target)} symbols: {", ".join(assets_target)}."""
        return prompt

    def _run_deterministic_fallback(
        self,
        tape: Dict[str, Any],
        cot: Dict[str, Any],
        news_bundle: Dict[str, Any],
        target_symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Pure quantitative cross-asset factor engine.
        Guarantees authentic, non-hardcoded causal chains and multi-asset scores directly from
        live real yields, nominal curve, DXY, G7 LFX spreads, VIX, credit stress, China/Asia,
        energy/copper, and CFTC positioning whenever the LLM is offline or disabled.
        """
        diag = tape.get("diagnostics", {})
        ust = tape.get("treasury_curves", {})
        yf = tape.get("yahoo_tape", {})
        mt5_tape = tape.get("mt5_tape", {})
        cot_assets = (cot or {}).get("assets", {})

        dxy_5d = float(diag.get("dxy_5d_pct") or 0.0)
        dxy_1d = float(diag.get("dxy_1d_pct") or 0.0)
        dxy_20d = float(diag.get("dxy_20d_pct") or 0.0)
        real_5d = float(diag.get("real_10y_5d_bps") or 0.0)
        real_lvl = float(diag.get("real_10y_level") or 0.0)
        be_5d = float(diag.get("breakeven_5d_bps") or 0.0)
        nom_5d = float(diag.get("nom_10y_5d_bps") or 0.0)
        tlt_5d = float(diag.get("tlt_5d_pct") or 0.0)
        spx_5d = float(diag.get("spx_5d_pct") or 0.0)
        nq_5d = float(diag.get("nq_5d_pct") or 0.0)
        vix_lvl = float(diag.get("vix_level") or 18.0)
        vix_5d = float(diag.get("vix_5d_pct") or 0.0)
        credit_5d = float(diag.get("credit_stress_5d_pct") or 0.0)
        csi_raw = diag.get("csi300_5d_pct")
        hk50_raw = diag.get("hk50_5d_pct")
        cnh_raw = diag.get("usdcnh_5d_pct")
        csi_5d = float(csi_raw) if csi_raw is not None else 0.0
        hk50_5d = float(hk50_raw) if hk50_raw is not None else 0.0
        cnh_5d = float(cnh_raw) if cnh_raw is not None else 0.0
        csi_lbl = f"{csi_5d:+.2f}%" if csi_raw is not None else "N/A"
        hk50_lbl = f"{hk50_5d:+.2f}%" if hk50_raw is not None else "N/A"
        cnh_lbl = f"{cnh_5d:+.2f}%" if cnh_raw is not None else "N/A"
        oil_5d = float(diag.get("oil_5d_pct") or 0.0)
        oil_20d = float(diag.get("oil_20d_pct") or 0.0)
        copper_5d = float(diag.get("copper_5d_pct") or 0.0)
        co_selloff = bool(diag.get("bond_equity_co_selloff"))
        asia_stress = bool(diag.get("asia_china_stress"))

        # Build quantitative causal chains directly from live diagnostics
        chains: List[Dict[str, Any]] = []

        if co_selloff:
            chains.append({
                "chain_id": "TAPE-CO-SELLOFF",
                "event": "Simultaneous Equity & Long-Duration Treasury Selloff",
                "transmission_steps": [
                    f"Risk equities fall (SPX 5D {spx_5d:+.2f}%, NQ 5D {nq_5d:+.2f}%)",
                    f"Long Treasuries sell off simultaneously instead of catching safety bid (TLT 5D {tlt_5d:+.2f}%, US10Y 5D {nom_5d:+.1f} bps)",
                    "Broad dash-for-cash / collateral demand strengthens USD funding and tightens liquidity across metals, tech, and crypto",
                ],
                "tape_verification": "CONFIRMED_BY_TAPE",
                "tape_evidence": f"SPX {spx_5d:+.2f}%, TLT {tlt_5d:+.2f}%, US10Y {nom_5d:+.1f}bps, DXY {dxy_5d:+.2f}%",
                "affected_assets": {"XAUUSD": "BEARISH", "NQ": "BEARISH", "SPX": "BEARISH", "BTCUSD": "BEARISH"},
                "horizon": "SWING_1_5D",
                "confidence": 0.80,
            })

        if abs(real_5d) >= 5.0 or abs(nom_5d) >= 5.0 or abs(be_5d) >= 5.0:
            if real_5d > 0:
                chains.append({
                    "chain_id": "TAPE-REAL-RATES",
                    "event": "TIPS Real Yield Tightening Impulse",
                    "transmission_steps": [
                        f"10Y Real Yield shifted {real_5d:+.1f} bps over 5D (level {real_lvl:.2f}%, 10Y BE {be_5d:+.1f} bps)",
                        "Higher inflation-adjusted sovereign yields raise opportunity cost of non-yielding assets and compress high-multiple valuations",
                        "Creates structural headwind for Gold/Silver and long-duration Nasdaq/Crypto while supporting USD rate carry",
                    ],
                    "tape_verification": "CONFIRMED_BY_TAPE",
                    "tape_evidence": f"US10Y Real {real_lvl:.2f}% ({real_5d:+.1f} bps 5D), Nom10Y ({nom_5d:+.1f} bps 5D)",
                    "affected_assets": {"XAUUSD": "BEARISH", "XAGUSD": "BEARISH", "NQ": "BEARISH", "USDJPY": "BULLISH"},
                    "horizon": "MACRO_1_4W",
                    "confidence": 0.78,
                })
            elif real_5d <= -5.0 or nom_5d <= -5.0:
                chains.append({
                    "chain_id": "TAPE-YIELD-EASING",
                    "event": "Sovereign Yield & Real Rate Compression",
                    "transmission_steps": [
                        f"10Y Nominal ({nom_5d:+.1f} bps 5D) and/or TIPS Real Yield ({real_5d:+.1f} bps 5D) compressed",
                        "Lower discount rates ease real opportunity cost of holding zero-yield stores of value and growth duration",
                        "Provides tailwind to Precious Metals, long-duration Tech (NQ), and non-USD majors (if VIX/credit stay contained)",
                    ],
                    "tape_verification": "CONFIRMED_BY_TAPE",
                    "tape_evidence": f"Nom10Y {nom_5d:+.1f}bps, Real10Y {real_5d:+.1f}bps (level {real_lvl:.2f}%)",
                    "affected_assets": {"XAUUSD": "BULLISH", "EURUSD": "BULLISH", "USDJPY": "BEARISH"},
                    "horizon": "SWING_1_5D",
                    "confidence": 0.74,
                })

        if asia_stress:
            chains.append({
                "chain_id": "TAPE-ASIA-LIQUIDITY",
                "event": "China / Asian Equity & Offshore Yuan (CNH) Stress",
                "transmission_steps": [
                    f"Asian risk assets under pressure (HK50 5D {hk50_lbl}, CSI300 5D {csi_lbl}, USD/CNH {cnh_lbl})",
                    "Regional equity drawdowns + weaker CNH tighten Asian dollar liquidity and weigh on global cyclicals/commodities",
                    "Supports USD liquidity preference while pressuring HK50, Industrial Metals (Copper/Silver), and high-beta FX",
                ],
                "tape_verification": "CONFIRMED_BY_TAPE",
                "tape_evidence": f"HK50 {hk50_lbl}, CSI300 {csi_lbl}, USD/CNH {cnh_lbl}",
                "affected_assets": {"HK50": "BEARISH", "XAGUSD": "BEARISH", "EURUSD": "BEARISH"},
                "horizon": "SWING_1_5D",
                "confidence": 0.74,
            })

        if abs(oil_5d) >= 2.5 or abs(oil_20d) >= 5.0:
            o_dir = "BULLISH" if oil_5d > 0 else "BEARISH"
            chains.append({
                "chain_id": "TAPE-ENERGY-SHOCK",
                "event": f"Crude Oil Supply/Demand Impulse ({oil_5d:+.2f}% 5D / {oil_20d:+.2f}% 20D)",
                "transmission_steps": [
                    f"Energy benchmarks shifted sharply (5D {oil_5d:+.2f}%, 20D {oil_20d:+.2f}%)",
                    "Rising oil injects headline inflation pressure (keeps central banks restrictive); falling oil relieves inflation and growth costs",
                    "Transmits across USD inflation expectations, net-importer FX (EUR/JPY), and bond yields",
                ],
                "tape_verification": "CONFIRMED_BY_TAPE",
                "tape_evidence": f"Oil 5D {oil_5d:+.2f}%, 20D {oil_20d:+.2f}%, 10Y BE {be_5d:+.1f}bps",
                "affected_assets": {"USCRUDE": o_dir},
                "horizon": "SWING_1_5D",
                "confidence": 0.72,
            })

        if abs(dxy_5d) >= 0.30:
            d_txt = "appreciation" if dxy_5d > 0 else "softening"
            chains.append({
                "chain_id": "TAPE-DOLLAR-FLOW",
                "event": f"Broad US Dollar {d_txt.title()} ({dxy_5d:+.2f}% 5D)",
                "transmission_steps": [
                    f"USDX shifted {dxy_5d:+.2f}% over 5D and {dxy_20d:+.2f}% over 20D",
                    "Dollar liquidity acts as global numeraire tightening/loosening valve across G7 FX, Commodities, and Crypto",
                ],
                "tape_verification": "CONFIRMED_BY_TAPE",
                "tape_evidence": f"USDX 1D {dxy_1d:+.2f}%, 5D {dxy_5d:+.2f}%, 20D {dxy_20d:+.2f}%",
                "affected_assets": {
                    "EURUSD": "BEARISH" if dxy_5d > 0 else "BULLISH",
                    "GBPUSD": "BEARISH" if dxy_5d > 0 else "BULLISH",
                    "USDJPY": "BULLISH" if dxy_5d > 0 else "BEARISH",
                    "XAUUSD": "BEARISH" if dxy_5d > 0 else "BULLISH",
                },
                "horizon": "INTRADAY",
                "confidence": 0.76,
            })

        if not chains:
            chains.append({
                "chain_id": "TAPE-EQUILIBRIUM",
                "event": "Balanced Cross-Asset Macro Equilibrium",
                "transmission_steps": [
                    f"US10Y Real Yield ({real_lvl:.2f}%, 5D {real_5d:+.1f}bps) and USDX ({dxy_5d:+.2f}% 5D) show muted impulse",
                    "No extreme cross-asset liquidation or rate shock detected on tape; technical structure dominates intraday",
                ],
                "tape_verification": "CONFIRMED_BY_TAPE",
                "tape_evidence": f"USDX {dxy_5d:+.2f}%, Real10Y {real_5d:+.1f}bps, VIX {vix_lvl:.1f}",
                "affected_assets": {},
                "horizon": "INTRADAY",
                "confidence": 0.60,
            })

        def _cot_nudge(sym: str) -> Tuple[float, Optional[str]]:
            c = cot_assets.get(sym)
            if not c:
                return 0.0, None
            n = 0.0
            wow = c.get("net_change_wow", 0)
            crowd = c.get("crowding_flag", "BALANCED")
            if wow > 0:
                n += 4.0
            elif wow < 0:
                n -= 4.0
            # Mild contrarian caution at extreme crowding
            note = f"COT {c['participant']}: Net {c['net_contracts']:+,} (WoW {wow:+,}, {crowd})"
            return n, note

        def _score_asset(sym: str) -> Dict[str, Any]:
            bullish_f: List[str] = []
            bearish_f: List[str] = []
            sc = 0.0

            eur_lfx_5d = mt5_tape.get("EURLFX", {}).get("chg_5d_pct", 0.0)
            gbp_lfx_5d = mt5_tape.get("GBPLFX", {}).get("chg_5d_pct", 0.0)
            jpy_lfx_5d = mt5_tape.get("LFXJPY", {}).get("chg_5d_pct", 0.0)

            if sym in ("XAUUSD", "XAGUSD"):
                # Real yield inverse + DXY inverse + Co-selloff liquidation drag vs geopolitical/flight-to-safety
                if real_5d > 3.0 or real_lvl >= 2.2:
                    drag = min(38.0, max(12.0, real_5d * 1.4 + max(0.0, (real_lvl - 2.0) * 18.0)))
                    sc -= drag
                    bearish_f.append(f"High/rising US 10Y TIPS Real Yield ({real_lvl:.2f}%, 5D {real_5d:+.1f}bps) increases opportunity cost")
                elif real_5d < -4.0:
                    lift = min(35.0, abs(real_5d) * 1.4)
                    sc += lift
                    bullish_f.append(f"Falling US 10Y TIPS Real Yield ({real_5d:+.1f}bps 5D) reduces carrying cost")

                if dxy_5d > 0.25:
                    sc -= min(28.0, dxy_5d * 20.0)
                    bearish_f.append(f"USD appreciation ({dxy_5d:+.2f}% 5D) compresses dollar-denominated metals")
                elif dxy_5d < -0.25:
                    sc += min(28.0, abs(dxy_5d) * 20.0)
                    bullish_f.append(f"USD softening ({dxy_5d:+.2f}% 5D) supports precious metals")

                if co_selloff:
                    sc -= 18.0
                    bearish_f.append(f"Bond-Equity co-selloff (TLT {tlt_5d:+.2f}%, SPX {spx_5d:+.2f}%) creates margin/reserve liquidity selling pressure")
                elif vix_lvl >= 22.0 and nom_5d <= -4.0:
                    sc += 16.0
                    bullish_f.append(f"Elevated VIX ({vix_lvl:.1f}) paired with falling Treasury yields signals genuine safe-haven bid")

                if sym == "XAGUSD":
                    # Silver also carries industrial China/Copper sensitivity
                    if copper_5d < -1.5 or asia_stress:
                        sc -= 14.0
                        bearish_f.append(f"Industrial/China slowdown drag (Copper {copper_5d:+.2f}%, HK50 {hk50_5d:+.2f}%) weighs on Silver")
                    elif copper_5d > 1.5:
                        sc += 12.0
                        bullish_f.append(f"Industrial Copper strength ({copper_5d:+.2f}% 5D) supports Silver")

            elif sym in ("EURUSD", "GBPUSD"):
                base_lfx = eur_lfx_5d if sym == "EURUSD" else gbp_lfx_5d
                base_name = "EUR" if sym == "EURUSD" else "GBP"
                spread = base_lfx - dxy_5d
                sc += _clamp(spread * 22.0, -45.0, 45.0)
                if dxy_5d > 0.2:
                    bearish_f.append(f"Broad USD strength ({dxy_5d:+.2f}% 5D) pressures {sym}")
                elif dxy_5d < -0.2:
                    bullish_f.append(f"USD softening ({dxy_5d:+.2f}% 5D) supports {sym}")
                if base_lfx > 0.2:
                    bullish_f.append(f"{base_name} sovereign index ({base_lfx:+.2f}% 5D) shows relative strength")
                elif base_lfx < -0.2:
                    bearish_f.append(f"{base_name} sovereign index ({base_lfx:+.2f}% 5D) shows relative weakness")
                if credit_5d < -1.0 or vix_lvl >= 24.0:
                    sc -= 12.0
                    bearish_f.append(f"Global risk-off/credit stress (VIX {vix_lvl:.1f}, HYG-SHY {credit_5d:+.2f}%) boosts safe-haven USD demand")
                if sym == "EURUSD" and (oil_5d >= 3.0 or oil_20d >= 8.0):
                    sc -= 10.0
                    bearish_f.append(f"Rising oil prices ({oil_5d:+.2f}% 5D) hurt Eurozone terms of trade")

            elif sym == "USDJPY":
                # Positive spread = USD stronger + US10Y higher - VIX carry unwind
                sc += _clamp((dxy_5d - jpy_lfx_5d) * 20.0, -35.0, 35.0)
                sc += _clamp(nom_5d * 1.1, -25.0, 25.0)
                if nom_5d > 3.0 or dxy_5d > 0.2:
                    bullish_f.append(f"US yield/dollar advantage (US10Y {nom_5d:+.1f}bps, USDX {dxy_5d:+.2f}%) supports USDJPY")
                if vix_lvl >= 23.0 and (spx_5d < -1.5 or nom_5d < -5.0):
                    sc -= 22.0
                    bearish_f.append(f"Equity/volatility stress (VIX {vix_lvl:.1f}, SPX {spx_5d:+.2f}%) triggers JPY carry unwind risk")

            elif sym in ("NQ", "SPX"):
                eq_chg = nq_5d if sym == "NQ" else spx_5d
                sc += _clamp(eq_chg * 6.0, -35.0, 35.0)
                if sym == "NQ":
                    sc -= _clamp(real_5d * 1.3, -25.0, 25.0)
                    if real_5d > 4.0:
                        bearish_f.append(f"Rising real yields ({real_5d:+.1f}bps) compress long-duration tech multiples")
                else:
                    sc -= _clamp(nom_5d * 0.9, -20.0, 20.0)
                sc += _clamp(credit_5d * 8.0, -20.0, 20.0)
                if credit_5d < -0.8:
                    bearish_f.append(f"High-yield credit underperformance ({credit_5d:+.2f}% vs SHY) signals risk contraction")
                elif credit_5d > 0.5:
                    bullish_f.append(f"Healthy credit appetite (HYG-SHY {credit_5d:+.2f}%) supports risk assets")
                if vix_lvl >= 22.0:
                    sc -= min(22.0, (vix_lvl - 20.0) * 2.5)
                    bearish_f.append(f"Elevated VIX ({vix_lvl:.1f}, 5D {vix_5d:+.1f}%) drives systematic vol-targeting de-risking")
                if eq_chg <= -2.0:
                    bearish_f.append(f"Negative 5D equity momentum ({eq_chg:+.2f}%) reflects active institutional distribution")
                elif eq_chg >= 1.5:
                    bullish_f.append(f"Positive 5D trend ({eq_chg:+.2f}%) confirms institutional accumulation")

            elif sym == "HK50":
                sc += _clamp(hk50_5d * 7.0 + csi_5d * 5.0 - cnh_5d * 18.0, -65.0, 65.0)
                if hk50_5d < -1.0 or csi_5d < -1.0:
                    bearish_f.append(f"China/HK equities weak (HK50 {hk50_lbl}, CSI300 {csi_lbl})")
                elif hk50_5d > 1.0:
                    bullish_f.append(f"Asian equity inflows (HK50 {hk50_5d:+.2f}%)")
                if cnh_5d > 0.25:
                    bearish_f.append(f"Offshore Yuan depreciation (USD/CNH {cnh_5d:+.2f}%) signals capital outflow pressure")

            elif sym in ("BTCUSD", "ETHUSD"):
                btc_5d = mt5_tape.get(sym, yf.get("BTC_YF", {})).get("chg_5d_pct", 0.0)
                sc += _clamp(btc_5d * 3.0, -25.0, 25.0)
                sc -= _clamp(dxy_5d * 18.0 + real_5d * 1.1, -30.0, 30.0)
                sc += _clamp(credit_5d * 7.0 + nq_5d * 3.0, -25.0, 25.0)
                if co_selloff or credit_5d < -1.0 or nq_5d <= -2.0:
                    bearish_f.append(f"Tightening liquidity / tech risk-off (NQ {nq_5d:+.2f}%, HYG-SHY {credit_5d:+.2f}%, DXY {dxy_5d:+.2f}%)")
                elif dxy_5d < -0.3 and nq_5d > 1.0:
                    bullish_f.append(f"Loose dollar liquidity & tech risk appetite support crypto flows")
                if btc_5d < -3.0:
                    bearish_f.append(f"Negative crypto tape momentum ({btc_5d:+.2f}% 5D)")
                elif btc_5d > 3.0:
                    bullish_f.append(f"Strong spot crypto demand ({btc_5d:+.2f}% 5D)")

            elif sym == "USCRUDE":
                sc += _clamp(oil_5d * 6.5 + oil_20d * 2.5, -55.0, 55.0)
                if oil_5d > 1.0:
                    bullish_f.append(f"Supply tightness / geopolitical risk bid pushing Crude {oil_5d:+.2f}% 5D")
                elif oil_5d < -1.0:
                    bearish_f.append(f"Demand weakness / supply easing pressuring Crude {oil_5d:+.2f}% 5D")
                if dxy_5d > 0.5 or copper_5d < -2.0:
                    sc -= 10.0
                    bearish_f.append(f"Strong USD ({dxy_5d:+.2f}%) / global growth drag (Copper {copper_5d:+.2f}%) caps upside")

            else:
                # Generic fallback for non-core MT5 symbols (e.g. AUDUSD, USDCHF, FDAX, NI225)
                if sym in mt5_tape:
                    chg5 = mt5_tape[sym].get("chg_5d_pct", 0.0)
                    sc += _clamp(chg5 * 14.0, -60.0, 60.0)
                    (bullish_f if chg5 >= 0 else bearish_f).append(f"Live 5D asset flow ({chg5:+.2f}%) vs USDX ({dxy_5d:+.2f}%)")
                else:
                    sc -= _clamp(dxy_5d * 18.0, -40.0, 40.0)

            cot_adj, cot_note = _cot_nudge(sym)
            sc += cot_adj
            if cot_note:
                (bullish_f if cot_adj >= 0 else bearish_f).append(cot_note)

            final_score = int(round(_clamp(sc, -95.0, 95.0)))
            bias = _score_to_bias(final_score)
            # Confidence scales sensibly with magnitude & data richness
            conf = round(_clamp(0.48 + (abs(final_score) / 100.0) * 0.35 + (0.08 if ust.get("status") == "OK" else 0.0), 0.35, 0.88), 2)

            if not bullish_f:
                bullish_f.append("Potential technical mean-reversion / oversold short covering")
            if not bearish_f:
                bearish_f.append("Headline reversal or unexpected sovereign yield rebound")

            dir_simple = "BULLISH" if final_score >= 20 else ("BEARISH" if final_score <= -20 else "NEUTRAL")
            posture = (
                "BUY_DIPS_ALIGNED" if final_score >= 30 else (
                    "SELL_RALLIES_ALIGNED" if final_score <= -30 else "TWO_WAY_SELECTIVE"
                )
            )
            dom_mech = (bearish_f[0] if final_score < 0 else bullish_f[0])

            return {
                "bias": bias,
                "score": final_score,
                "confidence": conf,
                "horizon_bias": {
                    "intraday": dir_simple,
                    "swing_1_5d": dir_simple,
                    "macro_1_4w": dir_simple,
                },
                "dominant_driver": chains[0]["event"],
                "dominant_mechanism": dom_mech,
                "bullish_forces": bullish_f[:3],
                "bearish_forces": bearish_f[:3],
                "invalidation_trigger": f"Reversal in 10Y real yield ({real_5d:+.1f}bps) or USDX ({dxy_5d:+.2f}% 5D) trend.",
                "execution_posture": posture,
            }

        symbols_list = target_symbols or CORE_ASSETS
        assets_dict = {s: _score_asset(s) for s in symbols_list}

        # Global macro regime classification directly from live diagnostics
        if co_selloff:
            regime_lbl = "LIQUIDITY_CRUNCH_CO_SELLOFF"
            risk_reg = "LIQUIDITY_CRUNCH_CO_SELLOFF"
        elif vix_lvl >= 23.0 and nom_5d < -4.0:
            regime_lbl = "FLIGHT_TO_SAFETY_RISK_OFF"
            risk_reg = "RISK_OFF_FLIGHT_TO_QUALITY"
        elif real_5d >= 6.0 and dxy_5d > 0.25:
            regime_lbl = "REAL_YIELD_AND_DOLLAR_TIGHTENING"
            risk_reg = "RISK_OFF"
        elif spx_5d > 1.0 and credit_5d > 0.2:
            regime_lbl = "RISK_ON_EXPANSION"
            risk_reg = "RISK_ON"
        else:
            regime_lbl = "MIXED_CROSS_ASSET_ROTATION"
            risk_reg = "ROTATION"

        dollar_reg = (
            "BULLISH_LIQUIDITY_SQUEEZE" if (co_selloff and dxy_5d > 0) else (
                "BULLISH_YIELD_DRIVEN" if (dxy_5d >= 0.35 and nom_5d > 0) else (
                    "BEARISH_EASING" if dxy_5d <= -0.35 else "NEUTRAL_RANGE"
                )
            )
        )

        # Pick strongest headline event from Layer 2 if available
        top_ev_title = (news_bundle.get("events") or [{}])[0].get("title", "Quantitative cross-asset telemetry")
        summary = (
            f"Tape-driven quantitative synthesis: {regime_lbl.replace('_', ' ').title()}. "
            f"US10Y Real Yield at {real_lvl:.2f}% ({real_5d:+.1f} bps 5D), DXY 5D {dxy_5d:+.2f}%, "
            f"SPX 5D {spx_5d:+.2f}%, TLT 5D {tlt_5d:+.2f}%. Top live news: {top_ev_title[:100]}."
        )

        return {
            "global_macro_regime": {
                "label": regime_lbl,
                "summary": summary,
                "dominant_theme": chains[0]["event"],
                "dollar_regime": dollar_reg,
                "rates_regime": diag.get("rate_impulse_driver", "BALANCED"),
                "risk_regime": risk_reg,
            },
            "causal_chains": chains,
            "assets": assets_dict,
            "analysis_source": "deterministic_tape_fallback",
        }

    def _validate_and_normalize_dossier(
        self,
        raw_llm: Optional[Dict[str, Any]],
        fallback: Dict[str, Any],
        target_symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Validates LLM JSON against strict institutional schema; clamps scores/confidence,
        enforces tape_verification tags, and backfills any missing asset from deterministic fallback.
        """
        if not isinstance(raw_llm, dict) or not isinstance(raw_llm.get("assets"), dict):
            return fallback

        symbols_req = target_symbols or CORE_ASSETS
        norm_assets: Dict[str, Any] = {}

        for sym in symbols_req:
            item = raw_llm["assets"].get(sym)
            if not isinstance(item, dict):
                norm_assets[sym] = fallback["assets"][sym]
                continue

            raw_score = item.get("score")
            try:
                score = int(round(_clamp(float(raw_score), -100.0, 100.0)))
            except Exception:
                score = fallback["assets"][sym]["score"]

            raw_conf = item.get("confidence")
            try:
                conf = round(_clamp(float(raw_conf), 0.0, 1.0), 2)
            except Exception:
                conf = fallback["assets"][sym]["confidence"]

            raw_bias = str(item.get("bias", "")).upper().strip()
            bias = raw_bias if raw_bias in VALID_BIASES else _score_to_bias(score)

            hb = item.get("horizon_bias")
            if not isinstance(hb, dict):
                hb = fallback["assets"][sym]["horizon_bias"]

            bull_f = item.get("bullish_forces") if isinstance(item.get("bullish_forces"), list) else fallback["assets"][sym]["bullish_forces"]
            bear_f = item.get("bearish_forces") if isinstance(item.get("bearish_forces"), list) else fallback["assets"][sym]["bearish_forces"]

            norm_assets[sym] = {
                "bias": bias,
                "score": score,
                "confidence": conf,
                "horizon_bias": {
                    "intraday": str(hb.get("intraday", bias)).upper(),
                    "swing_1_5d": str(hb.get("swing_1_5d", bias)).upper(),
                    "macro_1_4w": str(hb.get("macro_1_4w", bias)).upper(),
                },
                "dominant_driver": str(item.get("dominant_driver") or fallback["assets"][sym]["dominant_driver"]),
                "dominant_mechanism": str(item.get("dominant_mechanism") or fallback["assets"][sym]["dominant_mechanism"]),
                "bullish_forces": [str(x) for x in bull_f[:4]],
                "bearish_forces": [str(x) for x in bear_f[:4]],
                "invalidation_trigger": str(item.get("invalidation_trigger") or fallback["assets"][sym]["invalidation_trigger"]),
                "execution_posture": str(item.get("execution_posture") or fallback["assets"][sym]["execution_posture"]).upper(),
            }

        chains_raw = raw_llm.get("causal_chains")
        norm_chains: List[Dict[str, Any]] = []
        if isinstance(chains_raw, list):
            for idx, ch in enumerate(chains_raw[:6], 1):
                if not isinstance(ch, dict):
                    continue
                tv = str(ch.get("tape_verification", "PARTIAL")).upper().strip()
                if tv not in VALID_TAPE_TAGS:
                    tv = "PARTIAL"
                try:
                    c_conf = round(_clamp(float(ch.get("confidence", 0.65)), 0.0, 1.0), 2)
                except Exception:
                    c_conf = 0.65
                steps = ch.get("transmission_steps")
                if not isinstance(steps, list) or not steps:
                    steps = [str(ch.get("event", "Macro transmission"))]
                norm_chains.append({
                    "chain_id": str(ch.get("chain_id") or f"CHAIN-{idx}"),
                    "event": str(ch.get("event") or "Global Macro Event"),
                    "transmission_steps": [str(s) for s in steps[:5]],
                    "tape_verification": tv,
                    "tape_evidence": str(ch.get("tape_evidence") or "Derived from cross-asset tape"),
                    "affected_assets": ch.get("affected_assets") if isinstance(ch.get("affected_assets"), dict) else {},
                    "horizon": str(ch.get("horizon") or "SWING_1_5D").upper(),
                    "confidence": c_conf,
                })

        if not norm_chains:
            norm_chains = fallback["causal_chains"]

        reg_raw = raw_llm.get("global_macro_regime")
        fb_reg = fallback["global_macro_regime"]
        if isinstance(reg_raw, dict):
            global_reg = {
                "label": str(reg_raw.get("label") or fb_reg["label"]),
                "summary": str(reg_raw.get("summary") or fb_reg["summary"]),
                "dominant_theme": str(reg_raw.get("dominant_theme") or fb_reg["dominant_theme"]),
                "dollar_regime": str(reg_raw.get("dollar_regime") or fb_reg["dollar_regime"]),
                "rates_regime": str(reg_raw.get("rates_regime") or fb_reg["rates_regime"]),
                "risk_regime": str(reg_raw.get("risk_regime") or fb_reg["risk_regime"]),
            }
        else:
            global_reg = fb_reg

        return {
            "global_macro_regime": global_reg,
            "causal_chains": norm_chains,
            "assets": norm_assets,
            "analysis_source": f"llm:{FUNDAMENTAL_LLM_MODEL}",
        }

    def _append_history_log(self, dossier: Dict[str, Any]) -> None:
        """Appends a compact audit snapshot to JSONL for forward empirical accuracy auditing."""
        try:
            HISTORY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            diag = dossier.get("diagnostics", {})
            record = {
                "timestamp_utc": dossier.get("generated_at_utc"),
                "analysis_source": dossier.get("analysis_source"),
                "regime": dossier.get("global_macro_regime", {}).get("label"),
                "real_10y": diag.get("real_10y_level"),
                "nom_10y": diag.get("nom_10y_level"),
                "dxy_level": diag.get("dxy_level"),
                "dxy_5d_pct": diag.get("dxy_5d_pct"),
                "vix": diag.get("vix_level"),
                "assets": {
                    sym: {
                        "bias": data.get("bias"),
                        "score": data.get("score"),
                        "confidence": data.get("confidence"),
                    }
                    for sym, data in (dossier.get("assets") or {}).items()
                },
            }
            with open(HISTORY_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get_global_dossier(
        self,
        force_refresh: bool = False,
        allow_llm: bool = True,
    ) -> Dict[str, Any]:
        """
        Returns the unified multi-asset global macro dossier.
        Reads fresh memory/disk cache if < TTL unless force_refresh=True.
        Note: if existing cache was produced only by deterministic fallback and allow_llm=True
        and force_refresh=True (or if cache is empty), invokes LLM synthesis cleanly.
        """
        with _ENGINE_LOCK:
            now = time.time()
            if not force_refresh:
                if self._mem_dossier and (now - self._mem_ts < self.ttl_seconds):
                    return self._mem_dossier
                disk_data, is_fresh = read_json_cache(STATE_FILE, self.ttl_seconds)
                if disk_data and is_fresh and isinstance(disk_data.get("assets"), dict):
                    self._mem_dossier = disk_data
                    self._mem_ts = STATE_FILE.stat().st_mtime
                    return disk_data

            t0 = time.perf_counter()
            tape = collect_full_market_tape(force_refresh=force_refresh)
            cot = fetch_cot_positioning(force_refresh=force_refresh)
            news_bundle = fetch_global_macro_events(force_refresh=force_refresh)

            fallback = self._run_deterministic_fallback(tape, cot, news_bundle, target_symbols=CORE_ASSETS)
            synthesized = fallback

            if allow_llm:
                prompt = self._build_llm_prompt(tape, cot, news_bundle, target_symbols=CORE_ASSETS)
                raw_llm = _run_agy_json(prompt, model=FUNDAMENTAL_LLM_MODEL, timeout=210)
                synthesized = self._validate_and_normalize_dossier(raw_llm, fallback, target_symbols=CORE_ASSETS)

            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            dossier = {
                "generated_at_utc": now_utc,
                "generated_epoch": now,
                "latency_ms": elapsed_ms,
                "analysis_source": synthesized["analysis_source"],
                "global_macro_regime": synthesized["global_macro_regime"],
                "causal_chains": synthesized["causal_chains"],
                "assets": synthesized["assets"],
                "diagnostics": tape.get("diagnostics", {}),
                "treasury_curves": {
                    k: v
                    for k, v in (tape.get("treasury_curves") or {}).items()
                    if k in ("as_of_date", "nom_2y", "nom_10y", "nom_30y", "real_10y", "breakeven_10y", "slope_2s10s", "slope_3m10s")
                },
                "cot_positioning": cot.get("assets", {}),
                "cot_report_date": cot.get("latest_report_date"),
                "top_headlines": news_bundle.get("events", [])[:10],
                "upcoming_calendar": news_bundle.get("upcoming_calendar", [])[:10],
                "recent_releases": news_bundle.get("recent_releases", [])[:8],
                "feed_health": news_bundle.get("feed_health", {}),
            }

            write_json_atomic(STATE_FILE, dossier)
            self._append_history_log(dossier)
            self._mem_dossier = dossier
            self._mem_ts = now
            return dossier

    def get_asset_view(
        self,
        symbol: str = "XAUUSD",
        force_refresh: bool = False,
        allow_llm: bool = False,
    ) -> Dict[str, Any]:
        """
        Returns complete fundamental dossier + targeted single-asset view.
        Fast O(1) lookup for CORE_ASSETS when cache is warm or allow_llm=False.
        Synthesizes cross-asset proxy view cleanly for any non-core symbol (e.g. AUDUSD, FDAX).
        """
        norm_sym = normalize_fundamental_symbol(symbol)
        dossier = self.get_global_dossier(force_refresh=force_refresh, allow_llm=allow_llm)
        assets = dossier.get("assets", {})

        if norm_sym in assets:
            asset_entry = assets[norm_sym]
        else:
            # Synthesize cleanly for non-core symbol using cached tape & global regime
            tape = collect_full_market_tape(force_refresh=False)
            cot = fetch_cot_positioning(force_refresh=False)
            news_bundle = fetch_global_macro_events(force_refresh=False)
            fb = self._run_deterministic_fallback(tape, cot, news_bundle, target_symbols=[norm_sym])
            if allow_llm:
                prompt = self._build_llm_prompt(tape, cot, news_bundle, target_symbols=[norm_sym])
                raw = _run_agy_json(prompt, model=FUNDAMENTAL_LLM_MODEL, timeout=60)
                val = self._validate_and_normalize_dossier(raw, fb, target_symbols=[norm_sym])
                asset_entry = val["assets"][norm_sym]
            else:
                asset_entry = fb["assets"][norm_sym]

        diag = dossier.get("diagnostics", {})
        cot_entry = (dossier.get("cot_positioning") or {}).get(norm_sym)
        cal_up = get_upcoming_events(norm_sym, hours_ahead=48)
        cal_rec = get_recent_released_events(norm_sym, hours_back=12)

        return {
            "symbol": norm_sym,
            "requested_symbol": symbol,
            "generated_at_utc": dossier.get("generated_at_utc"),
            "analysis_source": dossier.get("analysis_source"),
            "global_macro_regime": dossier.get("global_macro_regime", {}),
            "causal_chains": dossier.get("causal_chains", []),
            "diagnostics": diag,
            "treasury_curves": dossier.get("treasury_curves", {}),
            "cot": cot_entry,
            "upcoming_calendar": cal_up[:6],
            "recent_releases": cal_rec[:5],
            "top_headlines": dossier.get("top_headlines", [])[:6],
            **asset_entry,
        }


# Global singleton instance
fundamental_engine = FundamentalCausalEngine()


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="TradingGuard Causal Fundamental Engine CLI")
    parser.add_argument("--refresh", action="store_true", help="Force fresh data & causal synthesis")
    parser.add_argument("--no-llm", action="store_true", help="Run deterministic quantitative tape synthesis only")
    parser.add_argument("--symbol", default="", help="Optional single asset deep dive (e.g. XAUUSD, NQ, BTCUSD)")
    args = parser.parse_args()

    dossier = fundamental_engine.get_global_dossier(force_refresh=args.refresh, allow_llm=not args.no_llm)
    print(f"=== GLOBAL MACRO REGIME [{dossier['analysis_source']}] ({dossier['latency_ms']} ms) ===")
    reg = dossier["global_macro_regime"]
    print(f"Regime: {reg['label']} | Theme: {reg['dominant_theme']}")
    print(f"Summary: {reg['summary']}\n")
    print("Active Causal Chains:")
    for ch in dossier["causal_chains"]:
        print(f"  [{ch['chain_id']} | {ch['tape_verification']} | conf={ch['confidence']}] {ch['event']}")
        for step in ch["transmission_steps"]:
            print(f"     -> {step}")
        print(f"     Evidence: {ch['tape_evidence']}")
    print("\nAsset Scoreboard:")
    for sym, a in dossier["assets"].items():
        print(f"  {sym:8s} | {a['bias']:14s} | score={a['score']:+4d} | conf={a['confidence']:.2f} | {a['dominant_mechanism'][:90]}")

    if args.symbol:
        av = fundamental_engine.get_asset_view(args.symbol, force_refresh=False, allow_llm=False)
        print(f"\n=== TARGET ASSET: {av['symbol']} ===")
        print(json.dumps({k: v for k, v in av.items() if k not in ("top_headlines", "causal_chains")}, indent=2, default=str))
