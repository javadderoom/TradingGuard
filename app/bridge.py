"""
TradingGuard — JSON Bridge
Manages the session.json file shared between the Python app and the MT5 EA.
Uses file-level locking (msvcrt on Windows) to prevent read/write collisions.
"""

import json
import os
import time
import msvcrt
from datetime import datetime
from app.config import SESSION_JSON_PATH


# Default state written when a new session starts or on reset
_DEFAULT_SESSION = {
    "version": 1,
    "session_active": False,
    "trading_allowed": False,
    "bias": "neutral",
    "invalidation_price": 0.0,
    "news_lock": False,
    "daily_loss_usd": 0.0,
    "daily_profit_usd": 0.0,
    "trades_today": 0,
    "consecutive_losses": 0,
    # Phase 3: bias expiry / strict mode
    "bias_set_at": "",
    "losses_since_bias": 0,
    "bias_expired": False,
    "strict_mode": False,
    # Long break after consecutive losses
    "break_active": False,
    "break_until": "",
    "shutdown_signal": False,
    "cooldown_until": "",
    "last_trade_result": "",
    "timestamp": "",
}


class SessionBridge:
    """Read / write the session.json bridge file with file-level locking."""

    def __init__(self, path: str = SESSION_JSON_PATH):
        self.path = path

    # ── Public API ─────────────────────────────────────────────────────────

    def read(self) -> dict:
        """Return the current session state. Creates file if missing.
        Merges any missing default fields for backward compatibility."""
        if not os.path.exists(self.path):
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.reset()
        data = self._locked_read()
        merged = dict(_DEFAULT_SESSION)
        merged.update(data)
        return merged

    def write(self, data: dict) -> None:
        """Overwrite the entire session file."""
        data["timestamp"] = datetime.now().isoformat()
        self._locked_write(data)

    def update(self, **fields) -> dict:
        """Merge *fields* into the current state and persist."""
        data = self.read()
        data.update(fields)
        self.write(data)
        return data

    def reset(self) -> dict:
        """Reset session.json to defaults."""
        data = dict(_DEFAULT_SESSION)
        self.write(data)
        return data

    # ── Internal helpers (Windows file locking) ────────────────────────────

    def _locked_read(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as f:
            # Shared lock for reading
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                content = f.read()
                return json.loads(content) if content.strip() else dict(_DEFAULT_SESSION)
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

    def _locked_write(self, data: dict) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            # Exclusive lock for writing
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                json.dump(data, f, indent=2)
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
