"""
Trade analysis tab widget.

Stores per-trade discretionary analysis linked by trade_date + trade_index.
"""

import os
import shutil
from datetime import datetime

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor, QPixmap, QTextCharFormat
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)

from app.config import ANALYSIS_ASSETS_DIR
from app.database import DailyDatabase


class ClickableImageLabel(QLabel):
    """Thumbnail label that can open full-size image on click."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._on_click = None

    def set_click_handler(self, handler) -> None:
        self._on_click = handler

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click()
        super().mousePressEvent(event)


class TradeAnalysisWidget(QWidget):
    """Journal-like analysis UI for completed trades."""

    _TIMEFRAMES = ("M5", "M15", "H1", "H4")

    def __init__(self, db: DailyDatabase, parent=None):
        super().__init__(parent)
        self._db = db
        self._selected_trade_date: str | None = None
        self._selected_trade_index: int | None = None
        self._mt5_entry_tf_combo: QComboBox | None = None
        self._mt5_entry_path: str = ""
        self._mt5_thumb: ClickableImageLabel | None = None
        self._tv_paths: dict[str, str] = {}
        self._tv_thumbs: dict[str, ClickableImageLabel] = {}
        self._all_trades: list[dict] = []
        self._trades_by_day: dict[str, list[dict]] = {}
        self._calendar_marked_days: set[str] = set()
        self._calendar: QCalendarWidget | None = None
        self._calendar_trade_table: QTableWidget | None = None
        self._build_ui()
        self.refresh_trades()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("Trade Analysis Journal")
        title.setObjectName("heading")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            "Link notes and screenshots to each trade using Day + Index.\n"
            "Screenshot set: MT5 entry timeframe + TradingView (M5, M15, H1, H4)."
        )
        subtitle.setObjectName("subheading")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        actions = QHBoxLayout()
        self._btn_refresh = QPushButton("Refresh Trades")
        self._btn_refresh.clicked.connect(self.refresh_trades)
        actions.addWidget(self._btn_refresh)

        self._btn_save = QPushButton("Save Analysis")
        self._btn_save.clicked.connect(self._save_analysis)
        actions.addWidget(self._btn_save)
        layout.addLayout(actions)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, stretch=1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Select Trade"))
        selector_tabs = QTabWidget()

        list_tab = QWidget()
        list_layout = QVBoxLayout(list_tab)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self._trade_table = QTableWidget()
        self._trade_table.setColumnCount(5)
        self._trade_table.setHorizontalHeaderLabels(
            ["Day", "#", "Result", "P&L", "Recorded"]
        )
        self._trade_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._trade_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._trade_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._trade_table.horizontalHeader().setStretchLastSection(True)
        self._trade_table.itemSelectionChanged.connect(self._on_trade_selected)
        list_layout.addWidget(self._trade_table)
        selector_tabs.addTab(list_tab, "List View")

        calendar_tab = QWidget()
        calendar_layout = QVBoxLayout(calendar_tab)
        calendar_layout.setContentsMargins(0, 0, 0, 0)

        self._calendar = QCalendarWidget()
        self._calendar.setGridVisible(True)
        self._calendar.selectionChanged.connect(self._on_calendar_day_changed)
        calendar_layout.addWidget(self._calendar)

        calendar_layout.addWidget(QLabel("Trades On Selected Day"))
        self._calendar_trade_table = QTableWidget()
        self._calendar_trade_table.setColumnCount(4)
        self._calendar_trade_table.setHorizontalHeaderLabels(
            ["#", "Result", "P&L", "Recorded"]
        )
        self._calendar_trade_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._calendar_trade_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._calendar_trade_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._calendar_trade_table.horizontalHeader().setStretchLastSection(True)
        self._calendar_trade_table.itemSelectionChanged.connect(
            self._on_calendar_trade_selected
        )
        calendar_layout.addWidget(self._calendar_trade_table)

        selector_tabs.addTab(calendar_tab, "Calendar View")
        left_layout.addWidget(selector_tabs)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self._selected_label = QLabel("Selected: none")
        self._selected_label.setObjectName("subheading")
        right_layout.addWidget(self._selected_label)

        form = QFormLayout()
        self._entry_reason = QTextEdit()
        self._entry_reason.setPlaceholderText("Why this entry was valid.")
        self._entry_reason.setMinimumHeight(80)
        form.addRow("Entry reason", self._entry_reason)

        self._setup_tags = QLineEdit()
        self._setup_tags.setPlaceholderText("comma,separated,tags")
        form.addRow("Setup tags", self._setup_tags)

        self._notes = QTextEdit()
        self._notes.setPlaceholderText("Execution notes, mistakes, improvements.")
        self._notes.setMinimumHeight(100)
        form.addRow("Review notes", self._notes)

        right_layout.addLayout(form)
        right_layout.addWidget(self._build_mt5_entry_group())
        right_layout.addWidget(self._build_screenshot_group("TradingView Screenshots", "TV"))

        self._save_status = QLabel("")
        self._save_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        right_layout.addWidget(self._save_status)
        splitter.addWidget(right)
        splitter.setSizes([460, 640])

    def _build_screenshot_group(self, title: str, source: str) -> QGroupBox:
        group = QGroupBox(title)
        grid = QGridLayout(group)
        for i, tf in enumerate(self._TIMEFRAMES):
            card = QGroupBox(tf)
            card_layout = QVBoxLayout(card)
            thumb = self._build_thumb_label()
            thumb.set_click_handler(lambda t=tf: self._open_tv_preview(t))
            self._tv_thumbs[tf] = thumb
            self._tv_paths[tf] = ""
            browse_btn = QPushButton("Browse")
            browse_btn.clicked.connect(
                lambda _checked=False, s=source, t=tf: self._pick_screenshot(s, t)
            )
            card_layout.addWidget(thumb)
            card_layout.addWidget(browse_btn)
            grid.addWidget(card, i // 2, i % 2)
        return group

    def _build_mt5_entry_group(self) -> QGroupBox:
        group = QGroupBox("MT5 Entry Screenshot")
        grid = QGridLayout(group)

        tf_lbl = QLabel("Entry TF")
        self._mt5_entry_tf_combo = QComboBox()
        self._mt5_entry_tf_combo.addItems(["M1", "M5", "M15", "M30", "H1", "H4", "D1"])
        self._mt5_entry_tf_combo.setCurrentText("M15")

        self._mt5_thumb = self._build_thumb_label()
        self._mt5_thumb.set_click_handler(self._open_mt5_preview)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._pick_mt5_entry_screenshot)

        grid.addWidget(tf_lbl, 0, 0)
        grid.addWidget(self._mt5_entry_tf_combo, 0, 1)
        grid.addWidget(self._mt5_thumb, 1, 0, 1, 2)
        grid.addWidget(browse_btn, 2, 0, 1, 2)
        return group

    def _build_thumb_label(self) -> ClickableImageLabel:
        thumb = ClickableImageLabel()
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        thumb.setMinimumSize(200, 120)
        thumb.setStyleSheet(
            "border: 1px solid #2d2d4a; border-radius: 6px; background-color: #121d33;"
        )
        thumb.setText("Preview")
        return thumb

    def refresh_trades(self) -> None:
        """Reload trades from ledger/events into selector table."""
        ledger_rows = self._db.get_trade_ledger(limit=300)
        event_rows = self._db.get_trade_events(limit=300)

        # Merge by (day, index). Prefer ledger rows (richer metadata), but keep
        # events-only rows so older trades still show up for analysis.
        merged: dict[tuple[str, int], dict] = {}
        for e in event_rows:
            trade_date = str(e.get("trade_date", "")).strip()
            try:
                trade_index = int(e.get("trade_index", 0) or 0)
            except (TypeError, ValueError):
                trade_index = 0
            merged[(trade_date, trade_index)] = {
                "trade_date": trade_date,
                "trade_index": trade_index,
                "result": e.get("result", "unknown"),
                "pnl": e.get("pnl"),
                "recorded_at": e.get("recorded_at", ""),
            }

        for t in ledger_rows:
            trade_date = str(t.get("trade_date", "")).strip()
            try:
                trade_index = int(t.get("trade_index", 0) or 0)
            except (TypeError, ValueError):
                trade_index = 0
            key = (trade_date, trade_index)
            existing = merged.get(key, {})
            merged[key] = {
                "trade_date": trade_date,
                "trade_index": trade_index,
                "result": t.get("result", existing.get("result", "unknown")),
                "pnl": t.get("pnl") if t.get("pnl") is not None else existing.get("pnl"),
                "recorded_at": t.get("recorded_at", existing.get("recorded_at", "")),
            }

        trades = sorted(
            merged.values(),
            key=lambda row: (row.get("trade_date", ""), int(row.get("trade_index", 0) or 0)),
            reverse=True,
        )[:300]
        self._all_trades = trades
        self._trades_by_day = {}
        for trade in trades:
            day = str(trade.get("trade_date", "")).strip()
            if day:
                self._trades_by_day.setdefault(day, []).append(trade)

        self._trade_table.blockSignals(True)
        self._trade_table.setRowCount(len(trades))
        for i, trade in enumerate(trades):
            self._trade_table.setItem(i, 0, QTableWidgetItem(trade["trade_date"]))
            self._trade_table.setItem(i, 1, QTableWidgetItem(str(trade["trade_index"])))
            self._trade_table.setItem(i, 2, QTableWidgetItem((trade.get("result") or "unknown").upper()))
            pnl_val = trade.get("pnl")
            pnl_text = "-" if pnl_val is None else f"${float(pnl_val):+.2f}"
            self._trade_table.setItem(i, 3, QTableWidgetItem(pnl_text))
            self._trade_table.setItem(i, 4, QTableWidgetItem(trade.get("recorded_at", "")))
        self._trade_table.blockSignals(False)

        self._refresh_calendar_markers()

        selected_key = (
            self._selected_trade_date,
            self._selected_trade_index,
        )
        if (
            selected_key[0]
            and selected_key[1] is not None
            and any(
                t.get("trade_date") == selected_key[0]
                and int(t.get("trade_index", 0) or 0) == selected_key[1]
                for t in trades
            )
        ):
            self._select_trade(
                str(selected_key[0]),
                int(selected_key[1]),
                update_list=True,
                update_calendar=True,
                load_analysis=False,
            )
        elif trades:
            first = trades[0]
            self._select_trade(
                str(first.get("trade_date", "")),
                int(first.get("trade_index", 0) or 0),
                update_list=True,
                update_calendar=True,
                load_analysis=True,
            )
        else:
            if self._calendar is not None:
                self._calendar.setSelectedDate(QDate.currentDate())
                self._populate_calendar_day_table(self._calendar.selectedDate().toString("yyyy-MM-dd"))

    def _on_trade_selected(self) -> None:
        rows = self._trade_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        day_item = self._trade_table.item(row, 0)
        idx_item = self._trade_table.item(row, 1)
        if day_item is None or idx_item is None:
            return

        try:
            trade_index = int(idx_item.text().strip())
        except ValueError:
            return
        self._select_trade(
            day_item.text().strip(),
            trade_index,
            update_list=False,
            update_calendar=True,
            load_analysis=True,
        )

    def _on_calendar_day_changed(self) -> None:
        if self._calendar is None:
            return
        day = self._calendar.selectedDate().toString("yyyy-MM-dd")
        self._populate_calendar_day_table(day)

    def _on_calendar_trade_selected(self) -> None:
        if self._calendar_trade_table is None or self._calendar is None:
            return
        rows = self._calendar_trade_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        idx_item = self._calendar_trade_table.item(row, 0)
        if idx_item is None:
            return
        try:
            trade_index = int(idx_item.text().strip())
        except ValueError:
            return
        day = self._calendar.selectedDate().toString("yyyy-MM-dd")
        self._select_trade(
            day,
            trade_index,
            update_list=True,
            update_calendar=False,
            load_analysis=True,
        )

    def _select_trade(
        self,
        trade_date: str,
        trade_index: int,
        *,
        update_list: bool,
        update_calendar: bool,
        load_analysis: bool,
    ) -> None:
        if not trade_date or trade_index <= 0:
            return

        self._selected_trade_date = trade_date
        self._selected_trade_index = trade_index
        self._selected_label.setText(
            f"Selected: {self._selected_trade_date} / #{self._selected_trade_index}"
        )
        if update_list:
            self._select_list_row(trade_date, trade_index)
        if update_calendar:
            self._select_calendar_trade(trade_date, trade_index)
        if load_analysis:
            self._load_existing_analysis()

    def _select_list_row(self, trade_date: str, trade_index: int) -> None:
        self._trade_table.blockSignals(True)
        self._trade_table.clearSelection()
        for row in range(self._trade_table.rowCount()):
            day_item = self._trade_table.item(row, 0)
            idx_item = self._trade_table.item(row, 1)
            if day_item is None or idx_item is None:
                continue
            try:
                idx = int(idx_item.text().strip())
            except ValueError:
                continue
            if day_item.text().strip() == trade_date and idx == trade_index:
                self._trade_table.selectRow(row)
                break
        self._trade_table.blockSignals(False)

    def _select_calendar_trade(self, trade_date: str, trade_index: int) -> None:
        if self._calendar is None or self._calendar_trade_table is None:
            return

        qdate = QDate.fromString(trade_date, "yyyy-MM-dd")
        if qdate.isValid():
            self._calendar.blockSignals(True)
            self._calendar.setSelectedDate(qdate)
            self._calendar.blockSignals(False)
        self._populate_calendar_day_table(trade_date)

        self._calendar_trade_table.blockSignals(True)
        self._calendar_trade_table.clearSelection()
        for row in range(self._calendar_trade_table.rowCount()):
            idx_item = self._calendar_trade_table.item(row, 0)
            if idx_item is None:
                continue
            try:
                idx = int(idx_item.text().strip())
            except ValueError:
                continue
            if idx == trade_index:
                self._calendar_trade_table.selectRow(row)
                break
        self._calendar_trade_table.blockSignals(False)

    def _populate_calendar_day_table(self, trade_date: str) -> None:
        if self._calendar_trade_table is None:
            return
        day_trades = self._trades_by_day.get(trade_date, [])
        ordered = sorted(
            day_trades,
            key=lambda row: int(row.get("trade_index", 0) or 0),
            reverse=True,
        )
        self._calendar_trade_table.blockSignals(True)
        self._calendar_trade_table.setRowCount(len(ordered))
        for i, trade in enumerate(ordered):
            self._calendar_trade_table.setItem(
                i, 0, QTableWidgetItem(str(trade.get("trade_index", 0)))
            )
            self._calendar_trade_table.setItem(
                i, 1, QTableWidgetItem((trade.get("result") or "unknown").upper())
            )
            pnl_val = trade.get("pnl")
            pnl_text = "-" if pnl_val is None else f"${float(pnl_val):+.2f}"
            self._calendar_trade_table.setItem(i, 2, QTableWidgetItem(pnl_text))
            self._calendar_trade_table.setItem(
                i, 3, QTableWidgetItem(str(trade.get("recorded_at", "")))
            )

        if self._selected_trade_date == trade_date and self._selected_trade_index is not None:
            for row in range(self._calendar_trade_table.rowCount()):
                idx_item = self._calendar_trade_table.item(row, 0)
                if idx_item is None:
                    continue
                try:
                    idx = int(idx_item.text().strip())
                except ValueError:
                    continue
                if idx == self._selected_trade_index:
                    self._calendar_trade_table.selectRow(row)
                    break
        self._calendar_trade_table.blockSignals(False)

    def _refresh_calendar_markers(self) -> None:
        if self._calendar is None:
            return
        default_fmt = QTextCharFormat()
        for day in self._calendar_marked_days:
            qd = QDate.fromString(day, "yyyy-MM-dd")
            if qd.isValid():
                self._calendar.setDateTextFormat(qd, default_fmt)

        mark_fmt = QTextCharFormat()
        mark_fmt.setBackground(QColor("#22314f"))
        mark_fmt.setForeground(QColor("#dfe8ff"))
        mark_fmt.setFontWeight(700)
        for day in self._trades_by_day.keys():
            qd = QDate.fromString(day, "yyyy-MM-dd")
            if qd.isValid():
                self._calendar.setDateTextFormat(qd, mark_fmt)
        self._calendar_marked_days = set(self._trades_by_day.keys())

    def _load_existing_analysis(self) -> None:
        if not self._selected_trade_date or self._selected_trade_index is None:
            return
        analysis = self._db.get_trade_analysis(
            self._selected_trade_date,
            self._selected_trade_index,
        )
        if analysis is None:
            self._entry_reason.clear()
            self._setup_tags.clear()
            self._notes.clear()
            self._mt5_entry_path = ""
            if self._mt5_entry_tf_combo is not None:
                self._mt5_entry_tf_combo.setCurrentText("M15")
            for tf in self._TIMEFRAMES:
                self._set_tv_screenshot_path(tf, "")
            self._save_status.setText("No analysis saved yet for this trade.")
            self._set_thumbnail(self._mt5_thumb, "", "MT5 Entry")
            return

        self._entry_reason.setPlainText(analysis.get("entry_reason", ""))
        self._setup_tags.setText(",".join(analysis.get("setup_tags") or []))
        self._notes.setPlainText(analysis.get("notes", ""))

        mt5_map = analysis.get("mt5_screenshots") or {}
        tv_map = analysis.get("tradingview_screenshots") or {}
        # New shape: {"entry_tf": "M15", "entry_path": "..."}.
        entry_tf = str(mt5_map.get("entry_tf", "")).strip()
        entry_path = str(mt5_map.get("entry_path", "")).strip()
        # Backward compatibility: older shape stored multiple TF keys.
        if not entry_path:
            for tf in self._TIMEFRAMES:
                old_path = str(mt5_map.get(tf, "")).strip()
                if old_path:
                    entry_tf = tf
                    entry_path = old_path
                    break
        if self._mt5_entry_tf_combo is not None and entry_tf:
            self._mt5_entry_tf_combo.setCurrentText(entry_tf)
        self._mt5_entry_path = entry_path

        for tf in self._TIMEFRAMES:
            self._set_tv_screenshot_path(tf, str(tv_map.get(tf, "")))

        self._set_thumbnail(self._mt5_thumb, entry_path, "MT5 Entry")

        self._save_status.setText("Loaded existing analysis.")

    def _set_tv_screenshot_path(self, tf: str, value: str) -> None:
        self._tv_paths[tf] = value
        thumb = self._tv_thumbs.get(tf)
        self._set_thumbnail(thumb, value, tf)

    def _pick_screenshot(self, source: str, tf: str) -> None:
        if not self._selected_trade_date or self._selected_trade_index is None:
            QMessageBox.warning(
                self,
                "Trade Required",
                "Select a trade first, then attach screenshots.",
            )
            return
        src_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {source} {tf} Screenshot",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*.*)",
        )
        if not src_path:
            return

        os.makedirs(ANALYSIS_ASSETS_DIR, exist_ok=True)
        trade_dir = os.path.join(
            ANALYSIS_ASSETS_DIR,
            f"{self._selected_trade_date}_{self._selected_trade_index}",
        )
        os.makedirs(trade_dir, exist_ok=True)

        ext = os.path.splitext(src_path)[1] or ".png"
        stamp = datetime.now().strftime("%H%M%S")
        dest_name = f"{source.lower()}_{tf.lower()}_{stamp}{ext}"
        dest_path = os.path.join(trade_dir, dest_name)
        try:
            shutil.copy2(src_path, dest_path)
        except Exception as exc:
            QMessageBox.warning(self, "Copy Failed", f"Could not copy screenshot:\n{exc}")
            return

        if source == "TV":
            self._set_tv_screenshot_path(tf, dest_path)

    def _pick_mt5_entry_screenshot(self) -> None:
        if not self._selected_trade_date or self._selected_trade_index is None:
            QMessageBox.warning(
                self,
                "Trade Required",
                "Select a trade first, then attach screenshots.",
            )
            return
        if self._mt5_entry_tf_combo is None:
            return
        entry_tf = self._mt5_entry_tf_combo.currentText().strip() or "M15"
        src_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select MT5 {entry_tf} Entry Screenshot",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*.*)",
        )
        if not src_path:
            return

        os.makedirs(ANALYSIS_ASSETS_DIR, exist_ok=True)
        trade_dir = os.path.join(
            ANALYSIS_ASSETS_DIR,
            f"{self._selected_trade_date}_{self._selected_trade_index}",
        )
        os.makedirs(trade_dir, exist_ok=True)

        ext = os.path.splitext(src_path)[1] or ".png"
        stamp = datetime.now().strftime("%H%M%S")
        dest_name = f"mt5_entry_{entry_tf.lower()}_{stamp}{ext}"
        dest_path = os.path.join(trade_dir, dest_name)
        try:
            shutil.copy2(src_path, dest_path)
        except Exception as exc:
            QMessageBox.warning(self, "Copy Failed", f"Could not copy screenshot:\n{exc}")
            return
        self._mt5_entry_path = dest_path
        self._set_thumbnail(self._mt5_thumb, dest_path, f"MT5 {entry_tf}")

    def _set_thumbnail(self, label: ClickableImageLabel | None, path: str, placeholder: str) -> None:
        if label is None:
            return
        if not path:
            label.setPixmap(QPixmap())
            label.setText(placeholder + "\n(click)")
            return
        if not os.path.exists(path):
            label.setPixmap(QPixmap())
            label.setText("Missing file")
            return

        pix = QPixmap(path)
        if pix.isNull():
            label.setPixmap(QPixmap())
            label.setText("Invalid image")
            return
        scaled = pix.scaled(
            label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(scaled)
        label.setText("")

    def _open_mt5_preview(self) -> None:
        tf = self._mt5_entry_tf_combo.currentText().strip() if self._mt5_entry_tf_combo else "Entry"
        self._open_full_image(self._mt5_entry_path, f"MT5 {tf}")

    def _open_tv_preview(self, tf: str) -> None:
        self._open_full_image(self._tv_paths.get(tf, ""), f"TradingView {tf}")

    def _open_full_image(self, path: str, title: str) -> None:
        if not path:
            QMessageBox.information(self, "No Screenshot", "No screenshot attached yet.")
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "Missing File", "Screenshot file was not found on disk.")
            return

        pix = QPixmap(path)
        if pix.isNull():
            QMessageBox.warning(self, "Invalid Image", "Cannot open this image file.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        screen = self.screen()
        if screen is not None:
            rect = screen.availableGeometry()
            dialog.resize(int(rect.width() * 0.9), int(rect.height() * 0.9))
        else:
            dialog.resize(1200, 800)

        dlg_layout = QVBoxLayout(dialog)
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setPixmap(pix)
        scroll.setWidget(image_label)
        dlg_layout.addWidget(scroll)
        dialog.exec()

    def _save_analysis(self) -> None:
        if not self._selected_trade_date or self._selected_trade_index is None:
            QMessageBox.warning(self, "No Trade Selected", "Select a trade first.")
            return

        missing = []
        if not self._mt5_entry_path.strip():
            mt5_tf = self._mt5_entry_tf_combo.currentText() if self._mt5_entry_tf_combo else "entry"
            missing.append(f"MT5 {mt5_tf} entry")
        for tf in self._TIMEFRAMES:
            if not self._tv_paths.get(tf, "").strip():
                missing.append(f"TradingView {tf}")
        if missing:
            reply = QMessageBox.question(
                self,
                "Missing Screenshots",
                "Some timeframe screenshots are missing:\n"
                + "\n".join(missing)
                + "\n\nSave anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        tags = [t.strip() for t in self._setup_tags.text().split(",") if t.strip()]
        mt5_entry_tf = self._mt5_entry_tf_combo.currentText().strip() if self._mt5_entry_tf_combo else ""
        mt5_entry_path = self._mt5_entry_path.strip()
        mt5_map = {"entry_tf": mt5_entry_tf, "entry_path": mt5_entry_path}
        tv_map = {
            tf: self._tv_paths.get(tf, "").strip()
            for tf in self._TIMEFRAMES
            if self._tv_paths.get(tf, "").strip()
        }
        self._db.upsert_trade_analysis(
            trade_date=self._selected_trade_date,
            trade_index=self._selected_trade_index,
            entry_reason=self._entry_reason.toPlainText().strip(),
            setup_tags=tags,
            notes=self._notes.toPlainText().strip(),
            mt5_screenshots=mt5_map,
            tradingview_screenshots=tv_map,
        )
        self._save_status.setText(
            f"Saved at {datetime.now().strftime('%H:%M:%S')} for "
            f"{self._selected_trade_date} #{self._selected_trade_index}"
        )
