"""
Comprehensive Unit & Contract Tests for TradingGuard Fundamental Causal Engine
Covers:
  - US Treasury newest-first CSV sorting, TIPS Real Yields, Breakevens & Regime Diagnostics
  - Multi-source RSS/Atom parsing, 48h freshness window & Jaccard deduplication
  - Official CFTC TFF & Disaggregated COT parsing + USDJPY futures inversion
  - Causal Engine JSON validation, deterministic tape fallback & JSONL history logging
  - Runtime Enforcement Governor ('advisory' vs 'hard_veto' with tape confirmation)
  - Regression fixes in sentiment_feed.py (misclassified bearish titles + BTCUSD routing)
  - Facade compatibility across macro_bias.py, off_chart_macro.py (-5m danger window) & formatters
"""

import datetime
import json
from unittest.mock import patch

import pytest

from hitl.fundamental.causal_engine import CORE_ASSETS, FundamentalCausalEngine
from hitl.fundamental.cot_feed import parse_cftc_rows
from hitl.fundamental.formatter import format_asset_macro_card, format_global_macro_card
from hitl.fundamental.governor import (
    evaluate_fundamental_gate,
    get_enforcement_mode,
    set_enforcement_mode,
    toggle_enforcement_mode,
)
from hitl.fundamental.market_tape import (
    _extract_curve_metric,
    _parse_treasury_csv,
    compute_cross_asset_diagnostics,
)
from hitl.fundamental.news_aggregator import deduplicate_news_items, parse_rss_xml
from hitl.macro_bias import calculate_htf_fundamental_bias, format_fundamental_bias_prompt
from hitl.sentiment_feed import _resolve_tv_symbol, classify_tv_idea_sentiment, fetch_tradingview_ideas


@pytest.fixture
def isolated_fundamental_files(tmp_path, monkeypatch):
    """Isolates persistent governor/state/log files into tmp_path so tests never touch live state."""
    gov_file = tmp_path / "fundamental_governor.json"
    state_file = tmp_path / "fundamental_state.json"
    hist_file = tmp_path / "fundamental_history_log.jsonl"

    monkeypatch.setattr("hitl.fundamental.governor.GOVERNOR_STATE_FILE", gov_file)
    monkeypatch.setattr("hitl.fundamental.causal_engine.STATE_FILE", state_file)
    monkeypatch.setattr("hitl.fundamental.causal_engine.HISTORY_LOG_FILE", hist_file)
    return {"gov": gov_file, "state": state_file, "hist": hist_file}


