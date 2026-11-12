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
    assert "XAUUSD" in data["symbol"]
    assert "current_price" in data
    assert "daily_structure" in data
    assert "weekly_structure" in data
    assert "session_ranges" in data
    assert "draw_on_liquidity" in data
    assert "liquidity_pools" in data
    assert "htf_trend" in data
    assert "smt_divergence" in data
    assert "active_anchor" in data
    assert "london_context" in data
    assert data["active_anchor"] in ("PRE_LONDON", "PRE_NY", "AFTER_HOURS")
    assert "is_established" in data["london_context"]

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
    classifier = SnapTrendClassifier(api_key="", api_url="")  # Force deterministic mode

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
            "daily_range": 12.0,
            "adr_14": 30.0,
            "adr_utilization_pct": 35.0,
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

    # Verify asymmetric trade management recommendations
    assert "trade_management" in res
    assert res["trade_management"]["aligned"]["tp_r"] == 3.5
    assert res["trade_management"]["aligned"]["be_ratchet_r"] == 1.5
    assert res["trade_management"]["counter"]["tp_r"] == 1.5
    assert res["trade_management"]["counter"]["be_ratchet_r"] == 1.0
    assert res["trade_management"]["sideways"]["tp_r"] == 3.5
    assert res["trade_management"]["sideways"]["be_ratchet_r"] == 1.0


def test_snap_trend_classifier_deterministic_bearish():
    """Verifies deterministic matrix logic on synthetic bearish institutional state."""
    classifier = SnapTrendClassifier(api_key="", api_url="")

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
            "daily_range": 10.0,
            "adr_14": 30.0,
            "adr_utilization_pct": 33.3,
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


def test_snap_trend_classifier_adr_exhaustion_gating():
    """Verifies that when ADR utilization >= 55%, classifier forces CONSOLIDATION (Sideways)."""
    classifier = SnapTrendClassifier(api_key="", api_url="")

    on_chart_exhausted = {
        "symbol": "XAUUSD",
        "current_price": 2745.0,
        "daily_structure": {
            "pdh": 2740.0,
            "pdl": 2700.0,
            "pdc": 2715.0,
            "daily_open": 2710.0,
            "daily_high": 2748.0,
            "daily_low": 2708.0,
            "daily_range": 40.0,
            "adr_14": 40.0,
            "adr_utilization_pct": 75.0,  # Range exhausted
            "has_swept_pdh": True,
            "has_swept_pdl": False
        },
        "weekly_structure": {"pwh": 2760.0, "pwl": 2680.0, "cwo": 2710.0},
        "session_ranges": {"asian_high": 2730.0, "asian_low": 2712.0},
        "draw_on_liquidity": {"type": "BUY_SIDE_LIQUIDITY", "target_price": 2760.0},
        "htf_trend": {"h1_regime": "BULLISH_EXPANSION"},
        "smt_divergence": {"has_smt": False, "type": "NONE"}
    }

    off_chart = {"catalysts": {"session_risk": "LOW"}, "retail_sentiment": {"retail_long_pct": 50.0}}

    res = classifier.classify_trend(on_chart_exhausted, off_chart)
    assert res["horizons"]["day"]["bias"] == "CONSOLIDATION"
    assert res["horizons"]["day"]["candle_archetype"] == "ADR_EXHAUSTED_ROTATION"
    assert res["trade_management"]["sideways"]["tp_r"] == 3.5
    assert res["trade_management"]["sideways"]["be_ratchet_r"] == 1.0


def test_trend_oracle_service_and_card_formatting():
    """Verifies complete end-to-end trend oracle forecasting and telegram card formatting."""
    oracle = TrendOracle()
    fc = oracle.get_forecast("XAUUSD", force_refresh=True)

    assert "symbol" in fc
    assert "XAUUSD" in fc["symbol"]
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


