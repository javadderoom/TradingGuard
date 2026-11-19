"""
TradingGuard HITL - Review Council Governor
Manages dynamic and persistent toggling of the Review Council (LLM deliberation).

When Council is ENABLED:
    Live radar convenes the 6-seat LLM deliberation council for tactical assessment
    and qualitative scrutiny before generating order plans.

When Council is DISABLED / BYPASSED:
    Live radar bypasses LLM deliberation entirely. Screener setups directly generate
    validated limit order execution plans (entry, SL, TP, R:R) with MT5 execution buttons,
    eliminating LLM latency and preventing adverse selection/flawed vetoes.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from hitl.config import BASE_DIR, COUNCIL_ENABLED

logger = logging.getLogger(__name__)

STATE_FILE = BASE_DIR / "hitl" / "memory" / "council_state.json"
_LOCK = threading.Lock()


def _read_state_file() -> Dict[str, Any]:
    """Reads state file safely."""
    if not STATE_FILE.exists():
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[CouncilGovernor] Failed to read state file: {e}")
        return {}


def _write_state_file(data: Dict[str, Any]) -> bool:
    """Writes state file safely."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = STATE_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp_file.replace(STATE_FILE)
        return True
    except Exception as e:
        logger.error(f"[CouncilGovernor] Failed to write state file: {e}")
        return False


def is_council_enabled() -> bool:
    """
    Returns True if Review Council is enabled, False if bypassed.
    Priority:
      1. Runtime persisted state in council_state.json
      2. hitl.config.COUNCIL_ENABLED (from .env / default True)
    """
    with _LOCK:
        state = _read_state_file()
        if "council_enabled" in state:
            return bool(state["council_enabled"])
        return bool(COUNCIL_ENABLED)


def set_council_enabled(enabled: bool, toggled_by: str = "user") -> bool:
    """
    Explicitly sets the Review Council enabled state and persists it.
    """
    with _LOCK:
        state = _read_state_file()
        state["council_enabled"] = bool(enabled)
        state["last_toggled"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        state["toggled_by"] = toggled_by
        _write_state_file(state)
        logger.info(f"[CouncilGovernor] Council enabled set to {enabled} by {toggled_by}")
        return bool(enabled)


def toggle_council(toggled_by: str = "user") -> bool:
    """
    Inverts the current Review Council state and returns the new state.
    """
    current = is_council_enabled()
    return set_council_enabled(not current, toggled_by=toggled_by)


def get_council_state_info() -> Dict[str, Any]:
    """
    Returns full metadata regarding current Council governor state.
    """
    with _LOCK:
        state = _read_state_file()
        is_persisted = "council_enabled" in state
        enabled = bool(state["council_enabled"]) if is_persisted else bool(COUNCIL_ENABLED)
        return {
            "council_enabled": enabled,
            "last_toggled": state.get("last_toggled"),
            "toggled_by": state.get("toggled_by"),
            "source": "runtime_state" if is_persisted else "config_default",
            "config_default": COUNCIL_ENABLED,
        }


def format_council_status_card() -> Tuple[str, Dict[str, Any]]:
    """
    Formats an unvarnished status card and Telegram inline keyboard
    for managing Review Council deliberation mode.
    """
    info = get_council_state_info()
    enabled = info["council_enabled"]

    status_badge = "🟢 *ENABLED* (Full 6-Seat LLM Deliberation)" if enabled else "🔴 *DISABLED / BYPASSED* (Direct Quant Setup Execution)"
    last_chg = info.get("last_toggled") or "Not toggled yet (System Default)"
    toggled_by = info.get("toggled_by") or "system"

    toggle_btn_text = "🔴 Disable Review Council" if enabled else "🟢 Enable Review Council"
    toggle_cb_data = "council_disable" if enabled else "council_enable"

    card = (
        f"🏛️ *TradingGuard Review Council Governor*\n\n"
        f"⚖️ *Current Status:* {status_badge}\n"
        f"⏱ *Last Changed:* `{last_chg}` ({toggled_by})\n"
        f"⚙️ *Configuration Fallback:* `COUNCIL_ENABLED={COUNCIL_ENABLED}`\n\n"
        f"📖 *Execution Pipelines:*\n"
        f"• *🟢 ENABLED:* Screener setups pass to the 6-Seat LLM Council for multi-perspective macro, HTF, liquidity, and risk scrutiny before generating order plans.\n"
        f"• *🔴 DISABLED (Recommended for Pure Alpha):* Screener setups bypass LLM vetoes and latency, immediately constructing validated limit order plans with Telegram execution buttons (`[Approve & Place]`, `[Veto]`).\n\n"
        f"🔬 *Empirical Audit Note:*\n"
        f"Forensic audits identified that bypassing LLM Council prevents adverse selection and flawed vetoes on statistically ratified setups."
    )

    inline_kb = {
        "inline_keyboard": [
            [
                {"text": toggle_btn_text, "callback_data": toggle_cb_data},
                {"text": "🔄 Refresh", "callback_data": "council_refresh"}
            ]
        ]
    }

    return card, inline_kb
