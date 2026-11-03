"""
TradingGuard HITL - Multi-Timeframe (MTF) Structural & Phase Analyzer
Synchronizes Daily (1D), 1-Hour (1H), 15-Minute (15M), and 5-Minute (5M) timeframes:
1. Daily Macro Context: Computes Draw on Liquidity (DOL), Prior Day Range (PDR), and Inside Day Equilibrium.
2. 1-Hour Structural State Machine: Detects genuine institutional Market Structure Shifts (MSS)
   and tracks structural invalidation levels chronologically without lookahead.
3. Phase Classification per Trade Direction:
   - PRO_EXPANSION: Direction aligned with 1H MSS (Bigger Target: 4.5R, Runner mode / No early BE choke, Proximal entry).
   - HTF_RETRACEMENT: Counter-trend pullback seeking internal POI (Smaller Target: 2.2R, Fast 1.5R BE defense, Deep OTE entry).
   - BALANCED_RANGE: Neutral 1H regime (Standard 2.5R target, 1.5R BE).
   - CONSOLIDATION: Mid-range equilibrium compression on inside days (Trade suppression / Stand Aside).
"""

from typing import List, Dict, Any, Tuple, Optional
import datetime


def analyze_mtf_state(
    bars_1d: Optional[List[Dict[str, Any]]],
    bars_1h: Optional[List[Dict[str, Any]]],
    bars_5m: List[Dict[str, Any]],
    symbol: str = "XAUUSD"
) -> Dict[str, Any]:
    """
    Analyzes Daily and 1-Hour market structure up to timestamp T.
    Returns market state dictionary for phase classification.
    """
    if not bars_5m:
        return _fallback_state("No 5M bars")

    current_price = bars_5m[-1]['close']
    is_gold = "XAU" in symbol.upper()
    is_silver = "XAG" in symbol.upper()
    is_fx = "EUR" in symbol.upper() or "GBP" in symbol.upper()

    # 1. Daily Macro Context
    pdh, pdl, pdr = None, None, None
    in_mid_equilibrium = False
    is_inside_day = False
    dol_external = None
    dol_internal = None

    if bars_1d and len(bars_1d) >= 2:
        pd = bars_1d[-2]
        pdh = pd['high']
        pdl = pd['low']
        pdr = pdh - pdl
        cd = bars_1d[-1]

        is_inside_day = (cd['high'] <= pdh and cd['low'] >= pdl)
        if pdr > 0:
            in_mid_equilibrium = (pdl + 0.25 * pdr) <= current_price <= (pdl + 0.75 * pdr)
            dol_internal = round(pdl + 0.50 * pdr, 2 if is_gold else 5)

        if len(bars_1d) >= 5:
            recent_highs = [b['high'] for b in bars_1d[-10:-1]]
            recent_lows = [b['low'] for b in bars_1d[-10:-1]]
            major_high = max(recent_highs)
            major_low = min(recent_lows)
            dol_external = major_high if current_price >= (pdl + 0.50 * pdr) else major_low

    # 2. 1-Hour Structural State Machine
    h1_state = "NEUTRAL"
    last_mss_level = None
    invalidation_level = None
    min_mss_disp = 6.0 if is_gold else (0.40 if is_silver else 0.0025)

    if bars_1h and len(bars_1h) >= 10:
        n = len(bars_1h)
        swings = []
        for i in range(2, n - 2):
            b = bars_1h[i]
            dt = datetime.datetime.fromtimestamp(b['time']) if isinstance(b['time'], (int, float)) else b['time']
            is_sh = (b['high'] >= bars_1h[i-1]['high'] and b['high'] >= bars_1h[i-2]['high'] and
                     b['high'] >= bars_1h[i+1]['high'] and b['high'] >= bars_1h[i+2]['high'])
            is_sl = (b['low'] <= bars_1h[i-1]['low'] and b['low'] <= bars_1h[i-2]['low'] and
                     b['low'] <= bars_1h[i+1]['low'] and b['low'] <= bars_1h[i+2]['low'])
            if is_sh:
                swings.append(('SH', i, dt, b['high']))
            if is_sl:
                swings.append(('SL', i, dt, b['low']))

        # Step through bars chronologically
        for i in range(2, n):
            b = bars_1h[i]
            c = b['close']
            h = b['high']
            l = b['low']

            prior_shs = [s for s in swings if s[0] == 'SH' and s[1] <= i - 2]
            prior_sls = [s for s in swings if s[0] == 'SL' and s[1] <= i - 2]

            # Invalidation checks
            if 'BULLISH' in h1_state:
                if invalidation_level and l < invalidation_level:
                    h1_state = 'BEARISH_MSS'
                    recent_crest = [s for s in prior_shs if s[1] >= (i - 10)]
                    invalidation_level = max(recent_crest, key=lambda s: s[3])[3] if recent_crest else h

            if 'BEARISH' in h1_state:
                if invalidation_level and h > invalidation_level:
                    h1_state = 'BULLISH_MSS'
                    recent_trough = [s for s in prior_sls if s[1] >= (i - 10)]
                    invalidation_level = min(recent_trough, key=lambda s: s[3])[3] if recent_trough else l

            # Breakout triggers
            if 'BEARISH' in h1_state or h1_state == 'NEUTRAL':
                if prior_shs and prior_sls:
                    last_sh = prior_shs[-1]
                    relevant_sls = [s for s in prior_sls if s[1] >= last_sh[1]]
                    if not relevant_sls:
                        relevant_sls = prior_sls[-2:]
                    trough_sl = min(relevant_sls, key=lambda s: s[3])

                    if (c > last_sh[3] or h > last_sh[3] + 2.0) and (last_sh[3] - trough_sl[3]) >= min_mss_disp:
                        h1_state = 'BULLISH_MSS'
                        last_mss_level = last_sh[3]
                        invalidation_level = trough_sl[3]

            if 'BULLISH' in h1_state or h1_state == 'NEUTRAL':
                if prior_shs and prior_sls:
                    last_sl = prior_sls[-1]
                    relevant_shs = [s for s in prior_shs if s[1] >= last_sl[1]]
                    if not relevant_shs:
                        relevant_shs = prior_shs[-2:]
                    crest_sh = max(relevant_shs, key=lambda s: s[3])

                    if (c < last_sl[3] or l < last_sl[3] - 2.0) and (crest_sh[3] - last_sl[3]) >= min_mss_disp:
                        h1_state = 'BEARISH_MSS'
                        last_mss_level = last_sl[3]
                        invalidation_level = crest_sh[3]

    is_dead_consolidation = is_inside_day and in_mid_equilibrium and (h1_state == 'NEUTRAL')

    return {
        "h1_state": h1_state,
        "mss_level": last_mss_level,
        "invalidation_level": invalidation_level,
        "is_inside_day": is_inside_day,
        "in_mid_equilibrium": in_mid_equilibrium,
        "is_dead_consolidation": is_dead_consolidation,
        "dol_external": dol_external,
        "dol_internal": dol_internal,
        "current_price": current_price,
        "pdh": pdh,
        "pdl": pdl,
        "pdr": pdr
    }