def test_on_chart_microstructure_gbpusd():
    """Verifies that on-chart microstructure extraction works seamlessly on Cable (GBPUSD)."""
    data = extract_on_chart_microstructure("GBPUSD")
    assert "symbol" in data
    assert "GBPUSD" in data["symbol"]
    assert data["asset_class"] == "FOREX"
    assert "current_price" in data
    assert data["daily_structure"]["adr_14"] > 0
    assert data["draw_on_liquidity"]["target_price"] > 0
    assert "smt_divergence" in data


def test_snap_trend_classifier_forex_policy():
    """Verifies that Forex assets receive the calibrated 2.0R / 2.5R asymmetric execution policy."""
    classifier = SnapTrendClassifier(api_key="", api_url="")

    on_chart_forex = {
        "symbol": "GBPUSD_o",
        "asset_class": "FOREX",
        "current_price": 1.30500,
        "daily_structure": {
            "pdh": 1.31000,
            "pdl": 1.29500,
            "pdc": 1.30200,
            "daily_open": 1.30100,
            "daily_high": 1.30800,
            "daily_low": 1.29400,  # Swept PDL
            "daily_range": 0.00700,
            "adr_14": 0.00850,
            "adr_utilization_pct": 30.0,
            "has_swept_pdh": False,
            "has_swept_pdl": True
        },
        "weekly_structure": {
            "pwh": 1.32000,
            "pwl": 1.29000,
            "cwo": 1.30000,
            "relation_to_weekly_open": "ABOVE_WEEKLY_OPEN"
        },
        "session_ranges": {
            "asian_high": 1.30600,
            "asian_low": 1.30000,
            "asian_range": 0.00600
        },
        "draw_on_liquidity": {
            "type": "BUY_SIDE_LIQUIDITY",
            "target_price": 1.31000,
            "distance_pts": 50.0
        },
        "htf_trend": {
            "h1_regime": "BULLISH_EXPANSION"
        },
        "smt_divergence": {
            "has_smt": True,
            "type": "BULLISH_SMT"
        }
    }

    off_chart = {"catalysts": {"session_risk": "LOW"}, "retail_sentiment": {"retail_long_pct": 30.0}}
    res = classifier.classify_trend(on_chart_forex, off_chart)

    assert res["symbol"] == "GBPUSD_o"
    assert res["horizons"]["day"]["bias"] == "BULLISH"
    assert res["trade_management"]["aligned"]["tp_r"] == 2.0
    assert res["trade_management"]["aligned"]["be_ratchet_r"] == 1.0
    assert res["trade_management"]["counter"]["tp_r"] == 2.5
    assert res["trade_management"]["counter"]["be_ratchet_r"] == 1.0
    assert res["trade_management"]["sideways"]["tp_r"] == 2.5
    assert res["trade_management"]["sideways"]["be_ratchet_r"] == 0.8


def test_trend_oracle_service_gbpusd_card():
    """Verifies that TrendOracle formats Telegram card correctly for GBPUSD without currency symbol."""
    oracle = TrendOracle()
    fc = oracle.get_forecast("GBPUSD_o", force_refresh=True)

    assert "symbol" in fc
    assert "GBPUSD" in fc["symbol"]
    card = oracle.format_telegram_card(fc)

    assert "OmniTrend Oracle — GBPUSD" in card
    # Should not have dollar signs on the current price line
    assert "$" not in card.split("Current Price:")[1].split("\n")[0]
    # Trade policy should reflect forex parameters
    assert "TP 2.0R" in card
    assert "TP 2.5R" in card


def test_on_chart_microstructure_nq():
    """Verifies that on-chart microstructure extraction works seamlessly on NASDAQ 100 (NQ)."""
    data = extract_on_chart_microstructure("NQ")
    assert "symbol" in data
    assert "NQ" in data["symbol"]
    assert data["asset_class"] == "INDEX"
    assert "current_price" in data
    assert data["daily_structure"]["adr_14"] > 0
    assert data["draw_on_liquidity"]["target_price"] > 0
    assert "smt_divergence" in data


