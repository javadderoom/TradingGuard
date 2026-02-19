"""
TradingGuard — Main Window
Central QMainWindow with three tabs: Analysis, Session, History.
Polls session.json on a timer and orchestrates session lifecycle.
"""

import os
import logging
from datetime import date, datetime, timedelta

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QStatusBar,
)

from app.bridge import SessionBridge
from app.database import DailyDatabase
from app import mt5_controller
from app.config import SESSION_POLL_INTERVAL_MS
from app.ui.timer_widget import TimerWidget
from app.ui.bias_widget import BiasWidget
from app.ui.news_lock_widget import NewsLockWidget
from app.ui.session_widget import SessionWidget

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
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

    # ══════════════════════════════════════════════════════════════════════
    #  UI Construction
    # ══════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        # ── Tab 1: Analysis ───────────────────────────────────────────────
        analysis_tab = QWidget()
        analysis_layout = QVBoxLayout(analysis_tab)

        self._timer_widget = TimerWidget()
        analysis_layout.addWidget(self._timer_widget)

        self._bias_widget = BiasWidget(self._bridge)
        analysis_layout.addWidget(self._bias_widget)

        self._btn_start_session = QPushButton("▶  Start Trading Session")
        self._btn_start_session.setObjectName("btn_start")
        self._btn_start_session.clicked.connect(self._start_session)
        analysis_layout.addWidget(
            self._btn_start_session, alignment=Qt.AlignmentFlag.AlignCenter
        )

        self._tabs.addTab(analysis_tab, "📊  Analysis")

        # ── Tab 2: Session ────────────────────────────────────────────────
        from PyQt6.QtWidgets import QScrollArea
        session_tab = QWidget()
        session_scroll = QScrollArea()
        session_scroll.setWidgetResizable(True)
        session_scroll.setWidget(session_tab)
        
        session_layout = QVBoxLayout(session_tab)

        self._session_widget = SessionWidget()
        session_layout.addWidget(self._session_widget)

        self._news_lock_widget = NewsLockWidget(self._bridge)
        session_layout.addWidget(self._news_lock_widget)

        self._btn_end_session = QPushButton("⏹  End Session")
        self._btn_end_session.setObjectName("btn_stop")
        self._btn_end_session.clicked.connect(self._end_session)
        session_layout.addWidget(
            self._btn_end_session, alignment=Qt.AlignmentFlag.AlignCenter
        )

        self._tabs.addTab(session_scroll, "⚡  Session")

        # ── Tab 3: History ────────────────────────────────────────────────
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)

        history_title = QLabel("Daily Results")
        history_title.setObjectName("heading")
        history_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        history_layout.addWidget(history_title)

        self._history_table = QTableWidget()
        self._history_table.setColumnCount(4)
        self._history_table.setHorizontalHeaderLabels(
            ["Date", "P&L ($)", "Trades", "Result"]
        )
        self._history_table.horizontalHeader().setStretchLastSection(True)
        self._history_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        history_layout.addWidget(self._history_table)

        btn_refresh = QPushButton("🔄  Refresh History")
        btn_refresh.clicked.connect(self._load_history)
        history_layout.addWidget(
            btn_refresh, alignment=Qt.AlignmentFlag.AlignCenter
        )

        # Development helper: allow resetting today's lock so we can test flows
        # multiple times in a single day.
        self._btn_dev_reset = QPushButton("DEV: Reset Today's Lock")
        self._btn_dev_reset.clicked.connect(self._dev_reset_today)
        history_layout.addWidget(
            self._btn_dev_reset, alignment=Qt.AlignmentFlag.AlignCenter
        )

        self._tabs.addTab(history_tab, "📅  History")

        # ── Status bar ────────────────────────────────────────────────────
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

        self._load_history()

    # ══════════════════════════════════════════════════════════════════════
    #  Session Lifecycle
    # ══════════════════════════════════════════════════════════════════════

    def _check_recovery_day(self):
        """Evaluate whether trading is allowed today.

        - If the last 2 completed days were red → mandatory recovery day.
        - If there is already a record for today → today's session is finished.
        """
        # Mandatory recovery day after 2 consecutive red days
        if self._db.is_recovery_day():
            self._btn_start_session.setEnabled(False)
            self._timer_widget.setEnabled(False)
            self._shutdown_done = True  # treat as permanently shut down for today
            self._status_bar.showMessage(
                "🛑  RECOVERY DAY — 2 consecutive red days. Trading is blocked."
            )
            QMessageBox.warning(
                self,
                "Recovery Day",
                "You had 2 consecutive losing days.\n"
                "Today is a mandatory recovery day — no trading allowed.",
            )
            # Ensure MT5 is not running on a recovery day.
            mt5_controller.kill_mt5()
            return

        # If we already have a row for today, that means today's session was
        # completed earlier (either manually or via EA shutdown). Do not allow
        # a new session to start after reopening the app.
        today_row = self._db.get_today()
        if today_row is not None:
            self._btn_start_session.setEnabled(False)
            self._timer_widget.setEnabled(False)
            self._shutdown_done = True
            result = today_row.get("result", "completed").upper()
            self._status_bar.showMessage(
                f"🛑  SESSION COMPLETED TODAY ({result}) — no further trading allowed."
            )

    def _start_session(self):
        """Called when 'Start Trading Session' is clicked."""
        from app.config import is_within_trading_hours, get_tehran_time_str, TRADING_START_HOUR, TRADING_END_HOUR
        
        if not self._timer_widget.is_complete():
            QMessageBox.information(
                self,
                "Analysis Required",
                "Complete the 20-minute analysis timer first.",
            )
            return

        if self._shutdown_done:
            QMessageBox.warning(
                self,
                "Session Ended",
                "Today's session has already been shut down.\n"
                "You cannot restart until tomorrow.",
            )
            return

        # Check trading hours (Tehran time)
        if not is_within_trading_hours():
            tehran_time = get_tehran_time_str()
            QMessageBox.warning(
                self,
                "Outside Trading Hours",
                f"Trading is only allowed between {TRADING_START_HOUR}:00 and {TRADING_END_HOUR}:00 Tehran time.\n"
                f"Current Tehran time: {tehran_time}",
            )
            return

        # Write initial session state
        self._bridge.update(
            session_active=True,
            trading_allowed=True,
            shutdown_signal=False,
            daily_loss_usd=0.0,
            daily_profit_usd=0.0,
            trades_today=0,
            consecutive_losses=0,
            cooldown_until="",
            last_trade_result="",
        )

        # Launch MT5
        if mt5_controller.launch_mt5():
            self._session_started = True
            self._status_bar.showMessage("Session active — MT5 launched")
            self._tabs.setCurrentIndex(1)  # Switch to Session tab
        else:
            QMessageBox.critical(
                self,
                "MT5 Error",
                "Could not launch MetaTrader 5.\n"
                "Check that the path in config.py is correct.",
            )

    def _end_session(self):
        """Manually end the session, kill MT5, record daily result."""
        reply = QMessageBox.question(
            self,
            "End Session",
            "Are you sure you want to end today's trading session?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._shutdown_session()

    def _shutdown_session(self):
        """Shared shutdown logic (manual or triggered by EA limits)."""
        self._bridge.update(
            session_active=False,
            trading_allowed=False,
            shutdown_signal=True,
        )
        mt5_controller.kill_mt5()
        self._session_started = False
        self._shutdown_done = True

        # Record daily result
        data = self._bridge.read()
        pnl = data.get("daily_profit_usd", 0) - data.get("daily_loss_usd", 0)
        trades = data.get("trades_today", 0)
        self._db.record_day(pnl=pnl, trades=trades)

        self._load_history()
        self._status_bar.showMessage("Session ended — MT5 closed")

    def _handle_consecutive_losses_shutdown(self, data: dict):
        """Handle shutdown triggered by consecutive losses - 1 hour break."""
        mt5_controller.kill_mt5()
        self._session_started = False

        # Start 1-hour break (don't record day - user can resume after break)
        self._break_until = datetime.now() + timedelta(hours=1)
        self._bridge.update(
            session_active=False,
            trading_allowed=False,
            shutdown_signal=False,  # Clear shutdown so new session is possible
            break_until=self._break_until.isoformat(),
        )

        self._status_bar.showMessage(
            "🛑  2 consecutive losses — 1-hour break started"
        )

    def _dev_reset_today(self):
        """Development-only helper to clear today's lock and session state.

        This makes it possible to run multiple test sessions in one day while
        keeping production behavior strict by default.
        """
        reply = QMessageBox.question(
            self,
            "DEV: Reset Today's Lock",
            "This will clear today's result and re-enable trading for testing.\n"
            "Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Clear today's DB row and reset in-memory flags
        self._db.clear_today()
        self._shutdown_done = False
        self._btn_start_session.setEnabled(True)
        self._timer_widget.setEnabled(True)
        self._timer_widget.reset()
        
        # Also reset session.json to clear any stale break state
        self._bridge.reset()
        
        self._status_bar.showMessage(
            "DEV: Today's lock reset — you may start a test session."
        )

    def _guard_mt5_after_shutdown(self):
        """Continuously enforce 'no reopening after shutdown', recovery days, 
        and 1-hour break after consecutive losses."""
        
        break_active = False
        break_reason = ""
        break_until_str = ""
        try:
            data = self._bridge.read()
            break_until_str = data.get("break_until") or ""
            break_active = data.get("break_active", False)
            if break_until_str:
                try:
                    break_until = datetime.fromisoformat(break_until_str)
                    if datetime.now() < break_until:
                        break_reason = "1-hour break"
                    else:
                        break_active = False
                except ValueError:
                    break_reason = ""
                    break_active = False
        except Exception as exc:
            log.warning("Error reading session in guard_mt5: %s", exc)

        recovery_day = self._db.is_recovery_day()
        
        # Check daily break time
        from app.config import is_daily_break_time, get_tehran_time_str
        daily_break, break_reason = is_daily_break_time()
        
        # Add daily break to the check
        if daily_break and not break_active:
            break_active = True
            break_reason = break_reason or "daily break"
        
        log.debug(
            "MT5 guard check: _shutdown_done=%s, recovery_day=%s, break_active=%s, break_reason='%s'",
            self._shutdown_done, recovery_day, break_active, break_reason
        )

        if not self._shutdown_done and not recovery_day and not break_active:
            return

        if mt5_controller.is_mt5_running():
            mt5_controller.kill_mt5()
            if break_reason:
                reason = break_reason
            elif recovery_day:
                reason = "recovery day"
            elif self._shutdown_done:
                reason = "session shutdown"
            else:
                reason = "unknown"
            log.info("MT5 blocked: %s", reason)
            self._status_bar.showMessage(
                f"🛑  MT5 is blocked — {reason}"
            )

    # ══════════════════════════════════════════════════════════════════════
    #  Polling
    # ══════════════════════════════════════════════════════════════════════

    def _poll_session(self):
        """Read session.json and update the Session widget.
        Also auto-shutdown if the EA signals it."""
        try:
            data = self._bridge.read()
        except Exception as exc:
            log.warning("Failed to read session.json: %s", exc)
            return

        self._session_widget.refresh(data)

        # Enforce long break after consecutive losses (EA sets break_active).
        self._enforce_break(data)

        # Enforce bias expiry (Phase 3): after 2 hours or 3 losses since bias
        # was set, disable trading until the user updates their bias again.
        self._enforce_bias_expiry(data)

        # Auto-shutdown if EA sets shutdown_signal
        if (
            data.get("shutdown_signal")
            and self._session_started
            and not self._shutdown_done
        ):
            # Check if this is a consecutive losses shutdown (has break_active)
            if data.get("break_active"):
                # Consecutive losses: record result and start 1-hour break
                self._handle_consecutive_losses_shutdown(data)
            else:
                # Full daily shutdown (limits reached)
                self._shutdown_session()
                self._status_bar.showMessage(
                    "🛑  AUTO-SHUTDOWN — daily limit reached"
                )

    def _enforce_break(self, data: dict) -> None:
        """Keep MT5 closed for one hour after N consecutive losses.

        EA sets break_active=True and trading_allowed=False. Here we:
        - On first detection, set break_until = now + 1 hour.
        - While now < break_until, keep killing MT5.
        - When the hour has passed, clear break_active/break_until and
          re-enable trading (unless other shutdown rules apply).
        """
        if not data.get("break_active"):
            return

        if data.get("shutdown_signal"):
            # Full daily shutdown takes precedence.
            return

        # Initialise break_until if missing
        break_until_str = data.get("break_until") or ""
        now = datetime.now()

        if not break_until_str:
            until = now + timedelta(hours=1)
            self._bridge.update(break_until=until.isoformat())
            self._status_bar.showMessage(
                "🛑  1-hour break started after consecutive losses."
            )
            mt5_controller.kill_mt5()
            return

        try:
            break_until = datetime.fromisoformat(break_until_str)
        except ValueError:
            # If parsing fails, reset the break to be safe.
            until = now + timedelta(hours=1)
            self._bridge.update(break_until=until.isoformat())
            return

        if now < break_until:
            # Still in break window — keep MT5 closed.
            mt5_controller.kill_mt5()
            return

        # Break period finished — clear flags and re-enable trading.
        self._bridge.update(
            break_active=False,
            break_until="",
            trading_allowed=True,
        )
        self._status_bar.showMessage(
            "✅  1-hour break finished — trading re-enabled for this session."
        )

    def _enforce_bias_expiry(self, data: dict) -> None:
        """Disable trading when bias has expired by time or losses.

        Rules:
        - Bias expires after 2 hours OR 3 losses since it was set.
        - After expiry, trading_allowed is set False and bias_expired True.
        - Updating the bias (via BiasWidget) clears bias_expired and
          re-enables trading for the current session.
        """
        if not data.get("session_active"):
            return
        if data.get("shutdown_signal"):
            # Full daily shutdown already in effect; do not interfere.
            return

        bias_set_at = data.get("bias_set_at") or ""
        if not bias_set_at:
            return

        try:
            bias_time = datetime.fromisoformat(bias_set_at)
        except ValueError:
            return

        now = datetime.now()
        age = now - bias_time
        losses_since_bias = int(data.get("losses_since_bias", 0) or 0)
        expired = bool(data.get("bias_expired"))

        if expired:
            return

        if age >= timedelta(hours=2) or losses_since_bias >= 3:
            self._bridge.update(trading_allowed=False, bias_expired=True)
            self._status_bar.showMessage(
                "🛑  Bias expired — trading disabled until bias is updated."
            )
            QMessageBox.information(
                self,
                "Bias Expired",
                "Your bias has expired (time limit or 3 losses).\n"
                "Update your bias to resume trading.",
            )

    # ══════════════════════════════════════════════════════════════════════
    #  History
    # ══════════════════════════════════════════════════════════════════════

    def _load_history(self):
        rows = self._db.get_last_n_days(30)
        self._history_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self._history_table.setItem(i, 0, QTableWidgetItem(row["date"]))
            pnl_item = QTableWidgetItem(f"${row['pnl']:+.2f}")
            self._history_table.setItem(i, 1, pnl_item)
            self._history_table.setItem(
                i, 2, QTableWidgetItem(str(row["trades"]))
            )
            result_item = QTableWidgetItem(row["result"].upper())
            self._history_table.setItem(i, 3, result_item)
