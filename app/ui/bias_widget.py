"""
TradingGuard — HTF Bias Input Widget
Lets the trader declare their higher-timeframe directional bias and
invalidation price before trading, written to session.json.

Phase 3 additions:
- Tracks when the bias was last set (bias_set_at)
- Resets losses_since_bias on each new bias
- Allows enabling strict_mode (block opposite-direction trades)
"""

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox,
    QDoubleSpinBox, QGroupBox, QFormLayout, QCheckBox,
)
from app.config import BIAS_CHOICES


class BiasWidget(QWidget):
    """Form for selecting bias direction, strict mode, and invalidation price."""

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

        # Strict mode toggle
        self._strict_checkbox = QCheckBox("Strict mode (block opposite trades)")
        self._strict_checkbox.stateChanged.connect(self._on_change)
        form.addRow("Strict Mode:", self._strict_checkbox)

        layout.addWidget(group)

        self._info = QLabel(
            "Set your bias and invalidation before starting the session.\n"
            "Strict mode will automatically close trades against your bias."
        )
        self._info.setObjectName("subheading")
        self._info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._info)

    # ── Sync to bridge ────────────────────────────────────────────────────

    def _on_change(self):
        """Persist bias-related fields to session.json.

        - bias / invalidation_price reflect the current form.
        - bias_set_at is updated to 'now' whenever anything changes.
        - losses_since_bias is reset (new analysis).
        - bias_expired is cleared.
        - strict_mode reflects the checkbox state.
        - trading_allowed is set True so that after bias expiry, a new analysis
          re-enables trading (EA still honours full shutdown flags).
        """
        now = datetime.now().isoformat()
        self._bridge.update(
            bias=self._combo.currentText().lower(),
            invalidation_price=self._price_spin.value(),
            bias_set_at=now,
            losses_since_bias=0,
            bias_expired=False,
            strict_mode=self._strict_checkbox.isChecked(),
        )

    def get_bias(self) -> str:
        return self._combo.currentText().lower()

    def get_invalidation_price(self) -> float:
        return self._price_spin.value()