def test_snap_trend_classifier_index_policy():
    """Verifies that Index assets receive the calibrated 3.5R / 3.0R / 0.8R asymmetric execution policy."""
    classifier = SnapTrendClassifier(api_key="", api_url="")

    on_chart_index = {
        "symbol": "NQ",
        "asset_class": "INDEX",
        "current_price": 27500.0,
        "daily_structure": {
            "pdh": 27700.0,
            "pdl": 27300.0,
            "pdc": 27450.0,
            "daily_open": 27420.0,
            "daily_high": 27550.0,
            "daily_low": 27280.0,  # Swept PDL
            "daily_range": 270.0,
            "adr_14": 350.0,
            "adr_utilization_pct": 35.0,
            "has_swept_pdh": False,
            "has_swept_pdl": True
        },
        "weekly_structure": {
            "pwh": 28000.0,
            "pwl": 27000.0,
            "cwo": 27400.0,
            "relation_to_weekly_open": "ABOVE_WEEKLY_OPEN"
        },
        "session_ranges": {
            "asian_high": 27520.0,
            "asian_low": 27380.0,
            "asian_range": 140.0
        },
        "draw_on_liquidity": {
            "type": "BUY_SIDE_LIQUIDITY",
            "target_price": 27700.0,
            "distance_pts": 200.0
        },
        "htf_trend": {
            "h1_regime": "BULLISH_EXPANSION"
        },
        "smt_divergence": {
            "has_smt": True,
            "type": "BULLISH_SMT"
        }
    }

    off_chart = {"catalysts": {"session_risk": "LOW"}, "retail_sentiment": {"retail_long_pct": 35.0}}
    res = classifier.classify_trend(on_chart_index, off_chart)

    assert res["symbol"] == "NQ"
    assert res["horizons"]["day"]["bias"] == "BULLISH"
    assert res["trade_management"]["aligned"]["tp_r"] == 3.5
    assert res["trade_management"]["aligned"]["be_ratchet_r"] == 1.0
    assert res["trade_management"]["counter"]["tp_r"] == 3.0
    assert res["trade_management"]["counter"]["be_ratchet_r"] == 0.8
    assert res["trade_management"]["sideways"]["tp_r"] == 3.0
    assert res["trade_management"]["sideways"]["be_ratchet_r"] == 0.8


def test_trend_oracle_service_nq_card():
    """Verifies that TrendOracle formats Telegram card correctly for NQ without currency symbol."""
    oracle = TrendOracle()
    fc = oracle.get_forecast("NQ", force_refresh=True)

    assert "symbol" in fc
    assert "NQ" in fc["symbol"]
    card = oracle.format_telegram_card(fc)

    assert "OmniTrend Oracle — NQ" in card
    # Should not have dollar signs on the current price line
    assert "$" not in card.split("Current Price:")[1].split("\n")[0]
    # Trade policy should reflect index parameters
    assert "TP 3.5R" in card
    assert "TP 3.0R" in card


