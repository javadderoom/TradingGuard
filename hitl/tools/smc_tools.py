"""
TradingGuard HITL - Deterministic SMC Tools & Order Pre-Flight Validator
Provides pure mathematical, tick-verified SMC landmarks and MT5 broker pre-flight validation.
Replaces LLM arithmetic hallucinations with deterministic execution geometry.
"""

from typing import List, Dict, Any, Optional, Tuple
import datetime


def calculate_atr(bars: List[Dict[str, Any]], period: int = 14) -> float:
    """Calculates Average True Range over the specified period."""
    if not bars or len(bars) < 2:
        return 0.00500
    p = min(period, len(bars) - 1)
    tr_list = []
    for i in range(1, len(bars)):
        h = bars[i]['high']
        l = bars[i]['low']
        c_prev = bars[i-1]['close']
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        tr_list.append(tr)
    return sum(tr_list[-p:]) / p if tr_list else 0.00500


def get_smc_landmarks(
    bars_1d: List[Dict[str, Any]],
    bars_1h: List[Dict[str, Any]],
    bars_15m: List[Dict[str, Any]],
    bars_5m: List[Dict[str, Any]],
    symbol: str,
    current_bid: float,
    current_ask: float,
    broker_time: datetime.datetime
) -> Dict[str, Any]:
    """
    Extracts deterministic, tick-accurate SMC execution landmarks.
    Guarantees that entry, SL, and TP coordinates come from verified MT5 data.
    """
    is_fx = "GBP" in symbol.upper() or "EUR" in symbol.upper()
    pip_size = 0.00010 if "GBP" in symbol.upper() else (0.00010 if "EUR" in symbol.upper() else 0.01)

    atr_5m = calculate_atr(bars_5m, 14)
    atr_1d = calculate_atr(bars_1d, 14)

    # 1. Sweep Extremes & Protected Swings (Execution-level M5 sweep peak)
    recent_15 = bars_5m[-15:] if len(bars_5m) >= 15 else bars_5m
    sweep_high = max(b['high'] for b in recent_15)
    sweep_low = min(b['low'] for b in recent_15)

    # Protected Swing Anchors (Stop Loss defense per RULE-CORE-005)
    protected_high = sweep_high
    protected_low = sweep_low
    sl_sell_pinned = round(protected_high + pip_size, 5) if is_fx else round(protected_high + pip_size, 2)
    sl_buy_pinned = round(protected_low - pip_size, 5) if is_fx else round(protected_low - pip_size, 2)

    # Targeted Swing Anchors (Opposing pools holding retail liquidity on 15M)
    swing_lows_15m = []
    swing_highs_15m = []
    if len(bars_15m) >= 5:
        for i in range(2, len(bars_15m) - 1):
            if bars_15m[i]['low'] <= bars_15m[i-1]['low'] and bars_15m[i]['low'] <= bars_15m[i-2]['low'] and bars_15m[i]['low'] <= bars_15m[i+1]['low']:
                swing_lows_15m.append(bars_15m[i]['low'])
            if bars_15m[i]['high'] >= bars_15m[i-1]['high'] and bars_15m[i]['high'] >= bars_15m[i-2]['high'] and bars_15m[i]['high'] >= bars_15m[i+1]['high']:
                swing_highs_15m.append(bars_15m[i]['high'])

    prior_days = bars_1d[-7:-1] if len(bars_1d) >= 7 else bars_1d[:-1]
    ext_swing_high = max(b['high'] for b in prior_days) if prior_days else bars_1d[-1]['high']
    ext_swing_low = min(b['low'] for b in prior_days) if prior_days else bars_1d[-1]['low']

    targeted_low_cands = [l for l in swing_lows_15m if l < current_bid - (5.0 * pip_size)]
    targeted_swing_low = min(targeted_low_cands) if targeted_low_cands else (ext_swing_low if ext_swing_low < current_bid else None)

    targeted_high_cands = [h for h in swing_highs_15m if h > current_ask + (5.0 * pip_size)]
    targeted_swing_high = max(targeted_high_cands) if targeted_high_cands else (ext_swing_high if ext_swing_high > current_ask else None)

    # 3. Active 5M Fair Value Gap Detection (Directional Separation)
    min_gap = 0.00005 if is_fx else 0.50
    bearish_fvg = None
    bullish_fvg = None

    for i in range(len(bars_5m) - 1, max(2, len(bars_5m) - 25), -1):
        c1, c2, c3 = bars_5m[i - 2], bars_5m[i - 1], bars_5m[i]
        # Bearish FVG: c1['low'] > c3['high']
        if not bearish_fvg and (c1['low'] - c3['high']) >= min_gap:
            bearish_fvg = {
                "proximal": round(c3['high'], 5) if is_fx else round(c3['high'], 2),
                "distal": round(c1['low'], 5) if is_fx else round(c1['low'], 2),
                "ce": round((c3['high'] + c1['low']) / 2.0, 5) if is_fx else round((c3['high'] + c1['low']) / 2.0, 2),
                "size_pips": round((c1['low'] - c3['high']) / pip_size, 1)
            }
        # Bullish FVG: c3['low'] > c1['high']
        if not bullish_fvg and (c3['low'] - c1['high']) >= min_gap:
            bullish_fvg = {
                "proximal": round(c3['low'], 5) if is_fx else round(c3['low'], 2),
                "distal": round(c1['high'], 5) if is_fx else round(c1['high'], 2),
                "ce": round((c3['low'] + c1['high']) / 2.0, 5) if is_fx else round((c3['low'] + c1['high']) / 2.0, 2),
                "size_pips": round((c3['low'] - c1['high']) / pip_size, 1)
            }
        if bearish_fvg and bullish_fvg:
            break

    # 4. External Structural Swing Targets (RULE-CORE-006 / RULE-TARGET-041)
    # Pro-Trend ATR Expansion Target (1.25x Daily ATR from current price)
    htf_expansion_bearish = round(current_bid - 1.25 * atr_1d, 5) if is_fx else round(current_bid - 1.25 * atr_1d, 2)
    htf_expansion_bullish = round(current_ask + 1.25 * atr_1d, 5) if is_fx else round(current_ask + 1.25 * atr_1d, 2)

    return {
        "symbol": symbol,
        "broker_time": broker_time,
        "current_bid": current_bid,
        "current_ask": current_ask,
        "pip_size": pip_size,
        "sweep_high": sweep_high,
        "sweep_low": sweep_low,
        "protected_high": protected_high,
        "protected_low": protected_low,
        "sl_sell_pinned": sl_sell_pinned,
        "sl_buy_pinned": sl_buy_pinned,
        "targeted_swing_low": targeted_swing_low,
        "targeted_swing_high": targeted_swing_high,
        "bearish_fvg": bearish_fvg,
        "bullish_fvg": bullish_fvg,
        # Backward-compatible convenience keys
        "fvg_type": "BEARISH" if bearish_fvg else ("BULLISH" if bullish_fvg else None),
        "fvg_proximal": bearish_fvg["proximal"] if bearish_fvg else (bullish_fvg["proximal"] if bullish_fvg else None),
        "fvg_distal": bearish_fvg["distal"] if bearish_fvg else (bullish_fvg["distal"] if bullish_fvg else None),
        "fvg_ce": bearish_fvg["ce"] if bearish_fvg else (bullish_fvg["ce"] if bullish_fvg else None),
        "ext_swing_high": ext_swing_high,
        "ext_swing_low": ext_swing_low,
        "htf_expansion_bearish": htf_expansion_bearish,
        "htf_expansion_bullish": htf_expansion_bullish
    }


