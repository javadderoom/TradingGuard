"""
TradingGuard Point-in-Time Causal Data Feed & Portfolio Event Queue
Guarantees zero-lookahead causality across multi-timeframe backtests and holdout evaluations.

Key Guarantees:
1. Strict Bar-Close Visibility:
   A timeframe bar [open_ts, open_ts + tf_seconds) is ONLY visible to detectors
   when decision_ts >= open_ts + tf_seconds.
   Forming candles (open_ts <= decision_ts < open_ts + tf_seconds) are strictly excluded.
2. Unambiguous Prior-Day (T-1) Indexing:
   Daily bars are filtered by open_ts + 86400 <= decision_ts, ensuring closed_1d[-1]
   is strictly the Prior Completed Day (T-1).
3. Dynamic ZoneInfo Conversions:
   Converts MT5 server timestamps via ZoneInfo("Europe/Athens") to UTC, Asia/Tehran,
   Europe/London, and America/New_York, factoring dynamic seasonal DST.
4. Chronological Portfolio Event Queue:
   Tracks open orders, active risk, and realized drawdown strictly at wall-clock
   event timestamps, preventing future exit PnL from leaking into current decisions.
"""

import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
import pandas as pd

# Timezone Singletons
TZ_EU_ATHENS = ZoneInfo("Europe/Athens")
TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_LONDON = ZoneInfo("Europe/London")
TZ_NY = ZoneInfo("America/New_York")
TZ_UTC = datetime.timezone.utc

TIMEFRAME_SECONDS = {
    "1M": 60,
    "5M": 300,
    "15M": 900,
    "1H": 3600,
    "4H": 14400,
    "1D": 86400,
}


def get_causal_slice(
    bars: List[Dict[str, Any]],
    decision_ts: int,
    tf_seconds: int = 300
) -> List[Dict[str, Any]]:
    """
    Returns only closed bars strictly completed at or before decision_ts.
    A bar covering [open_ts, open_ts + tf_seconds) is closed when open_ts + tf_seconds <= decision_ts.
    Any bar currently forming or in the future is excluded.
    """
    if not bars:
        return []
    return [b for b in bars if (int(b['time']) + tf_seconds) <= decision_ts]


def get_causal_d1_slice(
    bars_1d: List[Dict[str, Any]],
    decision_ts: int
) -> List[Dict[str, Any]]:
    """
    Returns closed daily bars completed strictly before the day of decision_ts.
    In broker server time, a daily bar opens at 00:00:00 and closes at 24:00:00 (00:00:00 + 86400s).
    Guarantees that the returned list's last element slice[-1] is strictly Prior Day (T-1).
    """
    if not bars_1d:
        return []
    return [b for b in bars_1d if (int(b['time']) + 86400) <= decision_ts]


def convert_epoch_to_session_context(srv_epoch: int) -> Dict[str, Any]:
    """
    Converts MT5 broker server epoch into complete multi-timezone session context.
    Eliminates static hardcoded seasonal hours by resolving dynamic DST shifts.
    """
    srv_naive = datetime.datetime.fromtimestamp(int(srv_epoch), tz=TZ_UTC).replace(tzinfo=None)
    srv_aware = srv_naive.replace(tzinfo=TZ_EU_ATHENS)
    offset_sec = int(srv_aware.utcoffset().total_seconds())

    utc_dt = srv_aware.astimezone(TZ_UTC)
    teh_dt = srv_aware.astimezone(TZ_TEHRAN)
    lon_dt = srv_aware.astimezone(TZ_LONDON)
    ny_dt = srv_aware.astimezone(TZ_NY)

    # Rollover blackout: 23:45 to 01:05 broker server time
    srv_h = srv_naive.hour
    srv_m = srv_naive.minute
    is_rollover = (srv_h == 23 and srv_m >= 45) or (srv_h == 0) or (srv_h == 1 and srv_m <= 5)

    # London Open Killzone: 08:00 - 10:00 London local time
    lon_h = lon_dt.hour
    lon_m = lon_dt.minute
    is_london_open = (8 <= lon_h < 10)

    # NY Forex Open Killzone: 08:00 - 10:00 NY local time (13:00 - 15:00 UTC)
    ny_h = ny_dt.hour
    ny_m = ny_dt.minute
    is_ny_open = (8 <= ny_h < 10)

    # NYSE Equities Cash Open: 09:30 - 11:30 NY local time
    is_nyse_open = (ny_h == 9 and ny_m >= 30) or (ny_h == 10) or (ny_h == 11 and ny_m <= 30)

    return {
        "srv_epoch": srv_epoch,
        "utc_epoch": int(utc_dt.timestamp()),
        "srv_dt": srv_aware,
        "utc_dt": utc_dt,
        "teh_dt": teh_dt,
        "lon_dt": lon_dt,
        "ny_dt": ny_dt,
        "offset_sec": offset_sec,
        "srv_str": srv_naive.strftime("%H:%M"),
        "utc_str": utc_dt.strftime("%H:%M"),
        "tehran_str": teh_dt.strftime("%H:%M"),
        "london_str": lon_dt.strftime("%H:%M"),
        "ny_str": ny_dt.strftime("%H:%M"),
        "date_str": srv_naive.strftime("%Y-%m-%d"),
        "is_rollover_blackout": is_rollover,
        "is_london_open": is_london_open,
        "is_ny_open": is_ny_open,
        "is_nyse_open": is_nyse_open,
    }


