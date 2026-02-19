"""
TradingGuard - Manual Trading Checklist Widget
User-controlled checklist for discretionary strategy confirmation.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QCheckBox, QPushButton

from app.config import MANUAL_CHECKLIST_ITEMS


class ManualChecklistWidget(QWidget):
    """A user-managed checklist persisted to session.json."""

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self._bridge = bridge
        self._checkboxes: list[tuple[str, QCheckBox]] = []
        self._build_ui()
        self._load_saved_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("My Trading Checklist")
        title.setObjectName("heading")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        group = QGroupBox("Manual Confirmations")
        group_layout = QVBoxLayout(group)

        for item in MANUAL_CHECKLIST_ITEMS:
            cb = QCheckBox(item)
            cb.stateChanged.connect(self._on_check_changed)
            self._checkboxes.append((item, cb))
            group_layout.addWidget(cb)

        layout.addWidget(group)

        self._summary = QLabel("")
        self._summary.setObjectName("subheading")
        self._summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._summary)

        btn_reset = QPushButton("Reset Checklist")
        btn_reset.clicked.connect(self._reset_all)
        layout.addWidget(btn_reset, alignment=Qt.AlignmentFlag.AlignCenter)

        self._update_summary()

    def _load_saved_state(self) -> None:
        try:
            data = self._bridge.read()
            saved = data.get("manual_checklist", {}) or {}
            for item, cb in self._checkboxes:
                cb.blockSignals(True)
                cb.setChecked(bool(saved.get(item, False)))
                cb.blockSignals(False)
            self._update_summary()
        except Exception:
            # Keep defaults (all unchecked) if bridge read fails.
            pass

    def _on_check_changed(self) -> None:
        self._save_state()
        self._update_summary()

    def _save_state(self) -> None:
        mapping = {item: cb.isChecked() for item, cb in self._checkboxes}
        self._bridge.update(manual_checklist=mapping)

    def _reset_all(self) -> None:
        for _, cb in self._checkboxes:
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._save_state()
        self._update_summary()

    def _update_summary(self) -> None:
        total = len(self._checkboxes)
        done = sum(1 for _, cb in self._checkboxes if cb.isChecked())
        self._summary.setText(f"Checklist: {done}/{total} completed")
