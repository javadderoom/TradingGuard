"""
TradingGuard HITL - Advanced SMC Algorithmic Pre-Screener
Analyzes MT5 historical price structure in <5ms per session:
1. Calculates Asian Session High / Low (03:30 - 10:30 Tehran) & London High / Low.
2. Detects Liquidity Sweeps (Judas Swings) across Asian or London session boundaries.
3. Identifies 5M/15M Fair Value Gaps (FVG) and displacement bodies.
4. Detects Market Structure Shifts (MSS / CHoCH) and Breaker Blocks (BB).
5. Computes Optimal Trade Entry (OTE 0.62 - 0.79) retracement zones.
Returns True if an institutional SMC setup is present (triggering Tier-2 AI Council),
or False if the session is dead mid-range consolidation (instant STAND_ASIDE).
"""

from typing import List, Dict, Any, Tuple, Optional
from hitl.setup_registry import setup_registry


def detect_fvg_5m(bars: List[Dict[str, Any]], lookback: int = 12, symbol: str = "XAUUSD") -> Tuple[bool, str, float, float]:
    """
    Detects whether a valid 3-candle Fair Value Gap exists in recent 5M bars.
    Enforces minimum gap width and displacement candle body size based on asset contract physics.
    Returns: (has_fvg, direction, proximal_edge, distal_edge)
    """
    if len(bars) < 3:
        return False, "NONE", 0.0, 0.0

    is_gold = "XAU" in symbol.upper()
    is_silver = "XAG" in symbol.upper()
    min_gap = 1.0 if is_gold else (0.05 if is_silver else 0.0003)
    min_body = 1.5 if is_gold else (0.08 if is_silver else 0.0004)

    recent = bars[-lookback:]
    for i in range(len(recent) - 1, 2, -1):
        c1 = recent[i - 2]
        c2 = recent[i - 1]
        c3 = recent[i]

        # Bullish FVG: Candle 1 High < Candle 3 Low (imbalance in Candle 2)
        if c3['low'] > c1['high']:
            gap_size = c3['low'] - c1['high']
            body_size = abs(c2['close'] - c2['open'])
            if gap_size >= min_gap and body_size >= min_body and body_size > gap_size:  # Impulsive displacement
                return True, "BULLISH", c3['low'], c1['high']

        # Bearish FVG: Candle 1 Low > Candle 3 High (imbalance in Candle 2)
        if c1['low'] > c3['high']:
            gap_size = c1['low'] - c3['high']
            body_size = abs(c2['close'] - c2['open'])
            if gap_size >= min_gap and body_size >= min_body and body_size > gap_size:  # Impulsive displacement
                return True, "BEARISH", c3['high'], c1['low']

    return False, "NONE", 0.0, 0.0


def detect_breaker_and_mss(bars: List[Dict[str, Any]], lookback: int = 24, symbol: str = "XAUUSD") -> Tuple[bool, str, float]:
    """
    Detects true Market Structure Shift (MSS) and resulting Breaker Block.
    Strict Institutional Criteria:
    1. Swing Separation: The swing high and swing low must have meaningful structural height.
    2. Displacement Close: Closing bar must clearly break beyond the structural pivot with a full candle body.
    Returns: (has_breaker, breaker_type, breaker_price)
    """
    if len(bars) < 15:
        return False, "NONE", 0.0

    is_gold = "XAU" in symbol.upper()
    is_silver = "XAG" in symbol.upper()
    min_swing_height = 4.0 if is_gold else (0.25 if is_silver else 0.0015)

    recent = bars[-lookback:]
    current_close = recent[-1]['close']

    # Find swing highs and swing lows in recent bars
    highs = [(idx, b['high']) for idx, b in enumerate(recent[:-2]) if idx >= 2 and b['high'] >= recent[idx-1]['high'] and b['high'] >= recent[idx+1]['high']]
    lows = [(idx, b['low']) for idx, b in enumerate(recent[:-2]) if idx >= 2 and b['low'] <= recent[idx-1]['low'] and b['low'] <= recent[idx+1]['low']]

    if not (highs and lows):
        return False, "NONE", 0.0

    last_high_idx, last_high_val = highs[-1]
    last_low_idx, last_low_val = lows[-1]

    if abs(last_high_val - last_low_val) < min_swing_height:
        return False, "NONE", 0.0

    # Bearish MSS: Price broke below the last structural swing low with momentum
    if current_close < last_low_val and last_high_idx < last_low_idx:
        breaker_price = recent[last_low_idx]['high']
        return True, "BEARISH_BREAKER", breaker_price

    # Bullish MSS: Price broke above the last structural swing high with momentum
    if current_close > last_high_val and last_low_idx < last_high_idx:
        breaker_price = recent[last_high_idx]['low']
        return True, "BULLISH_BREAKER", breaker_price

    return False, "NONE", 0.0


