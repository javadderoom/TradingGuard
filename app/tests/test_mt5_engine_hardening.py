"""
Unit tests for Task 5: MT5 Engine Hardening & English Localization in hitl/mt5_engine.py
"""
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.mt5_engine import MT5Engine

class TestMT5EngineHardening(unittest.TestCase):

    @patch("hitl.account_risk_manager.risk_governor.evaluate_order_feasibility", return_value=(True, "", {}))
    @patch("hitl.mt5_engine.mt5")
    def test_dynamic_filling_mode_and_snapping(self, mock_mt5, mock_risk_gov):
        engine = MT5Engine()
        engine.ensure_connected = MagicMock(return_value=True)
        engine.is_within_session_hours = MagicMock(return_value=(True, ""))

        # Mock symbol_info with filling_mode = 2 (IOC only) and digits = 2
        sym_info = MagicMock()
        sym_info.filling_mode = 2 # IOC
        sym_info.digits = 2
        sym_info.trade_tick_size = 0.05
        sym_info.visible = True
        mock_mt5.symbol_info.return_value = sym_info

        # Mock tick
        tick = MagicMock()
        tick.time = 1700000000
        tick.ask = 2050.00
        tick.bid = 2049.80
        mock_mt5.symbol_info_tick.return_value = tick
        mock_mt5.history_deals_get.return_value = ()
        mock_mt5.order_calc_profit.return_value = 5.0

        # Mock successful order_send
        mock_res = MagicMock()
        mock_res.retcode = mock_mt5.TRADE_RETCODE_DONE
        mock_res.order = 123456
        mock_mt5.order_send.return_value = mock_res

        # Call place_limit_order with unsnapped price
        success, msg, ticket = engine.place_limit_order(
            symbol="XAUUSD",
            order_type_str="BUY_LIMIT",
            price=2040.1234,
            sl=2035.1234,
            tp=2055.1234,
            lot=0.01,
            is_autonomous=True
        )

        self.assertTrue(success, f"Failed with message: {msg}")
        self.assertEqual(ticket, 123456)
        self.assertNotIn("خطا", msg)
        self.assertNotIn("بروکر", msg)

        # Check request sent to order_send
        req = mock_mt5.order_send.call_args[0][0]
        self.assertEqual(req["type_filling"], mock_mt5.ORDER_FILLING_IOC)
        # Price snapped to 0.05 step
        self.assertEqual(req["price"], 2040.10)

    @patch("hitl.mt5_engine.mt5")
    def test_cancel_order_and_modify_position(self, mock_mt5):
        engine = MT5Engine()
        engine.ensure_connected = MagicMock(return_value=True)

        # 1. Test cancel_order success
        mock_res = MagicMock()
        mock_res.retcode = mock_mt5.TRADE_RETCODE_DONE
        mock_mt5.order_send.return_value = mock_res

        ok, msg = engine.cancel_order(999)
        self.assertTrue(ok)
        self.assertIn("cancelled successfully", msg)
        self.assertNotIn("خطا", msg)

        # Test cancel_order failure
        mock_res.retcode = 10004
        mock_res.comment = "Requote"
        ok_fail, msg_fail = engine.cancel_order(999)
        self.assertFalse(ok_fail)
        self.assertIn("Order cancellation failed: Requote", msg_fail)

        # 2. Test modify_position_sltp success
        pos = MagicMock()
        pos.symbol = "XAUUSD"
        mock_mt5.positions_get.return_value = [pos]
        mock_res.retcode = mock_mt5.TRADE_RETCODE_DONE

        ok_mod, msg_mod = engine.modify_position_sltp(888, 2040.0, 2070.0)
        self.assertTrue(ok_mod)
        self.assertIn("SL/TP updated successfully", msg_mod)

if __name__ == "__main__":
    unittest.main()
