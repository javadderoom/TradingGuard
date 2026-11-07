"""
TradingGuard HITL - Configuration Module
"""

import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "analysis_assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Load simple key=value pairs from .env if present
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
# Default local proxy (v2rayN on 10808)
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "http://127.0.0.1:10808")

# Risk & Execution Constraints
MAX_RISK_USD = float(os.getenv("MAX_RISK_USD", "12.0"))
BASE_LOT = float(os.getenv("BASE_LOT", "0.01"))
MAX_DAILY_LOSS_USD = float(os.getenv("MAX_DAILY_LOSS_USD", "34.0"))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "3"))
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "2"))

# Watchdog Parameters
MOMENTUM_ATR_MULTIPLIER = float(os.getenv("MOMENTUM_ATR_MULTIPLIER", "2.0"))
INACTIVITY_REMINDER_MINUTES = int(os.getenv("INACTIVITY_REMINDER_MINUTES", "75"))

# Session & Cooldown Constraints (Tehran Time)
SESSION_START_HOUR = int(os.getenv("SESSION_START_HOUR", "10"))
SESSION_START_MINUTE = int(os.getenv("SESSION_START_MINUTE", "30"))
SESSION_END_HOUR = int(os.getenv("SESSION_END_HOUR", "21"))
SESSION_END_MINUTE = int(os.getenv("SESSION_END_MINUTE", "00"))
COOLDOWN_WIN_MINUTES = int(os.getenv("COOLDOWN_WIN_MINUTES", "15"))
COOLDOWN_LOSS_MINUTES = int(os.getenv("COOLDOWN_LOSS_MINUTES", "25"))

# MT5 Details
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "XAUUSD_o")

# SubQ Snap Decision Engine Configuration
SNAP_API_KEY = os.getenv("SNAP_API_KEY", "")
SNAP_API_URL = os.getenv("SNAP_API_URL", "https://api.subq.ai/v1/systemone")
SNAP_MODEL = os.getenv("SNAP_MODEL", "subq-snap-1.1")
