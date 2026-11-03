"""MainWindow UI construction mixin."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.bias_widget import BiasWidget
from app.ui.news_lock_widget import NewsLockWidget
from app.ui.session_widget import SessionWidget
from app.ui.timer_widget import TimerWidget
from app.ui.trade_analysis_widget import TradeAnalysisWidget


class MainWindowUIMixin:
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
        history_scroll = QScrollArea()
        history_scroll.setWidgetResizable(True)
        history_scroll.setWidget(history_tab)
        history_layout = QVBoxLayout(history_tab)

        history_title = QLabel("History & Performance")
        history_title.setObjectName("heading")
        history_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        history_layout.addWidget(history_title)

        perf_title = QLabel("Performance (30 Days)")
        perf_title.setObjectName("subheading")
        perf_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        history_layout.addWidget(perf_title)

        perf_container = QFrame()
        perf_container.setObjectName("perf_container")
        perf_grid = QGridLayout(perf_container)
        perf_grid.setHorizontalSpacing(12)
        perf_grid.setVerticalSpacing(12)

        self._perf_values: dict[str, QLabel] = {}
        cards = [
            ("total_pnl", "Total P&L"),
            ("win_rate", "Win Rate"),
            ("wins_losses", "W/L"),
            ("total_trades", "Total Trades"),
            ("green_red_days", "Green/Red Days"),
            ("breakeven", "Breakeven"),
        ]
        for i, (key, title) in enumerate(cards):
            card = self._create_perf_card(title)
            value_label = card.findChild(QLabel, "value_label")
            if value_label:
                self._perf_values[key] = value_label
            perf_grid.addWidget(card, i // 3, i % 3)

        history_layout.addWidget(perf_container)

        daily_title = QLabel("Daily Results (Completed Days)")
        daily_title.setObjectName("subheading")
        daily_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        history_layout.addWidget(daily_title)
        self._history_table = QTableWidget()
        self._history_table.setColumnCount(4)
        self._history_table.setHorizontalHeaderLabels(
            ["Date", "P&L ($)", "Trades", "Result"]
        )
        self._history_table.setMinimumHeight(220)
        self._history_table.horizontalHeader().setStretchLastSection(True)
        self._history_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        history_layout.addWidget(self._history_table)

        trade_title = QLabel("Trade Ledger (Most Recent)")
        trade_title.setObjectName("subheading")
        trade_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        history_layout.addWidget(trade_title)
        self._trade_table = QTableWidget()
        self._trade_table.setColumnCount(7)
        self._trade_table.setHorizontalHeaderLabels(
            ["Day", "#", "Result", "P&L", "Close Reason", "Source", "Recorded At"]
        )
        self._trade_table.setMinimumHeight(260)
        self._trade_table.horizontalHeader().setStretchLastSection(True)
        self._trade_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        history_layout.addWidget(self._trade_table)

        violation_title = QLabel("Rule Violations / Enforcements (Most Recent)")
        violation_title.setObjectName("subheading")
        violation_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        history_layout.addWidget(violation_title)
        self._violation_table = QTableWidget()
        self._violation_table.setColumnCount(6)
        self._violation_table.setHorizontalHeaderLabels(
            ["Time", "Rule", "Severity", "Trade #", "Day", "Message"]
        )
        self._violation_table.setMinimumHeight(240)
        self._violation_table.horizontalHeader().setStretchLastSection(True)
        self._violation_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        history_layout.addWidget(self._violation_table)

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

        self._tabs.addTab(history_scroll, "📅  History")

        # ── Tab 4: Trade Analysis Journal ─────────────────────────────
        trade_analysis_tab = QWidget()
        trade_analysis_scroll = QScrollArea()
        trade_analysis_scroll.setWidgetResizable(True)
        trade_analysis_scroll.setWidget(trade_analysis_tab)
        trade_analysis_layout = QVBoxLayout(trade_analysis_tab)
        self._trade_analysis_widget = TradeAnalysisWidget(self._db)
        trade_analysis_layout.addWidget(self._trade_analysis_widget)
        self._tabs.addTab(trade_analysis_scroll, "Trade Analysis")

        # ── Status bar ────────────────────────────────────────────────────
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

        self._load_history()

    def _create_perf_card(self, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("perf_card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("perf_card_title")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        value_lbl = QLabel("--")
        value_lbl.setObjectName("value_label")
        value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_lbl)
        return card

    def _set_perf_value(self, key: str, value: str) -> None:
        lbl = self._perf_values.get(key)
        if lbl:
            lbl.setText(value)
