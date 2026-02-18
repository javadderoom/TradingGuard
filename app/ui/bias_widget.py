"""
TradingGuard — HTF Bias Input Widget
Lets the trader declare their higher-timeframe directional bias and
invalidation price before trading, written to session.json.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox,
    QDoubleSpinBox, QGroupBox, QFormLayout,
)
from app.config import BIAS_CHOICES


class BiasWidget(QWidget):
    """Form for selecting bias direction and invalidation price."""

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self._bridge = bridge
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        group = QGroupBox("HTF Bias Setup")
        form = QFormLayout(group)

        # Bias direction
        self._combo = QComboBox()
        self._combo.addItems(BIAS_CHOICES)
        self._combo.currentTextChanged.connect(self._on_change)
        form.addRow("Direction:", self._combo)

        # Invalidation price
        self._price_spin = QDoubleSpinBox()
        self._price_spin.setRange(0.0, 999999.0)
        self._price_spin.setDecimals(2)
        self._price_spin.setSingleStep(1.0)
        self._price_spin.setSpecialValueText("Not set")
        self._price_spin.valueChanged.connect(self._on_change)
        form.addRow("Invalidation Price:", self._price_spin)

        layout.addWidget(group)

        self._info = QLabel("Set your bias before starting the session.")
        self._info.setObjectName("subheading")
        self._info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._info)

    # ── Sync to bridge ────────────────────────────────────────────────────

    def _on_change(self):
        self._bridge.update(
            bias=self._combo.currentText().lower(),
            invalidation_price=self._price_spin.value(),
        )

    def get_bias(self) -> str:
        return self._combo.currentText().lower()

    def get_invalidation_price(self) -> float:
        return self._price_spin.value()
