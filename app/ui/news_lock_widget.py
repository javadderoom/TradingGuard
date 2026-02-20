"""
TradingGuard — Manual News Lock Widget
Toggle to block trading during high-impact news events.
Displays upcoming high-impact USD news and auto-locks during events.
"""

import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
)

from app import news_service

log = logging.getLogger(__name__)


class NewsLockWidget(QWidget):
    """A widget that shows upcoming high-impact news and allows locking."""

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self._bridge = bridge
        self._locked = False
        self._auto_lock_enabled = True
        self._events = []
        self._build_ui()
        self._fetch_news()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5 * 60 * 1000)
        self._refresh_timer.timeout.connect(self._fetch_news)
        self._refresh_timer.start()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        title = QLabel("News Lock")
        title.setObjectName("heading")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel(
            "Auto-blocks trades during high-impact USD news\n"
            "or manual toggle to block all trades."
        )
        desc.setObjectName("subheading")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        self._btn = QPushButton("🔓  News Lock OFF")
        self._btn.setObjectName("btn_news_lock")
        self._btn.setProperty("locked", "false")
        self._btn.setCheckable(True)
        self._btn.clicked.connect(self._toggle)
        layout.addWidget(self._btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._auto_checkbox = QPushButton("☑  Auto-lock during news")
        self._auto_checkbox.setCheckable(True)
        self._auto_checkbox.setChecked(self._auto_lock_enabled)
        self._auto_checkbox.clicked.connect(self._toggle_auto_lock)
        layout.addWidget(self._auto_checkbox, alignment=Qt.AlignmentFlag.AlignCenter)

        refresh_btn = QPushButton("🔄  Refresh News")
        refresh_btn.clicked.connect(self._fetch_news)
        layout.addWidget(refresh_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        upcoming_label = QLabel("Upcoming High-Impact USD News:")
        upcoming_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(upcoming_label)

        self._news_list = QListWidget()
        self._news_list.setMaximumHeight(100)
        layout.addWidget(self._news_list)

    def _toggle(self):
        self._locked = not self._locked
        self._update_button()
        self._bridge.update(news_lock=self._locked)

    def _toggle_auto_lock(self):
        self._auto_lock_enabled = not self._auto_lock_enabled
        if self._auto_lock_enabled:
            self._auto_checkbox.setText("☑  Auto-lock during news")
        else:
            self._auto_checkbox.setText("☐  Auto-lock during news")
        self._check_auto_lock()

    def _update_button(self):
        if self._locked:
            self._btn.setText("🔒  News Lock ON")
            self._btn.setProperty("locked", "true")
        else:
            self._btn.setText("🔓  News Lock OFF")
            self._btn.setProperty("locked", "false")
        style = self._btn.style()
        if style:
            style.unpolish(self._btn)
            style.polish(self._btn)
        self._btn.update()

    def _fetch_news(self):
        from app.config import NEWS_API_KEY
        if not NEWS_API_KEY:
            self._news_list.clear()
            self._news_list.addItem("Configure NEWS_API_KEY")
            self._news_list.addItem("in config.py to enable")
            self._status_label.setText("API key required")
            return
        
        self._events = news_service.fetch_high_impact_news(hours_ahead=24)
        self._update_news_list()
        self._check_auto_lock()

    def _update_news_list(self):
        self._news_list.clear()
        if not self._events:
            self._news_list.addItem("No high-impact USD news")
            self._status_label.setText("")
            return

        for event in self._events[:5]:
            time_str = event.time.strftime("%H:%M")
            self._news_list.addItem(f"{time_str} - {event.event[:40]}")

    def _check_auto_lock(self):
        if not self._auto_lock_enabled:
            return

        if news_service.is_news_active(self._events, buffer_minutes=30):
            if not self._locked:
                self._locked = True
                self._update_button()
                self._bridge.update(news_lock=True)
                log.info("Auto-locked trading due to high-impact news")

        next_event = news_service.get_next_high_impact_news(self._events)
        if next_event:
            self._status_label.setText(f"Next: {next_event.time.strftime('%H:%M')} - {next_event.event[:25]}")
        else:
            self._status_label.setText("")

    def is_locked(self) -> bool:
        return self._locked
