"""
TradingGuard HITL - On-Chart Market Microstructure Intelligence
Pulls multi-timeframe candle data from MetaTrader 5 and computes structural
anchors: Draw on Liquidity (DOL), Asian/London session ranges, SMT divergence,
and displacement velocity for Gold (XAUUSD).
"""

import sys
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from zoneinfo import ZoneInfo
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5

TZ_UTC = datetime.timezone.utc
TZ_TEHRAN = ZoneInfo("Asia/Tehran")


def _find_gold_symbol() -> str:
    """Detects available Gold symbol in MT5."""
    if not mt5.terminal_info():
        mt5.initialize()
    for candidate in ["XAUUSD_o", "XAUUSD", "GOLD"]:
        info = mt5.symbol_info(candidate)
        if info:
            return candidate
    return "XAUUSD_o"


def _find_silver_symbol() -> Optional[str]:
    """Detects available Silver symbol in MT5 for SMT divergence."""
    if not mt5.terminal_info():
        mt5.initialize()
    for candidate in ["XAGUSD_o", "XAGUSD", "SILVER"]:
        info = mt5.symbol_info(candidate)
        if info:
            return candidate
    return None


def _calc_atr(bars: List[Dict[str, Any]], period: int = 14) -> float:
    """Calculates Average True Range."""
    if len(bars) < 2:
        return 10.0
    trs = []
    for i in range(1, len(bars)):
        h = bars[i]["high"]
        l = bars[i]["low"]
        pc = bars[i - 1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    period = min(period, len(trs))
    return float(np.mean(trs[-period:])) if trs else 10.0


def _detect_fvg(bars: List[Dict[str, Any]], lookback: int = 30) -> List[Dict[str, Any]]:
    """Detects active Fair Value Gaps (imbalances) on higher timeframes."""
    fvgs = []
    recent = bars[-lookback:]
    for i in range(2, len(recent)):
        c1 = recent[i - 2]
        c2 = recent[i - 1]
        c3 = recent[i]

        # Bullish FVG: Candle 1 High < Candle 3 Low
        if c3["low"] > c1["high"]:
            gap = c3["low"] - c1["high"]
            if gap >= 1.0:  # Minimum 1 pt on Gold
                fvgs.append({
                    "type": "BULLISH_FVG",
                    "top": c3["low"],
                    "bottom": c1["high"],
                    "midpoint": round((c3["low"] + c1["high"]) / 2, 2),
                    "size": round(gap, 2),
                    "bar_time": c2["time"]
                })

        # Bearish FVG: Candle 1 Low > Candle 3 High
        if c1["low"] > c3["high"]:
            gap = c1["low"] - c3["high"]
            if gap >= 1.0:
                fvgs.append({
                    "type": "BEARISH_FVG",
                    "top": c1["low"],
                    "bottom": c3["high"],
                    "midpoint": round((c1["low"] + c3["high"]) / 2, 2),
                    "size": round(gap, 2),
                    "bar_time": c2["time"]
                })
    return fvgs


def _check_smt_divergence(
    gold_h1: List[Dict[str, Any]],
    silver_symbol: Optional[str]
) -> Dict[str, Any]:
    """
    Checks for Institutional SMT Divergence between Gold and Silver on H1.
    Bullish SMT: Gold makes Higher Low while Silver makes Lower Low.
    Bearish SMT: Gold makes Lower High while Silver makes Higher High.
    """
    if not silver_symbol:
        return {"has_smt": False, "type": "NONE", "note": "Silver unavailable"}

    rates_ag = mt5.copy_rates_from_pos(silver_symbol, mt5.TIMEFRAME_H1, 0, len(gold_h1))
    if rates_ag is None or len(rates_ag) < 10:
        return {"has_smt": False, "type": "NONE", "note": "Silver bars unavailable"}

    ag_h1 = [{"high": float(r["high"]), "low": float(r["low"]), "time": int(r["time"])} for r in rates_ag]

    # Compare last 2 prominent swing points
    if len(gold_h1) >= 20 and len(ag_h1) >= 20:
        au_recent_high = max(b["high"] for b in gold_h1[-10:])
        au_prior_high = max(b["high"] for b in gold_h1[-20:-10])

        ag_recent_high = max(b["high"] for b in ag_h1[-10:])
        ag_prior_high = max(b["high"] for b in ag_h1[-20:-10])

        # Bearish SMT: One made a higher high, the other failed
        if (au_recent_high > au_prior_high and ag_recent_high <= ag_prior_high):
            return {
                "has_smt": True,
                "type": "BEARISH_SMT",
                "note": "Gold broke higher high while Silver lagged/failed to confirm (Bearish SMT)"
            }
        elif (au_recent_high <= au_prior_high and ag_recent_high > ag_prior_high):
            return {
                "has_smt": True,
                "type": "BEARISH_SMT",
                "note": "Silver broke higher high while Gold showed relative weakness (Bearish SMT)"
            }

        # Bullish SMT: One made lower low, the other held higher low
        au_recent_low = min(b["low"] for b in gold_h1[-10:])
        au_prior_low = min(b["low"] for b in gold_h1[-20:-10])

        ag_recent_low = min(b["low"] for b in ag_h1[-10:])
        ag_prior_low = min(b["low"] for b in ag_h1[-20:-10])

        if (au_recent_low < au_prior_low and ag_recent_low >= ag_prior_low):
            return {
                "has_smt": True,
                "type": "BULLISH_SMT",
                "note": "Gold swept lower low while Silver held higher low (Institutional Accumulation SMT)"
            }
        elif (au_recent_low >= au_prior_low and ag_recent_low < ag_prior_low):
            return {
                "has_smt": True,
                "type": "BULLISH_SMT",
                "note": "Gold refused to make lower low while Silver swept low (Bullish SMT)"
            }

    return {"has_smt": False, "type": "NONE", "note": "Aligned market structure"}


def extract_on_chart_microstructure(symbol: str = "XAUUSD") -> Dict[str, Any]:
    """
    Extracts complete on-chart multi-timeframe microstructure telemetry for Gold.
    """
    if not mt5.terminal_info():
        mt5.initialize()

    gold_sym = _find_gold_symbol()
    silver_sym = _find_silver_symbol()

    # 1. Fetch MTF rates
    rates_d1 = mt5.copy_rates_from_pos(gold_sym, mt5.TIMEFRAME_D1, 0, 30)
    rates_h4 = mt5.copy_rates_from_pos(gold_sym, mt5.TIMEFRAME_H4, 0, 60)
    rates_h1 = mt5.copy_rates_from_pos(gold_sym, mt5.TIMEFRAME_H1, 0, 120)
    rates_m15 = mt5.copy_rates_from_pos(gold_sym, mt5.TIMEFRAME_M15, 0, 100)
    rates_m5 = mt5.copy_rates_from_pos(gold_sym, mt5.TIMEFRAME_M5, 0, 300)

    if rates_d1 is None or len(rates_d1) < 5 or rates_h1 is None or len(rates_h1) < 20:
        return {
            "symbol": symbol,
            "status": "DATA_ERROR",
            "error": "Failed to fetch sufficient MT5 rates for Gold"
        }

    # Convert to standard dict lists
    d1 = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for r in rates_d1]
    h4 = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for r in rates_h4]
    h1 = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for r in rates_h1]
    m15 = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for r in rates_m15]
    m5 = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for r in rates_m5]

    curr_p = m5[-1]["close"]

    # 2. Daily & Weekly Reference Levels
    prev_d = d1[-2]
    curr_d = d1[-1]
    pdh = prev_d["high"]
    pdl = prev_d["low"]
    pdc = prev_d["close"]

    daily_open = curr_d["open"]
    daily_high = curr_d["high"]
    daily_low = curr_d["low"]
    daily_range = daily_high - daily_low

    adr_14 = _calc_atr(d1, 14)
    adr_pct = round((daily_range / max(0.1, adr_14)) * 100.0, 1)

    # Weekly Levels (aggregate last 5-10 D1 bars)
    rates_w1 = mt5.copy_rates_from_pos(gold_sym, mt5.TIMEFRAME_W1, 0, 5)
    if rates_w1 is not None and len(rates_w1) >= 2:
        pwh = float(rates_w1[-2]["high"])
        pwl = float(rates_w1[-2]["low"])
        cwo = float(rates_w1[-1]["open"])
    else:
        pwh = max(b["high"] for b in d1[-10:-5])
        pwl = min(b["low"] for b in d1[-10:-5])
        cwo = d1[-5]["open"]

    # 3. Session Ranges (Asia & London) and Dynamic Dual-Anchor Resolution
    now_utc = datetime.datetime.now(TZ_UTC)
    today_utc_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_ts = int(today_utc_start.timestamp())

    # Asian Session: 00:00 to 06:00 UTC
    asian_bars = [b for b in m5 if today_start_ts <= b["time"] <= today_start_ts + (6 * 3600)]
    asian_high = max((b["high"] for b in asian_bars), default=daily_high)
    asian_low = min((b["low"] for b in asian_bars), default=daily_low)

    # London Session: 08:00 to 12:00 UTC
    london_bars = [b for b in m5 if today_start_ts + (8 * 3600) <= b["time"] <= today_start_ts + (12 * 3600)]
    is_london_established = (len(london_bars) >= 12) or (now_utc.hour >= 12)
    london_high = max((b["high"] for b in london_bars), default=asian_high)
    london_low = min((b["low"] for b in london_bars), default=asian_low)
    london_range = round(london_high - london_low, 2)
    london_swept_asian_h = london_high > asian_high
    london_swept_asian_l = london_low < asian_low

    # Dynamic Session Anchor: Pre-London vs Pre-NY vs After-Hours
    if now_utc.hour < 11:
        active_anchor = "PRE_LONDON"
    elif now_utc.hour < 17:
        active_anchor = "PRE_NY"
    else:
        active_anchor = "AFTER_HOURS"

    pre_ny_range = max(daily_high, london_high) - min(daily_low, london_low)
    pre_ny_adr_util = round((pre_ny_range / max(0.1, adr_14)) * 100.0, 1)
    adr_exhaustion_alert = pre_ny_adr_util >= 60.0

    # 4. Draw on Liquidity (DOL) Mapping
    # Unswept highs/lows
    h1_highs = [b["high"] for b in h1[-48:]]
    h1_lows = [b["low"] for b in h1[-48:]]

    unfilled_fvgs = _detect_fvg(h1, lookback=40)
    unfilled_h4_fvgs = _detect_fvg(h4, lookback=30)

    # Targets above market (Buy-Side Liquidity & Bearish FVGs to retest)
    bsl_targets = sorted([h for h in set(h1_highs) if h > curr_p])[:3]
    # Targets below market (Sell-Side Liquidity & Bullish FVGs to retest)
    ssl_targets = sorted([l for l in set(h1_lows) if l < curr_p], reverse=True)[:3]

    # Primary Daily DOL candidate:
    # If price swept PDH and displaced lower, target is PDL or lower FVG.
    # If price swept PDL and displaced higher, target is PDH or upper FVG.
    has_swept_pdh = daily_high > pdh
    has_swept_pdl = daily_low < pdl

    if has_swept_pdh and curr_p < pdh:
        primary_dol = {
            "type": "SELL_SIDE_LIQUIDITY",
            "target_price": round(pdl, 2),
            "distance_pts": round(curr_p - pdl, 2),
            "rationale": "Swept PDH with bearish displacement; Draw on Liquidity is PDL."
        }
    elif has_swept_pdl and curr_p > pdl:
        primary_dol = {
            "type": "BUY_SIDE_LIQUIDITY",
            "target_price": round(pdh, 2),
            "distance_pts": round(pdh - curr_p, 2),
            "rationale": "Swept PDL with bullish displacement; Draw on Liquidity is PDH."
        }
    elif curr_p > pdc:
        primary_dol = {
            "type": "BUY_SIDE_LIQUIDITY",
            "target_price": round(bsl_targets[0] if bsl_targets else pdh, 2),
            "distance_pts": round((bsl_targets[0] if bsl_targets else pdh) - curr_p, 2),
            "rationale": "Trading above previous day close; expanding toward resting buy-side liquidity."
        }
    else:
        primary_dol = {
            "type": "SELL_SIDE_LIQUIDITY",
            "target_price": round(ssl_targets[0] if ssl_targets else pdl, 2),
            "distance_pts": round(curr_p - (ssl_targets[0] if ssl_targets else pdl), 2),
            "rationale": "Trading below previous day close; expanding toward resting sell-side liquidity."
        }

    # 5. Higher Timeframe Market Structure Bias
    # Fast H1 swing structure
    h1_ma20 = np.mean([b["close"] for b in h1[-20:]])
    h4_ma20 = np.mean([b["close"] for b in h4[-20:]])

    h1_displacement = (h1[-1]["close"] - h1[-3]["open"])
    is_h1_bullish = curr_p > h1_ma20 and h1_displacement > 0
    is_h1_bearish = curr_p < h1_ma20 and h1_displacement < 0

    h1_regime = "BULLISH_EXPANSION" if is_h1_bullish else ("BEARISH_EXPANSION" if is_h1_bearish else "CONSOLIDATION_RANGE")

    # 6. SMT Divergence
    smt_info = _check_smt_divergence(h1, silver_sym)

    return {
        "symbol": "XAUUSD",
        "active_anchor": active_anchor,
        "current_price": round(curr_p, 2),
        "timestamp_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "timestamp_tehran": now_utc.astimezone(TZ_TEHRAN).strftime("%Y-%m-%d %H:%M:%S Tehran"),
        "daily_structure": {
            "pdh": round(pdh, 2),
            "pdl": round(pdl, 2),
            "pdc": round(pdc, 2),
            "daily_open": round(daily_open, 2),
            "daily_high": round(daily_high, 2),
            "daily_low": round(daily_low, 2),
            "daily_range": round(daily_range, 2),
            "adr_14": round(adr_14, 2),
            "adr_utilization_pct": adr_pct,
            "has_swept_pdh": has_swept_pdh,
            "has_swept_pdl": has_swept_pdl
        },
        "weekly_structure": {
            "pwh": round(pwh, 2),
            "pwl": round(pwl, 2),
            "cwo": round(cwo, 2),
            "relation_to_weekly_open": "ABOVE_WEEKLY_OPEN" if curr_p > cwo else "BELOW_WEEKLY_OPEN"
        },
        "session_ranges": {
            "asian_high": round(asian_high, 2),
            "asian_low": round(asian_low, 2),
            "asian_range": round(asian_high - asian_low, 2),
            "london_high": round(london_high, 2),
            "london_low": round(london_low, 2),
            "london_range": round(london_high - london_low, 2)
        },
        "london_context": {
            "is_established": is_london_established,
            "london_high": round(london_high, 2),
            "london_low": round(london_low, 2),
            "london_range": round(london_range, 2),
            "swept_asian_high": london_swept_asian_h,
            "swept_asian_low": london_swept_asian_l,
            "pre_ny_adr_util_pct": pre_ny_adr_util,
            "exhaustion_alert": adr_exhaustion_alert
        },
        "draw_on_liquidity": primary_dol,
        "liquidity_pools": {
            "overhead_bsl": [round(x, 2) for x in bsl_targets],
            "underlying_ssl": [round(x, 2) for x in ssl_targets],
            "active_h1_fvgs": unfilled_fvgs[:2],
            "active_h4_fvgs": unfilled_h4_fvgs[:2]
        },
        "htf_trend": {
            "h1_regime": h1_regime,
            "h1_ma20": round(float(h1_ma20), 2),
            "h4_ma20": round(float(h4_ma20), 2),
            "h1_displacement_3bar": round(float(h1_displacement), 2)
        },
        "smt_divergence": smt_info
    }
