"""
TradingGuard — Daily Results Database
SQLite-backed storage for daily P&L and session history.
"""

import sqlite3
from datetime import date, timedelta
from app.config import DB_PATH


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
        day = day or date.today().isoformat()
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
        today = date.today().isoformat()
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM daily_results WHERE date = ?", (today,)
            ).fetchone()
            return dict(row) if row else None

    def clear_today(self) -> None:
        """Delete today's row, if any.

        Intended for development/testing to reset the daily lock.
        """
        today = date.today().isoformat()
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM daily_results WHERE date = ?", (today,)
            )