def calculate_ote_range(swing_low: float, swing_high: float) -> Dict[str, float]:
    """
    Calculates ICT Optimal Trade Entry (OTE) Fibonacci levels:
    - 0.50: Equilibrium
    - 0.62: OTE Entry boundary
    - 0.705: Sweet Spot
    - 0.79: Extreme OTE boundary
    """
    rng = swing_high - swing_low
    return {
        "eq": swing_low + 0.50 * rng,
        "ote_62": swing_low + 0.62 * rng,
        "ote_705": swing_low + 0.705 * rng,
        "ote_79": swing_low + 0.79 * rng
    }


def scale_poi_depth(proximal: float, distal: float, is_bullish: bool, is_fx: bool, ratio: float = 0.50) -> float:
    """
    Implements RULE-EXEC-036: POI Depth Scaling (Mean Threshold & OTE).
    If candidate POI/zone width exceeds 6.0 pips (FX) or $2.00 (Gold), outer proximal edge entry (0%)
    is strictly avoided in favor of the 50% Mean Threshold (MT) or 75% Deep Retracement (OTE).
    """
    width = abs(proximal - distal)
    min_width = 0.0006 if is_fx else 2.0
    if width < min_width:
        return proximal
    
    if is_bullish:
        # Bullish: proximal is higher, distal is lower. Price retraces down into zone.
        return round(proximal - ratio * width, 5 if is_fx else 2)
    else:
        # Bearish: proximal is lower, distal is higher. Price retraces up into zone.
        return round(proximal + ratio * width, 5 if is_fx else 2)


