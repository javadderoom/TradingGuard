"""
TradingGuard — Application Configuration
All constants, limits, and file paths used across the app.
"""

import os

# ─── Risk Limits ───────────────────────────────────────────────────────────────
RISK_PER_TRADE_USD = 12.0       # Max loss per single trade ($)
MAX_DAILY_LOSS_USD = 24.0       # Daily loss shutdown threshold ($)
MAX_DAILY_PROFIT_USD = 35.0     # Daily profit lock threshold ($)
MAX_TRADES_PER_DAY = 3          # Maximum trades allowed per session
MAX_CONSECUTIVE_LOSSES = 2      # Stop trading after N consecutive losses

# ─── Cooldown ──────────────────────────────────────────────────────────────────
COOLDOWN_MINUTES = 15           # Base cooldown after any trade closes
COOLDOWN_LOSS_EXTRA_MINUTES = 10  # Extra cooldown if last trade was a loss

# ─── Pre-Session ───────────────────────────────────────────────────────────────
ANALYSIS_TIMER_MINUTES = 1      # ⚠ TESTING — set back to 20 for live use

# ─── Trading Hours (Tehran Time) ─────────────────────────────────────────────
# Tehran is UTC+3:30
TRADING_START_HOUR = 11        # Start trading at 11:00 Tehran time
TRADING_START_MINUTE = 0
TRADING_END_HOUR = 21         # Stop trading at 21:00 Tehran time
TRADING_END_MINUTE = 0

# ─── Daily Break ───────────────────────────────────────────────────────────
DAILY_BREAK_HOUR = 16          # Daily break at 16:20 Tehran time
DAILY_BREAK_MINUTE = 20
DAILY_BREAK_DURATION_MINUTES = 12  # 12 minute break

# ─── Bias ──────────────────────────────────────────────────────────────────────
BIAS_CHOICES = ["Bullish", "Bearish", "Neutral"]

# ─── Symbol ────────────────────────────────────────────────────────────────────
DEFAULT_SYMBOL = "XAUUSD"

# ─── News API ───────────────────────────────────────────────────────────────
NEWS_API_KEY = "kXrk8XlbuipqCD3VeMI6EJQR4PWAFO46"

# ─── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# MT5 Common Data Folder — This is shared between ALL MT5 instances and accessible by Python
# Path: %APPDATA%\MetaQuotes\Terminal\Common\Files
MT5_COMMON_PATH = os.path.join(os.environ["APPDATA"], "MetaQuotes", "Terminal", "Common", "Files")
SESSION_JSON_PATH = os.path.join(MT5_COMMON_PATH, "session.json")

DB_PATH = os.path.join(PROJECT_ROOT, "tradingguard.db")

# MT5 terminal executable — update if your installation differs
MT5_EXE_PATH = r"C:\Program Files\LiteFinance MT5 Terminal\terminal64.exe"

# MT5 Experts folder (for reference / copy instructions)
MT5_EXPERTS_PATH = (
    r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal"
    r"\A19DFEF1E80BEC73AB07B83E44201DC0\MQL5\Experts\Advisors"
)

# ─── Polling ───────────────────────────────────────────────────────────────────
SESSION_POLL_INTERVAL_MS = 2000  # How often the app re-reads session.json (ms)

# ─── Helper Functions ─────────────────────────────────────────────────────────
from datetime import datetime, timedelta

def is_within_trading_hours() -> bool:
    """Check if current time is within trading hours (Tehran time).
    Tehran is UTC+3:30.
    """
    utc_now = datetime.utcnow()
    tehran_offset = timedelta(hours=3, minutes=30)
    tehran_now = utc_now + tehran_offset
    
    start_minutes = TRADING_START_HOUR * 60 + TRADING_START_MINUTE
    end_minutes = TRADING_END_HOUR * 60 + TRADING_END_MINUTE
    current_minutes = tehran_now.hour * 60 + tehran_now.minute
    
    return start_minutes <= current_minutes < end_minutes


def is_daily_break_time() -> tuple[bool, str]:
    """Check if it's time for the daily 2-minute break.
    Returns (is_break_time, reason).
    """
    utc_now = datetime.utcnow()
    tehran_offset = timedelta(hours=3, minutes=30)
    tehran_now = utc_now + tehran_offset
    
    current_minutes = tehran_now.hour * 60 + tehran_now.minute
    break_start = DAILY_BREAK_HOUR * 60 + DAILY_BREAK_MINUTE
    break_end = break_start + DAILY_BREAK_DURATION_MINUTES
    
    if break_start <= current_minutes < break_end:
        return True, f"Daily break ({DAILY_BREAK_HOUR}:{DAILY_BREAK_MINUTE:02d} Tehran)"
    return False, ""


def get_tehran_time_str() -> str:
    """Get current Tehran time as string."""
    utc_now = datetime.utcnow()
    tehran_offset = timedelta(hours=3, minutes=30)
    tehran_now = utc_now + tehran_offset
    return tehran_now.strftime("%H:%M")
