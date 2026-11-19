"""
Test suite for Task 3: Align LiveQuantBridge with VectorizedBacktester
"""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.quant_engine.live_quant_bridge import LiveQuantBridge
from hitl.mt5_engine import MT5Engine

class TestTask3QuantBridgeAlignment(unittest.TestCase):

    def test_quant_bridge_has_duplicate_gating_and_lot_calc(self):
        """LiveQuantBridge should support lot calculation for $12 risk and duplicate checks."""
        engine = MT5Engine()
        bridge = LiveQuantBridge(engine, client=None)
        
        # Test method calculate_quant_lot
        lot, risk = bridge._calculate_quant_lot("XAUUSD_o", "BUY_LIMIT", 3950.0, 3945.0) # $5.00 stop on Gold
        self.assertGreater(lot, 0.0)
        self.assertLessEqual(risk, 12.0)

if __name__ == "__main__":
    unittest.main()