def classify_setup_phase(
    mtf_state: Dict[str, Any],
    direction: str,
    symbol: str = "XAUUSD"
) -> Dict[str, Any]:
    """
    Classifies the specific setup's phase, targets, breakeven, and entry anchor
    based on its directional alignment with the higher-timeframe orderflow.
    """
    dir_upper = direction.upper()
    is_buy = "BUY" in dir_upper or "LONG" in dir_upper or "BULLISH" in dir_upper
    is_gold = "XAU" in symbol.upper()
    val_fmt = ".2f" if is_gold else (".3f" if "XAG" in symbol.upper() else ".5f")

    # Case 0: Dead Market Consolidation
    if mtf_state.get("is_dead_consolidation", False):
        return {
            "phase": "CONSOLIDATION",
            "recommended_target_rr": 2.0,
            "recommended_be_rr": 1.5,
            "poi_ratio": 0.50,
            "entry_anchor": "DEEP_OTE_SCALED",
            "dol_target": mtf_state.get("dol_internal"),
            "summary": "Suppressed: Daily Inside Day Mid-Range Compression with no 1H MSS."
        }

    h1_state = mtf_state.get("h1_state", "NEUTRAL")
    mss_lvl = mtf_state.get("mss_level")
    inv_lvl = mtf_state.get("invalidation_level")
    curr_p = mtf_state.get("current_price", 0.0)

    # Case 1: Pro-HTF Expansion Phase
    # Direction is completely aligned with 1H Market Structure Shift
    if (is_buy and h1_state == "BULLISH_MSS") or ((not is_buy) and h1_state == "BEARISH_MSS"):
        dol = mtf_state.get("dol_external")
        if not dol:
            dol = (curr_p + 35.0) if is_buy else (curr_p - 35.0)

        mss_str = f"at {mss_lvl:{val_fmt}}" if mss_lvl else ""
        return {
            "phase": "PRO_EXPANSION",
            "recommended_target_rr": 4.5,       # Bigger Target for Pro-HTF Expansion
            "recommended_be_rr": None,          # Runner mode (do not choke Judas swings)
            "poi_ratio": 0.20,                  # Proximal edge fill (momentum won't retrace deep)
            "entry_anchor": "PROXIMAL_EDGE",
            "dol_target": dol,
            "summary": f"Pro-HTF Expansion aligned with 1H {h1_state} {mss_str}. Target set to 4.5R."
        }

    # Case 2: Counter-HTF Retracement Phase
    # Direction is counter to 1H MSS (Trading pullback into internal POI / broken structure)
    if ((not is_buy) and h1_state == "BULLISH_MSS") or (is_buy and h1_state == "BEARISH_MSS"):
        dol = mtf_state.get("dol_internal") or mss_lvl or curr_p
        return {
            "phase": "HTF_RETRACEMENT",
            "recommended_target_rr": 2.2,       # Smaller Target for Retracement
            "recommended_be_rr": 1.5,           # Fast Breakeven defense before macro trend snaps back
            "poi_ratio": 0.50,                  # Deep OTE / MT entry to maximize safety buffer
            "entry_anchor": "DEEP_OTE_SCALED",
            "dol_target": dol,
            "summary": f"HTF Retracement counter to 1H {h1_state}. Target set to 2.2R with 1.5R BE defense."
        }

    # Case 3: Balanced Session Range (Neutral 1H Structure)
    return {
        "phase": "BALANCED_RANGE",
        "recommended_target_rr": 2.5,
        "recommended_be_rr": 1.5,
        "poi_ratio": 0.50,
        "entry_anchor": "DEEP_OTE_SCALED",
        "dol_target": mtf_state.get("dol_internal"),
        "summary": "Balanced session range trading with standard 2.5R target."
    }


def analyze_mtf_structure(
    bars_1d: Optional[List[Dict[str, Any]]],
    bars_1h: Optional[List[Dict[str, Any]]],
    bars_15m: Optional[List[Dict[str, Any]]],
    bars_5m: List[Dict[str, Any]],
    symbol: str = "XAUUSD"
) -> Dict[str, Any]:
    """
    Backward-compatible entrypoint.
    Returns overall structural context.
    """
    state = analyze_mtf_state(bars_1d, bars_1h, bars_5m, symbol)
    phase_info = classify_setup_phase(state, direction="LONG", symbol=symbol)
    res = {**state, **phase_info}
    res["htf_bias"] = "BULLISH" if state["h1_state"] == "BULLISH_MSS" else ("BEARISH" if state["h1_state"] == "BEARISH_MSS" else "NEUTRAL")
    return res


def _fallback_state(reason: str) -> Dict[str, Any]:
    return {
        "h1_state": "NEUTRAL",
        "mss_level": None,
        "invalidation_level": None,
        "is_inside_day": False,
        "in_mid_equilibrium": False,
        "is_dead_consolidation": False,
        "dol_external": None,
        "dol_internal": None,
        "current_price": 0.0,
        "pdh": None,
        "pdl": None,
        "pdr": None
    }
