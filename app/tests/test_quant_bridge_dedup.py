"""
Unit tests for Task 3: Quant Rule Orthogonalization in hitl/quant_engine/live_quant_bridge.py
"""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.quant_engine.live_quant_bridge import LiveQuantBridge
from hitl.mt5_engine import MT5Engine

class TestQuantBridgeDedup(unittest.TestCase):

    def test_quant_rules_are_orthogonal_and_deduplicated(self):
        bridge = LiveQuantBridge(MT5Engine(), None)
        nq_rules = [r.rule_id for r in bridge.rules_by_symbol.get("NQ", [])]
        xau_rules = [r.rule_id for r in bridge.rules_by_symbol.get("XAUUSD", [])]

        # NQ must NOT include duplicate clone R14_009
        self.assertNotIn("R14_009", nq_rules, "Clone rule R14_009 must be removed from NQ portfolio")
        self.assertIn("R14_011", nq_rules)
        self.assertIn("R14_025", nq_rules)

        # Gold must NOT include duplicate kurtosis rule R11_022
        self.assertNotIn("R11_022", xau_rules, "Duplicate kurtosis rule R11_022 must be removed from Gold portfolio")
        self.assertIn("R15_048", xau_rules)
        self.assertIn("R14_058", xau_rules)
        self.assertIn("R15_023", xau_rules)

if __name__ == "__main__":
    unittest.main()
