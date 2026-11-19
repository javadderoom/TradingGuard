"""
Unit tests for Task 2: Live SMT & M1 Wiring in hitl/screener_gate.py
"""
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import hitl.screener_gate as sg

class TestScreenerGateWiring(unittest.TestCase):

    @patch("hitl.screener_gate.mt5")
    @patch("hitl.screener_gate.MT5Engine")
    def test_fetch_live_bars_fetches_240_m5_and_60_m1(self, mock_engine_cls, mock_mt5):
        mock_engine = MagicMock()
        mock_engine.ensure_connected.return_value = True
        mock_engine.resolve_symbol.return_value = "XAUUSD"
        mock_engine_cls.return_value = mock_engine

        # Mock rates
        dummy_rate = [(1000 + i * 300, 100.0, 101.0, 99.0, 100.5, 10) for i in range(240)]
        dummy_h1 = [(1000 + i * 3600, 100.0, 101.0, 99.0, 100.5, 10) for i in range(80)]
        dummy_m1 = [(1000 + i * 60, 100.0, 101.0, 99.0, 100.5, 10) for i in range(60)]
        dummy_d1 = [(1000 + i * 86400, 100.0, 101.0, 99.0, 100.5, 10) for i in range(10)]

        def copy_rates(sym, tf, pos, count):
            if tf == mock_mt5.TIMEFRAME_M5:
                return dummy_rate[:count]
            elif tf == mock_mt5.TIMEFRAME_H1:
                return dummy_h1[:count]
            elif tf == mock_mt5.TIMEFRAME_M1:
                return dummy_m1[:count]
            elif tf == mock_mt5.TIMEFRAME_D1:
                return dummy_d1[:count]
            return None

        mock_mt5.copy_rates_from_pos.side_effect = copy_rates

        bars = sg.fetch_live_bars("XAUUSD")
        self.assertIsNotNone(bars)
        self.assertIn("bars_5m", bars)
        self.assertIn("bars_1m", bars)
        self.assertEqual(len(bars["bars_5m"]), 240)
        self.assertEqual(len(bars["bars_1m"]), 60)

    @patch("hitl.backtest.fast_screener.screen_ict_session")
    @patch("hitl.screener_gate.fetch_live_bars")
    def test_run_screener_gate_passes_smt_and_m1(self, mock_fetch, mock_screen):
        mock_fetch.return_value = {
            "bars_5m": [{'time': 1000, 'open': 100, 'high': 101, 'low': 99, 'close': 100.5}],
            "bars_1h": [{'time': 1000, 'open': 100, 'high': 101, 'low': 99, 'close': 100.5}],
            "bars_1d": [{'time': 1000, 'open': 100, 'high': 101, 'low': 99, 'close': 100.5}],
            "bars_1m": [{'time': 1000, 'open': 100, 'high': 101, 'low': 99, 'close': 100.5}],
        }
        mock_screen.return_value = {"has_setup": False, "setup_type": "NONE"}

        sg.run_screener_gate("XAUUSD")
        self.assertTrue(mock_screen.called)
        _, kwargs = mock_screen.call_args
        self.assertIn("bars_1m", kwargs)
        self.assertEqual(len(kwargs["bars_1m"]), 1)
        self.assertIn("smt_info", kwargs)

if __name__ == "__main__":
    unittest.main()
