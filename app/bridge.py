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
        self._ensure_file_exists()
        with open(self.path, "r", encoding="utf-8") as f:
            self._acquire_lock(f, exclusive=False)
            try:
                content = f.read()
                return json.loads(content) if content.strip() else dict(_DEFAULT_SESSION)
            finally:
                self._release_lock(f)

    def _locked_write(self, data: dict) -> None:
        self._ensure_file_exists()
        payload = json.dumps(data, indent=2)
        with open(self.path, "r+", encoding="utf-8") as f:
            self._acquire_lock(f, exclusive=True)
            try:
                f.seek(0)
                f.truncate()
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            finally:
                self._release_lock(f)

    def _ensure_file_exists(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            with open(self.path, "w", encoding="utf-8") as f:
                f.write("{}")

    @staticmethod
    def _acquire_lock(file_obj, exclusive: bool, retries: int = 20, delay: float = 0.05) -> None:
        lock_mode = msvcrt.LK_NBLCK if exclusive else msvcrt.LK_NBRLCK
        for attempt in range(retries):
            try:
                file_obj.seek(0)
                msvcrt.locking(file_obj.fileno(), lock_mode, 0x7FFFFFFF)
                return
            except OSError:
                if attempt == retries - 1:
                    raise
                time.sleep(delay)

    @staticmethod
    def _release_lock(file_obj) -> None:
        file_obj.seek(0)
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 0x7FFFFFFF)