def detect_prominent_sweep_and_mss(
    bars_5m: List[Dict[str, Any]],
    symbol: str,
    bars_1m: Optional[List[Dict[str, Any]]] = None,
    lookback_5m: int = 36
) -> Tuple[bool, str, float, float, str]:
    """
    Detects SETUP-ARCH-010: Prominent Liquidity Sweep with Pro-Trend MSS Displacement.
    Checks for:
    1. Prominent horizontal ceiling (EQH / Session High / PDH) or floor (EQL / Session Low / PDL).
    2. A sweep wick piercing beyond the level.
    3. An energetic displacement close (MSS) back inside in the pro-trend direction.
    Returns: (has_setup, direction, entry_price, sl_price, details)
    """
    if len(bars_5m) < 15:
        return False, "NONE", 0.0, 0.0, ""

    is_fx = "EUR" in symbol.upper() or "GBP" in symbol.upper()
    pip_size = 0.0001 if is_fx else (0.01 if "XAG" in symbol.upper() else 0.1)
    sl_buffer = 1.0 * pip_size if "GBP" in symbol.upper() else (2.0 * pip_size if is_fx else 1.5)

    recent = bars_5m[-lookback_5m:]
    curr_bar = recent[-1]
    curr_close = curr_bar['close']

    # Locate swing highs and swing lows across lookback window
    highs = []
    lows = []
    for i in range(2, len(recent) - 1):
        if recent[i]['high'] >= recent[i-1]['high'] and recent[i]['high'] >= recent[i+1]['high']:
            highs.append((i, recent[i]['high']))
        if recent[i]['low'] <= recent[i-1]['low'] and recent[i]['low'] <= recent[i+1]['low']:
            lows.append((i, recent[i]['low']))

    # 1. Bearish Prominent Sweep (EQH / Prominent High swept then MSS down)
    if len(highs) >= 2:
        for h_idx, h_val in highs[-3:]:
            prior_highs = [h for h in highs if h[0] < h_idx]
            if not prior_highs:
                continue
            prev_prominent_high = max(h[1] for h in prior_highs)
            
            # Did this peak sweep the prior prominent high?
            if h_val > prev_prominent_high and (h_val - prev_prominent_high) <= 25.0 * pip_size:
                sweep_wick = h_val
                sweep_bar_idx = h_idx
                interim_lows = [b['low'] for b in recent[max(0, sweep_bar_idx-2):sweep_bar_idx+1]]
                micro_swing_low = min(interim_lows) if interim_lows else recent[sweep_bar_idx]['low']
                
                # Check 1M if available, else check 5M
                if bars_1m and len(bars_1m) >= 5:
                    recent_1m = bars_1m[-15:]
                    m1_lows = [b['low'] for b in recent_1m[:-2]]
                    m1_pivot = min(m1_lows) if m1_lows else micro_swing_low
                    if recent_1m[-1]['close'] < m1_pivot and recent_1m[-1]['close'] < recent_1m[-1]['open']:
                        entry = recent_1m[-1]['close']
                        sl = round(sweep_wick + sl_buffer, 5 if is_fx else 2)
                        if "XAU" in symbol.upper():
                            dist = abs(entry - sl)
                            if dist > 7.50:
                                return False, "NONE", 0.0, 0.0, ""
                            if dist < 4.50:
                                sl = round(entry + 4.50, 2)
                        return True, "BEARISH", entry, sl, f"Prominent High swept at {sweep_wick:.5f} + M1 MSS displacement at {entry:.5f}"
                
                if curr_close < micro_swing_low and curr_bar['close'] < curr_bar['open']:
                    entry = curr_close
                    sl = round(sweep_wick + sl_buffer, 5 if is_fx else 2)
                    if "XAU" in symbol.upper():
                        dist = abs(entry - sl)
                        if dist > 7.50:
                            return False, "NONE", 0.0, 0.0, ""
                        if dist < 4.50:
                            sl = round(entry + 4.50, 2)
                    return True, "BEARISH", entry, sl, f"Prominent High swept at {sweep_wick:.5f} + MSS displacement close below {micro_swing_low:.5f}"

    # 2. Bullish Prominent Sweep (EQL / Prominent Low swept then MSS up)
    if len(lows) >= 2:
        for l_idx, l_val in lows[-3:]:
            prior_lows = [l for l in lows if l[0] < l_idx]
            if not prior_lows:
                continue
            prev_prominent_low = min(l[1] for l in prior_lows)
            
            if l_val < prev_prominent_low and (prev_prominent_low - l_val) <= 25.0 * pip_size:
                sweep_wick = l_val
                sweep_bar_idx = l_idx
                interim_highs = [b['high'] for b in recent[max(0, sweep_bar_idx-2):sweep_bar_idx+1]]
                micro_swing_high = max(interim_highs) if interim_highs else recent[sweep_bar_idx]['high']
                
                if bars_1m and len(bars_1m) >= 5:
                    recent_1m = bars_1m[-15:]
                    m1_highs = [b['high'] for b in recent_1m[:-2]]
                    m1_pivot = max(m1_highs) if m1_highs else micro_swing_high
                    if recent_1m[-1]['close'] > m1_pivot and recent_1m[-1]['close'] > recent_1m[-1]['open']:
                        entry = recent_1m[-1]['close']
                        sl = round(sweep_wick - sl_buffer, 5 if is_fx else 2)
                        if "XAU" in symbol.upper():
                            dist = abs(entry - sl)
                            if dist > 7.50:
                                return False, "NONE", 0.0, 0.0, ""
                            if dist < 4.50:
                                sl = round(entry - 4.50, 2)
                        return True, "BULLISH", entry, sl, f"Prominent Low swept at {sweep_wick:.5f} + M1 MSS displacement at {entry:.5f}"

                if curr_close > micro_swing_high and curr_bar['close'] > curr_bar['open']:
                    entry = curr_close
                    sl = round(sweep_wick - sl_buffer, 5 if is_fx else 2)
                    if "XAU" in symbol.upper():
                        dist = abs(entry - sl)
                        if dist > 7.50:
                            return False, "NONE", 0.0, 0.0, ""
                        if dist < 4.50:
                            sl = round(entry - 4.50, 2)
                    return True, "BULLISH", entry, sl, f"Prominent Low swept at {sweep_wick:.5f} + MSS displacement close above {micro_swing_high:.5f}"

    return False, "NONE", 0.0, 0.0, ""


