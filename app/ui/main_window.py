"""TradingGuard main window orchestration class."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMainWindow

from app.bridge import SessionBridge
from app.config import SESSION_POLL_INTERVAL_MS, get_session_day_str
from app.database import DailyDatabase
from app.ui.main_window_history import MainWindowHistoryMixin
from app.ui.main_window_session import MainWindowSessionMixin
from app.ui.main_window_ui import MainWindowUIMixin


class MainWindow(
    QMainWindow,
    MainWindowUIMixin,
    MainWindowSessionMixin,
    MainWindowHistoryMixin,
):
    """Top-level application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TradingGuard")
        self.setMinimumSize(700, 600)

        self._bridge = SessionBridge()
        self._db = DailyDatabase()
        self._session_started = False
        self._shutdown_done = False
        self._break_until = None  # 1-hour break after consecutive losses
        self._prev_trades_today = None
        self._prev_net_pnl = None
        self._prev_shutdown_signal = False
        self._prev_break_active = False
        self._prev_bias_expired = False
        self._prev_news_lock = False
        self._last_watchdog_challenge_at = None
        self._tamper_alerted = False
        self._violation_dedupe: set[str] = set()
        self._session_day_key = get_session_day_str()
        self._active_session_since = None
        self._last_seen_ea_heartbeat: str = ""
        self._last_seen_ea_heartbeat_at = None

        self._build_ui()
        self._check_recovery_day()

        # Polling timer — reads session.json periodically
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(SESSION_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_session)
        self._poll_timer.start()

        # MT5 guard timer — ensures terminal cannot be reopened after shutdown
        # or on a mandatory recovery day.
        self._mt5_guard_timer = QTimer(self)
        self._mt5_guard_timer.setInterval(5000)  # 5 seconds
        self._mt5_guard_timer.timeout.connect(self._guard_mt5_after_shutdown)
        self._mt5_guard_timer.start()