class PortfolioEventQueue:
    """
    Maintains a strict chronological event queue of trades across symbols.
    Ensures concurrency limits, active portfolio risk, and daily drawdowns
    update only after a trade's true exit timestamp has elapsed.
    """

    def __init__(self, max_concurrent: int = 2, max_daily_dd_usd: float = 34.0):
        self.max_concurrent = max_concurrent
        self.max_daily_dd_usd = max_daily_dd_usd
        self.trades: List[Dict[str, Any]] = []

    def record_trade(
        self,
        trade_id: str,
        symbol: str,
        placed_ts: int,
        fill_ts: Optional[int],
        exit_ts: Optional[int],
        status: str,
        risk_usd: float,
        realized_pnl_usd: float,
        date_str: str
    ):
        """Records an evaluated trade into the chronological ledger."""
        self.trades.append({
            "trade_id": trade_id,
            "symbol": symbol,
            "placed_ts": placed_ts,
            "fill_ts": fill_ts,
            "exit_ts": exit_ts,
            "status": status,
            "risk_usd": risk_usd,
            "realized_pnl_usd": realized_pnl_usd,
            "date_str": date_str
        })

    def get_open_trades_at(self, timestamp: int) -> List[Dict[str, Any]]:
        """Returns trades currently active (filled and not yet exited) at timestamp."""
        active = []
        for t in self.trades:
            if t["fill_ts"] is not None and t["fill_ts"] <= timestamp:
                if t["exit_ts"] is None or t["exit_ts"] > timestamp:
                    active.append(t)
        return active

    def get_realized_daily_pnl_usd(self, timestamp: int, date_str: str) -> float:
        """
        Calculates realized daily PnL up to timestamp for the given date.
        Strictly zero lookahead: trades exiting after timestamp are NOT added.
        """
        realized = 0.0
        for t in self.trades:
            if t["date_str"] == date_str:
                if t["exit_ts"] is not None and t["exit_ts"] <= timestamp:
                    realized += t["realized_pnl_usd"]
        return round(realized, 2)

    def can_open_trade(
        self,
        timestamp: int,
        new_risk_usd: float,
        date_str: str
    ) -> Tuple[bool, str]:
        """
        Evaluates portfolio gating at timestamp T:
        1. Daily Drawdown Circuit Breaker (-$34.00 stop)
        2. Concurrent Position Limit (default: max 2 open trades)
        """
        # 1. Circuit breaker check
        realized_today = self.get_realized_daily_pnl_usd(timestamp, date_str)
        if realized_today <= -abs(self.max_daily_dd_usd):
            return False, f"Daily circuit breaker breached (-${abs(realized_today):.2f} <= -${self.max_daily_dd_usd:.2f})"

        # 2. Concurrency check
        open_trades = self.get_open_trades_at(timestamp)
        if len(open_trades) >= self.max_concurrent:
            return False, f"Max concurrent trades reached ({len(open_trades)} >= {self.max_concurrent})"

        return True, "APPROVED"


class CausalDataFeed:
    """
    High-level causal data slicer wrapping historical bar stores.
    Enforces point-in-time causality across 1M, 5M, 1H, and 1D series.
    """

    def __init__(self, bars_dict: Dict[str, Dict[str, List[Dict[str, Any]]]]):
        """
        bars_dict: { symbol: { "1M": [...], "5M": [...], "1H": [...], "1D": [...] } }
        """
        self.bars_dict = bars_dict

    def get_snapshot(
        self,
        symbol: str,
        decision_ts: int,
        lookback_m5: int = 60,
        lookback_h1: int = 24,
        lookback_d1: int = 30
    ) -> Dict[str, Any]:
        """
        Extracts a point-in-time MTF snapshot where every bar is strictly completed
        at or before decision_ts.
        """
        sym_data = self.bars_dict.get(symbol, {})
        raw_m5 = sym_data.get("5M", [])
        raw_h1 = sym_data.get("1H", [])
        raw_d1 = sym_data.get("1D", [])
        raw_m1 = sym_data.get("1M", [])

        # Filter strictly by bar close
        causal_m5 = get_causal_slice(raw_m5, decision_ts, tf_seconds=300)[-lookback_m5:]
        causal_h1 = get_causal_slice(raw_h1, decision_ts, tf_seconds=3600)[-lookback_h1:]
        causal_d1 = get_causal_d1_slice(raw_d1, decision_ts)[-lookback_d1:]
        causal_m1 = get_causal_slice(raw_m1, decision_ts, tf_seconds=60)[-120:] if raw_m1 else None

        # Session context at decision timestamp
        session_info = convert_epoch_to_session_context(decision_ts)

        return {
            "symbol": symbol,
            "decision_ts": decision_ts,
            "bars_5m": causal_m5,
            "bars_1h": causal_h1,
            "bars_1d": causal_d1,
            "bars_1m": causal_m1,
            "session_info": session_info,
        }
