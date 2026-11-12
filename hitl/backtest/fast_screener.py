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

import datetime
from typing import List, Dict, Any, Tuple, Optional
from hitl.setup_registry import setup_registry
from hitl.backtest.session_clock import get_session_times_for_date


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
    is_crypto = "BTC" in symbol.upper() or "ETH" in symbol.upper()
    is_spx = "SPX" in symbol.upper() or "US500" in symbol.upper()
    is_ym = "YM" in symbol.upper() or "US30" in symbol.upper() or "DOW" in symbol.upper()
    is_nq = "NQ" in symbol.upper() or "NAS" in symbol.upper() or "US100" in symbol.upper()
    is_index = is_nq or is_spx or is_ym
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
        min_gap = 25.0 if "BTC" in symbol.upper() else 2.0
        min_body = 45.0 if "BTC" in symbol.upper() else 3.0
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
    is_crypto = "BTC" in symbol.upper() or "ETH" in symbol.upper()
    is_spx = "SPX" in symbol.upper() or "US500" in symbol.upper()
    is_ym = "YM" in symbol.upper() or "US30" in symbol.upper() or "DOW" in symbol.upper()
    is_nq = "NQ" in symbol.upper() or "NAS" in symbol.upper() or "US100" in symbol.upper()
    is_index = is_nq or is_spx or is_ym
    if is_spx:
        min_swing_height = 6.0
    elif is_ym:
        min_swing_height = 40.0
    elif is_nq:
        min_swing_height = 25.0
    elif is_crypto:
        min_swing_height = 120.0 if "BTC" in symbol.upper() else 8.0
    elif is_gold:
        min_swing_height = 4.0
    elif is_silver:
        min_swing_height = 0.25
    else:
        min_swing_height = 0.0015

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


def scale_poi_depth(proximal: float, distal: float, is_bullish: bool, is_fx: bool, ratio: float = 0.50, is_crypto: bool = False, is_index: bool = False, symbol: str = "") -> float:
    """
    Implements RULE-EXEC-036: POI Depth Scaling (Mean Threshold & OTE).
    """
    width = abs(proximal - distal)
    is_spx = "SPX" in symbol.upper() or "US500" in symbol.upper()
    is_ym = "YM" in symbol.upper() or "US30" in symbol.upper()
    min_width = 2.5 if is_spx else (12.0 if is_ym else (8.0 if is_index else (25.0 if is_crypto else (0.0006 if is_fx else 2.0))))
    if width < min_width:
        return proximal
    
    dec = 1 if is_index else (5 if is_fx else 2)
    if is_bullish:
        return round(proximal - ratio * width, dec)
    else:
        return round(proximal + ratio * width, dec)


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
    is_crypto = "BTC" in symbol.upper() or "ETH" in symbol.upper()
    is_spx = "SPX" in symbol.upper() or "US500" in symbol.upper()
    is_ym = "YM" in symbol.upper() or "US30" in symbol.upper()
    is_nq = "NQ" in symbol.upper() or "NAS" in symbol.upper() or "US100" in symbol.upper()
    is_index = is_nq or is_spx or is_ym
    pip_size = 0.5 if is_spx else (2.0 if is_ym else (1.0 if is_nq else (5.0 if is_crypto else (0.0001 if is_fx else (0.01 if "XAG" in symbol.upper() else 0.1)))))
    sl_buffer = 1.0 if is_spx else (6.0 if is_ym else (4.0 if is_nq else (20.0 if is_crypto else (1.0 * pip_size if "GBP" in symbol.upper() else (2.0 * pip_size if is_fx else 1.5)))))

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
            prev_high_item = max(prior_highs, key=lambda x: x[1])
            prev_high_idx = prev_high_item[0]
            prev_prominent_high = prev_high_item[1]
            
            # Did this peak sweep the prior prominent high?
            if h_val > prev_prominent_high and (h_val - prev_prominent_high) <= 25.0 * pip_size:
                sweep_wick = h_val
                sweep_bar_idx = h_idx
                # Calculate originating swing low between prior high and the sweep high
                between_lows = [b['low'] for b in recent[prev_high_idx:sweep_bar_idx+1]]
                origin_swing_low = min(between_lows) if between_lows else recent[sweep_bar_idx]['low']
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
                            if dist > 15.0:
                                return False, "NONE", 0.0, 0.0, ""
                            if dist < 4.50:
                                sl = round(entry + 4.50, 2)
                        elif is_crypto:
                            dist = abs(entry - sl)
                            if dist > 800.0:
                                return False, "NONE", 0.0, 0.0, ""
                            if dist < 150.0:
                                sl = round(entry + 150.0, 2)
                        elif is_spx:
                            dist = abs(entry - sl)
                            if dist > 25.0:
                                return False, "NONE", 0.0, 0.0, ""
                            if dist < 3.0:
                                sl = round(entry + 3.0, 1)
                        elif is_ym:
                            dist = abs(entry - sl)
                            if dist > 180.0:
                                return False, "NONE", 0.0, 0.0, ""
                            if dist < 25.0:
                                sl = round(entry + 25.0, 1)
                        elif is_nq:
                            dist = abs(entry - sl)
                            if dist > 120.0:
                                return False, "NONE", 0.0, 0.0, ""
                            if dist < 20.0:
                                sl = round(entry + 20.0, 1)
                        return True, "BEARISH", entry, sl, f"Prominent High swept at {sweep_wick:.5f} + M1 MSS displacement at {entry:.5f}"
                
                is_gold_sym = "XAU" in symbol.upper()
                is_mss_bear = curr_close < micro_swing_low or (is_gold_sym and curr_close < origin_swing_low)
                if is_mss_bear and curr_bar['close'] < curr_bar['open']:
                    entry = curr_close
                    sl = round(sweep_wick + sl_buffer, 5 if is_fx else (1 if is_index else 2))
                    if "XAU" in symbol.upper():
                        dist = abs(entry - sl)
                        if dist > 15.0:
                            return False, "NONE", 0.0, 0.0, ""
                        if dist < 4.50:
                            sl = round(entry + 4.50, 2)
                    elif is_crypto:
                        dist = abs(entry - sl)
                        if dist > 800.0:
                            return False, "NONE", 0.0, 0.0, ""
                        if dist < 150.0:
                            sl = round(entry + 150.0, 2)
                    elif is_spx:
                        dist = abs(entry - sl)
                        if dist > 25.0:
                            return False, "NONE", 0.0, 0.0, ""
                        if dist < 3.0:
                            sl = round(entry + 3.0, 1)
                    elif is_ym:
                        dist = abs(entry - sl)
                        if dist > 180.0:
                            return False, "NONE", 0.0, 0.0, ""
                        if dist < 25.0:
                            sl = round(entry + 25.0, 1)
                    elif is_nq:
                        dist = abs(entry - sl)
                        if dist > 120.0:
                            return False, "NONE", 0.0, 0.0, ""
                        if dist < 20.0:
                            sl = round(entry + 20.0, 1)
                    mss_ref = origin_swing_low if curr_close < origin_swing_low else micro_swing_low
                    return True, "BEARISH", entry, sl, f"Prominent High swept at {sweep_wick:.5f} + MSS displacement close below {mss_ref:.5f}"

    # 2. Bullish Prominent Sweep (EQL / Prominent Low swept then MSS up)
    if len(lows) >= 2:
        for l_idx, l_val in lows[-3:]:
            prior_lows = [l for l in lows if l[0] < l_idx]
            if not prior_lows:
                continue
            prev_low_item = min(prior_lows, key=lambda x: x[1])
            prev_low_idx = prev_low_item[0]
            prev_prominent_low = prev_low_item[1]
            
            if l_val < prev_prominent_low and (prev_prominent_low - l_val) <= 25.0 * pip_size:
                sweep_wick = l_val
                sweep_bar_idx = l_idx
                # Calculate originating swing high between prior low and the sweep low
                between_highs = [b['high'] for b in recent[prev_low_idx:sweep_bar_idx+1]]
                origin_swing_high = max(between_highs) if between_highs else recent[sweep_bar_idx]['high']
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
                            if dist > 15.0:
                                return False, "NONE", 0.0, 0.0, ""
                            if dist < 4.50:
                                sl = round(entry - 4.50, 2)
                        elif is_crypto:
                            dist = abs(entry - sl)
                            if dist > 800.0:
                                return False, "NONE", 0.0, 0.0, ""
                            if dist < 150.0:
                                sl = round(entry - 150.0, 2)
                        elif is_spx:
                            dist = abs(entry - sl)
                            if dist > 25.0:
                                return False, "NONE", 0.0, 0.0, ""
                            if dist < 3.0:
                                sl = round(entry - 3.0, 1)
                        elif is_ym:
                            dist = abs(entry - sl)
                            if dist > 180.0:
                                return False, "NONE", 0.0, 0.0, ""
                            if dist < 25.0:
                                sl = round(entry - 25.0, 1)
                        elif is_nq:
                            dist = abs(entry - sl)
                            if dist > 120.0:
                                return False, "NONE", 0.0, 0.0, ""
                            if dist < 20.0:
                                sl = round(entry - 20.0, 1)
                        return True, "BULLISH", entry, sl, f"Prominent Low swept at {sweep_wick:.5f} + M1 MSS displacement at {entry:.5f}"

                is_gold_sym = "XAU" in symbol.upper()
                is_mss_bull = curr_close > micro_swing_high or (is_gold_sym and curr_close > origin_swing_high)
                if is_mss_bull and curr_bar['close'] > curr_bar['open']:
                    entry = curr_close
                    sl = round(sweep_wick - sl_buffer, 5 if is_fx else (1 if is_index else 2))
                    if "XAU" in symbol.upper():
                        dist = abs(entry - sl)
                        if dist > 15.0:
                            return False, "NONE", 0.0, 0.0, ""
                        if dist < 4.50:
                            sl = round(entry - 4.50, 2)
                    elif is_crypto:
                        dist = abs(entry - sl)
                        if dist > 800.0:
                            return False, "NONE", 0.0, 0.0, ""
                        if dist < 150.0:
                            sl = round(entry - 150.0, 2)
                    elif is_spx:
                        dist = abs(entry - sl)
                        if dist > 25.0:
                            return False, "NONE", 0.0, 0.0, ""
                        if dist < 3.0:
                            sl = round(entry - 3.0, 1)
                    elif is_ym:
                        dist = abs(entry - sl)
                        if dist > 180.0:
                            return False, "NONE", 0.0, 0.0, ""
                        if dist < 25.0:
                            sl = round(entry - 25.0, 1)
                    elif is_nq:
                        dist = abs(entry - sl)
                        if dist > 120.0:
                            return False, "NONE", 0.0, 0.0, ""
                        if dist < 20.0:
                            sl = round(entry - 20.0, 1)
                    mss_ref = origin_swing_high if curr_close > origin_swing_high else micro_swing_high
                    return True, "BULLISH", entry, sl, f"Prominent Low swept at {sweep_wick:.5f} + MSS displacement close above {mss_ref:.5f}"

    return False, "NONE", 0.0, 0.0, ""


