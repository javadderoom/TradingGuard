"""Tests for the DailyDatabase (SQLite daily results tracker)."""

import os
import tempfile
import pytest
from app.database import DailyDatabase


@pytest.fixture
def db(tmp_path):
    """Create a database with a temp file."""
    path = str(tmp_path / "test.db")
    return DailyDatabase(db_path=path)


class TestDailyDatabase:
    def test_record_and_retrieve(self, db):
        db.record_day(pnl=15.0, trades=2, day="2026-02-18")
        rows = db.get_last_n_days(1)
        assert len(rows) == 1
        assert rows[0]["date"] == "2026-02-18"
        assert rows[0]["pnl"] == 15.0
        assert rows[0]["trades"] == 2
        assert rows[0]["result"] == "green"

    def test_negative_pnl_is_red(self, db):
        db.record_day(pnl=-10.0, trades=3, day="2026-02-17")
        rows = db.get_last_n_days(1)
        assert rows[0]["result"] == "red"

    def test_zero_pnl_is_flat(self, db):
        db.record_day(pnl=0.0, trades=1, day="2026-02-16")
        rows = db.get_last_n_days(1)
        assert rows[0]["result"] == "flat"

    def test_upsert_updates_existing(self, db):
        db.record_day(pnl=5.0, trades=1, day="2026-02-18")
        db.record_day(pnl=-3.0, trades=2, day="2026-02-18")
        rows = db.get_last_n_days(5)
        assert len(rows) == 1
        assert rows[0]["pnl"] == -3.0
        assert rows[0]["result"] == "red"

    def test_is_recovery_day_false_with_no_data(self, db):
        assert db.is_recovery_day() is False

    def test_is_recovery_day_false_with_one_red(self, db):
        db.record_day(pnl=-5.0, trades=2, day="2026-02-17")
        assert db.is_recovery_day() is False

    def test_is_recovery_day_true_with_two_reds(self, db):
        db.record_day(pnl=-5.0, trades=2, day="2026-02-17")
        db.record_day(pnl=-8.0, trades=3, day="2026-02-18")
        assert db.is_recovery_day() is True

    def test_is_recovery_day_false_with_green_then_red(self, db):
        db.record_day(pnl=10.0, trades=2, day="2026-02-17")
        db.record_day(pnl=-5.0, trades=1, day="2026-02-18")
        assert db.is_recovery_day() is False

    def test_get_last_n_days_ordering(self, db):
        db.record_day(pnl=1.0, trades=1, day="2026-02-15")
        db.record_day(pnl=2.0, trades=1, day="2026-02-16")
        db.record_day(pnl=3.0, trades=1, day="2026-02-17")
        rows = db.get_last_n_days(2)
        assert len(rows) == 2
        assert rows[0]["date"] == "2026-02-17"  # most recent first
        assert rows[1]["date"] == "2026-02-16"

    def test_get_today_returns_none_when_empty(self, db):
        assert db.get_today() is None

    def test_trade_ledger_upsert_and_fetch(self, db):
        db.record_trade_ledger(
            trade_index=1,
            result="win",
            pnl=5.5,
            close_reason="session_update",
            source="bridge",
            trade_day="2026-02-19",
        )
        db.record_trade_ledger(
            trade_index=1,
            result="win",
            pnl=6.0,
            close_reason="manual_adjust",
            source="bridge",
            trade_day="2026-02-19",
        )

        rows = db.get_trade_ledger(trade_day="2026-02-19", limit=10)
        assert len(rows) == 1
        assert rows[0]["trade_index"] == 1
        assert rows[0]["result"] == "win"
        assert rows[0]["pnl"] == 6.0
        assert rows[0]["close_reason"] == "manual_adjust"

    def test_violation_log_insert_and_fetch(self, db):
        db.record_violation(
            rule_code="TEST_RULE",
            severity="warn",
            message="Test violation message",
            trade_index=2,
            trade_day="2026-02-19",
            context={"foo": "bar"},
            event_time="2026-02-19T10:00:00",
        )

        rows = db.get_violation_log(trade_day="2026-02-19", limit=10)
        assert len(rows) == 1
        assert rows[0]["rule_code"] == "TEST_RULE"
        assert rows[0]["severity"] == "warn"
        assert rows[0]["trade_index"] == 2
        assert rows[0]["message"] == "Test violation message"
