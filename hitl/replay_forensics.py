"""
TradingGuard HITL - SMC Forensic Scanner & System Risk Governor
Provides:
- detect_fvg_boxes: Extracts exact Fair Value Gap 2D coordinates (top, bottom, t_start, t_end, dir).
- detect_breaker_boxes: Extracts Market Structure Shift & Breaker Block coordinates (top, bottom, t_start, t_end, type).
- run_bot_scan: Full chronological SMC session scanner across 5M bars enforcing:
  * true_tehran vs live_legacy timezone handling (with broker UTC offset shimming).
  * Anti-spoiler incremental Asian Range boundaries (never leaking prior to 07:00 UTC).
  * System-wide risk governance ($2,000 reference equity, $20 per-trade risk cap, max 3 open positions,
    $80 daily drawdown limit, $200 overall trailing drawdown limit, 30m duplicate-wave guard).
  * SETUP-ARCH-013 structural Draw on Liquidity runner (target_rr_cap=7.5).
  * Marked BOT trades and comprehensive performance scorecard.
- simulate_custom_trade: Canonical M1 simulation for human-proposed and human-edited setups
  without R:R clipping + $20 risk limit compliance badge.
"""

import collections
import datetime
import threading
from typing import Any, Dict, List, Optional, Tuple

from hitl.replay_data import (
    SYMBOL_CATALOG,
    ReplayDataManager,
    server_epoch_to_zones,
    TZ_UTC,
    TZ_TEHRAN,
)
from hitl.replay_ledger import calculate_trade_risk_usd
from hitl.backtest.session_clock import get_session_times_for_date
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.evaluator import evaluate_council_decision
from hitl.screener_gate import tehran_hour_from_bar_time
import hitl.backtest.chart_renderer as chart_renderer

# Module-level lock guarding global chart_renderer offset shimming during concurrent bot scans
_SCREENER_OFFSET_LOCK = threading.Lock()


def detect_fvg_boxes(
    bars: List[Dict[str, Any]],
    lookback: int = 12,
    symbol: str = "XAUUSD"
) -> Optional[Dict[str, Any]]:
    """
    Detects 3-candle Fair Value Gap in recent 5M bars and computes box boundary coordinates.
    Returns: {top, bottom, t_start, t_end, dir} or None
    """
    if len(bars) < 3:
        return None

    sym = symbol.upper()
    is_spx = "SPX" in sym or "US500" in sym
    is_ym = "YM" in sym or "US30" in sym or "DOW" in sym
    is_nq = "NQ" in sym or "NAS" in sym or "US100" in sym
    is_crypto = "BTC" in sym or "ETH" in sym
    is_gold = "XAU" in sym
    is_silver = "XAG" in sym

    if is_spx:
        min_gap = 1.5
        min_body = 2.5
    elif is_ym:
        min_gap = 8.0
        min_body = 15.0
    elif is_nq:
        min_gap = 5.0
        min_body = 10.0
    elif is_crypto:
        min_gap = 25.0 if "BTC" in sym else 2.0
        min_body = 45.0 if "BTC" in sym else 3.0
    elif is_gold:
        min_gap = 1.0
        min_body = 1.5
    elif is_silver:
        min_gap = 0.05
        min_body = 0.08
    else:
        min_gap = 0.0003
        min_body = 0.0004

    recent = bars[-lookback:]
    for i in range(len(recent) - 1, 1, -1):
        c1 = recent[i - 2]
        c2 = recent[i - 1]
        c3 = recent[i]

        # Bullish FVG: Candle 1 High < Candle 3 Low
        if c3["low"] > c1["high"]:
            gap_size = c3["low"] - c1["high"]
            body_size = abs(c2["close"] - c2["open"])
            if gap_size >= min_gap and body_size >= min_body and body_size > gap_size:
                return {
                    "top": c3["low"],
                    "bottom": c1["high"],
                    "t_start": c1["time"],
                    "t_end": c3["time"],
                    "dir": "BULLISH",
                }

        # Bearish FVG: Candle 1 Low > Candle 3 High
        if c1["low"] > c3["high"]:
            gap_size = c1["low"] - c3["high"]
            body_size = abs(c2["close"] - c2["open"])
            if gap_size >= min_gap and body_size >= min_body and body_size > gap_size:
                return {
                    "top": c1["low"],
                    "bottom": c3["high"],
                    "t_start": c1["time"],
                    "t_end": c3["time"],
                    "dir": "BEARISH",
                }

    return None