def test_treasury_csv_newest_first_sorting_and_diagnostics():
    """Verifies US Treasury newest-first CSVs sort ascending and compute breakeven & co-selloff diagnostics."""
    # Simulated Treasury CSV rows arriving NEWEST-FIRST
    nom_csv = (
        "Date,3 Mo,2 Yr,10 Yr,30 Yr\n"
        "11/20/2026,4.32,4.63,4.92,5.31\n"
        "11/19/2026,4.30,4.55,4.85,5.25\n"
        "11/18/2026,4.28,4.50,4.80,5.20\n"
        "11/17/2026,4.25,4.45,4.74,5.15\n"
        "11/16/2026,4.22,4.40,4.68,5.10\n"
        "11/13/2026,4.20,4.35,4.60,5.02\n"
    )
    real_csv = (
        "Date,5 YR,10 YR,30 YR\n"
        "11/20/2026,2.53,2.77,3.17\n"
        "11/19/2026,2.50,2.72,3.12\n"
        "11/18/2026,2.45,2.68,3.08\n"
        "11/17/2026,2.40,2.62,3.02\n"
        "11/16/2026,2.35,2.58,2.98\n"
        "11/13/2026,2.30,2.52,2.92\n"
    )
    nom_rows = _parse_treasury_csv(nom_csv)
    real_rows = _parse_treasury_csv(real_csv)

    # Sorted ascending chronologically (oldest first, newest last)
    assert nom_rows[0]["_date"] == "2026-11-13"
    assert nom_rows[-1]["_date"] == "2026-11-20"
    assert real_rows[-1]["_date"] == "2026-11-20"

    nom_10 = _extract_curve_metric(nom_rows, "10 Yr")
    nom_2 = _extract_curve_metric(nom_rows, "2 Yr")
    real_10 = _extract_curve_metric(real_rows, "10 YR")
    assert nom_10["latest"] == 4.92
    assert nom_10["chg_5d_bps"] == 32.0  # (4.92 - 4.60) * 100
    assert real_10["latest"] == 2.77
    assert real_10["chg_5d_bps"] == 25.0  # (2.77 - 2.52) * 100

    # Breakeven calculation: 4.92 - 2.77 = 2.15% (up +7 bps vs 4.60 - 2.52 = 2.08%)
    be_rows = [{"_date": n["_date"], "BE10": n["10 Yr"] - r["10 YR"]} for n, r in zip(nom_rows, real_rows)]
    be_10 = _extract_curve_metric(be_rows, "BE10")
    assert be_10["latest"] == 2.15
    assert be_10["chg_5d_bps"] == 7.0

    treasury_bundle = {
        "status": "OK",
        "nom_10y": nom_10,
        "nom_2y": nom_2,
        "real_10y": real_10,
        "breakeven_10y": be_10,
        "slope_2s10s": {"latest": round(4.92 - 4.63, 2)},
    }
    yahoo_bundle = {
        "tickers": {
            "US10Y_YF": {"latest": 4.92, "chg_1d_bps": 7.0, "chg_5d_bps": 32.0},
            "TLT": {"latest": 85.0, "chg_5d_pct": -2.4},
            "HYG": {"latest": 77.0, "chg_5d_pct": -1.5},
            "SHY": {"latest": 82.0, "chg_5d_pct": -0.1},
            "CSI300": {"latest": 3600.0, "chg_5d_pct": -3.1},
            "USDCNH": {"latest": 7.28, "chg_5d_pct": 0.65},
            "COPPER": {"latest": 4.05, "chg_5d_pct": -2.2},
            "VIX_YF": {"latest": 24.5, "chg_5d_pct": 18.0},
        }
    }
    mt5_bundle = {
        "USDX": {"latest": 104.2, "chg_1d_pct": 0.35, "chg_5d_pct": 1.15, "chg_20d_pct": 2.4},
        "SPX": {"latest": 5800.0, "chg_5d_pct": -2.5},
        "NQ": {"latest": 20100.0, "chg_5d_pct": -3.4},
        "HK50": {"latest": 19100.0, "chg_5d_pct": -3.2},
        "XAUUSD": {"latest": 3570.0, "chg_5d_pct": -3.1},
        "USCRUDE": {"latest": 74.5, "chg_5d_pct": 4.2, "chg_20d_pct": 8.5},
    }

    diag = compute_cross_asset_diagnostics(treasury_bundle, yahoo_bundle, mt5_bundle)
    assert diag["real_10y_level"] == 2.77
    assert diag["breakeven_10y_level"] == 2.15
    assert diag["rate_impulse_driver"] == "REAL_YIELD_TIGHTENING"
    assert diag["bond_equity_co_selloff"] is True
    assert diag["asia_china_stress"] is True
    assert diag["credit_stress_5d_pct"] == -1.4


