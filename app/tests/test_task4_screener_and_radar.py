"""
Test suite for Task 4: Fix Screener Core, Live Radar Pre-Filter & Dynamic Session Clock
"""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.fast_screener import detect_breaker_and_mss, detect_fvg_5m

class TestTask4ScreenerAndRadar(unittest.TestCase):

    def test_detect_breaker_and_mss_pivot_order_bearish(self):
        """Bearish MSS requires swing low BEFORE sweep high, followed by break below swing low."""
        prefix = [{'open': 102.0, 'high': 103.0, 'low': 101.5, 'close': 102.0}] * 10
        bars = prefix + [
            {'open': 102.0, 'high': 103.0, 'low': 101.5, 'close': 102.0},
            {'open': 102.0, 'high': 103.0, 'low': 102.0, 'close': 102.5},
            {'open': 102.5, 'high': 103.0, 'low': 100.0, 'close': 101.0}, # Swing Low at 100.0 (idx 12)
            {'open': 101.0, 'high': 104.0, 'low': 101.0, 'close': 103.5},
            {'open': 103.5, 'high': 106.0, 'low': 103.0, 'close': 105.0},
            {'open': 105.0, 'high': 110.0, 'low': 104.5, 'close': 108.0}, # Sweep High at 110.0 (idx 15)
            {'open': 108.0, 'high': 108.5, 'low': 105.0, 'close': 105.5},
            {'open': 105.5, 'high': 106.0, 'low': 101.0, 'close': 101.5},
            {'open': 101.5, 'high': 102.0, 'low': 97.5, 'close': 98.0},   # Break below 100.0 (idx 18)
        ]
        has_b, b_type, b_price = detect_breaker_and_mss(bars, lookback=20, symbol="XAUUSD")
        self.assertTrue(has_b, "Should detect Bearish Breaker / MSS")
        self.assertEqual(b_type, "BEARISH_BREAKER")

    def test_detect_breaker_and_mss_pivot_order_bullish(self):
        """Bullish MSS requires swing high BEFORE sweep low, followed by break above swing high."""
        prefix = [{'open': 102.0, 'high': 103.0, 'low': 101.5, 'close': 102.0}] * 10
        bars = prefix + [
            {'open': 102.0, 'high': 103.0, 'low': 101.5, 'close': 102.0},
            {'open': 102.0, 'high': 103.0, 'low': 102.0, 'close': 102.5},
            {'open': 102.5, 'high': 110.0, 'low': 102.0, 'close': 109.0}, # Swing High at 110.0 (idx 12)
            {'open': 109.0, 'high': 109.5, 'low': 105.0, 'close': 106.0},
            {'open': 106.0, 'high': 106.5, 'low': 103.0, 'close': 104.0},
            {'open': 104.0, 'high': 104.5, 'low': 98.0, 'close': 99.0},   # Sweep Low at 98.0 (idx 15)
            {'open': 99.0, 'high': 103.0, 'low': 99.0, 'close': 102.5},
            {'open': 102.5, 'high': 108.0, 'low': 102.0, 'close': 107.5},
            {'open': 107.5, 'high': 112.0, 'low': 107.0, 'close': 111.5}, # Break above 110.0 (idx 18)
        ]
        has_b, b_type, b_price = detect_breaker_and_mss(bars, lookback=20, symbol="XAUUSD")
        self.assertTrue(has_b, "Should detect Bullish Breaker / MSS")
        self.assertEqual(b_type, "BULLISH_BREAKER")

    def test_detect_breaker_and_mss_rejects_continuation_downtrend(self):
        """Downtrend continuation (High at idx 2, Low at idx 5, break below at idx 8) is NOT a high-sweep reversal."""
        prefix = [{'open': 102.0, 'high': 103.0, 'low': 101.5, 'close': 102.0}] * 10
        bars = prefix + [
            {'open': 105.0, 'high': 106.0, 'low': 104.5, 'close': 105.0},
            {'open': 105.0, 'high': 107.0, 'low': 104.5, 'close': 106.5},
            {'open': 106.5, 'high': 110.0, 'low': 106.0, 'close': 108.0}, # High at 110.0
            {'open': 108.0, 'high': 108.5, 'low': 103.0, 'close': 104.0},
            {'open': 104.0, 'high': 105.0, 'low': 102.0, 'close': 103.0},
            {'open': 103.0, 'high': 103.5, 'low': 100.0, 'close': 101.0}, # Low at 100.0
            {'open': 101.0, 'high': 102.0, 'low': 100.5, 'close': 101.5},
            {'open': 101.5, 'high': 102.0, 'low': 99.0, 'close': 99.5},
            {'open': 99.5, 'high': 100.0, 'low': 97.0, 'close': 97.5},    # Continuation drop below 100.0
        ]
        has_b, b_type, b_price = detect_breaker_and_mss(bars, lookback=20, symbol="XAUUSD")
        self.assertFalse(has_b, "Continuation breakdown should NOT be classified as Bearish Breaker reversal")

    def test_detect_fvg_5m_rejects_mitigated_gap(self):
        """detect_fvg_5m should ignore FVGs that have been filled/mitigated by subsequent price action."""
        bars_fvg = [
            {'open': 98.0, 'high': 100.0, 'low': 97.0, 'close': 99.0},     # c1: high 100.0
            {'open': 100.0, 'high': 104.0, 'low': 100.0, 'close': 103.5},  # c2: big up
            {'open': 103.5, 'high': 105.0, 'low': 102.0, 'close': 104.5},  # c3: low 102.0 (bullish FVG: 100.0 - 102.0)
            {'open': 104.5, 'high': 105.0, 'low': 99.0, 'close': 103.0},   # dips to 99.0 (mitigating gap), closes 103.0 (high=105.0)
            {'open': 103.0, 'high': 104.0, 'low': 102.5, 'close': 103.5},  # no bearish gap (c1 low=102.0 <= c3 high=104.0)
        ]
        has_fvg, fvg_dir, top, bot = detect_fvg_5m(bars_fvg, lookback=5, symbol="XAUUSD")
        self.assertFalse(has_fvg, "Mitigated FVG should not be returned as active POI")

    def test_detect_fvg_5m_accepts_unmitigated_gap(self):
        """detect_fvg_5m accepts valid unmitigated FVG."""
        bars_fvg = [
            {'open': 98.0, 'high': 100.0, 'low': 97.0, 'close': 99.0},     # c1: high 100.0
            {'open': 100.0, 'high': 104.0, 'low': 100.0, 'close': 103.5},  # c2: big up
            {'open': 103.5, 'high': 105.0, 'low': 102.0, 'close': 104.5},  # c3: low 102.0 (bullish FVG: 100.0 - 102.0)
            {'open': 104.5, 'high': 105.0, 'low': 103.0, 'close': 104.0},   # low stays above gap
        ]
        has_fvg, fvg_dir, top, bot = detect_fvg_5m(bars_fvg, lookback=5, symbol="XAUUSD")
        self.assertTrue(has_fvg, "Unmitigated FVG should be accepted")
        self.assertEqual(fvg_dir, "BULLISH")
        self.assertEqual(top, 102.0)
        self.assertEqual(bot, 100.0)

if __name__ == "__main__":
    unittest.main()