def format_smc_tools_block(landmarks: Dict[str, Any]) -> str:
    """Formats deterministic tool output block for Council deliberation prompt."""
    if not landmarks:
        return ""
    is_fx = "GBP" in landmarks["symbol"] or "EUR" in landmarks["symbol"]
    fmt = ".5f" if is_fx else ".2f"

    bfvg = landmarks.get("bearish_fvg")
    ufvg = landmarks.get("bullish_fvg")

    b_prox = f"{bfvg['proximal']:{fmt}}" if bfvg else "None"
    b_ce = f"{bfvg['ce']:{fmt}}" if bfvg else "None"
    b_dist = f"{bfvg['distal']:{fmt}}" if bfvg else "None"

    u_prox = f"{ufvg['proximal']:{fmt}}" if ufvg else "None"
    u_ce = f"{ufvg['ce']:{fmt}}" if ufvg else "None"
    u_dist = f"{ufvg['distal']:{fmt}}" if ufvg else "None"

    lines = [
        "=== DETERMINISTIC SMC TOOL ARTIFACTS (VERIFIED BROKER DATA) ===",
        f"• Real-Time Quote: Bid = {landmarks['current_bid']:{fmt}} | Ask = {landmarks['current_ask']:{fmt}}",
        f"• Structural Invalidation Anchors (RULE-CORE-005):",
        f"  - Bearish Pinned SL (Sweep Wick Peak + 1.0 pip): {landmarks['sl_sell_pinned']:{fmt}}",
        f"  - Bullish Pinned SL (Sweep Wick Low - 1.0 pip): {landmarks['sl_buy_pinned']:{fmt}}",
        f"• Active Bearish Fair Value Gap (Short Setup POIs):",
        f"  - [BEARISH-POI-PROXIMAL]: {b_prox} (Shallow Retracement Fill per RULE-CORE-005)",
        f"  - [BEARISH-POI-CE]: {b_ce} (50% Consequent Encroachment)",
        f"  - [BEARISH-POI-DISTAL]: {b_dist} (Deep Boundary)",
        f"• Active Bullish Fair Value Gap (Long Setup POIs):",
        f"  - [BULLISH-POI-PROXIMAL]: {u_prox} (Shallow Retracement Fill per RULE-CORE-005)",
        f"  - [BULLISH-POI-CE]: {u_ce} (50% Consequent Encroachment)",
        f"  - [BULLISH-POI-DISTAL]: {u_dist} (Deep Boundary)",
        f"• Objective Structural Target Pools (RULE-CORE-006 / RULE-TARGET-041):",
        f"  - Bearish External Target (HTF Expansion / Swing Low): {landmarks['htf_expansion_bearish']:{fmt}}",
        f"  - Bullish External Target (HTF Expansion / Swing High): {landmarks['htf_expansion_bullish']:{fmt}}",
        "=================================================================="
    ]
    return "\n".join(lines)


