"""
Tests for Multi-Asset Historical Data & Causal MTF Slicer (hitl/replay_data.py)
Covering:
1. Catalog metadata (BTCUSD MANUAL_ONLY, SPX/YM uncalibrated, GBPUSD_o normalized without real_volume)
2. Causal partial HTF bar prevents lookahead (1H and 1D forming bars up to replay_to)
3. Broker day 1D Europe/Athens bounds and DST summer (10800s) vs winter (7200s) offset
4. Max bars truncation cap and safe weekend / empty queries
5. LRU cache eviction (MAX_CACHED_ASSETS = 4)
6. Safe offline fallback for MT5 sync
"""

import datetime
from zoneinfo import ZoneInfo
import pytest

from hitl.replay_data import (
    SYMBOL_CATALOG,
    MAX_CACHED_ASSETS,
    server_epoch_to_zones,
    ReplayDataManager,
)


def test_catalog_marks_btcusd_manual_only_and_loads_gbpusd_without_real_volume():
    """Verifies catalog metadata (BTCUSD engine_mode == 'MANUAL_ONLY', GBPUSD_o loads cleanly despite missing real_volume)."""
    # 1. Verify SYMBOL_CATALOG definitions
    assert "BTCUSD" in SYMBOL_CATALOG
    assert SYMBOL_CATALOG["BTCUSD"]["engine_mode"] == "MANUAL_ONLY"
    assert SYMBOL_CATALOG["BTCUSD"]["uncalibrated"] is False
    assert SYMBOL_CATALOG["BTCUSD"]["spread_pts"] == 0.20

    assert SYMBOL_CATALOG["XAUUSD_o"]["engine_mode"] == "SMC"
    assert SYMBOL_CATALOG["XAUUSD_o"]["uncalibrated"] is False
    assert SYMBOL_CATALOG["XAUUSD_o"]["spread_pts"] == 0.22

    assert SYMBOL_CATALOG["GBPUSD_o"]["engine_mode"] == "SMC"
    assert SYMBOL_CATALOG["GBPUSD_o"]["uncalibrated"] is False
    assert SYMBOL_CATALOG["GBPUSD_o"]["spread_pts"] == 0.00006

    assert SYMBOL_CATALOG["NQ"]["engine_mode"] == "SMC"
    assert SYMBOL_CATALOG["NQ"]["uncalibrated"] is False
    assert SYMBOL_CATALOG["NQ"]["spread_pts"] == 1.0

    assert SYMBOL_CATALOG["SPX"]["engine_mode"] == "SMC"
    assert SYMBOL_CATALOG["SPX"]["uncalibrated"] is True
    assert SYMBOL_CATALOG["SPX"]["spread_pts"] == 0.50

    assert SYMBOL_CATALOG["YM"]["engine_mode"] == "SMC"
    assert SYMBOL_CATALOG["YM"]["uncalibrated"] is True
    assert SYMBOL_CATALOG["YM"]["spread_pts"] == 2.0

    # 2. ReplayDataManager catalog listing
    mgr = ReplayDataManager()
    cat = mgr.get_catalog()
    assert len(cat) == 6
    symbols = {item["symbol"]: item for item in cat}
    assert "BTCUSD" in symbols
    assert symbols["BTCUSD"]["engine_mode"] == "MANUAL_ONLY"
    assert symbols["XAUUSD_o"]["engine_mode"] == "SMC"
    assert "1M" in symbols["XAUUSD_o"]["timeframes"]
    assert "1D" in symbols["XAUUSD_o"]["timeframes"]

    # Shallow copy safety: modifying returned dict must not mutate internal cache
    cat[0]["custom_mutated"] = True
    cat_fresh = mgr.get_catalog()
    assert "custom_mutated" not in cat_fresh[0]

    # 3. GBPUSD_o parquet load: verify real_volume normalized to 0
    df_gbp = mgr.load_m1_df("GBPUSD_o")
    assert len(df_gbp) > 300000
    assert "real_volume" in df_gbp.columns
    assert (df_gbp["real_volume"] == 0.0).all()
    expected_cols = {"time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"}
    assert expected_cols.issubset(set(df_gbp.columns))


