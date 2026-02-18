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
