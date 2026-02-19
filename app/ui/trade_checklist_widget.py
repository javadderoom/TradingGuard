"""
TradingGuard - Per-Trade Checklist Widget
Displays a live GO/NO-GO checklist before taking any new trade.
"""

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QGridLayout

from app.config import is_within_trading_hours, is_daily_break_time


class TradeChecklistWidget(QWidget):
    """Live checklist of conditions required before taking a trade."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[tuple[str, QLabel]] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Pre-Trade Checklist")
        title.setObjectName("heading")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._summary = QLabel("Checking...")
        self._summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary.setObjectName("status_value_neutral")
        layout.addWidget(self._summary)

        group = QGroupBox("Entry Gate")
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(8)

        checks = [
            "Session active",
            "Trading allowed",
            "No news lock",
            "Within trading hours",
            "Not daily break",
            "No cooldown",
            "No break lock",
            "No shutdown signal",
            "Bias set (not neutral)",
        ]

        for row, text in enumerate(checks):
            name = QLabel(text + ":")
            name.setObjectName("subheading")
            status = QLabel("-")
            status.setObjectName("status_value")
            self._rows.append((text, status))
            grid.addWidget(name, row, 0)
            grid.addWidget(status, row, 1)

        layout.addWidget(group)

    def refresh(self, data: dict) -> None:
        checks = {
            "Session active": bool(data.get("session_active")),
            "Trading allowed": bool(data.get("trading_allowed")),
            "No news lock": not bool(data.get("news_lock")),
            "Within trading hours": is_within_trading_hours(),
            "Not daily break": not is_daily_break_time()[0],
            "No cooldown": not self._is_cooldown_active(data),
            "No break lock": not bool(data.get("break_active")),
            "No shutdown signal": not bool(data.get("shutdown_signal")),
            "Bias set (not neutral)": (data.get("bias") or "neutral").lower() != "neutral",
        }

        ready = True
        for name, label in self._rows:
            ok = checks.get(name, False)
            ready = ready and ok
            label.setText("PASS" if ok else "BLOCK")
            label.setObjectName("status_value_green" if ok else "status_value_red")
            style = label.style()
            if style:
                style.unpolish(label)
                style.polish(label)

        self._summary.setText("READY TO TRADE" if ready else "DO NOT ENTER")
        self._summary.setObjectName("status_value_green" if ready else "status_value_red")
        style = self._summary.style()
        if style:
            style.unpolish(self._summary)
            style.polish(self._summary)

    @staticmethod
    def _is_cooldown_active(data: dict) -> bool:
        value = data.get("cooldown_until")
        if value in (None, "", "0"):
            return False

        text = str(value).strip()
        if text.isdigit():
            return int(text) > 0

        try:
            return datetime.fromisoformat(text) > datetime.now()
        except ValueError:
            return False
