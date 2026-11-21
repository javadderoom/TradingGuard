"""
TradingGuard HITL - Fundamental Enforcement Governor
Manages dynamic and persistent switching between:
  - "advisory"  : Enriches Telegram cards, OmniTrend Oracle, and Council without blocking trades.
  - "hard_veto" : Blocks counter-fundamental entries ONLY when high-conviction AND tape-confirmed.
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from hitl.config import BASE_DIR, FUNDAMENTAL_ENFORCEMENT_MODE
from hitl.fundamental.http_utils import write_json_atomic

logger = logging.getLogger(__name__)

GOVERNOR_STATE_FILE = BASE_DIR / "hitl" / "memory" / "fundamental_governor.json"
_LOCK = threading.Lock()
VALID_MODES = ("advisory", "hard_veto")


def normalize_fundamental_symbol(symbol: str) -> str:
    """Maps broker/user aliases (e.g. XAUUSD_o, GOLD, USTEC, WTI) to canonical asset keys."""
    s = (symbol or "XAUUSD").upper().replace("_O", "").replace("_", "").strip()
    if any(k in s for k in ("XAU", "GOLD")):
        return "XAUUSD"
    if any(k in s for k in ("XAG", "SILVER")):
        return "XAGUSD"
    if "EUR" in s and "GBP" not in s and "JPY" not in s and "XAU" not in s:
        return "EURUSD"
    if "GBP" in s:
        return "GBPUSD"
    if "JPY" in s and "USD" in s:
        return "USDJPY"
    if "USDJPY" in s:
        return "USDJPY"
    if any(k in s for k in ("NQ", "NAS", "USTEC", "US100")):
        return "NQ"
    if any(k in s for k in ("SPX", "US500", "SP500")):
        return "SPX"
    if any(k in s for k in ("HK50", "HSI", "HANG")):
        return "HK50"
    if "BTC" in s:
        return "BTCUSD"
    if "ETH" in s:
        return "ETHUSD"
    if any(k in s for k in ("CRUDE", "OIL", "WTI", "BRENT", "CL=F")):
        return "USCRUDE"
    return s or "XAUUSD"


def _read_governor_file() -> Dict[str, Any]:
    if not GOVERNOR_STATE_FILE.exists():
        return {}
    try:
        with open(GOVERNOR_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"[FundamentalGovernor] Failed reading state: {e}")
        return {}


def get_enforcement_mode() -> str:
    """
    Returns active enforcement mode ('advisory' or 'hard_veto').
    Priority: persisted fundamental_governor.json -> hitl.config.FUNDAMENTAL_ENFORCEMENT_MODE -> 'advisory'.
    """
    with _LOCK:
        state = _read_governor_file()
        mode = str(state.get("mode", "")).strip().lower()
        if mode in VALID_MODES:
            return mode
        cfg = str(FUNDAMENTAL_ENFORCEMENT_MODE).strip().lower()
        return cfg if cfg in VALID_MODES else "advisory"


def set_enforcement_mode(mode: str, toggled_by: str = "user") -> str:
    """Sets and persists fundamental enforcement mode ('advisory' or 'hard_veto')."""
    clean_mode = str(mode or "advisory").strip().lower()
    if clean_mode not in VALID_MODES:
        raise ValueError(f"Invalid fundamental enforcement mode: {mode!r}. Expected one of {VALID_MODES}.")
    with _LOCK:
        state = _read_governor_file()
        state["mode"] = clean_mode
        state["last_toggled"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        state["toggled_by"] = toggled_by
        write_json_atomic(GOVERNOR_STATE_FILE, state)
        logger.info(f"[FundamentalGovernor] Mode set to {clean_mode} by {toggled_by}")
        return clean_mode


def toggle_enforcement_mode(toggled_by: str = "user") -> str:
    """Switches between 'advisory' and 'hard_veto'."""
    curr = get_enforcement_mode()
    nxt = "hard_veto" if curr == "advisory" else "advisory"
    return set_enforcement_mode(nxt, toggled_by=toggled_by)


def get_governor_info() -> Dict[str, Any]:
    """Returns full metadata on current enforcement mode."""
    with _LOCK:
        state = _read_governor_file()
        persisted = str(state.get("mode", "")).strip().lower() in VALID_MODES
        mode = state["mode"].strip().lower() if persisted else (
            FUNDAMENTAL_ENFORCEMENT_MODE if FUNDAMENTAL_ENFORCEMENT_MODE in VALID_MODES else "advisory"
        )
        return {
            "mode": mode,
            "last_toggled": state.get("last_toggled"),
            "toggled_by": state.get("toggled_by"),
            "source": "runtime_state" if persisted else "config_default",
            "config_default": FUNDAMENTAL_ENFORCEMENT_MODE,
        }


def evaluate_fundamental_gate(
    symbol: str,
    side: str,
    dossier: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluates a candidate trade direction against the latest Fundamental Causal Dossier.
    In 'advisory' mode: ALWAYS sets allow_trade=True.
    In 'hard_veto' mode: ONLY blocks when direction directly opposes a high-conviction bias
    (|score| >= 55, confidence >= 0.75) backed by at least one CONFIRMED_BY_TAPE causal chain.
    """
    mode = get_enforcement_mode()
    norm_sym = normalize_fundamental_symbol(symbol)
    side_u = (side or "").upper()
    is_buy = any(k in side_u for k in ("BUY", "LONG"))
    is_sell = any(k in side_u for k in ("SELL", "SHORT"))

    if dossier is None:
        from hitl.fundamental.causal_engine import fundamental_engine
        dossier = fundamental_engine.get_global_dossier(force_refresh=False, allow_llm=False)

    assets = (dossier or {}).get("assets", {})
    asset_view = assets.get(norm_sym) or assets.get(symbol.upper()) or {}

    if not asset_view:
        return {
            "mode": mode,
            "symbol": norm_sym,
            "allow_trade": True,
            "aligned": None,
            "alignment_label": "UNAVAILABLE",
            "asset_bias": "NEUTRAL",
            "asset_score": 0,
            "confidence": 0.0,
            "tape_verified": False,
            "dominant_mechanism": "No fundamental view available for symbol.",
            "reason": "Fundamental data unavailable; failing open.",
        }

    score = int(asset_view.get("score", 0) or 0)
    bias = str(asset_view.get("bias", "NEUTRAL")).upper()
    confidence = float(asset_view.get("confidence", 0.0) or 0.0)
    dominant_mechanism = str(
        asset_view.get("dominant_mechanism") or asset_view.get("dominant_driver") or "Balanced macro cross-currents"
    )

    # Verify whether at least one tape-confirmed causal chain applies to this symbol (or whole portfolio)
    chains = (dossier or {}).get("causal_chains", []) or []
    tape_verified = False
    for ch in chains:
        if str(ch.get("tape_verification", "")).upper() != "CONFIRMED_BY_TAPE":
            continue
        affected = ch.get("affected_assets", {}) or {}
        if isinstance(affected, dict) and (norm_sym in affected or "ALL" in affected):
            tape_verified = True
            break
        elif isinstance(affected, list) and (norm_sym in affected or not affected):
            tape_verified = True
            break

    # Alignment evaluation
    opposes_bullish = is_sell and score >= 25
    opposes_bearish = is_buy and score <= -25
    aligned_bullish = is_buy and score >= 25
    aligned_bearish = is_sell and score <= -25

    if aligned_bullish or aligned_bearish:
        aligned: Optional[bool] = True
        alignment_label = "ALIGNED"
    elif opposes_bullish or opposes_bearish:
        aligned = False
        alignment_label = "COUNTER_FUNDAMENTAL"
    else:
        aligned = None
        alignment_label = "NEUTRAL"

    strong_oppose = (is_sell and score >= 55) or (is_buy and score <= -55)
    allow_trade = True
    reason = f"Fundamental posture: {bias} (score {score:+d}, conf {int(confidence * 100)}%, mode={mode})."

    if mode == "hard_veto":
        if strong_oppose and confidence >= 0.75 and tape_verified:
            allow_trade = False
            reason = (
                f"HARD_VETO ({norm_sym} {'SELL' if is_sell else 'BUY'} opposes {bias} "
                f"score {score:+d}, conf {int(confidence * 100)}%, CONFIRMED_BY_TAPE): {dominant_mechanism}"
            )
        elif strong_oppose:
            reason = (
                f"Counter-fundamental warning ({bias}, score {score:+d}, conf {int(confidence * 100)}%, "
                f"tape_verified={tape_verified}) — below hard veto gate."
            )

    return {
        "mode": mode,
        "symbol": norm_sym,
        "allow_trade": allow_trade,
        "aligned": aligned,
        "alignment_label": alignment_label,
        "asset_bias": bias,
        "asset_score": score,
        "confidence": round(confidence, 2),
        "tape_verified": tape_verified,
        "dominant_mechanism": dominant_mechanism,
        "reason": reason,
    }
