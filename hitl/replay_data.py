"""
TradingGuard HITL - Multi-Asset Historical Data & Causal MTF Resampler
Provides:
- SYMBOL_CATALOG: Unified registry of cached 2026 Parquet instruments, execution engine modes,
  uncalibrated index badges, and conservative broker spread points.
- server_epoch_to_zones: Accurate EET/EEST (Europe/Athens) to UTC and Asia/Tehran timezone resolver
  factoring dynamic seasonal DST shifts (7200s winter vs 10800s summer).
- ReplayDataManager: High-performance LRU-cached (MAX_CACHED_ASSETS = 4) M1 reader and causal MTF
  resampler (1M, 5M, 15M, 1H, 4H, 1D on Europe/Athens broker days) with zero-lookahead partial bar synthesis.
"""

import collections
import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import pandas as pd
import pyarrow.parquet as pq

# Europe/Athens DST rules (EET UTC+2 winter / EEST UTC+3 summer)
TZ_EU_ATHENS = ZoneInfo("Europe/Athens")
# Tehran permanently abolished DST (fixed UTC+3:30 year-round)
TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_UTC = datetime.timezone.utc

MAX_CACHED_ASSETS = 4

TIMEFRAME_SECONDS: Dict[str, int] = {
    "1M": 60,
    "5M": 300,
    "15M": 900,
    "1H": 3600,
    "4H": 14400,
    "1D": 86400,
}

SYMBOL_CATALOG: Dict[str, Dict[str, Any]] = {
    "XAUUSD_o": {
        "cache_file": "M1_XAUUSD_o_2026.parquet",
        "engine_mode": "SMC",
        "uncalibrated": False,
        "spread_pts": 0.22,
        "digits": 2,
        "display_name": "Gold (Spot / USD)",
    },
    "GBPUSD_o": {
        "cache_file": "M1_GBPUSD_o_2026.parquet",
        "engine_mode": "SMC",
        "uncalibrated": False,
        "spread_pts": 0.00006,
        "digits": 5,
        "display_name": "GBP/USD (Cable)",
    },
    "NQ": {
        "cache_file": "NQ_M1_EXTENDED_2026.parquet",
        "engine_mode": "SMC",
        "uncalibrated": False,
        "spread_pts": 1.0,
        "digits": 2,
        "display_name": "Nasdaq 100 Index",
    },
    "SPX": {
        "cache_file": "SPX_M1_2026.parquet",
        "engine_mode": "SMC",
        "uncalibrated": True,
        "spread_pts": 0.50,
        "digits": 2,
        "display_name": "S&P 500 Index (Uncalibrated)",
    },
    "YM": {
        "cache_file": "YM_M1_2026.parquet",
        "engine_mode": "SMC",
        "uncalibrated": True,
        "spread_pts": 2.0,
        "digits": 2,
        "display_name": "Dow Jones 30 Index (Uncalibrated)",
    },
    "BTCUSD": {
        "cache_file": "BTCUSD_M1_2026.parquet",
        "engine_mode": "MANUAL_ONLY",
        "uncalibrated": False,
        "spread_pts": 0.20,
        "digits": 2,
        "display_name": "Bitcoin / USD (Manual Only)",
    },
}


def server_epoch_to_zones(srv_epoch: int) -> Dict[str, Any]:
    """
    MT5 broker timestamps represent EET (UTC+2) / EEST (UTC+3) server wall-clock time
    encoded as integer epochs.
    Converts cleanly to:
    - srv_str: '%H:%M' server time
    - utc_str: '%H:%M' UTC time
    - tehran_str: '%H:%M' Tehran time
    - utc_epoch: int UTC epoch
    - offset_sec: EET/EEST offset (7200 in winter, 10800 in summer)
    - date_str: '%Y-%m-%d' server date
    - utc_dt: aware datetime in UTC
    - teh_dt: aware datetime in Tehran
    """
    srv_naive = datetime.datetime.fromtimestamp(int(srv_epoch), tz=TZ_UTC).replace(tzinfo=None)
    srv_aware = srv_naive.replace(tzinfo=TZ_EU_ATHENS)
    offset_sec = int(srv_aware.utcoffset().total_seconds())
    utc_dt = srv_aware.astimezone(TZ_UTC)
    teh_dt = srv_aware.astimezone(TZ_TEHRAN)
    return {
        "srv_str": srv_naive.strftime("%H:%M"),
        "utc_str": utc_dt.strftime("%H:%M"),
        "tehran_str": teh_dt.strftime("%H:%M"),
        "utc_epoch": int(utc_dt.timestamp()),
        "offset_sec": offset_sec,
        "date_str": srv_naive.strftime("%Y-%m-%d"),
        "utc_dt": utc_dt,
        "teh_dt": teh_dt,
    }


