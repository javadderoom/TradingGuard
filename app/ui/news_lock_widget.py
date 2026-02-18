"""
TradingGuard — Manual News Lock Widget
Toggle to block trading during high-impact news events.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton


class NewsLockWidget(QWidget):
    """A toggle button that writes news_lock to session.json."""

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self._bridge = bridge
        self._locked = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        title = QLabel("News Lock")
        title.setObjectName("heading")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel(
            "Activate this during high-impact USD news events\n"
            "to block all new trades."
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

    def _toggle(self):
        self._locked = not self._locked
        if self._locked:
            self._btn.setText("🔒  News Lock ON")
            self._btn.setProperty("locked", "true")
        else:
            self._btn.setText("🔓  News Lock OFF")
            self._btn.setProperty("locked", "false")
        # Force style re-evaluation
        self._btn.style().unpolish(self._btn)
        self._btn.style().polish(self._btn)
        self._bridge.update(news_lock=self._locked)

    def is_locked(self) -> bool:
        return self._locked
