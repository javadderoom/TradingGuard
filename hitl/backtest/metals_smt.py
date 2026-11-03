"""
TradingGuard HITL - Precious Metals Intermarket SMT Divergence Engine
Analyzes relative high/low structural non-confirmation between Gold (XAUUSD) and Silver (XAGUSD):
- Bullish SMT: One metal sweeps the session Low, while the other metal holds a Higher Low.
  (Signals aggressive institutional accumulation and impending explosive rally).
- Bearish SMT: One metal sweeps the session High, while the other metal holds a Lower High.
  (Signals aggressive institutional distribution and impending sharp dump).
- Correlated Sweep: Both metals sweep simultaneously (Standard expansion).
- Correlated Hold: Neither metal sweeps (Consolidation).
"""

from typing import Dict, Any, List, Optional
import MetaTrader5 as mt5


def detect_metals_smt_divergence(
    rates_5m_gold: List[Dict[str, Any]],
    rates_5m_silver: List[Dict[str, Any]],
    session_hour: int
) -> Dict[str, Any]:
    """
    Computes real-time or historical SMT divergence between Gold and Silver.
    """
    if len(rates_5m_gold) < 40 or len(rates_5m_silver) < 40:
        return {
            "has_smt": False,
            "smt_type": "NONE",
            "summary": "Insufficient data for SMT calculation"
        }

    # 1. Determine prior session benchmark window
    if session_hour in (9, 10, 11):
        window_g = rates_5m_gold[-84:-10] if len(rates_5m_gold) >= 84 else rates_5m_gold[:-10]
        window_s = rates_5m_silver[-84:-10] if len(rates_5m_silver) >= 84 else rates_5m_silver[:-10]
        label = "Asian Range"
    elif session_hour in (14, 15, 16):
        window_g = rates_5m_gold[-72:-10] if len(rates_5m_gold) >= 72 else rates_5m_gold[:-10]
        window_s = rates_5m_silver[-72:-10] if len(rates_5m_silver) >= 72 else rates_5m_silver[:-10]
        label = "London Range"
    else:
        window_g = rates_5m_gold[-36:-6] if len(rates_5m_gold) >= 36 else rates_5m_gold[:-6]
        window_s = rates_5m_silver[-36:-6] if len(rates_5m_silver) >= 36 else rates_5m_silver[:-6]
        label = "NY AM Range"

    if not (window_g and window_s):
        return {"has_smt": False, "smt_type": "NONE", "summary": "No session window data"}

    # Benchmarks
    high_g = max(b['high'] for b in window_g)
    low_g = min(b['low'] for b in window_g)

    high_s = max(b['high'] for b in window_s)
    low_s = min(b['low'] for b in window_s)

    # Recent testing bars (last 10 5M bars)
    recent_g = rates_5m_gold[-10:]
    recent_s = rates_5m_silver[-10:]

    max_g = max(b['high'] for b in recent_g)
    min_g = min(b['low'] for b in recent_g)

    max_s = max(b['high'] for b in recent_s)
    min_s = min(b['low'] for b in recent_s)

    # Sweep flags
    gold_swept_high = max_g >= high_g
    gold_swept_low = min_g <= low_g

    silver_swept_high = max_s >= high_s
    silver_swept_low = min_s <= low_s

    # SMT Logic
    # 1. Bearish SMT: One swept High, other failed to sweep High
    if gold_swept_high and not silver_swept_high:
        delta_g = max_g - high_g
        return {
            "has_smt": True,
            "smt_type": "BEARISH_SMT",
            "leading_asset": "XAUUSD",
            "lagging_asset": "XAGUSD",
            "summary": (
                f"BEARISH SMT DIVERGENCE: Gold swept {label} High by {delta_g:.2f} pts, "
                f"but Silver REFUSED to sweep its High (Silver held lower high). Institutional Distribution in Metals!"
            )
        }

    if silver_swept_high and not gold_swept_high:
        delta_s = max_s - high_s
        return {
            "has_smt": True,
            "smt_type": "BEARISH_SMT",
            "leading_asset": "XAGUSD",
            "lagging_asset": "XAUUSD",
            "summary": (
                f"BEARISH SMT DIVERGENCE: Silver swept {label} High by {delta_s:.3f} pts, "
                f"but Gold REFUSED to sweep its High (Gold held lower high). Institutional Distribution in Metals!"
            )
        }

    # 2. Bullish SMT: One swept Low, other failed to sweep Low
    if gold_swept_low and not silver_swept_low:
        delta_g = low_g - min_g
        return {
            "has_smt": True,
            "smt_type": "BULLISH_SMT",
            "leading_asset": "XAUUSD",
            "lagging_asset": "XAGUSD",
            "summary": (
                f"BULLISH SMT DIVERGENCE: Gold swept {label} Low by {delta_g:.2f} pts (Judas Purge), "
                f"while Silver REFUSED to sweep its Low (Higher Low accumulation). Institutional Smart Money Buy Signal!"
            )
        }

    if silver_swept_low and not gold_swept_low:
        delta_s = low_s - min_s
        return {
            "has_smt": True,
            "smt_type": "BULLISH_SMT",
            "leading_asset": "XAGUSD",
            "lagging_asset": "XAUUSD",
            "summary": (
                f"BULLISH SMT DIVERGENCE: Silver swept {label} Low by {delta_s:.3f} pts (Judas Purge), "
                f"while Gold REFUSED to sweep its Low (Higher Low accumulation). Institutional Smart Money Buy Signal!"
            )
        }

    # Correlated
    if gold_swept_high and silver_swept_high:
        return {
            "has_smt": False,
            "smt_type": "CORRELATED_HIGH_SWEEP",
            "summary": f"Correlated High Sweep: Both Gold and Silver swept {label} Highs simultaneously."
        }

    if gold_swept_low and silver_swept_low:
        return {
            "has_smt": False,
            "smt_type": "CORRELATED_LOW_SWEEP",
            "summary": f"Correlated Low Sweep: Both Gold and Silver swept {label} Lows simultaneously."
        }

    return {
        "has_smt": False,
        "smt_type": "IN_RANGE_CORRELATION",
        "summary": f"Both metals trading inside {label} boundaries."
    }