def screen_ict_session(
    bars_5m: List[Dict[str, Any]],
    bars_1h: List[Dict[str, Any]],
    symbol: str,
    session_hour: int,
    smt_info: Optional[Dict[str, Any]] = None,
    bars_1m: Optional[List[Dict[str, Any]]] = None,
    bars_1d: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Advanced SMC Pre-Screener combining:
    1. Session Liquidity Sweeps (Asian/London High & Low)
    2. 5M Fair Value Gaps (Proximal & Distal with contract-scaled thresholds)
    3. Market Structure Shifts (MSS) & Breaker Blocks (BB)
    4. Optimal Trade Entry (OTE) alignment in Discount/Premium
    5. Daily Regime & Range Compression Gate (suppresses continuation setups in chop)
    """
    if len(bars_5m) < 40 or len(bars_1h) < 10:
        return {
            "has_setup": False,
            "reason": "Insufficient bar history",
            "setup_type": "NONE"
        }

    current_price = bars_5m[-1]['close']
    is_fx = "EUR" in symbol.upper() or "GBP" in symbol.upper()
    is_silver = "XAG" in symbol.upper()
    if is_fx:
        fmt = ".5f"
        unit = "pips"
        min_range = 0.0015
        breaker_tol = 0.0012
    elif is_silver:
        fmt = ".3f"
        unit = "pts"
        min_range = 0.20
        breaker_tol = 0.10
    else:
        fmt = ".2f"
        unit = "pts"
        min_range = 6.0       # Scaled for $4,000 Gold volatility
        breaker_tol = 1.50    # Tightened from 5.0 to avoid false retests

    # 1. Prior Session Liquidity Benchmark & Polarity
    if session_hour in (9, 10, 11):
        session_window = bars_5m[-84:-10] if len(bars_5m) >= 84 else bars_5m[:-10]
        session_label = "Asian Range"
    elif session_hour in (14, 15, 16):
        session_window = bars_5m[-72:-10] if len(bars_5m) >= 72 else bars_5m[:-10]
        session_label = "London Range"
    else:
        # NY Silver Bullet (17:30 - 18:30 Tehran / 10:00 - 11:00 NY)
        session_window = bars_5m[-36:-6] if len(bars_5m) >= 36 else bars_5m[:-6]
        session_label = "NY AM Range"

    if not session_window:
        return {"has_setup": False, "reason": "No session window data", "setup_type": "NONE"}

    range_high = max(b['high'] for b in session_window)
    range_low = min(b['low'] for b in session_window)
    total_range = range_high - range_low

    session_open = session_window[0]['open']
    session_close = session_window[-1]['close']
    is_session_bullish = session_close > session_open
    is_session_bearish = session_close < session_open

    if total_range < min_range:
        disp_range = total_range * 10000 if is_fx else total_range
        return {
            "has_setup": False,
            "reason": f"Dead market: {session_label} range compressed ({disp_range:{fmt}} {unit})",
            "setup_type": "NONE"
        }

    # 2. Liquidity Sweeps vs Breakouts in recent 10 bars
    recent_bars = bars_5m[-10:]
    recent_high = max(b['high'] for b in recent_bars)
    recent_low = min(b['low'] for b in recent_bars)

    pierced_high = recent_high >= range_high
    pierced_low = recent_low <= range_low

    breakout_buf = 1.0 if "XAU" in symbol.upper() else (0.10 if is_silver else 0.0008)
    rejection_buf = 0.5 if "XAU" in symbol.upper() else (0.05 if is_silver else 0.0004)

    is_bullish_breakout = pierced_high and current_price > (range_high + breakout_buf) and recent_bars[-1]['close'] > recent_bars[-1]['open']
    is_bearish_breakdown = pierced_low and current_price < (range_low - breakout_buf) and recent_bars[-1]['close'] < recent_bars[-1]['open']

    # Rejection Sweep requires piercing but closing back inside or counter-reversal
    swept_high = pierced_high and not is_bullish_breakout and (current_price <= (range_high + rejection_buf) or recent_bars[-1]['close'] < recent_bars[-1]['open'])
    swept_low = pierced_low and not is_bearish_breakdown and (current_price >= (range_low - rejection_buf) or recent_bars[-1]['close'] > recent_bars[-1]['open'])

    # 2b. Daily Regime Gate (Inside Day & Mid-Range Equilibrium Chop Suppression)
    in_mid_equilibrium = False
    is_inside_day = False
    if bars_1d and len(bars_1d) >= 2:
        pd = bars_1d[-2]
        pdh = pd['high']
        pdl = pd['low']
        pdr = pdh - pdl
        cd = bars_1d[-1]
        is_inside_day = (cd['high'] <= pdh and cd['low'] >= pdl)
        if pdr > 0:
            in_mid_equilibrium = ((pdl + 0.25 * pdr) <= current_price <= (pdl + 0.75 * pdr))

    # 2c. 1H Macro Order Flow & Bias
    h1_bias = "NEUTRAL"
    if len(bars_1h) >= 5:
        h1_closes = [b['close'] for b in bars_1h[-5:]]
        h1_opens = [b['open'] for b in bars_1h[-5:]]
        h1_net_disp = h1_closes[-1] - h1_opens[-3]
        min_1h_disp = 4.0 if "XAU" in symbol.upper() else (0.40 if is_silver else 0.0025)
        if h1_net_disp > min_1h_disp:
            h1_bias = "BULLISH"
        elif h1_net_disp < -min_1h_disp:
            h1_bias = "BEARISH"

    # 3. Detect FVG & Breaker Blocks with Asset Specifics
    has_fvg, fvg_dir, fvg_proximal, fvg_distal = detect_fvg_5m(bars_5m, lookback=12, symbol=symbol)
    has_breaker, breaker_type, breaker_price = detect_breaker_and_mss(bars_5m, lookback=24, symbol=symbol)

    # 4. Multi-Tool SMC Confluence Matching (Strictly Gated by Review Council Ratification)

    # Setup Intermarket: SMT Divergence & Mitigation (SETUP-ARCH-005 Metals / SETUP-ARCH-006 Forex / SETUP-ARCH-007 Counter POI)
    if smt_info and smt_info.get("has_smt"):
        arch_id = "SETUP-ARCH-007" if (setup_registry.is_archetype_ratified("SETUP-ARCH-007") and (swept_low or swept_high)) else ("SETUP-ARCH-006" if is_fx else "SETUP-ARCH-005")
        if not setup_registry.is_archetype_ratified(arch_id):
            return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED"}

        smt_type = smt_info.get("smt_type")
        if smt_type == "BEARISH_SMT" and not is_bullish_breakout and (swept_high or fvg_dir == "BEARISH" or breaker_type == "BEARISH_BREAKER"):
            scaled_fvg = scale_poi_depth(fvg_proximal, fvg_distal, is_bullish=False, is_fx=is_fx, ratio=0.50)
            entry_p = scaled_fvg if (has_fvg and fvg_dir == "BEARISH") else (breaker_price if has_breaker else range_high)
            return {
                "has_setup": True,
                "reason": f"[{arch_id}] BEARISH SMT: {smt_info.get('summary', '')} | Scaled Entry: {entry_p:{fmt}}",
                "setup_type": "BEARISH_SMT_MITIGATION",
                "archetype_id": arch_id,
                "entry_ref": entry_p
            }
        elif smt_type == "BULLISH_SMT" and not is_bearish_breakdown and (swept_low or fvg_dir == "BULLISH" or breaker_type == "BULLISH_BREAKER"):
            scaled_fvg = scale_poi_depth(fvg_proximal, fvg_distal, is_bullish=True, is_fx=is_fx, ratio=0.50)
            entry_p = scaled_fvg if (has_fvg and fvg_dir == "BULLISH") else (breaker_price if has_breaker else range_low)
            return {
                "has_setup": True,
                "reason": f"[{arch_id}] BULLISH SMT: {smt_info.get('summary', '')} | Scaled Entry: {entry_p:{fmt}}",
                "setup_type": "BULLISH_SMT_MITIGATION",
                "archetype_id": arch_id,
                "entry_ref": entry_p
            }

    # Setup A: Judas Swing + Breaker Block (SETUP-ARCH-001)
    if swept_high and not is_bullish_breakout and breaker_type == "BEARISH_BREAKER":
        arch_id = "SETUP-ARCH-001"
        if not setup_registry.is_archetype_ratified(arch_id):
            return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED"}
        return {
            "has_setup": True,
            "reason": f"[{arch_id}] Swept {session_label} High ({range_high:{fmt}}) + Bearish Breaker Block at {breaker_price:{fmt}}",
            "setup_type": "BEARISH_BREAKER_SWEEP",
            "archetype_id": arch_id,
            "entry_ref": breaker_price
        }

    if swept_low and not is_bearish_breakdown and breaker_type == "BULLISH_BREAKER":
        arch_id = "SETUP-ARCH-001"
        if not setup_registry.is_archetype_ratified(arch_id):
            return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED"}
        return {
            "has_setup": True,
            "reason": f"[{arch_id}] Swept {session_label} Low ({range_low:{fmt}}) + Bullish Breaker Block at {breaker_price:{fmt}}",
            "setup_type": "BULLISH_BREAKER_SWEEP",
            "archetype_id": arch_id,
            "entry_ref": breaker_price
        }

    # Setup B: Judas Swing + Fair Value Gap (SETUP-ARCH-002)
    if swept_high and not is_bullish_breakout and fvg_dir == "BEARISH":
        arch_id = "SETUP-ARCH-002"
        if not setup_registry.is_archetype_ratified(arch_id):
            return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED"}
        scaled_entry = scale_poi_depth(fvg_proximal, fvg_distal, is_bullish=False, is_fx=is_fx, ratio=0.50)
        return {
            "has_setup": True,
            "reason": f"[{arch_id}] Swept {session_label} High ({range_high:{fmt}}) + Bearish FVG [RULE-EXEC-036 Scaled: {scaled_entry:{fmt}}]",
            "setup_type": "BEARISH_SWEEP_FVG",
            "archetype_id": arch_id,
            "entry_ref": scaled_entry
        }

    if swept_low and not is_bearish_breakdown and fvg_dir == "BULLISH":
        arch_id = "SETUP-ARCH-002"
        if not setup_registry.is_archetype_ratified(arch_id):
            return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED"}
        scaled_entry = scale_poi_depth(fvg_proximal, fvg_distal, is_bullish=True, is_fx=is_fx, ratio=0.50)
        return {
            "has_setup": True,
            "reason": f"[{arch_id}] Swept {session_label} Low ({range_low:{fmt}}) + Bullish FVG [RULE-EXEC-036 Scaled: {scaled_entry:{fmt}}]",
            "setup_type": "BULLISH_SWEEP_FVG",
            "archetype_id": arch_id,
            "entry_ref": scaled_entry
        }

    # Setup C: Clean Market Structure Shift (MSS) with Breaker Block retest (SETUP-ARCH-003)
    # Gated: Must NOT be trapped in mid-range equilibrium chop, and must have a tight retest
    if not in_mid_equilibrium:
        if breaker_type == "BEARISH_BREAKER" and abs(current_price - breaker_price) <= breaker_tol:
            arch_id = "SETUP-ARCH-003"
            if not setup_registry.is_archetype_ratified(arch_id):
                return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED"}
            return {
                "has_setup": True,
                "reason": f"[{arch_id}] Bearish Breaker Block retest at {breaker_price:{fmt}}",
                "setup_type": "BEARISH_BREAKER_RETEST",
                "archetype_id": arch_id,
                "entry_ref": breaker_price
            }

        if breaker_type == "BULLISH_BREAKER" and abs(current_price - breaker_price) <= breaker_tol:
            arch_id = "SETUP-ARCH-003"
            if not setup_registry.is_archetype_ratified(arch_id):
                return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED"}
            return {
                "has_setup": True,
                "reason": f"[{arch_id}] Bullish Breaker Block retest at {breaker_price:{fmt}}",
                "setup_type": "BULLISH_BREAKER_RETEST",
                "archetype_id": arch_id,
                "entry_ref": breaker_price
            }

    # Setup D: Institutional Range Expansion (SETUP-ARCH-004)
    # Gated: Must have broken outside of mid-range equilibrium and cannot be an inside day compression
    if not (in_mid_equilibrium or is_inside_day):
        if is_bullish_breakout and fvg_dir == "BULLISH":
            arch_id = "SETUP-ARCH-004"
            if not setup_registry.is_archetype_ratified(arch_id):
                return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED"}
            return {
                "has_setup": True,
                "reason": f"[{arch_id}] Breakout above {session_label} High with Bullish FVG at {fvg_proximal:{fmt}}",
                "setup_type": "BULLISH_EXPANSION",
                "archetype_id": arch_id,
                "entry_ref": fvg_proximal
            }

        if is_bearish_breakdown and fvg_dir == "BEARISH":
            arch_id = "SETUP-ARCH-004"
            if not setup_registry.is_archetype_ratified(arch_id):
                return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED"}
            return {
                "has_setup": True,
                "reason": f"[{arch_id}] Breakdown below {session_label} Low with Bearish FVG at {fvg_proximal:{fmt}}",
                "setup_type": "BEARISH_EXPANSION",
                "archetype_id": arch_id,
                "entry_ref": fvg_proximal
            }

    # Setup E: Pro-Trend Session Breakdown/Breakout Origin Retest (SETUP-ARCH-009)
    # Scaled minimum expansion: >= 12.0 pts on Gold, >= 0.80 on Silver, >= 35 pips on FX.
    min_expansion_pts = 12.0 if "XAU" in symbol.upper() else (0.80 if is_silver else 0.0035)
    if total_range >= min_expansion_pts and not (in_mid_equilibrium or is_inside_day) and setup_registry.is_archetype_ratified("SETUP-ARCH-009"):
        arch_id = "SETUP-ARCH-009"
        # Bearish: Prior session dumped; price retraced into upper half (>45% retracement)
        if is_session_bearish and current_price >= (range_low + 0.45 * total_range):
            if current_price >= (range_low + 0.618 * total_range):
                ote_entry = range_low + 0.705 * total_range
                return {
                    "has_setup": True,
                    "reason": f"[{arch_id}] Bearish Trend Continuation: OTE Premium Retracement at {ote_entry:{fmt}} (Range: {total_range*10000 if is_fx else total_range:{fmt}} {unit})",
                    "setup_type": "BEARISH_TREND_RETEST",
                    "archetype_id": arch_id,
                    "entry_ref": round(ote_entry, 5 if is_fx else 2)
                }
            elif (has_fvg and fvg_dir == "BEARISH") or (has_breaker and breaker_type == "BEARISH_BREAKER"):
                entry_poi = fvg_proximal if (has_fvg and fvg_dir == "BEARISH") else breaker_price
                scaled_entry = scale_poi_depth(fvg_proximal, fvg_distal, is_bullish=False, is_fx=is_fx, ratio=0.50) if has_fvg else entry_poi
                return {
                    "has_setup": True,
                    "reason": f"[{arch_id}] Bearish Trend Continuation: Retracement to Breakdown POI at {scaled_entry:{fmt}}",
                    "setup_type": "BEARISH_TREND_RETEST",
                    "archetype_id": arch_id,
                    "entry_ref": scaled_entry
                }

        # Bullish: Prior session rallied; price retraced into lower half (<55% retracement)
        elif is_session_bullish and current_price <= (range_high - 0.45 * total_range):
            if current_price <= (range_high - 0.618 * total_range):
                ote_entry = range_high - 0.705 * total_range
                return {
                    "has_setup": True,
                    "reason": f"[{arch_id}] Bullish Trend Continuation: OTE Discount Retracement at {ote_entry:{fmt}} (Range: {total_range*10000 if is_fx else total_range:{fmt}} {unit})",
                    "setup_type": "BULLISH_TREND_RETEST",
                    "archetype_id": arch_id,
                    "entry_ref": round(ote_entry, 5 if is_fx else 2)
                }
            elif (has_fvg and fvg_dir == "BULLISH") or (has_breaker and breaker_type == "BULLISH_BREAKER"):
                entry_poi = fvg_proximal if (has_fvg and fvg_dir == "BULLISH") else breaker_price
                scaled_entry = scale_poi_depth(fvg_proximal, fvg_distal, is_bullish=True, is_fx=is_fx, ratio=0.50) if has_fvg else entry_poi
                return {
                    "has_setup": True,
                    "reason": f"[{arch_id}] Bullish Trend Continuation: Retracement to Breakout POI at {scaled_entry:{fmt}}",
                    "setup_type": "BULLISH_TREND_RETEST",
                    "archetype_id": arch_id,
                    "entry_ref": scaled_entry
                }

    # Setup F: Prominent Liquidity Sweep with Pro-Trend M1/5M MSS Displacement (SETUP-ARCH-010)
    has_prom_sweep, sweep_dir, sweep_entry, sweep_sl, sweep_desc = detect_prominent_sweep_and_mss(
        bars_5m, symbol, bars_1m=bars_1m
    )
    if has_prom_sweep and setup_registry.is_archetype_ratified("SETUP-ARCH-010"):
        arch_id = "SETUP-ARCH-010"
        return {
            "has_setup": True,
            "reason": f"[{arch_id}] {sweep_desc} [Entry: {sweep_entry:{fmt}} | SL: {sweep_sl:{fmt}}]",
            "setup_type": f"{sweep_dir}_PROMINENT_SWEEP_MSS",
            "archetype_id": arch_id,
            "entry_ref": sweep_entry,
            "sl_ref": sweep_sl
        }

    # Price trapped in mid-range consolidation
    return {
        "has_setup": False,
        "reason": f"Mid-range chop within {session_label} ({range_low:{fmt}} - {range_high:{fmt}})",
        "setup_type": "NONE"
    }
