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

# ─── Bias ──────────────────────────────────────────────────────────────────────
BIAS_CHOICES = ["Bullish", "Bearish", "Neutral"]

# ─── Symbol ────────────────────────────────────────────────────────────────────
DEFAULT_SYMBOL = "XAUUSD"

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