class ReplayDataManager:
    """Manages cached Parquet asset frames and provides causal multi-timeframe slicing."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.project_root = Path(__file__).resolve().parent.parent
        self.cache_dir = Path(cache_dir) if cache_dir else self.project_root / "backtest_results" / "cache"
        self._cache: collections.OrderedDict[str, pd.DataFrame] = collections.OrderedDict()
        self._catalog_cache: Optional[List[Dict[str, Any]]] = None

    def get_catalog(self) -> List[Dict[str, Any]]:
        """Returns catalog listing of all supported instruments with date bounds and execution mode."""
        if self._catalog_cache is not None:
            return self._catalog_cache

        catalog_list: List[Dict[str, Any]] = []
        for symbol, meta in SYMBOL_CATALOG.items():
            cache_file = meta["cache_file"]
            file_path = self.cache_dir / cache_file

            min_epoch: Optional[int] = None
            max_epoch: Optional[int] = None
            min_date: Optional[str] = None
            max_date: Optional[str] = None
            bars_count: int = 0

            if file_path.exists():
                try:
                    # Quick read of time column only for fast bounds extraction
                    tbl = pq.read_table(str(file_path), columns=["time"])
                    bars_count = len(tbl)
                    if bars_count > 0:
                        min_epoch = int(tbl["time"][0].as_py())
                        max_epoch = int(tbl["time"][-1].as_py())
                        min_date = server_epoch_to_zones(min_epoch)["date_str"]
                        max_date = server_epoch_to_zones(max_epoch)["date_str"]
                except Exception:
                    pass

            catalog_list.append({
                "symbol": symbol,
                "cache_file": cache_file,
                "engine_mode": meta["engine_mode"],
                "uncalibrated": meta["uncalibrated"],
                "spread_pts": meta["spread_pts"],
                "digits": meta.get("digits", 2),
                "display_name": meta.get("display_name", symbol),
                "timeframes": ["1M", "5M", "15M", "1H", "4H", "1D"],
                "min_epoch": min_epoch,
                "max_epoch": max_epoch,
                "min_date": min_date,
                "max_date": max_date,
                "bars_count": bars_count,
            })

        self._catalog_cache = catalog_list
        return catalog_list

    def load_m1_df(self, symbol: str) -> pd.DataFrame:
        """
        Loads the 1-minute Parquet dataset into an LRU cache (MAX_CACHED_ASSETS = 4).
        Normalizes columns cleanly (filling missing real_volume with 0.0).
        """
        if symbol not in SYMBOL_CATALOG:
            raise KeyError(f"Symbol '{symbol}' not recognized in SYMBOL_CATALOG")

        if symbol in self._cache:
            self._cache.move_to_end(symbol)
            return self._cache[symbol]

        file_name = SYMBOL_CATALOG[symbol]["cache_file"]
        file_path = self.cache_dir / file_name
        if not file_path.exists():
            raise FileNotFoundError(f"Cache file '{file_path}' does not exist for symbol '{symbol}'")

        df = pd.read_parquet(file_path)

        # Normalize time column
        if "time" in df.columns:
            df["time"] = df["time"].astype("int64")
        else:
            raise ValueError(f"Parquet dataset '{file_name}' lacks required 'time' column")

        # Normalize missing or null real_volume (e.g. GBPUSD_o)
        if "real_volume" not in df.columns:
            df["real_volume"] = 0.0
        else:
            df["real_volume"] = df["real_volume"].fillna(0.0).astype("float64")

        # Normalize spread if missing
        if "spread" not in df.columns:
            df["spread"] = 0
        else:
            df["spread"] = df["spread"].fillna(0).astype("int64")

        # Ensure standard OHLCV types
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype("float64")
        if "tick_volume" in df.columns:
            df["tick_volume"] = df["tick_volume"].astype("float64")
        else:
            df["tick_volume"] = 0.0

        # Sort and deduplicate on timestamp
        df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)

        # LRU eviction
        if len(self._cache) >= MAX_CACHED_ASSETS:
            self._cache.popitem(last=False)

        self._cache[symbol] = df
        return df

    def get_candles(
        self,
        symbol: str,
        tf: str,
        start_epoch: int,
        end_epoch: int,
        replay_to: Optional[int] = None,
        max_bars: int = 15000,
    ) -> Dict[str, Any]:
        """
        Retrieves candlesticks resampled to requested timeframe ('1M','5M','15M','1H','4H','1D').
        Enforces zero-lookahead:
        - When replay_to is set, M1 data is sliced strictly to M1 <= replay_to.
        - Higher timeframe bars completing after replay_to are synthesized strictly from M1 bars
          up to replay_to, returning forming_bar = True.
        - Groups 1D and 4H strictly on Europe/Athens broker-day 00:00 server boundaries.
        """
        if tf not in TIMEFRAME_SECONDS:
            raise ValueError(f"Unsupported timeframe '{tf}'. Valid options: {list(TIMEFRAME_SECONDS.keys())}")

        bucket_sec = TIMEFRAME_SECONDS[tf]

        # Guard against queries beyond replay cursor
        if replay_to is not None and start_epoch > replay_to:
            return {"bars": [], "truncated": False, "forming_bar": False}

        effective_end = min(end_epoch, replay_to) if replay_to is not None else end_epoch
        if effective_end < start_epoch:
            return {"bars": [], "truncated": False, "forming_bar": False}

        # Align start down to bucket start so initial bar captures full historical bucket
        aligned_start = (start_epoch // bucket_sec) * bucket_sec

        df = self.load_m1_df(symbol)
        m1_slice = df[(df["time"] >= aligned_start) & (df["time"] <= effective_end)]

        if m1_slice.empty:
            return {"bars": [], "truncated": False, "forming_bar": False}

        # Determine if a higher-timeframe forming bar is currently in progress at effective_end / replay_to
        forming_bar = False
        if replay_to is not None and tf != "1M":
            replay_bucket = (replay_to // bucket_sec) * bucket_sec
            # If replay_to hasn't reached the final minute of the bucket period
            if replay_to < (replay_bucket + bucket_sec - 60):
                forming_bar = True

        # Fast path for 1M: atomic resolution, no aggregation needed
        if tf == "1M":
            # Slice strictly within [start_epoch, effective_end]
            bars_df = m1_slice[m1_slice["time"] >= start_epoch]
            if bars_df.empty:
                return {"bars": [], "truncated": False, "forming_bar": False}

            truncated = len(bars_df) > max_bars
            if truncated:
                bars_df = bars_df.iloc[-max_bars:]

            bars = [
                {
                    "time": int(t),
                    "open": float(o),
                    "high": float(h),
                    "low": float(l),
                    "close": float(c),
                    "tick_volume": float(tv),
                    "spread": int(s),
                    "real_volume": float(rv),
                }
                for t, o, h, l, c, tv, s, rv in zip(
                    bars_df["time"],
                    bars_df["open"],
                    bars_df["high"],
                    bars_df["low"],
                    bars_df["close"],
                    bars_df["tick_volume"],
                    bars_df["spread"],
                    bars_df["real_volume"],
                )
            ]
            return {
                "bars": bars,
                "truncated": truncated,
                "forming_bar": forming_bar,
            }

        # HTF aggregation path (5M, 15M, 1H, 4H, 1D)
        # Broker day / 4H / 1H boundaries naturally align on server epoch // bucket_sec
        # because Parquet time column represents Europe/Athens wall-clock epoch.
        m1_slice = m1_slice.copy()
        m1_slice["bucket"] = (m1_slice["time"] // bucket_sec) * bucket_sec

        agg_df = m1_slice.groupby("bucket", as_index=False).agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            tick_volume=("tick_volume", "sum"),
            spread=("spread", "last"),
            real_volume=("real_volume", "sum"),
        ).rename(columns={"bucket": "time"})

        truncated = len(agg_df) > max_bars
        if truncated:
            agg_df = agg_df.iloc[-max_bars:]

        bars = [
            {
                "time": int(t),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "tick_volume": float(tv),
                "spread": int(s),
                "real_volume": float(rv),
            }
            for t, o, h, l, c, tv, s, rv in zip(
                agg_df["time"],
                agg_df["open"],
                agg_df["high"],
                agg_df["low"],
                agg_df["close"],
                agg_df["tick_volume"],
                agg_df["spread"],
                agg_df["real_volume"],
            )
        ]

        if forming_bar and len(bars) > 0:
            bars[-1]["is_forming"] = True

        return {
            "bars": bars,
            "truncated": truncated,
            "forming_bar": forming_bar,
        }

    def sync_symbol_from_mt5(self, symbol: str, days_back: int = 5) -> Dict[str, Any]:
        """
        Synchronizes latest M1 rates from running MetaTrader 5 terminal if available.
        Provides a graceful offline fallback if MT5 is closed or disconnected.
        """
        if symbol not in SYMBOL_CATALOG:
            return {
                "success": False,
                "symbol": symbol,
                "bars_added": 0,
                "total_bars": 0,
                "message": f"Symbol '{symbol}' not in SYMBOL_CATALOG",
            }

        try:
            from hitl.mt5_engine import MT5Engine
            engine = MT5Engine()
            if not engine.ensure_connected():
                cached_bars = len(self._cache[symbol]) if symbol in self._cache else 0
                return {
                    "success": False,
                    "symbol": symbol,
                    "bars_added": 0,
                    "total_bars": cached_bars,
                    "message": "MetaTrader 5 terminal is offline or disconnected",
                }
        except Exception as e:
            return {
                "success": False,
                "symbol": symbol,
                "bars_added": 0,
                "total_bars": 0,
                "message": f"MT5 connection check failed: {e}",
            }

        try:
            import MetaTrader5 as mt5

            # Find matching symbol on broker (e.g. XAUUSD_o vs XAUUSD)
            broker_sym = symbol
            if not mt5.symbol_info(broker_sym):
                alt_sym = symbol.replace("_o", "") if "_o" in symbol else f"{symbol}_o"
                if mt5.symbol_info(alt_sym):
                    broker_sym = alt_sym
                else:
                    return {
                        "success": False,
                        "symbol": symbol,
                        "bars_added": 0,
                        "total_bars": 0,
                        "message": f"Broker symbol '{symbol}' not found in MT5",
                    }

            count = max(1000, days_back * 1440)
            rates = mt5.copy_rates_from_pos(broker_sym, mt5.TIMEFRAME_M1, 0, count)
            if rates is None or len(rates) == 0:
                return {
                    "success": False,
                    "symbol": symbol,
                    "bars_added": 0,
                    "total_bars": 0,
                    "message": "No rates returned from MT5 terminal",
                }

            cols = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
            df_new = pd.DataFrame(rates)
            for c in cols:
                if c not in df_new.columns:
                    df_new[c] = 0.0

            df_new = df_new[cols]
            df_existing = self.load_m1_df(symbol)

            df_merged = pd.concat([df_existing, df_new], ignore_index=True)
            df_merged = df_merged.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
            bars_added = len(df_merged) - len(df_existing)

            # Persist updated cache file
            file_path = self.cache_dir / SYMBOL_CATALOG[symbol]["cache_file"]
            df_merged.to_parquet(file_path, index=False)

            # Update in-memory LRU cache
            self._cache[symbol] = df_merged
            self._catalog_cache = None  # invalidate catalog cache

            return {
                "success": True,
                "symbol": symbol,
                "bars_added": bars_added,
                "total_bars": len(df_merged),
                "message": f"Successfully synced {bars_added} new M1 bars from MT5",
            }
        except Exception as e:
            return {
                "success": False,
                "symbol": symbol,
                "bars_added": 0,
                "total_bars": 0,
                "message": f"MT5 sync failed: {e}",
            }