def validate_order_ticket(
    order_type: str,
    current_bid: float,
    current_ask: float,
    entry: float,
    sl: float,
    tp: float,
    pip_size: float = 0.00010,
    max_risk_usd: float = 17.0,
    min_rr: float = 3.0
) -> Dict[str, Any]:
    """
    Pre-flight execution validator.
    Simulates MT5 broker trade server acceptance rules BEFORE committing to orders_schedule.csv.
    Prevents [Invalid stops], wrong order type rejection, or excessive risk.
    """
    order_type = order_type.upper().strip()

    if order_type == "STAND_ASIDE":
        return {"is_valid": True, "reason": "Deliberate stand aside.", "risk_pips": 0.0, "rr": 0.0}

    if order_type not in ("BUY_LIMIT", "SELL_LIMIT"):
        return {"is_valid": False, "reason": f"Unsupported order type: {order_type}. Firm allows LIMIT orders only.", "risk_pips": 0.0, "rr": 0.0}

    # 1. Exchange Limit Placement Rule
    if order_type == "SELL_LIMIT":
        # Sell Limit must be strictly above current market Ask/Bid
        if entry <= current_bid:
            return {
                "is_valid": False,
                "reason": f"INVALID_LIMIT_GEOMETRY: Current Bid ({current_bid:.5f}) >= Entry ({entry:.5f}). A SELL_LIMIT cannot be placed below current market price.",
                "risk_pips": 0.0,
                "rr": 0.0
            }
        # Stop loss must be strictly above entry
        if sl <= entry:
            return {
                "is_valid": False,
                "reason": f"INVALID_STOPS: Stop Loss ({sl:.5f}) must be strictly above Sell entry ({entry:.5f}).",
                "risk_pips": 0.0,
                "rr": 0.0
            }
        # Take profit must be strictly below entry
        if tp >= entry:
            return {
                "is_valid": False,
                "reason": f"INVALID_TARGET: Take Profit ({tp:.5f}) must be strictly below Sell entry ({entry:.5f}).",
                "risk_pips": 0.0,
                "rr": 0.0
            }
    elif order_type == "BUY_LIMIT":
        # Buy Limit must be strictly below current market Ask/Bid
        if entry >= current_ask:
            return {
                "is_valid": False,
                "reason": f"INVALID_LIMIT_GEOMETRY: Current Ask ({current_ask:.5f}) <= Entry ({entry:.5f}). A BUY_LIMIT cannot be placed above current market price.",
                "risk_pips": 0.0,
                "rr": 0.0
            }
        # Stop loss must be strictly below entry
        if sl >= entry:
            return {
                "is_valid": False,
                "reason": f"INVALID_STOPS: Stop Loss ({sl:.5f}) must be strictly below Buy entry ({entry:.5f}).",
                "risk_pips": 0.0,
                "rr": 0.0
            }
        # Take profit must be strictly above entry
        if tp <= entry:
            return {
                "is_valid": False,
                "reason": f"INVALID_TARGET: Take Profit ({tp:.5f}) must be strictly above Buy entry ({entry:.5f}).",
                "risk_pips": 0.0,
                "rr": 0.0
            }

    # 2. Mathematical Capital Defense Rule (Strict Dollar & Pip Ceiling on 0.01 lot)
    is_fx = pip_size < 0.001
    price_dist = abs(entry - sl)

    if is_fx:
        # Forex: 1 pip = 0.00010, risk on 0.01 lot = $0.10 per pip
        risk_pips = round(price_dist / 0.00010, 1)
        risk_usd = round(risk_pips * 0.10, 2)
        max_stop_pips = 35.0  # Max 35.0 pips stop on FX ($3.50 risk on 0.01 lot)
        if risk_pips > max_stop_pips:
            return {
                "is_valid": False,
                "reason": f"RISK_CEILING_BREACH: FX stop distance ({risk_pips:.1f} pips) exceeds maximum allowable stop buffer ({max_stop_pips:.1f} pips).",
                "risk_pips": risk_pips,
                "risk_usd": risk_usd,
                "rr": 0.0
            }
    else:
        # Commodities (Gold): 1 point ($1.00 move) on 0.01 lot = $1.00 risk
        risk_pips = round(price_dist, 2)
        risk_usd = round(price_dist * 1.0, 2)
        if risk_usd > max_risk_usd:
            return {
                "is_valid": False,
                "reason": f"RISK_CEILING_BREACH: Gold stop distance (${risk_usd:.2f}) exceeds firm's ${max_risk_usd:.2f} maximum dollar ceiling.",
                "risk_pips": risk_pips,
                "risk_usd": risk_usd,
                "rr": 0.0
            }

    if risk_usd > max_risk_usd:
        return {
            "is_valid": False,
            "reason": f"RISK_CEILING_BREACH: Dollar risk ${risk_usd:.2f} exceeds firm's ${max_risk_usd:.2f} maximum dollar ceiling.",
            "risk_pips": risk_pips,
            "risk_usd": risk_usd,
            "rr": 0.0
        }

    # 3. Minimum Risk-to-Reward Threshold (min 3.0R)
    reward_dist = abs(tp - entry)
    reward_pips = round(reward_dist / 0.00010, 1) if is_fx else round(reward_dist, 2)
    rr = round(reward_dist / max(0.00001, price_dist), 2)
    if rr < min_rr:
        return {
            "is_valid": False,
            "reason": f"UNFAVORABLE_ASYMMETRY: R:R ({rr:.2f}R) is below institutional {min_rr:.1f}R minimum threshold.",
            "risk_pips": risk_pips,
            "rr": rr
        }

    return {
        "is_valid": True,
        "reason": "APPROVED_PRE_FLIGHT",
        "risk_pips": risk_pips,
        "rr": rr
    }


