"""
TradingGuard — Live Session Status Widget
Continuously reads session.json and displays real-time session metrics.
"""

from datetime import datetime
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox,
    QGridLayout, QProgressBar,
)
from app.config import (
    MAX_DAILY_LOSS_USD, MAX_DAILY_PROFIT_USD,
    MAX_TRADES_PER_DAY, MAX_CONSECUTIVE_LOSSES,
)


class SessionWidget(QWidget):
    """Read-only dashboard showing live session data from session.json."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Live Session")
        title.setObjectName("heading")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Status grid
        group = QGroupBox("Session Metrics")
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)

        self._labels: dict[str, QLabel] = {}
        fields = [
            ("Session Active", "session_active"),
            ("Trading Allowed", "trading_allowed"),
            ("Bias", "bias"),
            ("News Lock", "news_lock"),
            ("Trades Today", "trades_today"),
            ("Daily P&L ($)", "daily_pnl"),
            ("Consec. Losses", "consecutive_losses"),
            ("Cooldown", "cooldown_until"),
            ("Last Result", "last_trade_result"),
            ("Shutdown Signal", "shutdown_signal"),
        ]

        for row, (label_text, key) in enumerate(fields):
            lbl = QLabel(label_text + ":")
            lbl.setObjectName("subheading")
            grid.addWidget(lbl, row, 0)

            val = QLabel("—")
            val.setObjectName("status_value")
            self._labels[key] = val
            grid.addWidget(val, row, 1)

        layout.addWidget(group)

        # Limits progress section
        limits_group = QGroupBox("Daily Limits")
        limits_layout = QVBoxLayout(limits_group)

        self._loss_bar = QProgressBar()
        self._loss_bar.setRange(0, int(MAX_DAILY_LOSS_USD * 100))
        self._loss_bar.setFormat("Loss: $%v / $" + f"{MAX_DAILY_LOSS_USD:.0f}")
        limits_layout.addWidget(QLabel("Daily Loss"))
        limits_layout.addWidget(self._loss_bar)

        self._profit_bar = QProgressBar()
        self._profit_bar.setRange(0, int(MAX_DAILY_PROFIT_USD * 100))
        self._profit_bar.setFormat("Profit: $%v / $" + f"{MAX_DAILY_PROFIT_USD:.0f}")
        limits_layout.addWidget(QLabel("Daily Profit"))
        limits_layout.addWidget(self._profit_bar)

        layout.addWidget(limits_group)

    # ── Called externally by MainWindow polling timer ───────────────────────

    def refresh(self, data: dict):
        """Update all fields from a session.json dict."""
        pnl = data.get("daily_profit_usd", 0) - data.get("daily_loss_usd", 0)

        mapping = {
            "session_active": "✅ Active" if data.get("session_active") else "⏸ Inactive",
            "trading_allowed": "✅ Yes" if data.get("trading_allowed") else "🚫 No",
            "bias": (data.get("bias", "neutral") or "neutral").capitalize(),
            "news_lock": "🔒 Locked" if data.get("news_lock") else "🔓 Open",
            "trades_today": f"{data.get('trades_today', 0)} / {MAX_TRADES_PER_DAY}",
            "daily_pnl": f"${pnl:+.2f}",
            "consecutive_losses": f"{data.get('consecutive_losses', 0)} / {MAX_CONSECUTIVE_LOSSES}",
            "cooldown_until": data.get("cooldown_until") or "None",
            "last_trade_result": data.get("last_trade_result") or "—",
            "shutdown_signal": "🛑 YES" if data.get("shutdown_signal") else "No",
        }

        for key, text in mapping.items():
            lbl = self._labels.get(key)
            if lbl:
                lbl.setText(text)
                # Color coding
                if key == "daily_pnl":
                    if pnl > 0:
                        lbl.setObjectName("status_value_green")
                    elif pnl < 0:
                        lbl.setObjectName("status_value_red")
                    else:
                        lbl.setObjectName("status_value_neutral")
                    lbl.style().unpolish(lbl)
                    lbl.style().polish(lbl)

        # Update progress bars
        loss = abs(data.get("daily_loss_usd", 0))
        profit = data.get("daily_profit_usd", 0)
        self._loss_bar.setValue(int(loss * 100))
        self._loss_bar.setFormat(f"Loss: ${loss:.2f} / ${MAX_DAILY_LOSS_USD:.0f}")
        self._profit_bar.setValue(int(profit * 100))
        self._profit_bar.setFormat(f"Profit: ${profit:.2f} / ${MAX_DAILY_PROFIT_USD:.0f}")