def detect_breaker_boxes(
    bars: List[Dict[str, Any]],
    lookback: int = 24,
    symbol: str = "XAUUSD"
) -> Optional[Dict[str, Any]]:
    """
    Detects Market Structure Shift and resulting Breaker Block box coordinates.
    Returns: {top, bottom, t_start, t_end, type} or None
    """
    if len(bars) < 15:
        return None

    sym = symbol.upper()
    is_spx = "SPX" in sym or "US500" in sym
    is_ym = "YM" in sym or "US30" in sym or "DOW" in sym
    is_nq = "NQ" in sym or "NAS" in sym or "US100" in sym
    is_crypto = "BTC" in sym or "ETH" in sym
    is_gold = "XAU" in sym
    is_silver = "XAG" in sym

    if is_spx:
        min_swing_height = 6.0
    elif is_ym:
        min_swing_height = 40.0
    elif is_nq:
        min_swing_height = 25.0
    elif is_crypto:
        min_swing_height = 120.0 if "BTC" in sym else 8.0
    elif is_gold:
        min_swing_height = 4.0
    elif is_silver:
        min_swing_height = 0.25
    else:
        min_swing_height = 0.0015

    recent = bars[-lookback:]
    current_close = recent[-1]["close"]

    highs = [
        (idx, b["high"])
        for idx, b in enumerate(recent[:-2])
        if idx >= 2 and b["high"] >= recent[idx - 1]["high"] and b["high"] >= recent[idx + 1]["high"]
    ]
    lows = [
        (idx, b["low"])
        for idx, b in enumerate(recent[:-2])
        if idx >= 2 and b["low"] <= recent[idx - 1]["low"] and b["low"] <= recent[idx + 1]["low"]
    ]

    if not (highs and lows):
        return None

    last_high_idx, last_high_val = highs[-1]
    last_low_idx, last_low_val = lows[-1]

    if abs(last_high_val - last_low_val) < min_swing_height:
        return None

    # Bearish MSS: Price broke below last structural swing low
    if current_close < last_low_val and last_high_idx < last_low_idx:
        broken_candle = recent[last_low_idx]
        return {
            "top": broken_candle["high"],
            "bottom": broken_candle["low"],
            "t_start": broken_candle["time"],
            "t_end": recent[-1]["time"],
            "type": "BEARISH_BREAKER",
        }

    # Bullish MSS: Price broke above last structural swing high
    if current_close > last_high_val and last_low_idx < last_high_idx:
        broken_candle = recent[last_high_idx]
        return {
            "top": broken_candle["high"],
            "bottom": broken_candle["low"],
            "t_start": broken_candle["time"],
            "t_end": recent[-1]["time"],
            "type": "BULLISH_BREAKER",
        }

    return None