def test_rss_parsing_and_jaccard_deduplication():
    """Verifies RSS/Atom parsing across RFC2822 & ISO/Investing dates, 48h window, and Jaccard dedup."""
    now_utc = datetime.datetime(2026, 11, 21, 10, 0, tzinfo=datetime.timezone.utc)
    xml_tier1 = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item>
        <title>US Treasury 10Y yields surge to 4.92% on sticky CPI &amp; bond supply</title>
        <description>&lt;p&gt;Long-end yields jumped as bond selling intensified.&lt;/p&gt;</description>
        <pubDate>Sat, 21 Nov 2026 08:30:00 GMT</pubDate>
      </item>
      <item>
        <title>Stale article from 4 days ago should be dropped</title>
        <pubDate>Tue, 17 Nov 2026 08:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""

    xml_tier3_dup = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item>
        <title>US Treasury 10Y yields surge to 4.92% on sticky CPI bond supply - MarketWatch</title>
        <pubDate>2026-11-21 08:40:00</pubDate>
      </item>
    </channel></rss>"""

    items1 = parse_rss_xml(xml_tier1, "ForexLive", tier=1, now_utc=now_utc, hours_back=48)
    assert len(items1) == 1  # Stale item dropped
    assert items1[0]["summary"] == "Long-end yields jumped as bond selling intensified."

    items3 = parse_rss_xml(xml_tier3_dup, "GNews", tier=3, now_utc=now_utc, hours_back=48)
    assert len(items3) == 1

    merged = deduplicate_news_items(items3 + items1, max_items=10)
    assert len(merged) == 1
    assert merged[0]["source"] == "ForexLive"  # Higher-authority Tier 1 beats Tier 3 duplicate


def test_cftc_cot_parsing_and_usdjpy_inversion():
    """Verifies TFF + Disaggregated COT parsing, WoW delta calculation, crowding flag & USDJPY inversion."""
    tff_rows = [
        {
            "market_and_exchange_names": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
            "report_date_as_yyyy_mm_dd": "2026-11-17T00:00:00.000",
            "lev_money_positions_long": "20000",
            "lev_money_positions_short": "80000",
        },
        {
            "market_and_exchange_names": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
            "report_date_as_yyyy_mm_dd": "2026-11-10T00:00:00.000",
            "lev_money_positions_long": "30000",
            "lev_money_positions_short": "70000",
        },
        {
            "market_and_exchange_names": "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
            "report_date_as_yyyy_mm_dd": "2026-11-17T00:00:00.000",
            "lev_money_positions_long": "45000",
            "lev_money_positions_short": "15000",
        },
    ]
    disagg_rows = [
        {
            "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
            "report_date_as_yyyy_mm_dd": "2026-11-17T00:00:00.000",
            "m_money_positions_long_all": "180000",
            "m_money_positions_short_all": "40000",
        },
        {
            "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
            "report_date_as_yyyy_mm_dd": "2026-11-10T00:00:00.000",
            "m_money_positions_long_all": "195000",
            "m_money_positions_short_all": "35000",
        },
    ]

    cot = parse_cftc_rows(tff_rows, disagg_rows)
    assert cot["status"] == "OK"
    assert cot["latest_report_date"] == "2026-11-17"

    # Japanese Yen futures: 20k long, 80k short -> inverted to USDJPY = 80k long, 20k short (+60k net long USDJPY, EXTREME_LONG)
    jpy = cot["assets"]["USDJPY"]
    assert jpy["net_contracts"] == 60000
    assert jpy["net_change_wow"] == 20000  # prev was 70k-30k = 40k
    assert jpy["long_pct"] == 80.0
    assert jpy["crowding_flag"] == "EXTREME_LONG"

    gold = cot["assets"]["XAUUSD"]
    assert gold["net_contracts"] == 140000
    assert gold["net_change_wow"] == -20000  # prev 160k -> now 140k
    assert gold["long_pct"] == 81.8
    assert gold["crowding_flag"] == "EXTREME_LONG"


def test_causal_engine_llm_schema_fallback_and_persistence(isolated_fundamental_files):
    """
    Tests:
      1. LLM synthesis with valid multi-step causal JSON + missing asset backfill
      2. Graceful fallback to deterministic quantitative tape when LLM fails
      3. State caching + append-only JSONL history logging
    """
    fake_tape = {
        "treasury_curves": {"status": "OK", "as_of_date": "2026-11-20"},
        "yahoo_tape": {"TLT": {"latest": 85.0, "chg_1d_pct": -0.8, "chg_5d_pct": -2.1, "chg_20d_pct": -4.0}},
        "mt5_tape": {"XAUUSD": {"latest": 3570.0, "chg_1d_pct": -1.5, "chg_5d_pct": -3.0, "chg_20d_pct": -5.0}},
        "diagnostics": {
            "nom_10y_level": 4.92,
            "nom_10y_5d_bps": 28.0,
            "real_10y_level": 2.77,
            "real_10y_5d_bps": 22.0,
            "breakeven_10y_level": 2.15,
            "breakeven_5d_bps": 6.0,
            "slope_2s10s": 0.29,
            "rate_impulse_driver": "REAL_YIELD_TIGHTENING",
            "bond_equity_co_selloff": True,
            "tlt_5d_pct": -2.1,
            "spx_5d_pct": -2.4,
            "nq_5d_pct": -3.1,
            "credit_stress_5d_pct": -1.2,
            "asia_china_stress": True,
            "csi300_5d_pct": -2.9,
            "hk50_5d_pct": -3.0,
            "usdcnh_5d_pct": 0.55,
            "oil_5d_pct": 3.5,
            "oil_20d_pct": 7.0,
            "copper_5d_pct": -2.1,
            "gold_5d_pct": -3.0,
            "dxy_level": 104.2,
            "dxy_1d_pct": 0.4,
            "dxy_5d_pct": 1.1,
            "dxy_20d_pct": 2.2,
            "vix_level": 24.5,
            "vix_5d_pct": 15.0,
        },
    }
    fake_cot = {"status": "OK", "latest_report_date": "2026-11-17", "assets": {}}
    fake_news = {
        "events": [{"source": "ForexLive", "tier": 1, "title": "China stress triggers Treasury reserve sales; 10Y yields jump", "published_utc": "2026-11-21 08:00 UTC"}],
        "upcoming_calendar": [],
        "recent_releases": [],
        "feed_health": {"ForexLive": "OK(1)"},
    }

    fake_llm_output = {
        "global_macro_regime": {
            "label": "RESERVE_SELLING_LIQUIDITY_SQUEEZE",
            "summary": "Simultaneous bond & equity selling paired with Asia stress elevates US real yields & DXY.",
            "dominant_theme": "Foreign UST liquidation -> higher real yields & USD squeeze",
            "dollar_regime": "BULLISH_LIQUIDITY_SQUEEZE",
            "rates_regime": "REAL_YIELD_SURGE",
            "risk_regime": "LIQUIDITY_CRUNCH_CO_SELLOFF",
        },
        "causal_chains": [
            {
                "chain_id": "CHAIN-1",
                "event": "Asian Equity Stress + Treasury Supply Pressures Sovereign Bonds",
                "transmission_steps": [
                    "Chinese/Asian equity drawdowns force dollar liquidity conservation",
                    "Reserve managers trim US Treasury holdings -> US 10Y Real Yield climbs +22 bps to 2.77%",
                    "Higher real rates + USD liquidity squeeze weigh heavily on zero-yield Gold and duration Tech",
                ],
                "tape_verification": "CONFIRMED_BY_TAPE",
                "tape_evidence": "Real10Y 2.77% (+22bps 5D), TLT -2.1%, DXY +1.1%, XAUUSD -3.0%",
                "affected_assets": {"XAUUSD": "BEARISH", "NQ": "BEARISH"},
                "horizon": "SWING_1_5D",
                "confidence": 0.86,
            }
        ],
        "assets": {
            "XAUUSD": {
                "bias": "STRONG_BEARISH",
                "score": -72,
                "confidence": 0.85,
                "horizon_bias": {"intraday": "BEARISH", "swing_1_5d": "STRONG_BEARISH", "macro_1_4w": "BEARISH"},
                "dominant_driver": "US Real Yield & USD Liquidity Squeeze",
                "dominant_mechanism": "Reserve bond selling -> US10Y Real +22bps -> Gold opportunity cost surge",
                "bullish_forces": ["Residual geopolitical hedging"],
                "bearish_forces": ["TIPS Real 10Y at 2.77% (+22bps)", "DXY +1.1%"],
                "invalidation_trigger": "US10Y Real drops >12 bps & DXY breaks <103.5",
                "execution_posture": "SELL_RALLIES_ALIGNED",
            }
            # Deliberately omit remaining 10 CORE_ASSETS to verify automatic deterministic backfill!
        },
    }

    engine = FundamentalCausalEngine(ttl_minutes=45)
    with patch("hitl.fundamental.causal_engine.collect_full_market_tape", return_value=fake_tape), \
         patch("hitl.fundamental.causal_engine.fetch_cot_positioning", return_value=fake_cot), \
         patch("hitl.fundamental.causal_engine.fetch_global_macro_events", return_value=fake_news), \
         patch("hitl.fundamental.causal_engine._run_agy_json", return_value=fake_llm_output):
        dossier_llm = engine.get_global_dossier(force_refresh=True, allow_llm=True)

    assert dossier_llm["analysis_source"].startswith("llm:")
    assert dossier_llm["global_macro_regime"]["label"] == "RESERVE_SELLING_LIQUIDITY_SQUEEZE"
    assert dossier_llm["causal_chains"][0]["tape_verification"] == "CONFIRMED_BY_TAPE"
    assert dossier_llm["assets"]["XAUUSD"]["score"] == -72
    assert set(dossier_llm["assets"].keys()) == set(CORE_ASSETS)  # All missing assets backfilled cleanly!
    assert isolated_fundamental_files["state"].exists()
    assert isolated_fundamental_files["hist"].exists()

    # Now verify deterministic fallback when LLM returns None (timeout/error)
    with patch("hitl.fundamental.causal_engine.collect_full_market_tape", return_value=fake_tape), \
         patch("hitl.fundamental.causal_engine.fetch_cot_positioning", return_value=fake_cot), \
         patch("hitl.fundamental.causal_engine.fetch_global_macro_events", return_value=fake_news), \
         patch("hitl.fundamental.causal_engine._run_agy_json", return_value=None):
        dossier_fb = engine.get_global_dossier(force_refresh=True, allow_llm=True)

    assert dossier_fb["analysis_source"] == "deterministic_tape_fallback"
    assert set(dossier_fb["assets"].keys()) == set(CORE_ASSETS)
    # Co-selloff + Real Yield +22bps + DXY +1.1% must score XAUUSD and NQ distinctly bearish deterministically
    assert dossier_fb["assets"]["XAUUSD"]["score"] < -30
    assert dossier_fb["assets"]["NQ"]["score"] < -20

    # History JSONL has 2 records appended cleanly
    lines = isolated_fundamental_files["hist"].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    # Verify Telegram card formatters produce valid output without raising
    g_text, g_kb = format_global_macro_card(dossier_llm)
    assert "Causal Macro Intelligence" in g_text
    assert len(g_kb["inline_keyboard"]) >= 4
    a_text, _ = format_asset_macro_card(dossier_llm, "XAUUSD_o")
    assert "XAUUSD — Causal Fundamental Deep Dive" in a_text
    assert "-72" in a_text


def test_fundamental_enforcement_governor_advisory_and_hard_veto(isolated_fundamental_files):
    """Verifies default advisory mode, persistent switch, and strict tape-confirmed hard veto criteria."""
    sample_dossier = {
        "causal_chains": [
            {"chain_id": "C1", "tape_verification": "CONFIRMED_BY_TAPE", "affected_assets": {"XAUUSD": "BEARISH"}},
            {"chain_id": "C2", "tape_verification": "CONTRADICTED_BY_TAPE", "affected_assets": {"NQ": "BULLISH"}},
        ],
        "assets": {
            "XAUUSD": {"bias": "STRONG_BEARISH", "score": -70, "confidence": 0.85, "dominant_mechanism": "Real yields surging"},
            "NQ": {"bias": "STRONG_BULLISH", "score": 65, "confidence": 0.82, "dominant_mechanism": "Unverified headline rally"},
            "GBPUSD": {"bias": "BEARISH", "score": -35, "confidence": 0.65, "dominant_mechanism": "Moderate USD drift"},
        },
    }

    assert get_enforcement_mode() == "advisory"
    gate_adv = evaluate_fundamental_gate("XAUUSD_o", "BUY_LIMIT", dossier=sample_dossier)
    assert gate_adv["mode"] == "advisory"
    assert gate_adv["allow_trade"] is True
    assert gate_adv["aligned"] is False

    # Switch to hard_veto
    assert toggle_enforcement_mode(toggled_by="pytest") == "hard_veto"
    assert get_enforcement_mode() == "hard_veto"

    # Opposing XAUUSD LONG vs score=-70, conf=0.85, CONFIRMED_BY_TAPE -> VETOED
    gate_veto = evaluate_fundamental_gate("XAUUSD_o", "BUY_LIMIT", dossier=sample_dossier)
    assert gate_veto["allow_trade"] is False
    assert "HARD_VETO" in gate_veto["reason"]

    # Aligned XAUUSD SHORT -> ALLOWED
    gate_ok = evaluate_fundamental_gate("XAUUSD_o", "SELL_LIMIT", dossier=sample_dossier)
    assert gate_ok["allow_trade"] is True
    assert gate_ok["aligned"] is True

    # Opposing NQ SHORT vs score=+65, conf=0.82, but only CONTRADICTED_BY_TAPE -> NOT vetoed (tape guard!)
    gate_nq = evaluate_fundamental_gate("NQ", "SELL_LIMIT", dossier=sample_dossier)
    assert gate_nq["tape_verified"] is False
    assert gate_nq["allow_trade"] is True

    # Moderate GBPUSD conviction (<55 score, <0.75 conf) -> NOT vetoed
    gate_gbp = evaluate_fundamental_gate("GBPUSD", "BUY_LIMIT", dossier=sample_dossier)
    assert gate_gbp["allow_trade"] is True

    # Switch back cleanly
    assert set_enforcement_mode("advisory", toggled_by="pytest") == "advisory"


def test_sentiment_feed_regression_fixes():
    """Replays exact corrupted titles from tv_sentiment_cache.json and verifies symbol mapping fixes."""
    # HTML body deliberately includes "prolonged" and "long-squeeze" CSS noise without bull/bear badge class
    corrupted_html_wrapper = '<article class="tv-card"><p>After a prolonged move and along channel resistance...</p></article>'

    assert classify_tv_idea_sentiment(corrupted_html_wrapper, "XAUUSD Bearish Trendline | Critical Support Under Pressure") == "BEARISH"
    assert classify_tv_idea_sentiment(corrupted_html_wrapper, "EUR/USD 4H Analysis: Bearish Market Structure, Liquidity Zones") == "BEARISH"
    assert classify_tv_idea_sentiment(corrupted_html_wrapper, "US100 (1H): Trendline Breakdown & Resistance Rejection") == "BEARISH"
    assert classify_tv_idea_sentiment(corrupted_html_wrapper, "GBPUSD 4H – Bearish Breakdown Towards 1.3089 Target") == "BEARISH"
    assert classify_tv_idea_sentiment(corrupted_html_wrapper, "Gold Bullish Breakout & Long Rebound Setup") == "BULLISH"
    assert classify_tv_idea_sentiment('<article class="tv-idea-label--short">long text inside summary</article>', "Market Update") == "BEARISH"

    # Symbol routing must never map BTCUSD or unknown assets silently to XAUUSD
    assert _resolve_tv_symbol("BTCUSD") == "BTCUSD"
    assert _resolve_tv_symbol("NQ") == "NDX"
    assert _resolve_tv_symbol("USCRUDE") == "USOIL"
    assert _resolve_tv_symbol("UNKNOWN_MEME_COIN") is None
    assert fetch_tradingview_ideas("UNKNOWN_MEME_COIN") == []


def test_macro_bias_facade_all_assets_and_off_chart_post_news_window(isolated_fundamental_files):
    """Verifies macro_bias facade across FX/Metals/Indices/Crypto and -5m post-release window fix."""
    fake_dossier = FundamentalCausalEngine()._run_deterministic_fallback(
        tape={
            "treasury_curves": {"status": "OK"},
            "yahoo_tape": {"TLT": {"latest": 88.0, "chg_5d_pct": -1.2}},
            "mt5_tape": {"EURLFX": {"chg_5d_pct": -0.5}, "GBPLFX": {"chg_5d_pct": -0.4}, "LFXJPY": {"chg_5d_pct": -0.8}},
            "diagnostics": {
                "nom_10y_level": 4.85, "nom_10y_5d_bps": 12.0,
                "real_10y_level": 2.65, "real_10y_5d_bps": 10.0,
                "breakeven_10y_level": 2.20, "breakeven_5d_bps": 2.0,
                "dxy_level": 103.8, "dxy_5d_pct": 0.65, "vix_level": 21.0,
                "spx_5d_pct": -1.5, "nq_5d_pct": -2.0, "tlt_5d_pct": -1.2,
                "bond_equity_co_selloff": True, "credit_stress_5d_pct": -0.9,
                "asia_china_stress": False, "oil_5d_pct": 1.0, "oil_20d_pct": 2.0,
            },
        },
        cot={"assets": {}},
        news_bundle={"events": [{"title": "Yields climb"}], "upcoming_calendar": [], "recent_releases": []},
    )
    fake_dossier["generated_at_utc"] = "2026-11-21 10:00:00 UTC"
    fake_dossier["treasury_curves"] = {"as_of_date": "2026-11-20"}

    with patch("hitl.fundamental.causal_engine.fundamental_engine.get_global_dossier", return_value=fake_dossier):
        for sym in ["XAUUSD", "GBPUSD", "EURUSD", "NQ", "BTCUSD", "USDJPY"]:
            res = calculate_htf_fundamental_bias(sym)
            assert res["symbol"] == sym
            assert "causal_chains" in res
            assert "score" in res
            prompt = format_fundamental_bias_prompt(res)
            assert "CAUSAL FUNDAMENTAL & OFF-CHART INTELLIGENCE" in prompt

    # Verify -3m post-release high-impact event triggers CRITICAL (previously broken!)
    from hitl.trend.off_chart_macro import extract_off_chart_macro
    mock_ev = [{"title": "US CPI y/y", "country": "USD", "impact": "High", "minutes_away": -3}]
    with patch("hitl.trend.off_chart_macro.get_upcoming_events", return_value=mock_ev), \
         patch("hitl.trend.off_chart_macro.fetch_tradingview_ideas", return_value=[]), \
         patch("hitl.fundamental.causal_engine.fundamental_engine.get_global_dossier", return_value=fake_dossier):
        oc = extract_off_chart_macro("XAUUSD")
        assert oc["catalysts"]["session_risk"] == "CRITICAL"
        assert "fundamental_causal" in oc
        assert oc["fundamental_causal"]["asset_bias"] == fake_dossier["assets"]["XAUUSD"]["bias"]
