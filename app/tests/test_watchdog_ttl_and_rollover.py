"""
Unit tests for Task 4: Watchdog TTL Auto-Cancellation & Broker Rollover Blackout in hitl/watchdog.py
"""
import sys
import unittest
import datetime
from unittest.mock import patch, MagicMock
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.watchdog import MarketWatchdog, is_rollover_blackout

class TestWatchdogTTLAndRollover(unittest.TestCase):

    def test_is_rollover_blackout(self):
        # 23:56 broker time should be blackout
        dt_2356 = datetime.datetime(2026, 11, 18, 23, 56, 0)
        self.assertTrue(is_rollover_blackout(dt_2356))

        # 00:05 broker time should be blackout
        dt_0005 = datetime.datetime(2026, 11, 19, 0, 5, 0)
        self.assertTrue(is_rollover_blackout(dt_0005))

        # 14:30 broker time should NOT be blackout
        dt_1430 = datetime.datetime(2026, 11, 18, 14, 30, 0)
        self.assertFalse(is_rollover_blackout(dt_1430))

    @patch("hitl.watchdog.mt5")
    @patch("hitl.watchdog.get_order_metadata")
    def test_auto_ttl_cancellation(self, mock_get_meta, mock_mt5):
        mock_engine = MagicMock()
        mock_engine.ensure_connected.return_value = True
        mock_engine.is_within_session_hours.return_value = (False, "")
        mock_engine.cancel_order.return_value = (True, "Order cancelled")

        mock_client = MagicMock()
        watchdog = MarketWatchdog(mock_engine, mock_client)

        # Mock an order that is 80 minutes old (TTL = 75)
        mock_order = MagicMock()
        mock_order.ticket = 999111
        mock_order.symbol = "XAUUSD"
        mock_order.time_setup = 1000.0

        mock_mt5.orders_get.return_value = [mock_order]
        mock_mt5.positions_get.return_value = []
        mock_mt5.symbol_info.return_value = MagicMock(spread=25)

        mock_get_meta.return_value = {"ttl_minutes": 75.0, "archetype_id": "SETUP-ARCH-001"}

        with patch("hitl.watchdog.time.time", return_value=1000.0 + (80 * 60)):
            with patch.object(watchdog, "check_momentum_and_spread", return_value=(False, "")):
                with patch("hitl.watchdog.is_rollover_blackout", return_value=False):
                    with patch("hitl.account_risk_manager.risk_governor.sync_state", return_value={"circuit_breaker_active": False}):
                        watchdog.poll()

        mock_engine.cancel_order.assert_called_with(999111)
        self.assertTrue(mock_client.send_message.called)

if __name__ == "__main__":
    unittest.main()