def run_bot_scan(
    data_mgr: ReplayDataManager,
    symbol: str,
    start_epoch: int,
    end_epoch: int,
    clock_mode: str = "true_tehran",
    account_size_usd: float = 2000.0,
    max_risk_usd: float = 20.0,
    horizon: str = "window",
) -> Dict[str, Any]:
    """
    Chronological SMC forensic scanner across 5M bars.
    Enforces TradingGuard's real system-wide risk limits:
    - max_open_trades = 3
    - max_concurrent_risk = 2.0% ($40.00 total)
    - max_daily_drawdown = 4.0% ($80.00 / day)
    - max_overall_drawdown = 10.0% ($200.00 trailing HWM)
    - 30m duplicate signal cooldown
    """
    sym_clean = symbol.strip()
    catalog_meta = SYMBOL_CATALOG.get(sym_clean, {})
    spread_pts = catalog_meta.get("spread_pts", 0.22)

    # Load 5M bars covering lookback window (7 days prior for 5M history)
    lookback_5m_sec = 86400 * 7
    all_5m = data_mgr.get_candles(sym_clean, "5M", start_epoch - lookback_5m_sec, end_epoch)["bars"]
    if not all_5m:
        return {
            "killzones": [],
            "asian_ranges_by_day": {},
            "diagnostics": [],
            "events": [],
            "bot_trades": [],
            "bot_scorecard": {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "breakevens": 0,
                "win_rate_pct": 0.0,
                "net_pnl_usd": 0.0,
                "net_rr": 0.0,
                "profit_factor": 0.0,
                "max_drawdown_usd": 0.0,
            },
        }

    # Load HTF bars for MTF context (15 days 1H, 60 days 1D)
    all_1h = data_mgr.get_candles(sym_clean, "1H", start_epoch - (86400 * 15), end_epoch)["bars"]
    all_1d = data_mgr.get_candles(sym_clean, "1D", start_epoch - (86400 * 60), end_epoch)["bars"]

    # Pre-attach true UTC 'dt' to historical bars for MTF detectors
    for b in all_5m:
        b["dt"] = server_epoch_to_zones(b["time"])["utc_dt"]
    for b in all_1h:
        b["dt"] = server_epoch_to_zones(b["time"])["utc_dt"]
    for b in all_1d:
        b["dt"] = server_epoch_to_zones(b["time"])["utc_dt"]

    # Load M1 bars for forward simulation
    m1_df = data_mgr.load_m1_df(sym_clean)

    # Determine unique days in scan range for Killzones and Asian range benchmarks
    scan_bars = [b for b in all_5m if start_epoch <= b["time"] <= end_epoch]
    dates_in_scan = sorted(list({server_epoch_to_zones(b["time"])["date_str"] for b in scan_bars}))

    # 1. Compute Killzones
    killzones: List[Dict[str, Any]] = []
    for d_str in dates_in_scan:
        try:
            d_obj = datetime.date.fromisoformat(d_str)
            stimes = get_session_times_for_date(d_obj)

            # Asian Session: 00:00 to 07:00 UTC
            asian_start_utc = datetime.datetime(d_obj.year, d_obj.month, d_obj.day, 0, 0, tzinfo=TZ_UTC)
            asian_end_utc = datetime.datetime(d_obj.year, d_obj.month, d_obj.day, 7, 0, tzinfo=TZ_UTC)
            # Find matching server timestamps
            a_start_srv = int(asian_start_utc.timestamp()) + (7200 if not stimes["is_uk_dst"] else 10800)
            a_end_srv = int(asian_end_utc.timestamp()) + (7200 if not stimes["is_uk_dst"] else 10800)

            killzones.append({
                "name": "Asian Session",
                "label": "Asian Range (00:00 - 07:00 UTC)",
                "start_time": a_start_srv,
                "end_time": a_end_srv,
                "color": "rgba(240, 185, 11, 0.15)",
            })

            # London Open
            lon_utc = stimes["london"]["utc_time"]
            lon_srv = int(lon_utc.timestamp()) + (7200 if not stimes["is_uk_dst"] else 10800)
            killzones.append({
                "name": "London Open",
                "label": f"London Open ({stimes['london']['tehran_str']})",
                "start_time": lon_srv,
                "end_time": lon_srv + 7200,  # 2h killzone
                "color": "rgba(41, 98, 255, 0.15)",
            })

            # NY Open
            ny_utc = stimes["new_york"]["utc_time"]
            ny_srv = int(ny_utc.timestamp()) + (7200 if not stimes["is_uk_dst"] else 10800)
            killzones.append({
                "name": "NY Open",
                "label": f"NY Open ({stimes['new_york']['tehran_str']})",
                "start_time": ny_srv,
                "end_time": ny_srv + 7200,
                "color": "rgba(255, 109, 0, 0.15)",
            })
        except Exception:
            pass

    # 2. Asian range tracking per day (pre-compute daily boundaries)
    # Asian session: 00:00 <= utc_dt.hour < 7
    asian_bars_by_date: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for b in all_5m:
        z = server_epoch_to_zones(b["time"])
        if 0 <= z["utc_dt"].hour < 7:
            asian_bars_by_date[z["date_str"]].append(b)

    asian_ranges_by_day: Dict[str, Dict[str, Any]] = {}
    for d_str, a_bars in asian_bars_by_date.items():
        if a_bars:
            asian_ranges_by_day[d_str] = {
                "date": d_str,
                "high": max(b["high"] for b in a_bars),
                "low": min(b["low"] for b in a_bars),
                "start_time": a_bars[0]["time"],
                "end_time": a_bars[-1]["time"],
                "bars_count": len(a_bars),
            }

    # 3. System Risk Governor State
    current_equity = account_size_usd
    high_water_mark = account_size_usd
    daily_pnl_by_date: Dict[str, float] = collections.defaultdict(float)
    active_bot_trades: List[Dict[str, Any]] = []
    completed_bot_trades: List[Dict[str, Any]] = []
    last_signal_time: Dict[Tuple[str, str, float], int] = {}

    diagnostics: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []

    # Map 5M bars by time for index lookup
    time_to_idx = {b["time"]: i for i, b in enumerate(all_5m)}

    # Chronological Walk
    for bar in scan_bars:
        t = bar["time"]
        idx = time_to_idx[t]
        z = server_epoch_to_zones(t)
        date_str = z["date_str"]

        # Check for trade exits occurring at or before t to update realized equity and risk governor
        for at in list(active_bot_trades):
            if at.get("exit_time") is not None and at["exit_time"] <= t:
                # Trade has exited
                realized_pnl = float(at.get("realized_pnl_usd", 0.0))
                current_equity += realized_pnl
                exit_date = server_epoch_to_zones(at["exit_time"])["date_str"]
                daily_pnl_by_date[exit_date] += realized_pnl
                if current_equity > high_water_mark:
                    high_water_mark = current_equity
                completed_bot_trades.append(at)
                active_bot_trades.remove(at)

                events.append({
                    "time": at["exit_time"],
                    "type": f"BOT_TRADE_{at.get('status')}",
                    "description": f"Bot trade {at['trade_id']} exited: {at.get('status')} ({realized_pnl:+.2f} USD, {at.get('rr_realized', 0):+.2f}R)",
                })

        # Incremental Asian High/Low for this bar (anti-spoiler)
        day_asian_bars = asian_bars_by_date.get(date_str, [])
        asian_high: Optional[float] = None
        asian_low: Optional[float] = None

        if day_asian_bars:
            asian_session_start = day_asian_bars[0]["time"]
            asian_session_end = day_asian_bars[-1]["time"]

            if t < asian_session_start:
                asian_high = None
                asian_low = None
            elif t <= asian_session_end:
                # Inside Asian session: strictly calculate from bars up to current time t
                curr_asian = [b for b in day_asian_bars if b["time"] <= t]
                if curr_asian:
                    asian_high = max(b["high"] for b in curr_asian)
                    asian_low = min(b["low"] for b in curr_asian)
            else:
                # After Asian session: locked completed Asian range
                asian_high = max(b["high"] for b in day_asian_bars)
                asian_low = min(b["low"] for b in day_asian_bars)

        # Boxes
        fvg_box = detect_fvg_boxes(all_5m[: idx + 1], lookback=12, symbol=sym_clean)
        breaker_box = detect_breaker_boxes(all_5m[: idx + 1], lookback=24, symbol=sym_clean)

        # Slices up to forming bar (closed_bars_only=True drops bar at idx)
        bars_5m_slice = all_5m[: idx + 1]
        bars_1h_slice = [h for h in all_1h if h["time"] <= t]
        bars_1d_slice = [d for d in all_1d if d["time"] <= t]

        # Determine session hour and offset shimming
        if clock_mode == "true_tehran":
            sess_hour = z["teh_dt"].hour
            offset_sec = z["offset_sec"]

            def _shimmed_offset() -> int:
                return offset_sec

            with _SCREENER_OFFSET_LOCK:
                orig_offset_func = chart_renderer.get_broker_utc_offset_seconds
                chart_renderer.get_broker_utc_offset_seconds = _shimmed_offset
                try:
                    screener_res = screen_ict_session(
                        bars_5m=bars_5m_slice,
                        bars_1h=bars_1h_slice,
                        symbol=sym_clean,
                        session_hour=sess_hour,
                        bars_1d=bars_1d_slice,
                        closed_bars_only=True,
                    )
                finally:
                    chart_renderer.get_broker_utc_offset_seconds = orig_offset_func
        else:
            # live_legacy: uncalibrated tehran_hour_from_bar_time
            sess_hour = tehran_hour_from_bar_time(t)
            screener_res = screen_ict_session(
                bars_5m=bars_5m_slice,
                bars_1h=bars_1h_slice,
                symbol=sym_clean,
                session_hour=sess_hour,
                bars_1d=bars_1d_slice,
                closed_bars_only=True,
            )

        has_setup = screener_res.get("has_setup", False)
        reason = screener_res.get("reason", "")
        setup_type = screener_res.get("setup_type", "NONE")
        arch_id = screener_res.get("archetype_id")
        phase = screener_res.get("phase", "UNKNOWN")

        # Record bar diagnostic
        diag_entry = {
            "time": t,
            "session_hour": sess_hour,
            "has_setup": has_setup,
            "archetype_id": arch_id,
            "setup_type": setup_type,
            "reason": reason,
            "phase": phase,
            "asian_high": asian_high,
            "asian_low": asian_low,
            "fvg_box": fvg_box,
            "breaker_box": breaker_box,
        }
        diagnostics.append(diag_entry)

        if not has_setup:
            continue

        # Setup Fired! Process through System Risk Governor
        events.append({
            "time": t,
            "type": "SETUP_FIRED",
            "description": f"SMC setup fired: {arch_id} ({setup_type}) at {screener_res.get('entry_ref')}",
        })

        direction = (
            "LONG"
            if ("BULLISH" in setup_type or "LONG" in reason or "Breakout above" in reason)
            else "SHORT"
        )
        entry_p = float(screener_res["entry_ref"])
        sl_p = float(screener_res["sl_ref"])
        rec_target = float(screener_res.get("recommended_target_rr", 3.0))
        rec_be = float(screener_res.get("recommended_be_rr", 2.0))

        # Check for dol_target on SETUP-ARCH-013
        target_rr_cap = 3.5
        if arch_id == "SETUP-ARCH-013" and screener_res.get("dol_target") is not None:
            tp_p = float(screener_res["dol_target"])
            target_rr_cap = 7.5
        else:
            risk_dist = abs(entry_p - sl_p)
            tp_p = entry_p + (risk_dist * rec_target) if direction == "LONG" else entry_p - (risk_dist * rec_target)

        # 1. 30m duplicate-wave guard
        dup_key = (arch_id, direction, round(entry_p, 2))
        last_sig = last_signal_time.get(dup_key)
        if last_sig is not None and (t - last_sig) < 1800:
            diag_entry["governor_veto"] = "Veto: Risk Governor - Duplicate signal within 30m cooldown"
            continue

        # 2. Max open trades guard (max 3)
        # Count all trades currently active (from decision/order time until exit)
        active_at_t = [
            ot for ot in active_bot_trades
            if ot.get("decision_time", 0) <= t < ot.get("exit_time", float("inf"))
        ]
        if len(active_at_t) >= 3:
            diag_entry["governor_veto"] = "Veto: Risk Governor - Max open trades (3) reached"
            continue

        # 3. Concurrent open risk guard (max 2.0% = $40.00 at $2,000)
        hard_concurrent_cap = account_size_usd * 0.02
        current_open_risk = sum(ot.get("risk_usd_001", max_risk_usd) for ot in active_at_t)
        if (current_open_risk + max_risk_usd) > hard_concurrent_cap + 0.01:
            diag_entry["governor_veto"] = f"Veto: Risk Governor - Concurrent open risk exceeds ${hard_concurrent_cap:.2f}"
            continue

        # 4. Daily drawdown limit guard (4.0% = $80.00 at $2,000)
        daily_loss_limit = account_size_usd * 0.04
        if daily_pnl_by_date[date_str] <= -daily_loss_limit:
            diag_entry["governor_veto"] = f"Veto: Risk Governor - Daily drawdown limit (${daily_loss_limit:.2f}) reached"
            continue

        # 5. Overall trailing drawdown limit guard (10.0% = $200.00 at $2,000)
        overall_dd_limit = account_size_usd * 0.10
        if (high_water_mark - current_equity) >= overall_dd_limit:
            diag_entry["governor_veto"] = f"Veto: Risk Governor - Overall drawdown limit (${overall_dd_limit:.2f}) reached"
            continue

        # All risk governance checks PASSED! Simulate forward execution
        sig_bar_time = int(screener_res["signal_bar_time"])
        # Forward M1 bars start strictly after closed 5M signal bar
        fwd_m1_df = m1_df[m1_df["time"] >= (sig_bar_time + 300)]
        if horizon == "8h":
            fwd_m1_df = fwd_m1_df[fwd_m1_df["time"] <= (sig_bar_time + 300 + 28800)]
        fwd_m1_bars = fwd_m1_df.to_dict("records")

        if not fwd_m1_bars:
            continue

        decision_dict = {
            "decision": "BUY" if direction == "LONG" else "SELL",
            "entry": entry_p,
            "sl": sl_p,
            "tp": tp_p,
            "lot": 0.01,
        }

        eval_res = evaluate_council_decision(
            decision_dict=decision_dict,
            forward_m1_bars=fwd_m1_bars,
            symbol=sym_clean,
            spread_pts=spread_pts,
            breakeven_rr=rec_be,
            target_rr_cap=target_rr_cap,
            max_risk_usd=max_risk_usd,
        )

        if eval_res.get("is_realized") and eval_res.get("status") in ("WIN", "LOSS", "BREAKEVEN"):
            fill_idx = eval_res["fill_minute"]
            exit_idx = eval_res["exit_minute"]
            fill_time = fwd_m1_bars[fill_idx]["time"] if fill_idx is not None and fill_idx < len(fwd_m1_bars) else None
            exit_time = fwd_m1_bars[exit_idx]["time"] if exit_idx is not None and exit_idx < len(fwd_m1_bars) else None

            price_risk = calculate_trade_risk_usd(sym_clean, entry_p, sl_p, lot=0.01)

            trade_record = {
                "trade_id": f"BOT-{sym_clean}-{sig_bar_time}-{arch_id}",
                "origin": "BOT",
                "symbol": sym_clean,
                "direction": direction,
                "signal_time": sig_bar_time,
                "decision_time": t,
                "archetype_id": arch_id,
                "entry": entry_p,
                "sl": sl_p,
                "tp": tp_p,
                "status": eval_res["status"],
                "realized_pnl_usd": eval_res.get("realized_pnl_usd", 0.0),
                "rr_realized": eval_res.get("rr_realized"),
                "fill_time": fill_time,
                "exit_time": exit_time,
                "risk_usd_001": min(price_risk, max_risk_usd),
                "exceeds_risk_cap": price_risk > max_risk_usd,
                "notes": eval_res.get("notes", ""),
                "target_optimization": eval_res.get("target_optimization"),
            }

            active_bot_trades.append(trade_record)
            last_signal_time[dup_key] = t

            events.append({
                "time": fill_time if fill_time else t,
                "type": "BOT_TRADE_FILLED",
                "description": f"Bot filled limit order for {arch_id} at {entry_p}",
            })

    # Wrap up any trades still open at end of scan
    all_trades = completed_bot_trades + active_bot_trades

    # Build Bot Scorecard
    total = len(all_trades)
    wins = [t for t in all_trades if t.get("status") == "WIN"]
    losses = [t for t in all_trades if t.get("status") == "LOSS"]
    bes = [t for t in all_trades if t.get("status") == "BREAKEVEN"]

    gross_win = sum(float(t.get("realized_pnl_usd", 0.0)) for t in wins)
    gross_loss = abs(sum(float(t.get("realized_pnl_usd", 0.0)) for t in losses))
    net_pnl = round(sum(float(t.get("realized_pnl_usd", 0.0)) for t in all_trades), 2)
    net_rr = round(sum(float(t.get("rr_realized", 0.0)) for t in all_trades if t.get("rr_realized") is not None), 2)
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
    wr = round((len(wins) / total) * 100.0, 1) if total > 0 else 0.0

    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for t_item in sorted(all_trades, key=lambda x: (x.get("exit_time") or x.get("decision_time") or 0)):
        running += float(t_item.get("realized_pnl_usd", 0.0))
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd

    bot_scorecard = {
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "breakevens": len(bes),
        "win_rate_pct": wr,
        "net_pnl_usd": net_pnl,
        "net_rr": net_rr,
        "profit_factor": pf,
        "max_drawdown_usd": round(max_dd, 2),
    }

    return {
        "killzones": killzones,
        "asian_ranges_by_day": asian_ranges_by_day,
        "diagnostics": diagnostics,
        "events": events,
        "bot_trades": all_trades,
        "bot_scorecard": bot_scorecard,
    }


