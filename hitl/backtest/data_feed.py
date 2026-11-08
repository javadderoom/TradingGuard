"""
TradingGuard HITL - Backtest Historical Data & Chart Feed
Fetches historical MTF bars strictly up to timestamp T (zero lookahead)
and renders the 4 chart images required by the AI Investment Council.
Also retrieves forward M1 bars for trade outcome evaluation.
"""

import sys
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import MetaTrader5 as mt5

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.chart_renderer import render_candlestick_chart
from hitl.mt5_engine import MT5Engine

MTF_BACKTEST_DIR = BASE_DIR / "analysis_assets" / "backtest_mtf"
MTF_BACKTEST_DIR.mkdir(parents=True, exist_ok=True)


def _convert_records(bars) -> List[Dict[str, Any]]:
    if bars is None or len(bars) == 0:
        return []
    return [
        {
            'time': int(b[0]),
            'dt': datetime.datetime.fromtimestamp(int(b[0]), tz=datetime.timezone.utc),
            'open': float(b[1]),
            'high': float(b[2]),
            'low': float(b[3]),
            'close': float(b[4]),
            'tick_volume': int(b[5])
        }
        for b in bars
    ]


def _ceil_to_5m_boundary(dt: datetime.datetime) -> datetime.datetime:
    """Rounds a timestamp up to the next 5-minute bar boundary (unchanged if
    already on one). A 5M bar that starts at T closes at T+5m, so a forward
    window starting inside that bar would include the signal bar itself."""
    if dt.second == 0 and dt.microsecond == 0 and dt.minute % 5 == 0:
        return dt
    base = dt.replace(second=0, microsecond=0)
    add = 5 - (dt.minute % 5)
    return base + datetime.timedelta(minutes=add)


