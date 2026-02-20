"""
TradingGuard — Daily Results Database
SQLite-backed storage for daily P&L and session history.
"""

import json
import sqlite3
from datetime import datetime
from app.config import DB_PATH, get_session_day_str


class DailyDatabase:
    """Tracks daily trading results in SQLite."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    # ── Setup ──────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_results (
                    date       TEXT PRIMARY KEY,
                    pnl        REAL NOT NULL DEFAULT 0.0,
                    trades     INTEGER NOT NULL DEFAULT 0,
                    result     TEXT NOT NULL DEFAULT 'flat'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_events (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date   TEXT NOT NULL,
                    trade_index  INTEGER NOT NULL,
                    result       TEXT NOT NULL DEFAULT 'unknown',
                    pnl          REAL,
                    recorded_at  TEXT NOT NULL,
                    UNIQUE(trade_date, trade_index)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_ledger (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date    TEXT NOT NULL,
                    trade_index   INTEGER NOT NULL,
                    result        TEXT NOT NULL DEFAULT 'unknown',
                    pnl           REAL,
                    close_reason  TEXT NOT NULL DEFAULT '',
                    source        TEXT NOT NULL DEFAULT 'bridge',
                    recorded_at   TEXT NOT NULL,
                    UNIQUE(trade_date, trade_index)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS violation_log (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time    TEXT NOT NULL,
                    trade_date    TEXT,
                    trade_index   INTEGER,
                    rule_code     TEXT NOT NULL,
                    severity      TEXT NOT NULL DEFAULT 'warn',
                    message       TEXT NOT NULL,
                    context_json  TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_analysis (
                    trade_date             TEXT NOT NULL,
                    trade_index            INTEGER NOT NULL,
                    entry_reason           TEXT NOT NULL DEFAULT '',
                    setup_tags             TEXT NOT NULL DEFAULT '[]',
                    notes                  TEXT NOT NULL DEFAULT '',
                    mt5_screenshots        TEXT NOT NULL DEFAULT '{}',
                    tradingview_screenshots TEXT NOT NULL DEFAULT '{}',
                    created_at             TEXT NOT NULL,
                    updated_at             TEXT NOT NULL,
                    PRIMARY KEY (trade_date, trade_index)
                )
                """
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ── Public API ─────────────────────────────────────────────────────────

    def record_day(
        self,
        pnl: float,
        trades: int,
        day: str | None = None,
    ) -> None:
        """Insert or replace today's result.  ``day`` defaults to today."""
        day = day or get_session_day_str()
        result = "green" if pnl > 0 else ("red" if pnl < 0 else "flat")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO daily_results (date, pnl, trades, result)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    pnl = excluded.pnl,
                    trades = excluded.trades,
                    result = excluded.result
                """,
                (day, pnl, trades, result),
            )

    def get_last_n_days(self, n: int = 7) -> list[dict]:
        """Return the last *n* daily results, most recent first."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM daily_results ORDER BY date DESC LIMIT ?",
                (n,),
            ).fetchall()
            return [dict(r) for r in rows]

    def is_recovery_day(self) -> bool:
        """True if the last 2 completed days were both red → forced rest day."""
        rows = self.get_last_n_days(2)
        if len(rows) < 2:
            return False
        return all(r["result"] == "red" for r in rows)

    def get_today(self) -> dict | None:
        """Return today's row or None."""
        today = get_session_day_str()
        return self.get_day(today)

    def get_day(self, day: str) -> dict | None:
        """Return one specific day row or None."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM daily_results WHERE date = ?", (day,)
            ).fetchone()
            return dict(row) if row else None

    def clear_today(self) -> None:
        """Delete today's row, if any.

        Intended for development/testing to reset the daily lock.
        """
        self.clear_day(get_session_day_str())

    def clear_day(self, day: str) -> None:
        """Delete one specific day from daily and intraday tables."""
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM daily_results WHERE date = ?", (day,)
            )
            conn.execute(
                "DELETE FROM trade_events WHERE trade_date = ?", (day,)
            )
            conn.execute(
                "DELETE FROM trade_ledger WHERE trade_date = ?", (day,)
            )
            conn.execute(
                "DELETE FROM violation_log WHERE trade_date = ?", (day,)
            )
            conn.execute(
                "DELETE FROM trade_analysis WHERE trade_date = ?", (day,)
            )

    def record_trade_event(
        self,
        trade_index: int,
        result: str = "unknown",
        pnl: float | None = None,
        trade_day: str | None = None,
    ) -> None:
        """Insert one trade event for the given day/index (idempotent)."""
        trade_day = trade_day or get_session_day_str()
        recorded_at = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO trade_events (trade_date, trade_index, result, pnl, recorded_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(trade_date, trade_index) DO UPDATE SET
                    result = excluded.result,
                    pnl = COALESCE(excluded.pnl, trade_events.pnl),
                    recorded_at = excluded.recorded_at
                """,
                (trade_day, trade_index, result, pnl, recorded_at),
            )

    def get_last_trade_index(self, trade_day: str | None = None) -> int:
        """Return max trade_index for a day (0 if none)."""
        trade_day = trade_day or get_session_day_str()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT MAX(trade_index) FROM trade_events WHERE trade_date = ?",
                (trade_day,),
            ).fetchone()
            return int(row[0] or 0)

    def get_trade_events(
        self,
        trade_day: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return trade events newest first; optionally restricted to one day."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            if trade_day:
                rows = conn.execute(
                    """
                    SELECT trade_date, trade_index, result, pnl, recorded_at
                    FROM trade_events
                    WHERE trade_date = ?
                    ORDER BY trade_date DESC, trade_index DESC
                    LIMIT ?
                    """,
                    (trade_day, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT trade_date, trade_index, result, pnl, recorded_at
                    FROM trade_events
                    ORDER BY trade_date DESC, trade_index DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def record_trade_ledger(
        self,
        trade_index: int,
        result: str = "unknown",
        pnl: float | None = None,
        close_reason: str = "",
        source: str = "bridge",
        trade_day: str | None = None,
    ) -> None:
        """Insert one trade ledger row for the given day/index (idempotent)."""
        trade_day = trade_day or get_session_day_str()
        recorded_at = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO trade_ledger (
                    trade_date, trade_index, result, pnl, close_reason, source, recorded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_date, trade_index) DO UPDATE SET
                    result = excluded.result,
                    pnl = COALESCE(excluded.pnl, trade_ledger.pnl),
                    close_reason = CASE
                        WHEN excluded.close_reason != '' THEN excluded.close_reason
                        ELSE trade_ledger.close_reason
                    END,
                    source = excluded.source,
                    recorded_at = excluded.recorded_at
                """,
                (trade_day, trade_index, result, pnl, close_reason, source, recorded_at),
            )

    def get_trade_ledger(
        self,
        trade_day: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """Return trade ledger rows newest first; optionally restricted to one day."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            if trade_day:
                rows = conn.execute(
                    """
                    SELECT trade_date, trade_index, result, pnl, close_reason, source, recorded_at
                    FROM trade_ledger
                    WHERE trade_date = ?
                    ORDER BY trade_date DESC, trade_index DESC
                    LIMIT ?
                    """,
                    (trade_day, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT trade_date, trade_index, result, pnl, close_reason, source, recorded_at
                    FROM trade_ledger
                    ORDER BY trade_date DESC, trade_index DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def record_violation(
        self,
        rule_code: str,
        message: str,
        severity: str = "warn",
        trade_index: int | None = None,
        trade_day: str | None = None,
        context: dict | None = None,
        event_time: str | None = None,
    ) -> None:
        """Append a rule violation / enforcement event to the audit log."""
        trade_day = trade_day or get_session_day_str()
        event_time = event_time or datetime.now().isoformat()
        context_json = json.dumps(context or {}, ensure_ascii=True)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO violation_log (
                    event_time, trade_date, trade_index, rule_code, severity, message, context_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_time, trade_day, trade_index, rule_code, severity, message, context_json),
            )

    def get_violation_log(
        self,
        trade_day: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """Return violation log rows newest first; optionally restricted to one day."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            if trade_day:
                rows = conn.execute(
                    """
                    SELECT event_time, trade_date, trade_index, rule_code, severity, message, context_json
                    FROM violation_log
                    WHERE trade_date = ?
                    ORDER BY event_time DESC, id DESC
                    LIMIT ?
                    """,
                    (trade_day, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT event_time, trade_date, trade_index, rule_code, severity, message, context_json
                    FROM violation_log
                    ORDER BY event_time DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def upsert_trade_analysis(
        self,
        trade_date: str,
        trade_index: int,
        entry_reason: str = "",
        setup_tags: list[str] | None = None,
        notes: str = "",
        mt5_screenshots: dict | None = None,
        tradingview_screenshots: dict | None = None,
    ) -> None:
        """Insert or update analysis metadata for one trade."""
        now = datetime.now().isoformat()
        setup_tags_json = json.dumps(setup_tags or [], ensure_ascii=True)
        mt5_json = json.dumps(mt5_screenshots or {}, ensure_ascii=True)
        tv_json = json.dumps(tradingview_screenshots or {}, ensure_ascii=True)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO trade_analysis (
                    trade_date, trade_index, entry_reason, setup_tags, notes,
                    mt5_screenshots, tradingview_screenshots, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_date, trade_index) DO UPDATE SET
                    entry_reason = excluded.entry_reason,
                    setup_tags = excluded.setup_tags,
                    notes = excluded.notes,
                    mt5_screenshots = excluded.mt5_screenshots,
                    tradingview_screenshots = excluded.tradingview_screenshots,
                    updated_at = excluded.updated_at
                """,
                (
                    trade_date,
                    trade_index,
                    entry_reason,
                    setup_tags_json,
                    notes,
                    mt5_json,
                    tv_json,
                    now,
                    now,
                ),
            )

    def get_trade_analysis(self, trade_date: str, trade_index: int) -> dict | None:
        """Return analysis metadata for one trade, if available."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT trade_date, trade_index, entry_reason, setup_tags, notes,
                       mt5_screenshots, tradingview_screenshots, created_at, updated_at
                FROM trade_analysis
                WHERE trade_date = ? AND trade_index = ?
                """,
                (trade_date, trade_index),
            ).fetchone()
            if not row:
                return None

            data = dict(row)
            try:
                data["setup_tags"] = json.loads(data.get("setup_tags") or "[]")
            except Exception:
                data["setup_tags"] = []
            try:
                data["mt5_screenshots"] = json.loads(data.get("mt5_screenshots") or "{}")
            except Exception:
                data["mt5_screenshots"] = {}
            try:
                data["tradingview_screenshots"] = json.loads(data.get("tradingview_screenshots") or "{}")
            except Exception:
                data["tradingview_screenshots"] = {}
            return data

    def get_overview_stats(self, days: int = 30) -> dict:
        """Aggregate history stats over the last *days* days."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            daily_rows = conn.execute(
                """
                SELECT date, pnl, trades, result
                FROM daily_results
                ORDER BY date DESC
                LIMIT ?
                """,
                (days,),
            ).fetchall()
            trade_rows = conn.execute(
                """
                SELECT result
                FROM trade_events
                WHERE trade_date >= date('now', ?)
                """,
                (f"-{max(days - 1, 0)} day",),
            ).fetchall()

        wins = sum(1 for r in trade_rows if (r["result"] or "").lower() == "win")
        losses = sum(1 for r in trade_rows if (r["result"] or "").lower() == "loss")
        breakeven = sum(1 for r in trade_rows if (r["result"] or "").lower() in ("be", "flat", "breakeven"))
        unknown = sum(1 for r in trade_rows if (r["result"] or "").lower() not in ("win", "loss", "be", "flat", "breakeven"))
        decided = wins + losses
        win_rate = (wins / decided * 100.0) if decided else 0.0

        total_pnl = sum(float(r["pnl"]) for r in daily_rows) if daily_rows else 0.0
        total_days = len(daily_rows)
        green_days = sum(1 for r in daily_rows if (r["result"] or "") == "green")
        red_days = sum(1 for r in daily_rows if (r["result"] or "") == "red")
        total_trades = sum(int(r["trades"]) for r in daily_rows) if daily_rows else 0

        return {
            "days": days,
            "total_days": total_days,
            "green_days": green_days,
            "red_days": red_days,
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "breakeven": breakeven,
            "unknown": unknown,
            "win_rate": win_rate,
        }
