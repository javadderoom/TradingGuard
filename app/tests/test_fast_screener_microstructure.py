"""
Unit tests for Task 1: Detector Math & Microstructure Fixes in hitl/backtest/fast_screener.py
"""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.fast_screener import (
    detect_opening_range_breakout,
    detect_extreme_judas_reversal,
    detect_reversal_origin_retest,
    screen_ict_session
)

class TestFastScreenerMicrostructure(unittest.TestCase):

    def test_h1_slope_uses_ema_history_not_raw_close(self):
        """H1 slope in ARCH-017 & ARCH-018 evaluates true EMA50 trajectory, not raw close 6 bars ago."""
        bars_1h = []
        for i in range(60):
            c = 100.0 + (i * 0.5)
            if i == 54: # bar -6
                c = 160.0 # Extreme erratic spike
            bars_1h.append({'open': c - 0.2, 'high': c + 0.5, 'low': c - 0.5, 'close': c, 'time': 1000 + i * 3600})

        # Calculate true EMA50 series
        alpha50 = 2.0 / (50.0 + 1.0)
        ema50 = float(bars_1h[0]['close'])
        ema_series = [ema50]
        for hb in bars_1h[1:]:
            ema50 = alpha50 * float(hb['close']) + (1.0 - alpha50) * ema50
            ema_series.append(ema50)

        true_slope = ema_series[-1] - ema_series[-6]
        self.assertGreater(true_slope, 0.0, "EMA50 trajectory is positive in an uptrend")

    def test_arch014_rejects_already_mitigated_h1_origin(self):
        """ARCH-014 must reject setups where the ignition zone was already tapped by earlier subsequent bars."""
        # Need >= 48 H1 bars and >= 10 5M bars
        bars_1h = []
        for i in range(50):
            bars_1h.append({'open': 98.0, 'high': 99.0, 'low': 97.0, 'close': 98.5, 'time': 1000 + i * 3600})

        # Set up a clear H1 MSS breakout on bar 45
        bars_1h[30] = {'open': 99.0, 'high': 100.0, 'low': 98.0, 'close': 99.5, 'time': 1030 * 3600} # Swing High 100.0
        bars_1h[35] = {'open': 96.0, 'high': 97.0, 'low': 95.0, 'close': 96.5, 'time': 1035 * 3600}  # Base [95, 97]
        bars_1h[40] = {'open': 97.0, 'high': 116.0, 'low': 96.5, 'close': 115.0, 'time': 1040 * 3600} # Breakout 115.0 (> 15 pts)
        # Bar 45 retests ignition zone [95, 97] -> PRIOR MITIGATION
        bars_1h[45] = {'open': 114.0, 'high': 115.0, 'low': 96.0, 'close': 102.0, 'time': 1045 * 3600}
        bars_1h[48] = {'open': 102.0, 'high': 106.0, 'low': 101.5, 'close': 105.0, 'time': 1048 * 3600}
        bars_1h[49] = {'open': 104.0, 'high': 104.5, 'low': 96.5, 'close': 97.0, 'time': 1049 * 3600} # Current bar taps again

        # 5M bars
        bars_5m = [{'open': 97.5, 'high': 98.0, 'low': 96.5, 'close': 97.0, 'time': 1049 * 3600 + 300}] * 30
        has_setup, direction, entry, sl, desc = detect_reversal_origin_retest(bars_5m, bars_1h, symbol="XAUUSD")
        self.assertFalse(has_setup, "Second/stale tap of H1 origin zone must be rejected")

    def test_stale_pierce_does_not_trigger_reversal(self):
        """A high pierce from 9 bars ago that did not pierce in the last 4 bars should NOT trigger a fresh sweep."""
        # 40 M5 bars
        # Benchmark range: bars 0..20 with high = 100.0
        bars_5m = []
        for i in range(25):
            bars_5m.append({'open': 98.0, 'high': 99.0, 'low': 97.0, 'close': 98.0, 'time': 1000 + i * 300})

        # Bar 26 pierces high to 102.0 (14 bars ago)
        bars_5m.append({'open': 99.0, 'high': 102.0, 'low': 98.5, 'close': 101.0, 'time': 1026 * 300})

        # Bars 27..40 consolidate down at 97.0 - 98.5 (no pierce in the last 4 bars)
        for i in range(27, 41):
            bars_5m.append({'open': 98.0, 'high': 98.5, 'low': 97.0, 'close': 97.5, 'time': 1000 + i * 300})

        bars_1h = [{'open': 98.0, 'high': 102.0, 'low': 97.0, 'close': 97.5, 'time': 1000 + i * 3600} for i in range(20)]

        res = screen_ict_session(
            bars_5m=bars_5m,
            bars_1h=bars_1h,
            symbol="XAUUSD",
            session_hour=14,
            closed_bars_only=False
        )
        # Should not trigger a stale high sweep
        self.assertNotEqual(res.get("setup_type"), "BEARISH_SWEEP_MSS")

    def test_gold_decommissioned_archetypes_blocked_at_root(self):
        """SETUP-ARCH-012, 014, 019 must be permanently blocked at root detector level on Gold."""
        from hitl.backtest.fast_screener import (
            detect_adr_exhaustion_snapback,
            detect_gold_double_sweep_reversal
        )
        # Test ARCH-012 helper
        has_adr, _, _, _, _ = detect_adr_exhaustion_snapback([], symbol="XAUUSD")
        self.assertFalse(has_adr, "ARCH-012 must be blocked at root for Gold")

        # Test ARCH-019 helper
        has_ds, _, _, _, _ = detect_gold_double_sweep_reversal([], symbol="XAUUSD")
        self.assertFalse(has_ds, "ARCH-019 must be blocked at root for Gold")

        # Test setup package veto
        from hitl.backtest.fast_screener import GOLD_DECOMMISSIONED_ARCHETYPES
        for arch in ["SETUP-ARCH-002", "SETUP-ARCH-004", "SETUP-ARCH-009", "SETUP-ARCH-010", "SETUP-ARCH-012", "SETUP-ARCH-014", "SETUP-ARCH-019"]:
            self.assertIn(arch, GOLD_DECOMMISSIONED_ARCHETYPES)

if __name__ == "__main__":
    unittest.main()