class HistoricalDataFeed:
    def __init__(self):
        self.engine = MT5Engine()

    def prepare_session_dossier(
        self,
        symbol: str,
        target_time: datetime.datetime,
        num_bars: int = 60
    ) -> Optional[Dict[str, Any]]:
        """
        Gathers historical MTF bars ending strictly at or before target_time (no lookahead).
        Renders 1D, 1H, 15M, and 5M chart images and returns their paths and latest quote at T.
        """
        if not self.engine.ensure_connected():
            return None

        resolved = self.engine.resolve_symbol(symbol)
        if not resolved:
            return None

        # Slices up to target_time
        # copy_rates_from returns 'count' bars ending at or before date_from
        rates_1d = mt5.copy_rates_from(resolved, mt5.TIMEFRAME_D1, target_time, num_bars)
        rates_1h = mt5.copy_rates_from(resolved, mt5.TIMEFRAME_H1, target_time, num_bars)
        rates_15m = mt5.copy_rates_from(resolved, mt5.TIMEFRAME_M15, target_time, num_bars)
        rates_5m = mt5.copy_rates_from(resolved, mt5.TIMEFRAME_M5, target_time, num_bars)

        list_1d = _convert_records(rates_1d)
        list_1h = _convert_records(rates_1h)
        list_15m = _convert_records(rates_15m)
        list_5m = _convert_records(rates_5m)

        if not (list_1d and list_1h and list_15m and list_5m):
            print(f"[DataFeed] Incomplete bar series at {target_time}")
            return None

        # Verify strict no-lookahead: last bar time must be <= target_time
        t_epoch = int(target_time.timestamp())
        if list_5m[-1]['time'] > t_epoch:
            print(f"[DataFeed] Warning: lookahead detected on 5M bars! ({list_5m[-1]['time']} > {t_epoch})")
            return None

        sym_clean = symbol.replace("/", "").replace("_", "").upper()
        if "XAU" in sym_clean:
            sym_clean = "XAUUSD"
        elif "XAG" in sym_clean:
            sym_clean = "XAGUSD"
        elif "EUR" in sym_clean:
            sym_clean = "EURUSD"
        elif "GBP" in sym_clean:
            sym_clean = "GBPUSD"
        elif "BTC" in sym_clean:
            sym_clean = "BTCUSD"
        p_1d = MTF_BACKTEST_DIR / f"{sym_clean}_1D.png"
        p_1h = MTF_BACKTEST_DIR / f"{sym_clean}_1H.png"
        p_15m = MTF_BACKTEST_DIR / f"{sym_clean}_15M.png"
        p_5m = MTF_BACKTEST_DIR / f"{sym_clean}_5M.png"

        # Render charts
        render_candlestick_chart(list_1d, sym_clean, "1D", p_1d)
        render_candlestick_chart(list_1h, sym_clean, "1H", p_1h)
        render_candlestick_chart(list_15m, sym_clean, "15M", p_15m)
        render_candlestick_chart(list_5m, sym_clean, "5M", p_5m)

        # Quote at T
        latest_5m = list_5m[-1]
        close_price = latest_5m['close']

        # Get USDX at T if available
        usdx_sym = self.engine.resolve_symbol("USDX")
        usdx_price = 101.75
        if usdx_sym:
            usdx_bars = mt5.copy_rates_from(usdx_sym, mt5.TIMEFRAME_H1, target_time, 1)
            if usdx_bars is not None and len(usdx_bars) > 0:
                usdx_price = float(usdx_bars[0][4])

        # Extract Hybrid Telemetry (Exact mathematical SMC landmarks)
        from hitl.backtest.hybrid_telemetry import extract_hybrid_telemetry, format_telemetry_prompt
        from hitl.macro_bias import calculate_htf_fundamental_bias, format_fundamental_bias_prompt
        from hitl.tools.smc_tools import get_smc_landmarks, format_smc_tools_block

        last_bar_time = list_5m[-1]['time'] if list_5m else 0
        dt_utc = datetime.datetime.fromtimestamp(last_bar_time, datetime.timezone.utc)
        # Note: MT5 Strategy Tester historical database replays directly on raw UTC bar timestamps.
        # To guarantee zero lookahead and exact tick-level synchronization with StringToTime() in MT5 Strategy Tester,
        # trigger timestamps must match the tester's native bar clock (dt_utc).
        dt_tester = dt_utc

        landmarks = get_smc_landmarks(
            list_1d, list_1h, list_15m, list_5m,
            symbol=sym_clean,
            current_bid=close_price,
            current_ask=close_price + (0.00020 if "GBP" in sym_clean or "EUR" in sym_clean else 0.05),
            broker_time=dt_tester
        )
        tools_prompt = format_smc_tools_block(landmarks)

        telemetry = extract_hybrid_telemetry(
            list_1d, list_1h, list_15m, list_5m,
            symbol=sym_clean,
            session_hour=target_time.hour,
            usdx_quote=usdx_price
        )
        telemetry_prompt = format_telemetry_prompt(telemetry, sym_clean)

        # Compute Active HTF Fundamental Directional Bias
        macro_bias_data = calculate_htf_fundamental_bias(sym_clean, target_time=target_time)
        macro_bias_prompt = format_fundamental_bias_prompt(macro_bias_data)

        # Prepend Fundamental Macro Bias and SMC Tools Artifacts to Telemetry Prompt
        combined_telemetry_prompt = macro_bias_prompt + "\n\n" + tools_prompt + "\n\n" + telemetry_prompt

        return {
            "symbol": sym_clean,
            "resolved_symbol": resolved,
            "target_time": target_time,
            "broker_time": dt_tester,
            "chart_paths": [p_1d, p_1h, p_15m, p_5m],
            "price_at_t": close_price,
            "usdx_at_t": usdx_price,
            "telemetry": telemetry,
            "landmarks": landmarks,
            "telemetry_prompt": combined_telemetry_prompt,
            "macro_bias_data": macro_bias_data
        }

    def get_forward_m1_bars(
        self,
        symbol: str,
        start_time: datetime.datetime,
        hours_forward: int = 8,
        closed_bars_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Fetches M1 bars forward from start_time to start_time + hours_forward.
        Used to simulate order filling, watchdog cancellations, and SL/TP hits.

        Closed-bars only (closed_bars_only=True, the default): start_time is
        the close of the signal bar, so the first forward M1 bar must be the
        minute *after* that close. mt5.copy_rates_range() includes the bar
        starting at start_time, which is the signal bar itself if start_time
        falls inside a 5M bar — a trade could then fill / hit TP / hit SL
        during the very bar whose close created the signal, i.e. before the
        signal existed. With the default, start_time is rounded up to the
        next 5M boundary first (a no-op when it is already on one, which is
        the case for the session milestones the runners use).
        """
        if closed_bars_only:
            start_time = _ceil_to_5m_boundary(start_time)

        resolved = self.engine.resolve_symbol(symbol)
        if not resolved:
            return []

        end_time = start_time + datetime.timedelta(hours=hours_forward)
        bars = mt5.copy_rates_range(resolved, mt5.TIMEFRAME_M1, start_time, end_time)
        return _convert_records(bars)


if __name__ == "__main__":
    feed = HistoricalDataFeed()
    # Test with yesterday's London Open
    test_dt = datetime.datetime.now() - datetime.timedelta(days=1)
    test_dt = test_dt.replace(hour=10, minute=30, second=0, microsecond=0)
    print(f"Testing session dossier at: {test_dt}")
    dossier = feed.prepare_session_dossier("XAUUSD", test_dt)
    if dossier:
        print("Dossier ready! Charts rendered:")
        for p in dossier["chart_paths"]:
            print(f" - {p.name} (exists={p.exists()})")
        print(f"Price at T: {dossier['price_at_t']}")
        fwd_bars = feed.get_forward_m1_bars("XAUUSD", test_dt, hours_forward=4)
        print(f"Forward M1 bars fetched: {len(fwd_bars)}")
    else:
        print("Failed to prepare session dossier.")