def detect_nested_double_mss(
    bars_5m: List[Dict[str, Any]],
    symbol: str = "XAUUSD",
    lookback: int = 50
) -> Tuple[bool, str, float, float, str]:
    """
    Detects Nested Double MSS (SETUP-ARCH-011):
    L1 -> H1 -> L2 (Sweep of L1) -> H2 (Breaks H1: 1st MSS) -> L3 -> H3 -> L4 -> H4 (Breaks H3: 2nd MSS).
    Entry at H3 breaker retest (L5), SL below L4 + $1.50 spread buffer.
    Mandatory prior sweep: L2 must sweep L1 or an opposing benchmark.
    """
    if len(bars_5m) < 30:
        return False, "NONE", 0.0, 0.0, ""

    recent = bars_5m[-lookback:]
    curr_bar = recent[-1]
    c = curr_bar['close']

    highs = []
    lows = []
    for i in range(2, len(recent) - 2):
        if recent[i]['high'] >= recent[i-1]['high'] and recent[i]['high'] >= recent[i-2]['high'] and \
           recent[i]['high'] >= recent[i+1]['high'] and recent[i]['high'] >= recent[i+2]['high']:
            highs.append((i, recent[i]['high']))
        if recent[i]['low'] <= recent[i-1]['low'] and recent[i]['low'] <= recent[i-2]['low'] and \
           recent[i]['low'] <= recent[i+1]['low'] and recent[i]['low'] <= recent[i+2]['low']:
            lows.append((i, recent[i]['low']))

    if len(highs) < 3 or len(lows) < 3:
        return False, "NONE", 0.0, 0.0, ""

    is_crypto = "BTC" in symbol.upper() or "ETH" in symbol.upper()
    is_index = "NQ" in symbol.upper() or "NAS" in symbol.upper() or "US100" in symbol.upper()
    step_buf = 8.0 if is_index else (25.0 if is_crypto else 1.0)
    sl_buf = 4.0 if is_index else (20.0 if is_crypto else 1.50)
    min_dist = 20.0 if is_index else (150.0 if is_crypto else 3.50)
    max_dist = 120.0 if is_index else (800.0 if is_crypto else 8.00)

    # 1. Bullish Nested Double MSS
    h3_idx, h3_price = highs[-1]
    if c > h3_price and curr_bar['close'] > curr_bar['open']:
        bars_after_h3 = recent[h3_idx:]
        if len(bars_after_h3) >= 2:
            l4_price = min(b['low'] for b in bars_after_h3)
            prior_h = [h for h in highs if h[0] < h3_idx]
            prior_l = [l for l in lows if l[0] < h3_idx]
            if len(prior_h) >= 2 and len(prior_l) >= 2:
                h2_idx, h2_price = prior_h[-1]
                h1_idx, h1_price = prior_h[-2]
                l3_idx, l3_price = prior_l[-1]
                l2_idx, l2_price = prior_l[-2]

                has_sweep = (len(prior_l) >= 3 and l2_price < prior_l[-3][1]) or (l2_price < prior_l[0][1])

                if has_sweep and (h2_price > h1_price + step_buf) and (h3_price < h2_price - step_buf) and (l3_price > l2_price) and (l4_price > l2_price):
                    entry = h3_price
                    sl = l4_price - sl_buf
                    dist = abs(entry - sl)
                    if dist < min_dist:
                        sl = entry - min_dist
                    elif dist > max_dist:
                        sl = entry - max_dist
                    return True, "BULLISH", entry, sl, f"Nested Double MSS (Swept {l2_price:.2f} -> 1st MSS {h2_price:.2f} -> Pullback -> 2nd MSS above {h3_price:.2f})"

    # 2. Bearish Nested Double MSS
    l3_idx, l3_price = lows[-1]
    if c < l3_price and curr_bar['close'] < curr_bar['open']:
        bars_after_l3 = recent[l3_idx:]
        if len(bars_after_l3) >= 2:
            h4_price = max(b['high'] for b in bars_after_l3)
            prior_h = [h for h in highs if h[0] < l3_idx]
            prior_l = [l for l in lows if l[0] < l3_idx]
            if len(prior_h) >= 2 and len(prior_l) >= 2:
                l2_idx, l2_price = prior_l[-1]
                l1_idx, l1_price = prior_l[-2]
                h3_idx, h3_price = prior_h[-1]
                h2_idx, h2_price = prior_h[-2]

                has_sweep = (len(prior_h) >= 3 and h2_price > prior_h[-3][1]) or (h2_price > prior_h[0][1])

                if has_sweep and (l2_price < l1_price - step_buf) and (l3_price > l2_price + step_buf) and (h3_price < h2_price) and (h4_price < h2_price):
                    entry = l3_price
                    sl = h4_price + sl_buf
                    dist = abs(entry - sl)
                    if dist < min_dist:
                        sl = entry + min_dist
                    elif dist > max_dist:
                        sl = entry + max_dist
                    return True, "BEARISH", entry, sl, f"Nested Double MSS (Swept {h2_price:.2f} -> 1st MSS {l2_price:.2f} -> Pullback -> 2nd MSS below {l3_price:.2f})"

    return False, "NONE", 0.0, 0.0, ""