def simulate_custom_trade(
    data_mgr: ReplayDataManager,
    symbol: str,
    direction: str,
    signal_time: int,
    entry: float,
    sl: float,
    tp: float,
    be_rr: Optional[float] = None,
    max_risk_usd: Optional[float] = None,
    horizon_end: Optional[int] = None,
    lot: float = 0.01,
) -> Dict[str, Any]:
    """
    Simulates a human-proposed or human-adjusted trade setup against canonical M1 evaluator.
    Maintains uncapped target R:R (target_rr_cap=None) and computes true risk compliance badge.
    """
    sym_clean = symbol.strip()
    meta = SYMBOL_CATALOG.get(sym_clean, {})
    spread_pts = meta.get("spread_pts", 0.22)

    risk_usd_001 = calculate_trade_risk_usd(sym_clean, entry, sl, lot=0.01)
    exceeds_risk_cap = risk_usd_001 > 20.0

    m1_df = data_mgr.load_m1_df(sym_clean)
    fwd_slice = m1_df[m1_df["time"] > signal_time]
    if horizon_end is not None:
        fwd_slice = fwd_slice[fwd_slice["time"] <= horizon_end]
    fwd_bars = fwd_slice.to_dict("records")

    action = "BUY" if direction.upper() in ("BUY", "LONG") else "SELL"
    dec_dict = {
        "decision": action,
        "entry": float(entry),
        "sl": float(sl),
        "tp": float(tp),
        "lot": lot,
    }

    eval_res = evaluate_council_decision(
        decision_dict=dec_dict,
        forward_m1_bars=fwd_bars,
        symbol=sym_clean,
        spread_pts=spread_pts,
        breakeven_rr=be_rr,
        target_rr_cap=None,
        max_risk_usd=max_risk_usd,
    )

    fill_idx = eval_res.get("fill_minute")
    exit_idx = eval_res.get("exit_minute")
    fill_time = fwd_bars[fill_idx]["time"] if fill_idx is not None and fill_idx < len(fwd_bars) else None
    exit_time = fwd_bars[exit_idx]["time"] if exit_idx is not None and exit_idx < len(fwd_bars) else None

    return {
        "status": eval_res.get("status"),
        "realized_pnl_usd": eval_res.get("realized_pnl_usd", 0.0),
        "is_realized": eval_res.get("is_realized", False),
        "fill_minute": fill_idx,
        "exit_minute": exit_idx,
        "fill_time": fill_time,
        "exit_time": exit_time,
        "rr_realized": eval_res.get("rr_realized"),
        "target_optimization": eval_res.get("target_optimization"),
        "notes": eval_res.get("notes", ""),
        "risk_usd_001": risk_usd_001,
        "exceeds_risk_cap": exceeds_risk_cap,
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "symbol": sym_clean,
    }