def build_validated_order_plan(
    decision: str,
    poi_selection: str,
    landmarks: Dict[str, Any],
    macro_filter: str
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Combines Council qualitative selection with deterministic SMC landmarks.
    Returns (order_dict or None, log_reason).
    """
    if decision not in ("BUY_LIMIT", "SELL_LIMIT"):
        return None, "Decision is STAND_ASIDE."

    is_fx = "GBP" in landmarks["symbol"] or "EUR" in landmarks["symbol"]

    # Entry Selection based on Council POI choice with automatic boundary fallback
    entry = None
    if decision == "SELL_LIMIT":
        bfvg = landmarks.get("bearish_fvg")
        candidates = []
        if bfvg:
            if poi_selection == "DISTAL_EDGE":
                candidates = [bfvg.get("distal"), bfvg.get("ce"), bfvg.get("proximal")]
            elif poi_selection == "CONSEQUENT_ENCROACHMENT":
                candidates = [bfvg.get("ce"), bfvg.get("distal")]
            else: # PROXIMAL_EDGE (default)
                candidates = [bfvg.get("proximal"), bfvg.get("ce"), bfvg.get("distal")]
        elif landmarks.get("fvg_type") == "BEARISH":
            candidates = [landmarks.get("fvg_proximal"), landmarks.get("fvg_ce"), landmarks.get("fvg_distal")]

        # Filter candidates that are valid limit orders strictly above current market Bid
        valid_candidates = [c for c in candidates if c and c > landmarks["current_bid"]]
        if not valid_candidates:
            # Fallback to 50% equilibrium retracement between current bid and sweep high
            sweep_high = landmarks.get("sweep_high")
            if sweep_high and sweep_high > landmarks["current_bid"]:
                eq = round((sweep_high + landmarks["current_bid"]) / 2.0, 5 if is_fx else 2)
                if eq > landmarks["current_bid"]:
                    valid_candidates = [eq]

        if not valid_candidates:
            return None, f"PRE_FLIGHT_REJECTION: All Bearish POIs are at or below current Bid ({landmarks['current_bid']:.5f}). Pending limit entry impossible without chasing."
        entry = valid_candidates[0]

        sl = landmarks.get("sl_sell_pinned")
        if not is_fx and sl and abs(sl - entry) > 17.0:
            sl = round(entry + 7.50, 2)
        targeted_low = landmarks.get("targeted_swing_low")
        htf_tp = landmarks.get("htf_expansion_bearish")
        risk_dist = abs(entry - sl) if sl else 1.0
        if targeted_low and targeted_low < entry and ((entry - targeted_low) / max(0.1, risk_dist)) >= 3.0:
            tp = targeted_low
        elif htf_tp and htf_tp < entry and ((entry - htf_tp) / max(0.1, risk_dist)) >= 3.0:
            tp = htf_tp
        else:
            tp = round(entry - 3.5 * risk_dist, 5 if is_fx else 2)

    elif decision == "BUY_LIMIT":
        ufvg = landmarks.get("bullish_fvg")
        candidates = []
        if ufvg:
            if poi_selection == "DISTAL_EDGE":
                candidates = [ufvg.get("distal"), ufvg.get("ce"), ufvg.get("proximal")]
            elif poi_selection == "CONSEQUENT_ENCROACHMENT":
                candidates = [ufvg.get("ce"), ufvg.get("distal")]
            else: # PROXIMAL_EDGE (default)
                candidates = [ufvg.get("proximal"), ufvg.get("ce"), ufvg.get("distal")]
        elif landmarks.get("fvg_type") == "BULLISH":
            candidates = [landmarks.get("fvg_proximal"), landmarks.get("fvg_ce"), landmarks.get("fvg_distal")]

        # Filter candidates that are valid limit orders strictly below current market Ask
        valid_candidates = [c for c in candidates if c and c < landmarks["current_ask"]]
        if not valid_candidates:
            # Fallback to 50% equilibrium retracement between current ask and sweep low
            sweep_low = landmarks.get("sweep_low")
            if sweep_low and sweep_low < landmarks["current_ask"]:
                eq = round((sweep_low + landmarks["current_ask"]) / 2.0, 5 if is_fx else 2)
                if eq < landmarks["current_ask"]:
                    valid_candidates = [eq]

        if not valid_candidates:
            return None, f"PRE_FLIGHT_REJECTION: All Bullish POIs are at or above current Ask ({landmarks['current_ask']:.5f}). Pending limit entry impossible without chasing."
        entry = valid_candidates[0]

        sl = landmarks.get("sl_buy_pinned")
        if not is_fx and sl and abs(entry - sl) > 17.0:
            sl = round(entry - 7.50, 2)
        targeted_high = landmarks.get("targeted_swing_high")
        htf_tp = landmarks.get("htf_expansion_bullish")
        risk_dist = abs(entry - sl) if sl else 1.0
        if targeted_high and targeted_high > entry and ((targeted_high - entry) / max(0.1, risk_dist)) >= 3.0:
            tp = targeted_high
        elif htf_tp and htf_tp > entry and ((htf_tp - entry) / max(0.1, risk_dist)) >= 3.0:
            tp = htf_tp
        else:
            tp = round(entry + 3.5 * risk_dist, 5 if is_fx else 2)

    if not entry or not sl or not tp:
        return None, "Incomplete landmark coordinates."

    # Pre-Flight Validation
    val = validate_order_ticket(
        order_type=decision,
        current_bid=landmarks["current_bid"],
        current_ask=landmarks["current_ask"],
        entry=entry,
        sl=sl,
        tp=tp,
        pip_size=landmarks["pip_size"],
        max_risk_usd=17.0,
        min_rr=3.0
    )

    if not val["is_valid"]:
        return None, f"PRE_FLIGHT_REJECTION: {val['reason']}"

    b_time = landmarks["broker_time"]
    order_id = f"ORD-{b_time.strftime('%m%d')}-{b_time.strftime('%H%M')}"
    plan = {
        "id": order_id,
        "symbol": "AUTO",
        "type": decision,
        "trigger_time": b_time.strftime("%Y.%m.%d %H:%M:00"),
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "lot": 0.01,
        "ttl": 360,
        "risk_pips": val["risk_pips"],
        "rr": val["rr"]
    }
    return plan, f"APPROVED: {plan['id']} {decision} @ {entry} (SL: {sl}, TP: {tp}, {val['rr']}R)"