def test_causal_partial_htf_bar_prevents_lookahead():
    """
    Queries tf='1H' on 2026-11-11 up to 10:15 server epoch (replay_to);
    verifies the 10:00 bar's High/Low/Close reflects ONLY M1 bars 10:00..10:15,
    NOT the final 10:00..10:59 high/low/close.
    """
    mgr = ReplayDataManager()

    # 2026-11-11 10:00:00 Server epoch = 1794391200
    ep_10 = 1794391200
    # 2026-11-11 10:15:00 Server epoch = 1794392100
    ep_1015 = 1794392100
    # 2026-11-11 12:00:00 Server epoch = 1794398400
    ep_12 = 1794398400

    # Query with replay_to = 10:15 (partial 1H bar in progress)
    res_partial = mgr.get_candles(
        symbol="XAUUSD_o",
        tf="1H",
        start_epoch=ep_10,
        end_epoch=ep_12,
        replay_to=ep_1015,
    )
    assert res_partial["truncated"] is False
    assert res_partial["forming_bar"] is True
    assert len(res_partial["bars"]) == 1

    bar_partial = res_partial["bars"][0]
    assert bar_partial["time"] == ep_10
    # Verified ground truth on M1 bars [10:00..10:15]:
    # High: 4060.26, Low: 4057.05, Close: 4058.39
    assert abs(bar_partial["high"] - 4060.26) < 1e-3
    assert abs(bar_partial["low"] - 4057.05) < 1e-3
    assert abs(bar_partial["close"] - 4058.39) < 1e-3

    # Must be strictly DIFFERENT from the full 1H candle (High: 4061.69, Low: 4055.09)
    assert bar_partial["high"] < 4061.69
    assert bar_partial["low"] > 4055.09

    # Query completed bar without replay_to (full 1H bar)
    res_full = mgr.get_candles(
        symbol="XAUUSD_o",
        tf="1H",
        start_epoch=ep_10,
        end_epoch=ep_12,
        replay_to=None,
    )
    assert res_full["forming_bar"] is False
    bar_full = [b for b in res_full["bars"] if b["time"] == ep_10][0]
    assert abs(bar_full["high"] - 4061.69) < 1e-3
    assert abs(bar_full["low"] - 4055.09) < 1e-3
    assert abs(bar_full["close"] - 4059.08) < 1e-3

    # Causal 1D forming bar check up to 10:15
    day_start = 1794355200  # 2026-11-11 00:00:00 server
    res_1d = mgr.get_candles(
        symbol="XAUUSD_o",
        tf="1D",
        start_epoch=day_start,
        end_epoch=day_start + 86400,
        replay_to=ep_1015,
    )
    assert res_1d["forming_bar"] is True
    assert len(res_1d["bars"]) == 1
    bar_1d = res_1d["bars"][0]
    assert bar_1d["time"] == day_start
    # At 10:15, the 1D candle close MUST equal the 10:15 M1 close (4058.39)
    assert abs(bar_1d["close"] - 4058.39) < 1e-3


def test_historical_closed_window_not_marked_forming_when_replay_to_in_future():
    """
    Regression test: Querying an earlier closed window [08:00, 09:00] while replay_to = 10:15
    must return forming_bar == False and NOT mark bars[-1]["is_forming"].
    """
    mgr = ReplayDataManager()
    ep_08 = 1794384000  # 2026-11-11 08:00:00 server
    ep_09 = 1794387600  # 2026-11-11 09:00:00 server
    ep_1015 = 1794392100  # 2026-11-11 10:15:00 server (replay_to)

    res = mgr.get_candles(
        symbol="XAUUSD_o",
        tf="1H",
        start_epoch=ep_08,
        end_epoch=ep_09,
        replay_to=ep_1015,
    )
    assert res["forming_bar"] is False
    assert len(res["bars"]) == 2  # 08:00 and 09:00 bars
    assert res["bars"][-1]["time"] == ep_09
    assert res["bars"][-1].get("is_forming") is not True

    # When query range extends to cover replay_to (10:15), the 10:00 bar IS forming
    res_covers_cursor = mgr.get_candles(
        symbol="XAUUSD_o",
        tf="1H",
        start_epoch=ep_08,
        end_epoch=ep_1015 + 3600,
        replay_to=ep_1015,
    )
    assert res_covers_cursor["forming_bar"] is True
    assert res_covers_cursor["bars"][-1]["time"] == 1794391200  # 10:00 bar
    assert res_covers_cursor["bars"][-1].get("is_forming") is True


