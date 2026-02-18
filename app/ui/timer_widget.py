"""
TradingGuard — 20-Minute Pre-Session Analysis Timer Widget
Forces the trader to spend at least 20 minutes on analysis before trading.
"""

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
)
from app.config import ANALYSIS_TIMER_MINUTES


class TimerWidget(QWidget):
    """Countdown timer that must reach zero before trading is allowed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._total_seconds = ANALYSIS_TIMER_MINUTES * 60
        self._remaining = self._total_seconds
        self._running = False

        self._build_ui()

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick)

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        title = QLabel("Pre-Session Analysis")
        title.setObjectName("heading")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            f"You must complete {ANALYSIS_TIMER_MINUTES} minutes of analysis\n"
            "before the session can begin."
        )
        subtitle.setObjectName("subheading")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        self._time_label = QLabel(self._format_time(self._remaining))
        self._time_label.setObjectName("timer_display")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._time_label)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._btn_start = QPushButton("Start Analysis Timer")
        self._btn_start.setObjectName("btn_start")
        self._btn_start.clicked.connect(self._start_timer)
        btn_row.addWidget(self._btn_start)

        self._btn_reset = QPushButton("Reset")
        self._btn_reset.clicked.connect(self._reset_timer)
        btn_row.addWidget(self._btn_reset)

        layout.addLayout(btn_row)

        self._status_label = QLabel("Timer not started")
        self._status_label.setObjectName("subheading")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

    # ── Logic ──────────────────────────────────────────────────────────────

    def _start_timer(self):
        if self._running:
            return
        self._running = True
        self._btn_start.setEnabled(False)
        self._status_label.setText("Analyzing... stay focused.")
        self._tick_timer.start()

    def _reset_timer(self):
        self._tick_timer.stop()
        self._running = False
        self._remaining = self._total_seconds
        self._time_label.setText(self._format_time(self._remaining))
        self._btn_start.setEnabled(True)
        self._status_label.setText("Timer reset")

    def _tick(self):
        self._remaining -= 1
        self._time_label.setText(self._format_time(self._remaining))
        if self._remaining <= 0:
            self._tick_timer.stop()
            self._running = False
            self._status_label.setText("✅  Analysis complete — you may start the session.")
            self._time_label.setStyleSheet("color: #00e676;")

    def is_complete(self) -> bool:
        """True when the timer has reached zero."""
        return self._remaining <= 0

    def reset(self) -> None:
        """Public wrapper to reset the timer (used by MainWindow)."""
        self._reset_timer()

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _format_time(seconds: int) -> str:
        m, s = divmod(max(seconds, 0), 60)
        return f"{m:02d}:{s:02d}"