def test_session_expected_range_bearish_below_asian_low_and_at_asian_low():
    """
    Regression test for inverted session expected_range when price is already at or
    below asian_low under a BEARISH forecast (2026-11-12 live XAUUSD bug).
    Verifies both SubQ Snap synthesis and deterministic fallback paths.
    """
    import json
    from unittest.mock import patch, MagicMock

    def _make_state(curr_p: float, d_low: float, d_range: float, util: float):
        return {
            "symbol": "XAUUSD_o",
            "current_price": curr_p,
            "daily_structure": {
                "pdh": 4066.87,
                "pdl": 3982.60,
                "pdc": 3987.74,
                "daily_open": 3993.39,
                "daily_high": 4000.34,
                "daily_low": d_low,
                "daily_range": d_range,
                "adr_14": 89.46,
                "adr_utilization_pct": util,
                "has_swept_pdh": False,
                "has_swept_pdl": True,
            },
            "weekly_structure": {
                "pwh": 4146.82,
                "pwl": 3890.91,
                "cwo": 4063.24,
                "relation_to_weekly_open": "BELOW_WEEKLY_OPEN",
            },
            "session_ranges": {
                "asian_high": 4000.34,
                "asian_low": 3968.70,
                "asian_range": 31.64,
            },
            "draw_on_liquidity": {
                "type": "SELL_SIDE_LIQUIDITY",
                "target_price": d_low,
                "distance_pts": round(curr_p - d_low, 2),
            },
            "htf_trend": {"h1_regime": "BEARISH_EXPANSION"},
            "smt_divergence": {"has_smt": False, "type": "NONE"},
        }

    off_chart = {
        "catalysts": {"session_risk": "MEDIUM", "day_risk": "LOW"},
        "retail_sentiment": {"retail_long_pct": 75.0, "retail_short_pct": 25.0, "contrarian_bias": "BEARISH"},
        "session_context": {"session_label": "Pre-London"},
    }

    # 1. SubQ Snap API path on exact 2026-11-12 state (price 3956.57 < asian_low 3968.70)
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "answers": {
            "session_horizon": {"choice": "BEARISH_EXPANSION", "confidence": 0.88},
            "day_horizon": {"choice": "BEARISH_DAY", "confidence": 0.85},
            "weekly_profile": {"choice": "MID_WEEK_REVERSAL", "confidence": 0.55},
        }
    }).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = lambda s, *a: None

    snap_clf = SnapTrendClassifier(api_key="test-key", api_url="https://example.test/snap")
    with patch("urllib.request.urlopen", return_value=mock_resp):
        snap_res = snap_clf.classify_trend(_make_state(3956.57, 3955.00, 45.34, 50.7), off_chart)

    sess_snap = snap_res["horizons"]["session"]
    rng_snap = sess_snap["expected_range"]
    assert sess_snap["bias"] == "BEARISH"
    assert rng_snap["low"] < 3956.57 < rng_snap["high"]
    assert (3956.57 - rng_snap["low"]) > (rng_snap["high"] - 3956.57)
    assert rng_snap["high"] < 4000.34

    # 2. Deterministic fallback at Asian Low / London Open (3968.70)
    det_clf = SnapTrendClassifier(api_key="", api_url="")
    det_res = det_clf.classify_trend(_make_state(3968.70, 3968.70, 31.64, 35.4), off_chart)
    sess_det = det_res["horizons"]["session"]
    rng_det = sess_det["expected_range"]
    assert sess_det["bias"] == "BEARISH"
    assert rng_det["low"] < 3968.70 < rng_det["high"]
    assert (3968.70 - rng_det["low"]) > (rng_det["high"] - 3968.70)


def test_session_expected_range_bullish_breakout_above_asian_high():
    """Verifies bullish expected_range stays upside-skewed when price breaks above asian_high."""
    det_clf = SnapTrendClassifier(api_key="", api_url="")
    state = {
        "symbol": "XAUUSD_o",
        "current_price": 4005.0,
        "daily_structure": {
            "pdh": 4050.0,
            "pdl": 3960.0,
            "pdc": 3985.0,
            "daily_open": 3986.0,
            "daily_high": 4006.0,
            "daily_low": 3972.0,
            "daily_range": 34.0,
            "adr_14": 80.0,
            "adr_utilization_pct": 42.5,
            "has_swept_pdh": False,
            "has_swept_pdl": False,
        },
        "weekly_structure": {"pwh": 4100.0, "pwl": 3900.0, "cwo": 3970.0},
        "session_ranges": {"asian_high": 3995.0, "asian_low": 3972.0, "asian_range": 23.0},
        "draw_on_liquidity": {"type": "BUY_SIDE_LIQUIDITY", "target_price": 4050.0, "distance_pts": 45.0},
        "htf_trend": {"h1_regime": "BULLISH_EXPANSION"},
        "smt_divergence": {"has_smt": True, "type": "BULLISH_SMT"},
    }
    off_chart = {"catalysts": {"session_risk": "LOW"}, "retail_sentiment": {"retail_long_pct": 25.0}}

    res = det_clf.classify_trend(state, off_chart)
    sess = res["horizons"]["session"]
    rng = sess["expected_range"]
    assert sess["bias"] == "BULLISH"
    assert rng["low"] < 4005.0 < rng["high"]
    assert (rng["high"] - 4005.0) > (4005.0 - rng["low"])



