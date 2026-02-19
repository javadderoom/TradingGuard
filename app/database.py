"""
TradingGuard — Daily Results Database
SQLite-backed storage for daily P&L and session history.
"""

import sqlite3
from datetime import date, datetime
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
            conn.execute(
                "DELETE FROM trade_events WHERE trade_date = ?", (today,)
            )

    def record_trade_event(
        self,
        trade_index: int,
        result: str = "unknown",
        pnl: float | None = None,
        trade_day: str | None = None,
    ) -> None:
        """Insert one trade event for the given day/index (idempotent)."""
        trade_day = trade_day or date.today().isoformat()
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
        trade_day = trade_day or date.today().isoformat()
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
