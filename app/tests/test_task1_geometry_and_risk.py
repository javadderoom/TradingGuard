"""
Test suite for Task 1: Unify Screener Setup Geometry & Multi-Asset Risk Math
"""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.tools.smc_tools import validate_order_ticket, build_validated_order_plan, get_smc_landmarks
from hitl.mt5_engine import MT5Engine

class TestTask1GeometryAndRisk(unittest.TestCase):

    def test_nq_risk_calculation_not_rejected_by_cap(self):
        """NQ with 30 pt stop should NOT calculate as $30 risk on 0.01 lot and get rejected."""
        val = validate_order_ticket(
            order_type="BUY_LIMIT",
            current_bid=21010.0,
            current_ask=21011.0,
            entry=21000.0,
            sl=20970.0,  # 30 pts stop
            tp=21090.0,  # 90 pts tp (3.0 RR)
            pip_size=0.1,
            symbol="NQ",
            lot=0.01,
            max_risk_usd=12.0,
            min_rr=2.5
        )
        self.assertTrue(val["is_valid"], f"Validation failed: {val.get('reason')}")
        self.assertLessEqual(val["risk_usd"], 12.0)
        # On LiteFinance 0.01 lot NQ 30 pts is ~$0.30 to $6.00 (not $30.00)
        self.assertLessEqual(val["risk_usd"], 1.0)

    def test_build_validated_order_plan_preserves_screener_geometry(self):
        """build_validated_order_plan must preserve exact screener entry, sl, target_rr and archetype_id."""
        landmarks = {
            "symbol": "XAUUSD_o",
            "current_bid": 3945.00,
            "current_ask": 3945.22,
            "pip_size": 0.01,
            "broker_time": type("TimeObj", (), {"strftime": lambda s, fmt: "2026.11.18 14:30"})()
        }
        
        # Test ARCH-015 Gold NY Trend Continuation (target 2.5R, explicit entry/SL)
        entry_ref = 3950.00
        sl_ref = 3958.00  # Sell limit with 8.00 risk
        plan, reason = build_validated_order_plan(
            decision="SELL_LIMIT",
            poi_selection="PROXIMAL_EDGE",
            landmarks=landmarks,
            macro_filter="",
            entry_ref=entry_ref,
            sl_ref=sl_ref,
            recommended_target_rr=2.5,
            archetype_id="SETUP-ARCH-015"
        )
        self.assertIsNotNone(plan, f"Plan should not be None: {reason}")
        self.assertEqual(plan["entry"], 3950.00)
        self.assertEqual(plan["sl"], 3958.00)
        expected_tp = round(3950.00 - (8.00 * 2.5), 2)
        self.assertEqual(plan["tp"], expected_tp)
        self.assertEqual(plan["rr"], 2.5)
        self.assertEqual(plan.get("archetype_id"), "SETUP-ARCH-015")

    def test_build_validated_order_plan_respects_arch001_min_rr(self):
        """ARCH-001 has 2.0 RR target, validate_order_ticket should not reject RR < 3.0 when min_rr=2.0."""
        landmarks = {
            "symbol": "XAUUSD_o",
            "current_bid": 3955.00,
            "current_ask": 3955.22,
            "pip_size": 0.01,
            "broker_time": type("TimeObj", (), {"strftime": lambda s, fmt: "2026.11.18 14:30"})()
        }
        entry_ref = 3960.00
        sl_ref = 3965.00  # 5.0 risk
        plan, reason = build_validated_order_plan(
            decision="SELL_LIMIT",
            poi_selection="PROXIMAL_EDGE",
            landmarks=landmarks,
            macro_filter="",
            entry_ref=entry_ref,
            sl_ref=sl_ref,
            recommended_target_rr=2.0,
            archetype_id="SETUP-ARCH-001"
        )
        self.assertIsNotNone(plan, f"Plan should not be None: {reason}")
        self.assertEqual(plan["rr"], 2.0)
        self.assertEqual(plan["tp"], 3950.00)

if __name__ == "__main__":
    unittest.main()