def detect_adr_exhaustion_snapback(
    bars_5m: List[Dict[str, Any]],
    bars_1d: Optional[List[Dict[str, Any]]] = None,
    bars_1h: Optional[List[Dict[str, Any]]] = None,
    symbol: str = "XAUUSD"
) -> Tuple[bool, str, float, float, str]:
    """
    Detects SETUP-ARCH-012: Macro ADR Exhaustion Mean-Reversion Snapback.
    Valid strictly on Gold (XAUUSD); prohibited on GBPUSD.
    Trigger Criteria:
    1. Intraday price range reaches >= 85% of 20-day Average Daily Range (ADR).
    2. Active during institutional session hours before 16:00 UTC (19:30 Tehran).
    3. Rejection candle prints at extreme (Close < Open at High; Close > Open at Low).
    4. Market order entry on candle close with SL beyond extreme + $1.50 buffer.
    """
    if "XAU" not in symbol.upper():
        return False, "NONE", 0.0, 0.0, ""

    if len(bars_5m) < 25:
        return False, "NONE", 0.0, 0.0, ""

    # Calculate 20-day ADR
    adr_20 = 0.0
    if bars_1d and len(bars_1d) >= 20:
        prior_20 = bars_1d[-21:-1] if len(bars_1d) > 20 else bars_1d[-20:]
        adr_20 = sum(b['high'] - b['low'] for b in prior_20) / len(prior_20)
    elif bars_1h and len(bars_1h) >= 480:  # ~20 days of 1H
        ranges = []
        for d in range(20):
            block = bars_1h[-(d+2)*24 : -(d+1)*24]
            if block:
                ranges.append(max(b['high'] for b in block) - min(b['low'] for b in block))
        if ranges:
            adr_20 = sum(ranges) / len(ranges)

    if adr_20 <= 5.0:
        adr_20 = 45.0  # Conservative fallback

    curr_b = bars_5m[-1]
    curr_dt = curr_b.get('dt')
    if curr_dt is not None and hasattr(curr_dt, 'hour') and curr_dt.hour >= 16:
        return False, "NONE", 0.0, 0.0, ""

    # Intraday range from recent 5M bars
    lookback = min(len(bars_5m), 72)
    day_window = bars_5m[-lookback:]
    high_so_far = max(b['high'] for b in day_window)
    low_so_far = min(b['low'] for b in day_window)
    range_so_far = high_so_far - low_so_far

    if range_so_far < (0.85 * adr_20):
        return False, "NONE", 0.0, 0.0, ""

    # Check rejection at high
    is_at_high = (curr_b['high'] >= high_so_far - 1.00) and (curr_b['close'] < curr_b['open'])
    # Check rejection at low
    is_at_low = (curr_b['low'] <= low_so_far + 1.00) and (curr_b['close'] > curr_b['open'])

    min_sl = 3.50
    max_sl = 9.00

    if is_at_high:
        entry = curr_b['close']
        sl = high_so_far + 1.50
        dist = abs(entry - sl)
        if min_sl <= dist <= max_sl:
            desc = f"ADR Exhaustion Snapback Short (Intraday Range {range_so_far:.2f} >= 85% ADR {adr_20:.2f}; Bearish Rejection at {high_so_far:.2f})"
            return True, "BEARISH", entry, sl, desc

    elif is_at_low:
        entry = curr_b['close']
        sl = low_so_far - 1.50
        dist = abs(entry - sl)
        if min_sl <= dist <= max_sl:
            desc = f"ADR Exhaustion Snapback Long (Intraday Range {range_so_far:.2f} >= 85% ADR {adr_20:.2f}; Bullish Rejection at {low_so_far:.2f})"
            return True, "BULLISH", entry, sl, desc

    return False, "NONE", 0.0, 0.0, ""


def detect_macro_dol_runner(
    bars_5m: List[Dict[str, Any]],
    bars_1h: List[Dict[str, Any]],
    bars_1d: Optional[List[Dict[str, Any]]] = None,
    bars_1m: Optional[List[Dict[str, Any]]] = None,
    symbol: str = "GBPUSD"
) -> Tuple[bool, str, float, float, float, str]:
    """
    Detects SETUP-ARCH-013: HTF Draw on Liquidity (DOL) Sweep & 15M Structural Trailing Runner.
    Exclusively ratified on GBPUSD (+47.1R Net, PF 1.53).
    Returns: (has_setup, direction, entry, sl, dol_target, desc)
    """
    if "GBP" not in symbol.upper():
        return False, "NONE", 0.0, 0.0, 0.0, ""

    if len(bars_5m) < 30 or len(bars_1h) < 10:
        return False, "NONE", 0.0, 0.0, 0.0, ""

    # Determine PDH/PDL from bars_1d or 24h blocks in bars_1h
    pdh = 0.0
    pdl = 0.0
    if bars_1d and len(bars_1d) >= 2:
        prev_d = bars_1d[-2]
        pdh = prev_d['high']
        pdl = prev_d['low']
    elif len(bars_1h) >= 48:
        prev_day_1h = bars_1h[-48:-24]
        pdh = max(b['high'] for b in prev_day_1h)
        pdl = min(b['low'] for b in prev_day_1h)

    # Asian session extremes from bars_1h (00:00 - 07:00 UTC)
    today_bars = [b for b in bars_1h[-24:]]
    asian_bars = [b for b in today_bars if hasattr(b.get('dt'), 'hour') and b['dt'].hour < 7]
    asian_high = max(b['high'] for b in asian_bars) if asian_bars else 0.0
    asian_low = min(b['low'] for b in asian_bars) if asian_bars else 0.0

    curr_p = bars_5m[-1]['close']

    # Bullish Macro Setup: Swept PDL or Asian Low
    swept_pdl = pdl > 0 and any(b['low'] < (pdl - 0.0001) for b in bars_5m[-12:])
    swept_asian_low = asian_low > 0 and any(b['low'] < (asian_low - 0.0001) for b in bars_5m[-12:])

    if swept_pdl or swept_asian_low:
        highs = [b['high'] for b in bars_5m[-12:-2]]
        if highs:
            swing_high = max(highs)
            recent_low = min(b['low'] for b in bars_5m[-12:])
            if curr_p > swing_high and bars_5m[-1]['close'] > bars_5m[-1]['open']:
                entry = curr_p
                sl = recent_low - 0.0006
                risk = entry - sl
                if 0.0005 <= risk <= 0.0014:
                    dol = pdh if pdh > entry else asian_high
                    if dol > entry and ((dol - entry) / risk) >= 7.0:
                        desc = f"Cable Macro DOL Runner Long (Swept {'PDL' if swept_pdl else 'Asian Low'} -> MSS above {swing_high:.5f}; DOL: {dol:.5f} [Potential {((dol-entry)/risk):.1f}R])"
                        return True, "BULLISH", entry, sl, dol, desc

    # Bearish Macro Setup: Swept PDH or Asian High
    swept_pdh = pdh > 0 and any(b['high'] > (pdh + 0.0001) for b in bars_5m[-12:])
    swept_asian_high = asian_high > 0 and any(b['high'] > (asian_high + 0.0001) for b in bars_5m[-12:])

    if swept_pdh or swept_asian_high:
        lows = [b['low'] for b in bars_5m[-12:-2]]
        if lows:
            swing_low = min(lows)
            recent_high = max(b['high'] for b in bars_5m[-12:])
            if curr_p < swing_low and bars_5m[-1]['close'] < bars_5m[-1]['open']:
                entry = curr_p
                sl = recent_high + 0.0006
                risk = sl - entry
                if 0.0005 <= risk <= 0.0014:
                    dol = pdl if pdl < entry else asian_low
                    if dol < entry and ((entry - dol) / risk) >= 7.0:
                        desc = f"Cable Macro DOL Runner Short (Swept {'PDH' if swept_pdh else 'Asian High'} -> MSS below {swing_low:.5f}; DOL: {dol:.5f} [Potential {((entry-dol)/risk):.1f}R])"
                        return True, "BEARISH", entry, sl, dol, desc

    return False, "NONE", 0.0, 0.0, 0.0, ""


