"""
Unit tests for Strict Counter-HTF Veto in fast_screener.py and screener_gate.py.
Verifies that fading limit orders trading counter to 1H Market Structure Shift (HTF_RETRACEMENT)
are strictly vetoed at both the root screener and gate levels.
"""
import unittest
from unittest.mock import patch, MagicMock

from hitl.backtest.fast_screener import screen_ict_session
import hitl.screener_gate as sg


class TestCounterHTFVeto(unittest.TestCase):

    def test_fast_screener_vetoes_short_when_h1_is_bullish_mss(self):
        """When 1H has shifted bullish (BULLISH_MSS), a micro-sweep short must be vetoed."""
        # Create M5 bars with a high sweep
        bars_5m = []
        for i in range(40):
            bars_5m.append({
                "open": 1.3140, "high": 1.3145, "low": 1.3138, "close": 1.3142,
                "time": 1000 + i * 300
            })
        # Last bar pierces Asian high to 1.31606
        bars_5m[-2]["high"] = 1.31606
        bars_5m[-1]["close"] = 1.31471

        # Create 1H bars with a clear BULLISH_MSS (e.g., breaking higher swing high)
        bars_1h = []
        for i in range(25):
            c = 1.3120 + (i * 0.0002)
            bars_1h.append({
                "open": c - 0.0001, "high": c + 0.0003, "low": c - 0.0002, "close": c,
                "time": 1000 + i * 3600
            })
        # Establish swing high at bar 10, then break it with displacement at bar 20
        bars_1h[10]["high"] = 1.3150
        for i in range(20, 25):
            bars_1h[i]["close"] = 1.3158
            bars_1h[i]["high"] = 1.3160

        res = screen_ict_session(
            bars_5m=bars_5m,
            bars_1h=bars_1h,
            symbol="GBPUSD",
            session_hour=14,  # London
            closed_bars_only=True
        )

        # If a setup was found, it must NOT be a counter-HTF short
        if res.get("setup_type") == "COUNTER_HTF_VETO":
            self.assertFalse(res.get("has_setup"))
            self.assertIn("counter to 1H", res.get("reason", ""))
        else:
            # If no setup at all or vetoed
            self.assertFalse(
                res.get("has_setup") and "BEARISH" in res.get("setup_type", "") and res.get("phase") == "HTF_RETRACEMENT",
                "Cannot return an active BEARISH setup during HTF_RETRACEMENT counter to BULLISH_MSS"
            )

    def test_screener_gate_defense_in_depth_counter_htf(self):
        """run_screener_gate must intercept and veto any candidate setup where phase is HTF_RETRACEMENT."""
        with patch("hitl.screener_gate.fetch_live_bars") as mock_fetch, \
             patch("hitl.backtest.fast_screener.screen_ict_session") as mock_screen:

            mock_fetch.return_value = {
                "bars_5m": [{"time": 1000, "open": 100, "high": 101, "low": 99, "close": 100.5}],
                "bars_1h": [{"time": 1000, "open": 100, "high": 101, "low": 99, "close": 100.5}],
                "bars_1d": None,
                "bars_1m": None,
            }

            # Simulate screener trying to return a counter-HTF short setup
            mock_screen.return_value = {
                "has_setup": True,
                "archetype_id": "SETUP-ARCH-010",
                "setup_type": "BEARISH_PROMINENT_SWEEP_MSS",
                "phase": "HTF_RETRACEMENT",
                "mtf_info": {"h1_state": "BULLISH_MSS"},
                "entry_ref": 1.31536,
                "sl_ref": 1.31616,
                "signal_bar_time": 1795087200,
            }

            gate_res = sg.run_screener_gate("GBPUSD")

            self.assertFalse(gate_res["has_setup"], "Gate must veto counter-HTF setup")
            self.assertEqual(gate_res["setup_type"], "COUNTER_HTF_VETO")
            self.assertIn("Counter-HTF phase conflict", gate_res["reason"])


if __name__ == "__main__":
    unittest.main()
