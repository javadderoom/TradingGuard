"""
TradingGuard — Main Window
Central QMainWindow with three tabs: Analysis, Session, History.
Polls session.json on a timer and orchestrates session lifecycle.
"""

import os
import logging
from datetime import date

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

        self._build_ui()
        self._check_recovery_day()

        # Polling timer — reads session.json periodically
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(SESSION_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_session)
        self._poll_timer.start()

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
        session_tab = QWidget()
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

        self._tabs.addTab(session_tab, "⚡  Session")

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
        """Block trading entirely if last 2 days were red."""
        if self._db.is_recovery_day():
            self._btn_start_session.setEnabled(False)
            self._status_bar.showMessage(
                "🛑  RECOVERY DAY — 2 consecutive red days. Trading is blocked."
            )
            QMessageBox.warning(
                self,
                "Recovery Day",
                "You had 2 consecutive losing days.\n"
                "Today is a mandatory recovery day — no trading allowed.",
            )

    def _start_session(self):
        """Called when 'Start Trading Session' is clicked."""
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

        # Auto-shutdown if EA sets shutdown_signal
        if (
            data.get("shutdown_signal")
            and self._session_started
            and not self._shutdown_done
        ):
            self._shutdown_session()
            self._status_bar.showMessage(
                "🛑  AUTO-SHUTDOWN — daily limit reached"
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
