"""Tests for the SessionBridge (session.json read/write)."""

import json
import os
import tempfile
import pytest
from app.bridge import SessionBridge


@pytest.fixture
def bridge(tmp_path):
    """Create a bridge pointing at a temp file."""
    path = str(tmp_path / "test_session.json")
    return SessionBridge(path=path)


class TestSessionBridge:
    def test_reset_creates_file(self, bridge):
        data = bridge.reset()
        assert os.path.exists(bridge.path)
        assert data["version"] == 1
        assert data["session_active"] is False
        assert data["trading_allowed"] is False

    def test_read_returns_defaults_when_missing(self, bridge):
        data = bridge.read()
        assert data["bias"] == "neutral"
        assert data["trades_today"] == 0
        assert data["last_trade_pnl"] == 0.0

    def test_write_and_read_roundtrip(self, bridge):
        bridge.reset()
        bridge.update(bias="bullish", invalidation_price=2050.5)
        data = bridge.read()
        assert data["bias"] == "bullish"
        assert data["invalidation_price"] == 2050.5

    def test_update_merges_fields(self, bridge):
        bridge.reset()
        bridge.update(trades_today=2, consecutive_losses=1)
        data = bridge.read()
        assert data["trades_today"] == 2
        assert data["consecutive_losses"] == 1
        # Other fields unchanged
        assert data["bias"] == "neutral"

    def test_update_adds_timestamp(self, bridge):
        bridge.reset()
        data = bridge.update(news_lock=True)
        assert "timestamp" in data
        assert data["timestamp"] != ""

    def test_reset_clears_state(self, bridge):
        bridge.update(
            session_active=True,
            trading_allowed=True,
            trades_today=3,
            daily_loss_usd=20.0,
        )
        data = bridge.reset()
        assert data["session_active"] is False
        assert data["trades_today"] == 0
        assert data["daily_loss_usd"] == 0.0