def detect_reversal_origin_retest(
    bars_5m: List[Dict[str, Any]],
    bars_1h: List[Dict[str, Any]],
    symbol: str = "XAUUSD"
) -> Tuple[bool, str, float, float, str]:
    """
    Detects SETUP-ARCH-014: Macro H1 Reversal Origin Retest (MSS Ignition Base).
    Valid exclusively on Gold (XAUUSD); prohibited on GBPUSD.
    Finds unmitigated H1 Reversal MSS bases from the past 2 to 7 days and triggers
    on an M5 retest during active session hours.
    """
    if "XAU" not in symbol.upper():
        return False, "NONE", 0.0, 0.0, ""

    if len(bars_1h) < 48 or len(bars_5m) < 10:
        return False, "NONE", 0.0, 0.0, ""

    curr_p = bars_5m[-1]['close']
    curr_low = bars_5m[-1]['low']
    curr_high = bars_5m[-1]['high']

    recent_h1 = bars_1h[-120:]
    n = len(recent_h1)

    highs = []
    lows = []
    for k in range(3, n - 3):
        h_val = recent_h1[k]['high']
        l_val = recent_h1[k]['low']
        if all(h_val >= recent_h1[k-m]['high'] for m in range(1, 4)) and all(h_val >= recent_h1[k+m]['high'] for m in range(1, 4)):
            highs.append((k, h_val))
        if all(l_val <= recent_h1[k-m]['low'] for m in range(1, 4)) and all(l_val <= recent_h1[k+m]['low'] for m in range(1, 4)):
            lows.append((k, l_val))

    for i in range(15, n - 2):
        b = recent_h1[i]
        c = b['close']

        # Bullish MSS break
        prior_h = [h for h in highs if h[0] < i]
        if prior_h:
            last_sw_h = prior_h[-1]
            if c > last_sw_h[1] and b['close'] > b['open']:
                interim = recent_h1[max(last_sw_h[0], i-10) : i+1]
                if interim:
                    base_bar = min(interim, key=lambda x: x['low'])
                    impulse = c - base_bar['low']
                    if impulse >= 15.0:
                        og_high = max(base_bar['open'], base_bar['close'])
                        og_low = base_bar['low']
                        inval_sl = og_low - 2.00

                        subsequent = recent_h1[i+1:]
                        if not any(sb['close'] < inval_sl for sb in subsequent):
                            if curr_low <= og_high and curr_high >= og_low:
                                entry = curr_p
                                risk = entry - inval_sl
                                if 4.00 <= risk <= 10.00:
                                    desc = f"H1 Bullish MSS Origin Retest (Ignition Base: {og_low:.2f}-{og_high:.2f}; SL: {inval_sl:.2f})"
                                    return True, "BULLISH", entry, inval_sl, desc

        # Bearish MSS break
        prior_l = [l for l in lows if l[0] < i]
        if prior_l:
            last_sw_l = prior_l[-1]
            if c < last_sw_l[1] and b['close'] < b['open']:
                interim = recent_h1[max(last_sw_l[0], i-10) : i+1]
                if interim:
                    base_bar = max(interim, key=lambda x: x['high'])
                    impulse = base_bar['high'] - c
                    if impulse >= 15.0:
                        og_high = base_bar['high']
                        og_low = min(base_bar['open'], base_bar['close'])
                        inval_sl = og_high + 2.00

                        subsequent = recent_h1[i+1:]
                        if not any(sb['close'] > inval_sl for sb in subsequent):
                            if curr_high >= og_low and curr_low <= og_high:
                                entry = curr_p
                                risk = inval_sl - entry
                                if 4.00 <= risk <= 10.00:
                                    desc = f"H1 Bearish MSS Origin Retest (Ignition Base: {og_low:.2f}-{og_high:.2f}; SL: {inval_sl:.2f})"
                                    return True, "BEARISH", entry, inval_sl, desc

    return False, "NONE", 0.0, 0.0, ""


def detect_ny_trend_continuation(
    bars_5m: List[Dict[str, Any]],
    bars_1h: Optional[List[Dict[str, Any]]],
    symbol: str = "XAUUSD"
) -> Tuple[bool, str, float, float, str]:
    """
    Detects SETUP-ARCH-015: NY Open One-Sided Trend Continuation Sweep on Gold.
    Conditions (strictly causal on closed bars):
      1. Symbol is XAUUSD and bar closes inside [NY Open .. NYSE Cash Open + 60m] via dynamic DST.
      2. London made a clean one-sided expansion past Asian Range (>= $4.00) without sweeping
         the opposite Asian boundary.
      3. Closed H1 close is aligned with H1 EMA(50).
      4. Pullback reached >= 45% of the post-London leg before/on the trigger bar.
      5. Closed 5M trigger bar (range >= $2.00) sweeps prior 6-bar high/low with >= 25% wick
         and closes in the outer 40% in the trend direction ($1.80 <= risk <= $20.00).
    """
    if "XAU" not in symbol.upper():
        return False, "NONE", 0.0, 0.0, ""
    if not bars_5m or len(bars_5m) < 12 or not bars_1h or len(bars_1h) < 50:
        return False, "NONE", 0.0, 0.0, ""

    offset_sec = 7200
    try:
        from hitl.backtest.chart_renderer import get_broker_utc_offset_seconds
        offset_sec = get_broker_utc_offset_seconds()
    except Exception:
        pass

    cur = bars_5m[-1]
    sig_utc = int(cur['time']) - offset_sec
    sig_dt = datetime.datetime.fromtimestamp(sig_utc, tz=datetime.timezone.utc)
    stimes = get_session_times_for_date(sig_dt.date())
    lon_utc = int(stimes["london"]["utc_time"].timestamp())
    ny_utc = int(stimes["new_york"]["utc_time"].timestamp())
    nyse_utc = int(stimes["nyse_open"]["utc_time"].timestamp())

    if not (ny_utc <= sig_utc <= nyse_utc + 3600):
        return False, "NONE", 0.0, 0.0, ""

    # Day rollover matches MT5 server 00:00 -> UTC epoch
    day_srv_date = datetime.datetime.fromtimestamp(int(cur['time']), tz=datetime.timezone.utc).date()
    day_start_utc = int(datetime.datetime(day_srv_date.year, day_srv_date.month, day_srv_date.day, 0, 0, tzinfo=datetime.timezone.utc).timestamp()) - offset_sec

    m5_day = [b for b in bars_5m if (int(b['time']) - offset_sec) >= day_start_utc]
    asia_bars = [b for b in m5_day if (int(b['time']) - offset_sec) < lon_utc]
    post_lon = [b for b in m5_day if (int(b['time']) - offset_sec) >= lon_utc]

    # If live caller only supplied a short M5 slice (e.g. 120 bars = 10h), backfill earlier today bounds from H1
    if bars_5m and (int(bars_5m[0]['time']) - offset_sec) > day_start_utc:
        h1_today = [b for b in bars_1h if day_start_utc <= (int(b['time']) - offset_sec) < sig_utc]
        asia_h1 = [b for b in h1_today if (int(b['time']) - offset_sec) + 3600 <= lon_utc]
        if len(asia_bars) < 6 and asia_h1:
            asia_bars = asia_bars + asia_h1
        earliest_m5_utc = int(bars_5m[0]['time']) - offset_sec
        early_lon_h1 = [b for b in h1_today if lon_utc <= (int(b['time']) - offset_sec) < earliest_m5_utc]
        if early_lon_h1:
            post_lon = early_lon_h1 + post_lon

    if not asia_bars or len(post_lon) < 10:
        return False, "NONE", 0.0, 0.0, ""

    asia_h = max(b['high'] for b in asia_bars)
    asia_l = min(b['low'] for b in asia_bars)
    if asia_h - asia_l < 4.0:
        return False, "NONE", 0.0, 0.0, ""

    lon_h = max(b['high'] for b in post_lon)
    lon_l = min(b['low'] for b in post_lon)
    hit_ah = lon_h >= asia_h
    hit_al = lon_l <= asia_l
    one_bear = hit_al and (not hit_ah) and (asia_l - lon_l) >= 4.0
    one_bull = hit_ah and (not hit_al) and (lon_h - asia_h) >= 4.0
    if not (one_bear or one_bull):
        return False, "NONE", 0.0, 0.0, ""

    # Causal H1 EMA(50) matching pandas ewm(span=50, adjust=False)
    alpha = 2.0 / (50.0 + 1.0)
    ema50 = float(bars_1h[0]['close'])
    for hb in bars_1h[1:]:
        ema50 = alpha * float(hb['close']) + (1.0 - alpha) * ema50
    h1_close = float(bars_1h[-1]['close'])

    cur_rng = cur['high'] - cur['low']
    if cur_rng < 2.0:
        return False, "NONE", 0.0, 0.0, ""

    pre6 = bars_5m[-7:-1]
    pre6_h = max(b['high'] for b in pre6)
    pre6_l = min(b['low'] for b in pre6)
    leg = lon_h - lon_l
    if leg <= 0:
        return False, "NONE", 0.0, 0.0, ""

    if one_bear and h1_close < ema50 and cur['high'] < asia_h:
        uw = cur['high'] - max(cur['open'], cur['close'])
        ret = (cur['high'] - lon_l) / leg
        if (
            cur['high'] > pre6_h
            and cur['close'] < cur['open']
            and cur['close'] <= cur['low'] + 0.40 * cur_rng
            and (uw / cur_rng) >= 0.25
            and ret >= 0.45
        ):
            entry = round(cur['close'], 2)
            sl = round(cur['high'] + 1.50, 2)
            risk = sl - entry
            if 1.80 <= risk <= 20.00:
                desc = f"NY Open One-Sided Bearish Trend Continuation (Swept pre-NY ceiling {pre6_h:.2f}, ret {ret*100:.0f}%, H1<EMA50 {ema50:.2f})"
                return True, "BEARISH", entry, sl, desc

    if one_bull and h1_close > ema50 and cur['low'] > asia_l:
        lw = min(cur['open'], cur['close']) - cur['low']
        ret = (lon_h - cur['low']) / leg
        if (
            cur['low'] < pre6_l
            and cur['close'] > cur['open']
            and cur['close'] >= cur['high'] - 0.40 * cur_rng
            and (lw / cur_rng) >= 0.25
            and ret >= 0.45
        ):
            entry = round(cur['close'], 2)
            sl = round(cur['low'] - 1.50, 2)
            risk = entry - sl
            if 1.80 <= risk <= 20.00:
                desc = f"NY Open One-Sided Bullish Trend Continuation (Swept pre-NY floor {pre6_l:.2f}, ret {ret*100:.0f}%, H1>EMA50 {ema50:.2f})"
                return True, "BULLISH", entry, sl, desc

    return False, "NONE", 0.0, 0.0, ""


