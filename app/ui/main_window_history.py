"""MainWindow history and live trade-sync mixin."""

import logging

from PyQt6.QtWidgets import QTableWidgetItem

from app.config import get_session_day_str

log = logging.getLogger(__name__)


class MainWindowHistoryMixin:
    def _load_history(self):
        stats = self._db.get_overview_stats(days=30)
        self._set_perf_value("total_pnl", f"${stats['total_pnl']:+.2f}")
        self._set_perf_value("win_rate", f"{stats['win_rate']:.1f}%")
        self._set_perf_value("wins_losses", f"{stats['wins']} / {stats['losses']}")
        self._set_perf_value("total_trades", str(stats["total_trades"]))
        self._set_perf_value("green_red_days", f"{stats['green_days']} / {stats['red_days']}")
        self._set_perf_value("breakeven", str(stats["breakeven"]))

        rows = self._db.get_last_n_days(30)
        self._history_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self._history_table.setItem(i, 0, QTableWidgetItem(row["date"]))
            pnl_item = QTableWidgetItem(f"${row['pnl']:+.2f}")
            self._history_table.setItem(i, 1, pnl_item)
            self._history_table.setItem(
                i, 2, QTableWidgetItem(str(row["trades"]))
            )
            result_item = QTableWidgetItem(row["result"].upper())
            self._history_table.setItem(i, 3, result_item)

        trades = self._db.get_trade_ledger(limit=150)
        self._trade_table.setRowCount(len(trades))
        for i, t in enumerate(trades):
            self._trade_table.setItem(i, 0, QTableWidgetItem(t["trade_date"]))
            self._trade_table.setItem(i, 1, QTableWidgetItem(str(t["trade_index"])))
            self._trade_table.setItem(i, 2, QTableWidgetItem((t["result"] or "unknown").upper()))
            pnl_val = t.get("pnl")
            pnl_text = "—" if pnl_val is None else f"${float(pnl_val):+.2f}"
            self._trade_table.setItem(i, 3, QTableWidgetItem(pnl_text))
            self._trade_table.setItem(i, 4, QTableWidgetItem(t.get("close_reason") or ""))
            self._trade_table.setItem(i, 5, QTableWidgetItem(t.get("source") or ""))
            self._trade_table.setItem(i, 6, QTableWidgetItem(t["recorded_at"]))

        violations = self._db.get_violation_log(limit=150)
        self._violation_table.setRowCount(len(violations))
        for i, v in enumerate(violations):
            self._violation_table.setItem(i, 0, QTableWidgetItem(v["event_time"]))
            self._violation_table.setItem(i, 1, QTableWidgetItem(v["rule_code"]))
            self._violation_table.setItem(i, 2, QTableWidgetItem((v.get("severity") or "warn").upper()))
            trade_idx = "-" if v.get("trade_index") is None else str(v.get("trade_index"))
            self._violation_table.setItem(i, 3, QTableWidgetItem(trade_idx))
            self._violation_table.setItem(i, 4, QTableWidgetItem(v.get("trade_date") or ""))
            self._violation_table.setItem(i, 5, QTableWidgetItem(v.get("message") or ""))

        if hasattr(self, "_trade_analysis_widget"):
            self._trade_analysis_widget.refresh_trades()

    def _sync_live_trade_events(self, data: dict) -> None:
        """Capture live trade events so History stays up-to-date intraday."""
        try:
            today = get_session_day_str()
            current_trades = int(data.get("trades_today", 0) or 0)
            net_pnl = float(data.get("daily_profit_usd", 0) or 0) - float(data.get("daily_loss_usd", 0) or 0)
            session_active = bool(data.get("session_active"))
            shutdown_signal = bool(data.get("shutdown_signal"))

            # Prevent ghost duplicates when app starts with stale bridge counters
            # from a previous day/session.
            if not self._is_bridge_data_for_current_session_day(data):
                self._prev_trades_today = current_trades
                self._prev_net_pnl = net_pnl
                return
            # If the session is inactive without a shutdown signal, treat the
            # bridge as non-authoritative for trade backfill.
            if not session_active and not shutdown_signal:
                self._prev_trades_today = current_trades
                self._prev_net_pnl = net_pnl
                return

            last = (data.get("last_trade_result") or "").strip().lower()
            has_last_result_signal = last in ("win", "loss", "flat", "breakeven", "be")

            raw_last_pnl = data.get("last_trade_pnl")
            parsed_last_pnl = None
            if raw_last_pnl not in (None, ""):
                try:
                    parsed_last_pnl = float(raw_last_pnl)
                except (TypeError, ValueError):
                    parsed_last_pnl = None

            pnl_delta_signal = False
            if (
                self._prev_trades_today is not None
                and self._prev_net_pnl is not None
                and current_trades - self._prev_trades_today == 1
            ):
                pnl_delta_signal = abs(net_pnl - self._prev_net_pnl) >= 0.0001

            has_pnl_signal = (
                parsed_last_pnl is not None
                and abs(parsed_last_pnl) >= 0.0001
            )
            has_trade_signal = has_last_result_signal or has_pnl_signal or pnl_delta_signal

            db_last_index = self._db.get_last_trade_index(today)
            if current_trades < db_last_index:
                self._prev_trades_today = current_trades
                self._prev_net_pnl = net_pnl
                return
            if current_trades == db_last_index:
                # If the latest stored row is a placeholder unknown, upgrade it
                # using bridge close payload without changing trade count.
                if current_trades > 0 and has_trade_signal:
                    latest_rows = self._db.get_trade_ledger(trade_day=today, limit=1)
                    if latest_rows:
                        latest = latest_rows[0]
                        latest_result = (latest.get("result") or "").strip().lower()
                        latest_idx = int(latest.get("trade_index", 0) or 0)
                        if latest_idx == current_trades and latest_result == "unknown":
                            upgraded_result = last if has_last_result_signal else "unknown"
                            upgraded_pnl = parsed_last_pnl
                            if (
                                upgraded_pnl is None
                                and self._prev_trades_today is not None
                                and self._prev_net_pnl is not None
                                and current_trades - self._prev_trades_today == 1
                            ):
                                upgraded_pnl = net_pnl - self._prev_net_pnl
                            self._db.record_trade_event(
                                trade_index=current_trades,
                                result=upgraded_result,
                                pnl=upgraded_pnl,
                                trade_day=today,
                            )
                            self._db.record_trade_ledger(
                                trade_index=current_trades,
                                result=upgraded_result,
                                pnl=upgraded_pnl,
                                close_reason="session_update",
                                source="bridge",
                                trade_day=today,
                            )
                            self._load_history()
                self._prev_trades_today = current_trades
                self._prev_net_pnl = net_pnl
                return

            if not has_trade_signal:
                log.warning(
                    "Skipping ambiguous bridge trade sync (bridge=%s, db=%s, day=%s).",
                    current_trades,
                    db_last_index,
                    today,
                )
                self._prev_trades_today = current_trades
                self._prev_net_pnl = net_pnl
                return

            # Backfill any missed entries. Older gaps are unknown because only
            # the latest close payload is available in session.json.
            for idx in range(db_last_index + 1, current_trades + 1):
                result = "unknown"
                pnl_delta = None
                if idx == current_trades:
                    if last in ("win", "loss", "flat", "breakeven", "be"):
                        result = last
                    pnl_delta = parsed_last_pnl
                    if (
                        pnl_delta is None
                        and
                        self._prev_trades_today is not None
                        and self._prev_net_pnl is not None
                        and current_trades - self._prev_trades_today == 1
                    ):
                        pnl_delta = net_pnl - self._prev_net_pnl

                self._db.record_trade_event(
                    trade_index=idx,
                    result=result,
                    pnl=pnl_delta,
                    trade_day=today,
                )
                close_reason = "sync_backfill" if idx < current_trades else "session_update"
                self._db.record_trade_ledger(
                    trade_index=idx,
                    result=result,
                    pnl=pnl_delta,
                    close_reason=close_reason,
                    source="bridge",
                    trade_day=today,
                )

            self._load_history()
            self._prev_trades_today = current_trades
            self._prev_net_pnl = net_pnl
        except Exception as exc:
            log.warning("Failed to sync live trade events: %s", exc)