def test_broker_day_1d_and_dst_summer_offset():
    """
    Verifies 1D bar spans Europe/Athens 00:00..23:59 rather than 00:00 UTC,
    and July summer timestamp computes offset_sec == 10800 vs November winter 7200.
    """
    # 1. Europe/Athens summer (EEST = UTC+3) vs winter (EET = UTC+2) offset check
    ep_winter = int(datetime.datetime(2026, 11, 11, 10, 0, tzinfo=datetime.timezone.utc).timestamp())
    zw = server_epoch_to_zones(ep_winter)
    assert zw["offset_sec"] == 7200
    assert zw["srv_str"] == "10:00"
    assert zw["utc_str"] == "08:00"
    assert zw["tehran_str"] == "11:30"

    ep_summer = int(datetime.datetime(2026, 7, 15, 10, 0, tzinfo=datetime.timezone.utc).timestamp())
    zs = server_epoch_to_zones(ep_summer)
    assert zs["offset_sec"] == 10800
    assert zs["srv_str"] == "10:00"
    assert zs["utc_str"] == "07:00"
    assert zs["tehran_str"] == "10:30"

    # 2. Broker day 1D alignment
    mgr = ReplayDataManager()
    day_start = 1794355200  # 2026-11-11 00:00:00 server epoch
    res = mgr.get_candles(
        symbol="XAUUSD_o",
        tf="1D",
        start_epoch=day_start,
        end_epoch=day_start + 86400,
    )
    assert len(res["bars"]) >= 1
    d1_bar = res["bars"][0]
    assert d1_bar["time"] == day_start

    # Check that day_start in server time corresponds to 22:00 UTC of prior day (NOT 00:00 UTC)
    z_day = server_epoch_to_zones(day_start)
    assert z_day["srv_str"] == "00:00"
    assert z_day["utc_str"] == "22:00"


def test_max_bars_cap_and_weekend_range_safe():
    """Queries 30 days of 1M -> returns truncated=True and len(bars) <= 15000; queries Saturday -> returns bars=[] cleanly."""
    mgr = ReplayDataManager()

    # 1. Truncation test: 30 days of 1M (~30,000 bars) with max_bars=15000
    end_ep = 1794415980  # 2026-11-11 16:53:00 server
    start_ep = end_ep - (30 * 86400)
    res = mgr.get_candles(
        symbol="XAUUSD_o",
        tf="1M",
        start_epoch=start_ep,
        end_epoch=end_ep,
        max_bars=15000,
    )
    assert res["truncated"] is True
    assert len(res["bars"]) == 15000

    # 2. Weekend query (Saturday 2026-11-07 00:00..23:59 server)
    sat_start = int(datetime.datetime(2026, 11, 7, 0, 0, tzinfo=datetime.timezone.utc).timestamp())
    res_sat = mgr.get_candles(
        symbol="XAUUSD_o",
        tf="1M",
        start_epoch=sat_start,
        end_epoch=sat_start + 86400,
    )
    assert res_sat["bars"] == []
    assert res_sat["truncated"] is False
    assert res_sat["forming_bar"] is False

    # 3. Direct python calls with max_bars <= 0 return empty bars and truncated=True (not all rows via iloc[-0:])
    res_zero = mgr.get_candles(
        symbol="XAUUSD_o",
        tf="1M",
        start_epoch=start_ep,
        end_epoch=end_ep,
        max_bars=0,
    )
    assert res_zero["bars"] == []
    assert res_zero["truncated"] is True

    res_neg_agg = mgr.get_candles(
        symbol="XAUUSD_o",
        tf="5M",
        start_epoch=start_ep,
        end_epoch=end_ep,
        max_bars=-1,
    )
    assert res_neg_agg["bars"] == []
    assert res_neg_agg["truncated"] is True


def test_lru_cache_eviction():
    """Verifies that LRU cache keeps at most MAX_CACHED_ASSETS DataFrames in memory."""
    mgr = ReplayDataManager()
    assert MAX_CACHED_ASSETS == 4

    # Load 5 distinct symbols
    syms = ["XAUUSD_o", "GBPUSD_o", "NQ", "SPX", "YM"]
    for s in syms:
        df = mgr.load_m1_df(s)
        assert len(df) > 0

    assert len(mgr._cache) == 4
    # The first loaded symbol ("XAUUSD_o") should have been evicted
    assert "XAUUSD_o" not in mgr._cache
    assert "YM" in mgr._cache


def test_offline_mt5_sync_graceful_fallback():
    """Verifies sync_symbol_from_mt5 handles offline MT5 without crashing."""
    mgr = ReplayDataManager()
    # If MT5 is not running/available or terminal is closed, should return success=False safely
    res = mgr.sync_symbol_from_mt5("XAUUSD_o", days_back=5)
    assert isinstance(res, dict)
    assert "success" in res
    assert "symbol" in res
    assert res["symbol"] == "XAUUSD_o"
