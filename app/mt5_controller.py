"""
TradingGuard — MT5 Process Controller
Launch, kill, and monitor the MetaTrader 5 terminal process on Windows.
"""

import subprocess
import logging

from app.config import MT5_EXE_PATH

log = logging.getLogger(__name__)

_MT5_PROCESS_NAME = "terminal64.exe"


def is_mt5_running() -> bool:
    """Return True if terminal64.exe is in the Windows task list."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {_MT5_PROCESS_NAME}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return _MT5_PROCESS_NAME.lower() in result.stdout.lower()
    except Exception as exc:
        log.warning("tasklist check failed: %s", exc)
        return False


def launch_mt5(exe_path: str = MT5_EXE_PATH) -> bool:
    """Start MT5 if it is not already running.  Returns True on success."""
    if is_mt5_running():
        log.info("MT5 is already running.")
        return True
    try:
        subprocess.Popen(
            [exe_path],
            creationflags=subprocess.DETACHED_PROCESS,
        )
        log.info("MT5 launched: %s", exe_path)
        return True
    except FileNotFoundError:
        log.error("MT5 executable not found at %s", exe_path)
        return False
    except Exception as exc:
        log.error("Failed to launch MT5: %s", exc)
        return False


def kill_mt5() -> bool:
    """Force-kill the MT5 terminal.  Returns True on success."""
    if not is_mt5_running():
        log.info("MT5 is not running; nothing to kill.")
        return True
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", _MT5_PROCESS_NAME],
            capture_output=True,
            text=True,
            timeout=10,
        )
        ok = result.returncode == 0
        if ok:
            log.info("MT5 terminated.")
        else:
            log.warning("taskkill output: %s", result.stderr.strip())
        return ok
    except Exception as exc:
        log.error("Failed to kill MT5: %s", exc)
        return False
