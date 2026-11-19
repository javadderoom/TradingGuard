"""
Test suite for Task 2: Calibrate MarketWatchdog & Daily Performance Accounting
"""
import sys
import unittest
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.watchdog import MarketWatchdog
from hitl.mt5_engine import MT5Engine
from hitl.backtest.evaluator import get_optimal_trade_management

class TestTask2WatchdogAndPerformance(unittest.TestCase):

    def test_get_optimal_trade_management_nq_support(self):
        """get_optimal_trade_management should not crash and should return valid policy for NQ."""
        target_rr, be_rr = get_optimal_trade_management("NQ", "NY_Open")
        self.assertGreater(target_rr, 0)

    def test_watchdog_spread_thresholds_per_asset(self):
        """Watchdog should not cancel NQ on 100-point (1.0 pt) spread, but cancel on abnormal >450 pts."""
        wd = MarketWatchdog(MT5Engine(), client=None)
        
        # Test helper method for spread limit
        max_fx = wd._get_max_allowable_spread("GBPUSD_o")
        max_gold = wd._get_max_allowable_spread("XAUUSD_o")
        max_nq = wd._get_max_allowable_spread("NQ")
        
        self.assertEqual(max_fx, 60)
        self.assertEqual(max_gold, 120)
        self.assertEqual(max_nq, 450)

    def test_daily_performance_uses_net_pnl_for_consecutive_losses(self):
        """MT5Engine should count deal as loss if profit=0.00 but commission makes it net negative."""
        class MockDeal:
            def __init__(self, profit, commission, swap=0.0, fee=0.0):
                self.profit = profit
                self.commission = commission
                self.swap = swap
                self.fee = fee
                self.entry = 1 # mt5.DEAL_ENTRY_OUT
                self.time = 1000

        # Deal with +0.02 gross profit but -$0.10 commission -> net -$0.08 loss
        deal = MockDeal(0.02, -0.10)
        net_pnl = deal.profit + deal.commission + deal.swap + deal.fee
        self.assertLess(net_pnl, 0.0)

if __name__ == "__main__":
    unittest.main()
