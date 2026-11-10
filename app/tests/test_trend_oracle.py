"""
Test Suite for TradingGuard OmniTrend Oracle Service.
Verifies multi-horizon trend predictions, on-chart microstructure extraction,
off-chart macro synthesis, SubQ Snap classifier, and Telegram card formatting.
"""

import pytest
import datetime
from pathlib import Path

from hitl.trend.on_chart_microstructure import extract_on_chart_microstructure
from hitl.trend.off_chart_macro import extract_off_chart_macro
from hitl.trend.snap_trend_classifier import SnapTrendClassifier
from hitl.trend.trend_oracle import TrendOracle, trend_oracle


def test_on_chart_microstructure_keys():
    """Verifies that on-chart microstructure extraction returns complete institutional schema."""
    data = extract_on_chart_microstructure("XAUUSD")
    assert "symbol" in data
    assert data["symbol"] == "XAUUSD"
    assert "current_price" in data
    assert "daily_structure" in data
    assert "weekly_structure" in data
    assert "session_ranges" in data
    assert "draw_on_liquidity" in data
    assert "liquidity_pools" in data
    assert "htf_trend" in data
    assert "smt_divergence" in data

    # Check key numerical bounds
    assert data["daily_structure"]["adr_14"] > 0
    assert data["draw_on_liquidity"]["target_price"] > 0


def test_off_chart_macro_keys():
    """Verifies that off-chart macro extraction returns catalyst and retail sentiment telemetry."""
    data = extract_off_chart_macro("XAUUSD")
    assert "symbol" in data
    assert "catalysts" in data
    assert "retail_sentiment" in data
    assert "session_context" in data

    assert data["catalysts"]["session_risk"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert 0 <= data["retail_sentiment"]["retail_long_pct"] <= 100
    assert 0 <= data["retail_sentiment"]["retail_short_pct"] <= 100


def test_snap_trend_classifier_deterministic_bullish():
    """Verifies deterministic matrix logic on synthetic bullish institutional state."""
    classifier = SnapTrendClassifier(api_key=None, api_url=None)  # Force deterministic mode

    on_chart_synthetic = {
        "symbol": "XAUUSD",
        "current_price": 2720.0,
        "daily_structure": {
            "pdh": 2740.0,
            "pdl": 2700.0,
            "pdc": 2715.0,
            "daily_open": 2710.0,
            "daily_high": 2725.0,
            "daily_low": 2698.0,  # Swept PDL
            "daily_range": 27.0,
            "adr_14": 30.0,
            "adr_utilization_pct": 90.0,
            "has_swept_pdh": False,
            "has_swept_pdl": True
        },
        "weekly_structure": {
            "pwh": 2760.0,
            "pwl": 2680.0,
            "cwo": 2710.0,
            "relation_to_weekly_open": "ABOVE_WEEKLY_OPEN"
        },
        "session_ranges": {
            "asian_high": 2722.0,
            "asian_low": 2705.0,
            "asian_range": 17.0
        },
        "draw_on_liquidity": {
            "type": "BUY_SIDE_LIQUIDITY",
            "target_price": 2740.0,
            "distance_pts": 20.0
        },
        "htf_trend": {
            "h1_regime": "BULLISH_EXPANSION"
        },
        "smt_divergence": {
            "has_smt": True,
            "type": "BULLISH_SMT"
        }
    }

    off_chart_synthetic = {
        "catalysts": {"session_risk": "LOW"},
        "retail_sentiment": {"retail_long_pct": 25.0, "retail_short_pct": 75.0}  # Heavy retail short = Long squeeze
    }

    res = classifier.classify_trend(on_chart_synthetic, off_chart_synthetic)
    assert res["symbol"] == "XAUUSD"
    horizons = res["horizons"]
    assert horizons["day"]["bias"] == "BULLISH"
    assert horizons["session"]["bias"] == "BULLISH"
    assert horizons["day"]["daily_dol"]["target"] == 2740.0


def test_snap_trend_classifier_deterministic_bearish():
    """Verifies deterministic matrix logic on synthetic bearish institutional state."""
    classifier = SnapTrendClassifier(api_key=None, api_url=None)

    on_chart_synthetic = {
        "symbol": "XAUUSD",
        "current_price": 2730.0,
        "daily_structure": {
            "pdh": 2735.0,
            "pdl": 2690.0,
            "pdc": 2735.0,
            "daily_open": 2732.0,
            "daily_high": 2738.0,  # Swept PDH
            "daily_low": 2725.0,
            "daily_range": 13.0,
            "adr_14": 25.0,
            "adr_utilization_pct": 52.0,
            "has_swept_pdh": True,
            "has_swept_pdl": False
        },
        "weekly_structure": {
            "pwh": 2750.0,
            "pwl": 2670.0,
            "cwo": 2740.0,
            "relation_to_weekly_open": "BELOW_WEEKLY_OPEN"
        },
        "session_ranges": {
            "asian_high": 2737.0,
            "asian_low": 2728.0,
            "asian_range": 9.0
        },
        "draw_on_liquidity": {
            "type": "SELL_SIDE_LIQUIDITY",
            "target_price": 2690.0,
            "distance_pts": 40.0
        },
        "htf_trend": {
            "h1_regime": "BEARISH_EXPANSION"
        },
        "smt_divergence": {
            "has_smt": True,
            "type": "BEARISH_SMT"
        }
    }

    off_chart_synthetic = {
        "catalysts": {"session_risk": "LOW"},
        "retail_sentiment": {"retail_long_pct": 80.0, "retail_short_pct": 20.0}  # Heavy retail long = Long flush
    }

    res = classifier.classify_trend(on_chart_synthetic, off_chart_synthetic)
    assert res["symbol"] == "XAUUSD"
    horizons = res["horizons"]
    assert horizons["day"]["bias"] == "BEARISH"
    assert horizons["session"]["bias"] == "BEARISH"
    assert horizons["day"]["daily_dol"]["target"] == 2690.0


def test_trend_oracle_service_and_card_formatting():
    """Verifies complete end-to-end trend oracle forecasting and telegram card formatting."""
    oracle = TrendOracle()
    fc = oracle.get_forecast("XAUUSD", force_refresh=True)

    assert "symbol" in fc
    assert fc["symbol"] == "XAUUSD"
    assert "horizons" in fc
    assert "session" in fc["horizons"]
    assert "day" in fc["horizons"]
    assert "week" in fc["horizons"]

    # Verify Telegram formatting
    card = oracle.format_telegram_card(fc)
    assert "OmniTrend Oracle" in card
    assert "SESSION HORIZON" in card
    assert "DAILY HORIZON" in card
    assert "WEEKLY HORIZON" in card
    assert "Advisory Mode" in card

    # Verify CLI summary formatting
    summary = oracle.format_cli_summary(fc)
    assert "OMNITREND ORACLE" in summary
    assert "Latency" in summary