def screen_ict_session(
    bars_5m: List[Dict[str, Any]],
    bars_1h: List[Dict[str, Any]],
    symbol: str,
    session_hour: int,
    smt_info: Optional[Dict[str, Any]] = None,
    bars_1m: Optional[List[Dict[str, Any]]] = None,
    bars_1d: Optional[List[Dict[str, Any]]] = None,
    closed_bars_only: bool = True
) -> Dict[str, Any]:
    """
    Advanced SMC Pre-Screener combining:
    1. Session Liquidity Sweeps (Asian/London High & Low)
    2. 5M Fair Value Gaps (Proximal & Distal with contract-scaled thresholds)
    3. Market Structure Shifts (MSS) & Breaker Blocks (BB)
    4. Optimal Trade Entry (OTE) alignment in Discount/Premium
    5. Daily Regime & Range Compression Gate (suppresses continuation setups in chop)

    Closed-bars only (closed_bars_only=True, the default): the last bar of
    every series passed in is the *forming* bar at the decision moment — its
    close/high/low are not final, so using it is lookahead/repainting (a
    setup that "fires" on the forming bar can un-fire before the bar
    closes, and the forward M1 window would then include the signal bar
    itself). With the default, the forming bar is dropped from every
    series, the signal is formed only on the last *closed* bar, and the
    entry is a limit order to be filled on the *next* bar (forward M1
    must start at/after the signal bar's close — see
    HistoricalDataFeed.get_forward_m1_bars(closed_bars_only=True)).
    Pass closed_bars_only=False only for research that explicitly wants
    the old forming-bar behaviour; the returned dict always reports
    which mode was used and the signal bar's time.
    """
    # Drop the forming bar from every series before any detector runs.
    if closed_bars_only:
        bars_5m = bars_5m[:-1]
        bars_1h = bars_1h[:-1]
        if bars_1d is not None:
            bars_1d = bars_1d[:-1]
        if bars_1m is not None:
            bars_1m = bars_1m[:-1]
    signal_bar_time = bars_5m[-1]['time'] if bars_5m else None

    if len(bars_5m) < 40 or len(bars_1h) < 10:
        return {
            "has_setup": False,
            "reason": "Insufficient bar history",
            "setup_type": "NONE",
            "closed_bars_only": closed_bars_only,
            "signal_bar_time": signal_bar_time
        }

    current_price = bars_5m[-1]['close']
    sym = symbol.upper()
    is_gbp = "GBP" in sym
    is_crypto = "BTC" in sym or "ETH" in sym

    # Policy Mandate: Bitcoin/Crypto permanently decommissioned from SMC Price Action Engine
    # 1-year empirical audit proved -49.56R drag (17.6% WR, PF 0.76). Crypto trades exclusively via Autonomous Quant Engine.
    if is_crypto:
        return {
            "has_setup": False,
            "reason": "Veto: Bitcoin/Crypto permanently decommissioned from SMC Engine per 1-year empirical audit (-49.56R drag). Crypto trades exclusively via Autonomous Quant Engine.",
            "setup_type": "NONE",
            "closed_bars_only": closed_bars_only,
            "signal_bar_time": signal_bar_time
        }

    is_spx = "SPX" in sym or "US500" in sym
    is_ym = "YM" in sym or "US30" in sym
    is_nq = "NQ" in sym or "NAS" in sym or "US100" in sym
    is_index = is_nq or is_spx or is_ym
    is_fx = "EUR" in sym or is_gbp
    is_silver = "XAG" in sym
    if is_spx:
        fmt = ".1f"
        unit = "pts"
        min_range = 8.0
        breaker_tol = 2.0
    elif is_ym:
        fmt = ".1f"
        unit = "pts"
        min_range = 60.0
        breaker_tol = 12.0
    elif is_nq:
        fmt = ".1f"
        unit = "pts"
        min_range = 35.0
        breaker_tol = 8.0
    elif is_crypto:
        fmt = ".2f"
        unit = "pts"
        min_range = 150.0
        breaker_tol = 35.0
    elif is_fx:
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

    def _build_setup_package(
        mtf_ctx: Dict[str, Any],
        arch_id: str,
        setup_type: str,
        entry_p: float,
        sl_p: Optional[float],
        reason_text: str,
        direction: str,
    ) -> Dict[str, Any]:
        from hitl.backtest.mtf_structure import classify_setup_phase
        p_info = classify_setup_phase(mtf_ctx, direction, symbol=symbol)
        rec_target = p_info["recommended_target_rr"]
        rec_be = p_info["recommended_be_rr"]
        if arch_id == "SETUP-ARCH-001" and "XAU" in symbol.upper():
            rec_target = 2.0  # Calibrated for Gold Judas High fade (48.1% WR, +16.00R, PF 2.60)
            rec_be = 1.2      # Early breakeven ratchet to eliminate adverse mean-reversion
        elif arch_id == "SETUP-ARCH-015" and "XAU" in symbol.upper():
            rec_target = 2.5  # Calibrated across 17-month OOS+IS audit (89tr, +25.45R, PF 1.55)
            rec_be = 1.5

        return {
            "has_setup": True,
            "reason": f"[{arch_id}] {reason_text} | Scaled Entry: {entry_p:{fmt}} | Phase: {p_info['phase']}",
            "setup_type": setup_type,
            "archetype_id": arch_id,
            "entry_ref": entry_p,
            "sl_ref": sl_p,
            "mtf_info": mtf_ctx,
            "recommended_target_rr": rec_target,
            "recommended_be_rr": rec_be,
            "phase": p_info["phase"],
            "poi_ratio": p_info["poi_ratio"],
            "dol_target": p_info["dol_target"],
            "phase_summary": p_info["summary"],
            # Signal formed on the last closed bar; entry is a limit order
            # to be filled on the next bar (see closed_bars_only above).
            "closed_bars_only": closed_bars_only,
            "signal_bar_time": signal_bar_time,
        }

    # 1. Prior Session Liquidity Benchmark & Polarity
    if session_hour in (9, 10, 11, 12, 13):
        # Gold London Continuation produces -$7.49R empirical drag (PF 0.81); restricted to London Open
        if "XAU" in symbol.upper():
            is_lon_continuation = False
            if signal_bar_time:
                # MT5 bar timestamps are broker server time (EET = UTC+2 in winter, UTC+3 in summer)
                offset_sec = 7200
                try:
                    from hitl.backtest.chart_renderer import get_broker_utc_offset_seconds
                    offset_sec = get_broker_utc_offset_seconds()
                except Exception:
                    pass
                sig_dt = datetime.datetime.fromtimestamp(int(signal_bar_time) - offset_sec, tz=datetime.timezone.utc)
                stimes = get_session_times_for_date(sig_dt.date())
                lon_open_utc = stimes["london"]["utc_time"]
                lon_cont_start_utc = lon_open_utc + datetime.timedelta(hours=2)
                lon_end_utc = lon_open_utc + datetime.timedelta(hours=4)
                if lon_cont_start_utc <= sig_dt < lon_end_utc:
                    is_lon_continuation = True
            elif session_hour in (14, 15):
                is_lon_continuation = True

            if is_lon_continuation:
                return {
                    "has_setup": False,
                    "reason": "Veto: London Continuation window bypassed on Gold per 1-year empirical audit (London Open & NY Open only)",
                    "setup_type": "BYPASSED_SESSION",
                    "closed_bars_only": closed_bars_only,
                    "signal_bar_time": signal_bar_time
                }
        session_window = bars_5m[-84:-10] if len(bars_5m) >= 84 else bars_5m[:-10]
        session_label = "Asian Range"
    elif session_hour in (14, 15, 16):
        if is_gbp:
            # NY Open on GBPUSD is an empirical drag (-21.55R, PF 0.67); institutional alpha is strictly in London sessions
            return {
                "has_setup": False,
                "reason": "Veto: NY Open window bypassed on GBPUSD per 1-year empirical audit (London sessions only)",
                "setup_type": "BYPASSED_SESSION",
                "closed_bars_only": closed_bars_only,
                "signal_bar_time": signal_bar_time
            }
        if is_nq:
            # NY Pre-Market on NQ is an empirical drag (-4.44R, PF 0.73); NQ alpha is strictly in London Open Bearish Judas fade
            return {
                "has_setup": False,
                "reason": "Veto: NY Pre-Market window bypassed on NQ per 1-year empirical audit (London Open fade only)",
                "setup_type": "BYPASSED_SESSION",
                "closed_bars_only": closed_bars_only,
                "signal_bar_time": signal_bar_time
            }
        session_window = bars_5m[-72:-10] if len(bars_5m) >= 72 else bars_5m[:-10]
        session_label = "London Range"
    elif session_hour in (17, 18, 19):
        # NY Silver Bullet / NYSE Cash Window (17:00 - 20:00 Tehran / 09:30 - 11:30 NY)
        # Allow DST-validated SETUP-ARCH-015 during Winter NY Open..NYSE+1h before applying legacy session ban
        if "XAU" in symbol.upper() and setup_registry.is_archetype_ratified("SETUP-ARCH-015"):
            has_ny_cont, nyc_dir, nyc_entry, nyc_sl, nyc_desc = detect_ny_trend_continuation(
                bars_5m, bars_1h, symbol=symbol
            )
            if has_ny_cont:
                from hitl.backtest.mtf_structure import analyze_mtf_state
                nyc_mtf = analyze_mtf_state(bars_1d=bars_1d, bars_1h=bars_1h, bars_5m=bars_5m, symbol=symbol)
                nyc_dir_label = "LONG" if nyc_dir == "BULLISH" else "SHORT"
                return _build_setup_package(nyc_mtf, "SETUP-ARCH-015", f"{nyc_dir}_NY_TREND_CONT", nyc_entry, nyc_sl, nyc_desc, nyc_dir_label)
        if "XAU" in symbol.upper() or is_gbp or is_nq:
            # Banned on Gold (-33.01R), Cable (-6.54R), and NQ per 1-year empirical audit
            return {
                "has_setup": False,
                "reason": f"Veto: Late NY PM / Silver Bullet window banned on {symbol} per 1-year empirical audit",
                "setup_type": "BANNED_SESSION",
                "closed_bars_only": closed_bars_only,
                "signal_bar_time": signal_bar_time
            }
        session_window = bars_5m[-36:-6] if len(bars_5m) >= 36 else bars_5m[:-6]
        session_label = "NY AM Range"
    else:
        # Off-hours / Pacific / Overnight Range
        session_window = bars_5m[-36:-6] if len(bars_5m) >= 36 else bars_5m[:-6]
        session_label = "Prior Session Range"

    if not session_window:
        return {"has_setup": False, "reason": "No session window data", "setup_type": "NONE", "closed_bars_only": closed_bars_only, "signal_bar_time": signal_bar_time}

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
            "setup_type": "NONE",
            "closed_bars_only": closed_bars_only,
            "signal_bar_time": signal_bar_time
        }

    # 2. Liquidity Sweeps vs Breakouts in recent 10 bars
    recent_bars = bars_5m[-10:]
    recent_high = max(b['high'] for b in recent_bars)
    recent_low = min(b['low'] for b in recent_bars)

    pierced_high = recent_high >= range_high
    pierced_low = recent_low <= range_low

    breakout_buf = 1.5 if is_spx else (8.0 if is_ym else (6.0 if is_nq else (30.0 if is_crypto else (1.0 if "XAU" in symbol.upper() else (0.10 if is_silver else 0.0008)))))
    rejection_buf = 0.8 if is_spx else (4.0 if is_ym else (3.0 if is_nq else (15.0 if is_crypto else (0.5 if "XAU" in symbol.upper() else (0.05 if is_silver else 0.0004)))))

    is_bullish_breakout = pierced_high and current_price > (range_high + breakout_buf) and recent_bars[-1]['close'] > recent_bars[-1]['open']
    is_bearish_breakdown = pierced_low and current_price < (range_low - breakout_buf) and recent_bars[-1]['close'] < recent_bars[-1]['open']

    # Rejection Sweep requires piercing but closing back inside or counter-reversal
    swept_high = pierced_high and not is_bullish_breakout and (current_price <= (range_high + rejection_buf) or recent_bars[-1]['close'] < recent_bars[-1]['open'])
    swept_low = pierced_low and not is_bearish_breakdown and (current_price >= (range_low - rejection_buf) or recent_bars[-1]['close'] > recent_bars[-1]['open'])

    # 2b. Multi-Timeframe Structural & Phase Analysis (Daily DOL + 1H MSS)
    from hitl.backtest.mtf_structure import analyze_mtf_state, classify_setup_phase
    mtf_state = analyze_mtf_state(bars_1d=bars_1d, bars_1h=bars_1h, bars_5m=bars_5m, symbol=symbol)

    if mtf_state.get("is_dead_consolidation", False):
        return {
            "has_setup": False,
            "reason": f"Dead market: Mid-range equilibrium compression ({mtf_state.get('h1_state', 'NEUTRAL')})",
            "setup_type": "NONE",
            "closed_bars_only": closed_bars_only,
            "signal_bar_time": signal_bar_time,
            "mtf_info": mtf_state
        }

    in_mid_equilibrium = mtf_state.get("in_mid_equilibrium", False)
    is_inside_day = mtf_state.get("is_inside_day", False)

    def _package_setup(arch_id: str, setup_type: str, entry_p: float, sl_p: Optional[float], reason_text: str, direction: str) -> Dict[str, Any]:
        return _build_setup_package(mtf_state, arch_id, setup_type, entry_p, sl_p, reason_text, direction)

    short_phase = classify_setup_phase(mtf_state, "SHORT", symbol)
    long_phase = classify_setup_phase(mtf_state, "LONG", symbol)

    # 3. Detect FVG & Breaker Blocks with Asset Specifics
    has_fvg, fvg_dir, fvg_proximal, fvg_distal = detect_fvg_5m(bars_5m, lookback=12, symbol=symbol)
    has_breaker, breaker_type, breaker_price = detect_breaker_and_mss(bars_5m, lookback=24, symbol=symbol)

    # 4. Multi-Tool SMC Confluence Matching (Strictly Gated by Review Council Ratification)

    # Setup Intermarket: SMT Divergence & Mitigation (SETUP-ARCH-005 Metals / SETUP-ARCH-006 Forex / SETUP-ARCH-007 Counter POI)
    if smt_info and smt_info.get("has_smt"):
        arch_id = "SETUP-ARCH-007" if (setup_registry.is_archetype_ratified("SETUP-ARCH-007") and (swept_low or swept_high)) else ("SETUP-ARCH-006" if is_fx else "SETUP-ARCH-005")
        if not setup_registry.is_archetype_ratified(arch_id):
            return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED", "closed_bars_only": closed_bars_only, "signal_bar_time": signal_bar_time}

        smt_type = smt_info.get("smt_type")
        if smt_type == "BEARISH_SMT" and not is_bullish_breakout and (swept_high or fvg_dir == "BEARISH" or breaker_type == "BEARISH_BREAKER"):
            scaled_fvg = scale_poi_depth(fvg_proximal, fvg_distal, is_bullish=False, is_fx=is_fx, ratio=short_phase["poi_ratio"], is_crypto=is_crypto, is_index=is_index, symbol=symbol)
            entry_p = scaled_fvg if (has_fvg and fvg_dir == "BEARISH") else (breaker_price if has_breaker else range_high)
            sl_dist = 12.0 if is_spx else (60.0 if is_ym else (50.0 if is_nq else (350.0 if is_crypto else (6.0 if "XAU" in symbol.upper() else (0.25 if is_silver else 0.0015)))))
            sl_buf = 1.0 if is_spx else (6.0 if is_ym else (4.0 if is_nq else (25.0 if is_crypto else (1.50 if "XAU" in symbol.upper() else 0.0010))))
            sl_p = max(range_high + sl_buf, entry_p + sl_dist)
            return _package_setup(arch_id, "BEARISH_SMT_MITIGATION", entry_p, sl_p, f"BEARISH SMT: {smt_info.get('summary', '')}", "SHORT")
        elif smt_type == "BULLISH_SMT" and not is_bearish_breakdown and (swept_low or fvg_dir == "BULLISH" or breaker_type == "BULLISH_BREAKER"):
            scaled_fvg = scale_poi_depth(fvg_proximal, fvg_distal, is_bullish=True, is_fx=is_fx, ratio=long_phase["poi_ratio"], is_crypto=is_crypto, is_index=is_index, symbol=symbol)
            entry_p = scaled_fvg if (has_fvg and fvg_dir == "BULLISH") else (breaker_price if has_breaker else range_low)
            sl_dist = 12.0 if is_spx else (60.0 if is_ym else (50.0 if is_nq else (350.0 if is_crypto else (6.0 if "XAU" in symbol.upper() else (0.25 if is_silver else 0.0015)))))
            sl_buf = 1.0 if is_spx else (6.0 if is_ym else (4.0 if is_nq else (25.0 if is_crypto else (1.50 if "XAU" in symbol.upper() else 0.0010))))
            sl_p = min(range_low - sl_buf, entry_p - sl_dist)
            return _package_setup(arch_id, "BULLISH_SMT_MITIGATION", entry_p, sl_p, f"BULLISH SMT: {smt_info.get('summary', '')}", "LONG")

    # Setup A: Judas Swing + Breaker Block (SETUP-ARCH-001)
    # Decommissioned on GBPUSD per 1-year audit (13.0% WR, -8.50R loss, PF 0.47)
    if swept_high and not is_bullish_breakout and breaker_type == "BEARISH_BREAKER" and not is_gbp:
        arch_id = "SETUP-ARCH-001"
        if not setup_registry.is_archetype_ratified(arch_id):
            return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED", "closed_bars_only": closed_bars_only, "signal_bar_time": signal_bar_time}
        sl_buf = 1.0 if is_spx else (6.0 if is_ym else (4.0 if is_nq else (25.0 if is_crypto else (1.50 if "XAU" in symbol.upper() else 0.0010))))
        sweep_high = max(recent_high, range_high)
        sl_p = sweep_high + sl_buf
        return _package_setup(arch_id, "BEARISH_BREAKER_SWEEP", breaker_price, sl_p, f"Swept {session_label} High ({sweep_high:{fmt}}) + Bearish Breaker Block", "SHORT")

    # Bullish Breaker decommissioned on GBPUSD (-9.50R), NQ (10% WR, -6.02R drag), and Gold (18.8% WR, -4.00R drag, PF 0.79) per 1-year audit
    if swept_low and not is_bearish_breakdown and breaker_type == "BULLISH_BREAKER" and not is_gbp and not is_nq and "XAU" not in symbol.upper():
        arch_id = "SETUP-ARCH-001"
        if not setup_registry.is_archetype_ratified(arch_id):
            return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED", "closed_bars_only": closed_bars_only, "signal_bar_time": signal_bar_time}
        sl_buf = 1.0 if is_spx else (6.0 if is_ym else (4.0 if is_nq else (25.0 if is_crypto else (1.50 if "XAU" in symbol.upper() else 0.0010))))
        sweep_low = min(recent_low, range_low)
        sl_p = sweep_low - sl_buf
        return _package_setup(arch_id, "BULLISH_BREAKER_SWEEP", breaker_price, sl_p, f"Swept {session_label} Low ({sweep_low:{fmt}}) + Bullish Breaker Block", "LONG")

    # Setup B: Judas Swing + Fair Value Gap (SETUP-ARCH-002)
    # Decommissioned on Gold per 2-month empirical audit (-11.0R loss, 12.5% WR)
    if "XAU" not in symbol.upper():
        if swept_high and not is_bullish_breakout and fvg_dir == "BEARISH":
            arch_id = "SETUP-ARCH-002"
            if not setup_registry.is_archetype_ratified(arch_id):
                return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED", "closed_bars_only": closed_bars_only, "signal_bar_time": signal_bar_time}
            scaled_entry = scale_poi_depth(fvg_proximal, fvg_distal, is_bullish=False, is_fx=is_fx, ratio=short_phase["poi_ratio"], is_crypto=is_crypto, is_index=is_index, symbol=symbol)
            sl_dist = 10.0 if is_spx else (50.0 if is_ym else (45.0 if is_nq else (300.0 if is_crypto else (0.25 if is_silver else 0.0015))))
            sl_buf = 1.0 if is_spx else (6.0 if is_ym else (4.0 if is_nq else (25.0 if is_crypto else 0.0010)))
            sl_p = max(range_high + sl_buf, scaled_entry + sl_dist)
            return _package_setup(arch_id, "BEARISH_SWEEP_FVG", scaled_entry, sl_p, f"Swept {session_label} High ({range_high:{fmt}}) + Bearish FVG", "SHORT")

        if swept_low and not is_bearish_breakdown and fvg_dir == "BULLISH":
            arch_id = "SETUP-ARCH-002"
            if not setup_registry.is_archetype_ratified(arch_id):
                return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED", "closed_bars_only": closed_bars_only, "signal_bar_time": signal_bar_time}
            scaled_entry = scale_poi_depth(fvg_proximal, fvg_distal, is_bullish=True, is_fx=is_fx, ratio=long_phase["poi_ratio"], is_crypto=is_crypto, is_index=is_index, symbol=symbol)
            sl_dist = 10.0 if is_spx else (50.0 if is_ym else (45.0 if is_nq else (300.0 if is_crypto else (0.25 if is_silver else 0.0015))))
            sl_buf = 1.0 if is_spx else (6.0 if is_ym else (4.0 if is_nq else (25.0 if is_crypto else 0.0010)))
            sl_p = min(range_low - sl_buf, scaled_entry - sl_dist)
            return _package_setup(arch_id, "BULLISH_SWEEP_FVG", scaled_entry, sl_p, f"Swept {session_label} Low ({range_low:{fmt}}) + Bullish FVG", "LONG")

    # Setup C: Clean Market Structure Shift (MSS) with Breaker Block retest (SETUP-ARCH-003)
    # Gated: Must NOT be trapped in mid-range equilibrium chop, and must have a tight retest
    if not in_mid_equilibrium:
        if breaker_type == "BEARISH_BREAKER" and abs(current_price - breaker_price) <= breaker_tol:
            arch_id = "SETUP-ARCH-003"
            if not setup_registry.is_archetype_ratified(arch_id):
                return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED", "closed_bars_only": closed_bars_only, "signal_bar_time": signal_bar_time}
            sl_dist = 12.0 if is_spx else (60.0 if is_ym else (50.0 if is_nq else (350.0 if is_crypto else (6.0 if "XAU" in symbol.upper() else 0.0015))))
            sl_p = breaker_price + sl_dist
            return _package_setup(arch_id, "BEARISH_BREAKER_RETEST", breaker_price, sl_p, f"Bearish Breaker Block retest at {breaker_price:{fmt}}", "SHORT")

        if breaker_type == "BULLISH_BREAKER" and abs(current_price - breaker_price) <= breaker_tol:
            arch_id = "SETUP-ARCH-003"
            if not setup_registry.is_archetype_ratified(arch_id):
                return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED", "closed_bars_only": closed_bars_only, "signal_bar_time": signal_bar_time}
            sl_dist = 12.0 if is_spx else (60.0 if is_ym else (50.0 if is_nq else (350.0 if is_crypto else (6.0 if "XAU" in symbol.upper() else 0.0015))))
            sl_p = breaker_price - sl_dist
            return _package_setup(arch_id, "BULLISH_BREAKER_RETEST", breaker_price, sl_p, f"Bullish Breaker Block retest at {breaker_price:{fmt}}", "LONG")

    # Setup D: Institutional Range Expansion (SETUP-ARCH-004)
    # Decommissioned on XAUUSD (-15.05R drag, 24.5% WR), GBPUSD (-8.50R drag), and NQ (0% WR) per 1-year audits.
    if not (in_mid_equilibrium or is_inside_day) and not is_nq and not is_gbp and "XAU" not in symbol.upper():
        if is_bullish_breakout and fvg_dir == "BULLISH":
            arch_id = "SETUP-ARCH-004"
            if not setup_registry.is_archetype_ratified(arch_id):
                return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED", "closed_bars_only": closed_bars_only, "signal_bar_time": signal_bar_time}
            sl_buf = 1.0 if is_spx else (6.0 if is_ym else (4.0 if is_nq else (25.0 if is_crypto else (1.50 if "XAU" in symbol.upper() else 0.0010))))
            sl_p = fvg_distal - sl_buf
            return _package_setup(arch_id, "BULLISH_EXPANSION", fvg_proximal, sl_p, f"Breakout above {session_label} High with Bullish FVG", "LONG")

        if is_bearish_breakdown and fvg_dir == "BEARISH":
            arch_id = "SETUP-ARCH-004"
            if not setup_registry.is_archetype_ratified(arch_id):
                return {"has_setup": False, "reason": f"Veto: Archetype {arch_id} is UNRATIFIED", "setup_type": "UNRATIFIED", "closed_bars_only": closed_bars_only, "signal_bar_time": signal_bar_time}
            sl_buf = 1.0 if is_spx else (6.0 if is_ym else (4.0 if is_nq else (25.0 if is_crypto else (1.50 if "XAU" in symbol.upper() else 0.0010))))
            sl_p = fvg_distal + sl_buf
            return _package_setup(arch_id, "BEARISH_EXPANSION", fvg_proximal, sl_p, f"Breakdown below {session_label} Low with Bearish FVG", "SHORT")

    # Setup E: Pro-Trend Session Breakdown/Breakout Origin Retest (SETUP-ARCH-009)
    # PERMANENTLY DECOMMISSIONED ACROSS ALL ASSETS (-77.41R loss, 11.6% WR in 1-year audit)
    # Deep OTE 50%-70.5% retracements consistently enter into adverse momentum continuations.

    # Setup F: Prominent Liquidity Sweep with Pro-Trend M1/5M MSS Displacement (SETUP-ARCH-010)
    # Decommissioned on NQ (14.5% WR) and Gold (7.4% WR, -8.0R drag, PF 0.47) per 1-year empirical audits
    if not is_nq and "XAU" not in symbol.upper():
        has_prom_sweep, sweep_dir, sweep_entry, sweep_sl, sweep_desc = detect_prominent_sweep_and_mss(
            bars_5m, symbol, bars_1m=bars_1m
        )
        if has_prom_sweep and setup_registry.is_archetype_ratified("SETUP-ARCH-010"):
            arch_id = "SETUP-ARCH-010"
            direction = "LONG" if sweep_dir == "BULLISH" else "SHORT"
            return _package_setup(arch_id, f"{sweep_dir}_PROMINENT_SWEEP_MSS", sweep_entry, sweep_sl, sweep_desc, direction)

    # Setup G: Nested Double MSS with Prior Liquidity Sweep (SETUP-ARCH-011)
    has_nested, nested_dir, nested_entry, nested_sl, nested_desc = detect_nested_double_mss(
        bars_5m, symbol=symbol
    )
    if has_nested and setup_registry.is_archetype_ratified("SETUP-ARCH-011"):
        arch_id = "SETUP-ARCH-011"
        direction = "LONG" if nested_dir == "BULLISH" else "SHORT"
        return _package_setup(arch_id, f"{nested_dir}_NESTED_DOUBLE_MSS", nested_entry, nested_sl, nested_desc, direction)

    # Setup H: Macro ADR Exhaustion Mean-Reversion Snapback (SETUP-ARCH-012)
    has_adr_snap, snap_dir, snap_entry, snap_sl, snap_desc = detect_adr_exhaustion_snapback(
        bars_5m, bars_1d=bars_1d, bars_1h=bars_1h, symbol=symbol
    )
    if has_adr_snap and setup_registry.is_archetype_ratified("SETUP-ARCH-012"):
        arch_id = "SETUP-ARCH-012"
        direction = "LONG" if snap_dir == "BULLISH" else "SHORT"
        return _package_setup(arch_id, f"{snap_dir}_ADR_EXHAUSTION_SNAPBACK", snap_entry, snap_sl, snap_desc, direction)

    # Setup I: HTF Draw on Liquidity (DOL) Sweep & 15M Structural Trailing Runner (SETUP-ARCH-013)
    has_dol_runner, runner_dir, runner_entry, runner_sl, dol_tgt, runner_desc = detect_macro_dol_runner(
        bars_5m, bars_1h, bars_1d=bars_1d, bars_1m=bars_1m, symbol=symbol
    )
    if has_dol_runner and setup_registry.is_archetype_ratified("SETUP-ARCH-013"):
        arch_id = "SETUP-ARCH-013"
        direction = "LONG" if runner_dir == "BULLISH" else "SHORT"
        setup_pkg = _package_setup(arch_id, f"{runner_dir}_MACRO_DOL_RUNNER", runner_entry, runner_sl, runner_desc, direction)
        setup_pkg["dol_target"] = dol_tgt
        setup_pkg["target_mode"] = "HTF_DOL_WITH_15M_STRUCTURAL_TRAIL"
        return setup_pkg

    # Setup J: Macro H1 Reversal Origin Retest (SETUP-ARCH-014)
    has_rev_orig, orig_dir, orig_entry, orig_sl, orig_desc = detect_reversal_origin_retest(
        bars_5m, bars_1h, symbol=symbol
    )
    if has_rev_orig and setup_registry.is_archetype_ratified("SETUP-ARCH-014"):
        arch_id = "SETUP-ARCH-014"
        direction = "LONG" if orig_dir == "BULLISH" else "SHORT"
        return _package_setup(arch_id, f"{orig_dir}_H1_REVERSAL_ORIGIN_RETEST", orig_entry, orig_sl, orig_desc, direction)

    # Setup K: NY Open One-Sided Trend Continuation Sweep (SETUP-ARCH-015)
    has_ny_cont, nyc_dir, nyc_entry, nyc_sl, nyc_desc = detect_ny_trend_continuation(
        bars_5m, bars_1h, symbol=symbol
    )
    if has_ny_cont and setup_registry.is_archetype_ratified("SETUP-ARCH-015"):
        arch_id = "SETUP-ARCH-015"
        direction = "LONG" if nyc_dir == "BULLISH" else "SHORT"
        return _package_setup(arch_id, f"{nyc_dir}_NY_TREND_CONT", nyc_entry, nyc_sl, nyc_desc, direction)

    # Price in equilibrium consolidation or no ratified archetype entry criteria met
    return {
        "has_setup": False,
        "reason": f"No ratified entry criteria met: Equilibrium consolidation at {current_price:{fmt}} within {session_label} ({range_low:{fmt}} - {range_high:{fmt}})",
        "setup_type": "NONE",
        "closed_bars_only": closed_bars_only,
        "signal_bar_time": signal_bar_time
    }
