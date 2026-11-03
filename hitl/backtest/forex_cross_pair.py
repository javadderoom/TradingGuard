"""
TradingGuard HITL - Forex Cross-Pair Symbiosis & Intermarket SMT Engine
Provides multi-asset structural intelligence between EURUSD (Fiber) and GBPUSD (Cable):
1. Intermarket SMT Divergence Radar: Real-time non-confirmation analysis at session boundaries.
2. Cross-Pair Leading Indicator Engine (Helper Pair Barometer):
   - Evaluates if the helper pair has already broken structure (MSS) or printed violent displacement
     while the target pair is still consolidating / lagging.
   - Detects Cross-Pair Confluence (Pro-Alignment vs. Leading Confirmation vs. Friction Divergence).
3. Enriches the AI Council prompt so deliberations on EURUSD leverage GBPUSD context,
   and deliberations on GBPUSD leverage EURUSD context.
"""

from typing import Dict, Any, List, Optional


def detect_forex_smt_divergence(
    rates_5m_eur: List[Dict[str, Any]],
    rates_5m_gbp: List[Dict[str, Any]],
    session_hour: int
) -> Dict[str, Any]:
    """
    Computes real-time or historical SMT divergence between EURUSD and GBPUSD.
    - Bullish SMT: One currency sweeps session Low (Judas purge), while the other holds a Higher Low.
    - Bearish SMT: One currency sweeps session High, while the other holds a Lower High.
    """
    if len(rates_5m_eur) < 40 or len(rates_5m_gbp) < 40:
        return {
            "has_smt": False,
            "smt_type": "NONE",
            "summary": "Insufficient data for SMT calculation"
        }

    # 1. Determine prior session benchmark window
    if session_hour in (9, 10, 11):
        window_eur = rates_5m_eur[-84:-10] if len(rates_5m_eur) >= 84 else rates_5m_eur[:-10]
        window_gbp = rates_5m_gbp[-84:-10] if len(rates_5m_gbp) >= 84 else rates_5m_gbp[:-10]
        label = "Asian Range"
    elif session_hour in (14, 15, 16):
        window_eur = rates_5m_eur[-72:-10] if len(rates_5m_eur) >= 72 else rates_5m_eur[:-10]
        window_gbp = rates_5m_gbp[-72:-10] if len(rates_5m_gbp) >= 72 else rates_5m_gbp[:-10]
        label = "London Range"
    else:
        window_eur = rates_5m_eur[-36:-6] if len(rates_5m_eur) >= 36 else rates_5m_eur[:-6]
        window_gbp = rates_5m_gbp[-36:-6] if len(rates_5m_gbp) >= 36 else rates_5m_gbp[:-6]
        label = "NY AM Range"

    if not (window_eur and window_gbp):
        return {"has_smt": False, "smt_type": "NONE", "summary": "No session window data"}

    high_eur = max(b['high'] for b in window_eur)
    low_eur = min(b['low'] for b in window_eur)

    high_gbp = max(b['high'] for b in window_gbp)
    low_gbp = min(b['low'] for b in window_gbp)

    # Recent testing bars (last 10 5M bars)
    recent_eur = rates_5m_eur[-10:]
    recent_gbp = rates_5m_gbp[-10:]

    max_eur = max(b['high'] for b in recent_eur)
    min_eur = min(b['low'] for b in recent_eur)

    max_gbp = max(b['high'] for b in recent_gbp)
    min_gbp = min(b['low'] for b in recent_gbp)

    eur_swept_high = max_eur >= high_eur
    eur_swept_low = min_eur <= low_eur

    gbp_swept_high = max_gbp >= high_gbp
    gbp_swept_low = min_gbp <= low_gbp

    # SMT Logic
    # 1. Bearish SMT: One swept High, other failed to sweep High
    if eur_swept_high and not gbp_swept_high:
        delta_pips = (max_eur - high_eur) * 10000
        return {
            "has_smt": True,
            "smt_type": "BEARISH_SMT",
            "leading_asset": "EURUSD",
            "lagging_asset": "GBPUSD",
            "summary": (
                f"BEARISH SMT DIVERGENCE: EURUSD swept {label} High by {delta_pips:.1f} pips, "
                f"but GBPUSD REFUSED to sweep its High (Cable held lower high). Institutional Distribution in European Currencies!"
            )
        }

    if gbp_swept_high and not eur_swept_high:
        delta_pips = (max_gbp - high_gbp) * 10000
        return {
            "has_smt": True,
            "smt_type": "BEARISH_SMT",
            "leading_asset": "GBPUSD",
            "lagging_asset": "EURUSD",
            "summary": (
                f"BEARISH SMT DIVERGENCE: GBPUSD swept {label} High by {delta_pips:.1f} pips, "
                f"but EURUSD REFUSED to sweep its High (Fiber held lower high). Institutional Distribution in European Currencies!"
            )
        }

    # 2. Bullish SMT: One swept Low, other failed to sweep Low
    if eur_swept_low and not gbp_swept_low:
        delta_pips = (low_eur - min_eur) * 10000
        return {
            "has_smt": True,
            "smt_type": "BULLISH_SMT",
            "leading_asset": "EURUSD",
            "lagging_asset": "GBPUSD",
            "summary": (
                f"BULLISH SMT DIVERGENCE: EURUSD swept {label} Low by {delta_pips:.1f} pips (Judas Purge), "
                f"while GBPUSD REFUSED to sweep its Low (Cable held Higher Low). Institutional Smart Money Buy Signal!"
            )
        }

    if gbp_swept_low and not eur_swept_low:
        delta_pips = (low_gbp - min_gbp) * 10000
        return {
            "has_smt": True,
            "smt_type": "BULLISH_SMT",
            "leading_asset": "GBPUSD",
            "lagging_asset": "EURUSD",
            "summary": (
                f"BULLISH SMT DIVERGENCE: GBPUSD swept {label} Low by {delta_pips:.1f} pips (Judas Purge), "
                f"while EURUSD REFUSED to sweep its Low (Fiber held Higher Low). Institutional Smart Money Buy Signal!"
            )
        }

    # Correlated
    if eur_swept_high and gbp_swept_high:
        return {
            "has_smt": False,
            "smt_type": "CORRELATED_HIGH_SWEEP",
            "summary": f"Correlated High Sweep: Both EURUSD and GBPUSD swept {label} Highs simultaneously."
        }

    if eur_swept_low and gbp_swept_low:
        return {
            "has_smt": False,
            "smt_type": "CORRELATED_LOW_SWEEP",
            "summary": f"Correlated Low Sweep: Both EURUSD and GBPUSD swept {label} Lows simultaneously."
        }

    return {
        "has_smt": False,
        "smt_type": "IN_RANGE_CORRELATION",
        "summary": f"Both EURUSD and GBPUSD trading inside {label} boundaries."
    }


def analyze_cross_pair_symbiosis(
    rates_5m_target: List[Dict[str, Any]],
    rates_5m_helper: List[Dict[str, Any]],
    target_symbol: str,
    helper_symbol: str,
    smt_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Performs deep cross-pair structural symbiosis analysis:
    Examines if the helper pair (e.g. GBPUSD) has already displaced, broken structure,
    or formed a clean SMC footprint that acts as a leading predictive confirmation for target (EURUSD).
    """
    if len(rates_5m_target) < 15 or len(rates_5m_helper) < 15:
        return {
            "helper_symbol": helper_symbol,
            "status": "INSUFFICIENT_DATA",
            "confluence": "NEUTRAL",
            "narrative": "Insufficient history for cross-pair analysis."
        }

    helper_close = rates_5m_helper[-1]['close']
    helper_open = rates_5m_helper[-1]['open']
    helper_recent_body = helper_close - helper_open

    # Helper displacement across last 3 candles
    h_disp_3 = rates_5m_helper[-1]['close'] - rates_5m_helper[-3]['open']
    h_disp_pips = h_disp_3 * 10000

    target_disp_3 = rates_5m_target[-1]['close'] - rates_5m_target[-3]['open']
    t_disp_pips = target_disp_3 * 10000

    # Helper swing high / low breakdown
    recent_h_window = rates_5m_helper[-24:]
    h_highs = [b['high'] for b in recent_h_window]
    h_lows = [b['low'] for b in recent_h_window]
    h_max = max(h_highs)
    h_min = min(h_lows)

    # Determine helper directional flow
    if h_disp_pips >= 8.0:
        h_bias = "BULLISH_EXPANSION"
    elif h_disp_pips <= -8.0:
        h_bias = "BEARISH_EXPANSION"
    else:
        h_bias = "CONSOLIDATION_DRIFT"

    # Leading Indicator Evaluation:
    # Does helper show violent displacement while target is lagging?
    is_helper_leading = False
    leading_narrative = ""

    if h_disp_pips >= 10.0 and abs(t_disp_pips) < 5.0:
        is_helper_leading = True
        confluence = "BULLISH_LEADING_CONFIRMATION"
        leading_narrative = (
            f"{helper_symbol} has ALREADY initiated an aggressive Bullish Displacement (+{h_disp_pips:.1f} pips), "
            f"while {target_symbol} is lagging at base (+{t_disp_pips:.1f} pips). High probability that {target_symbol} "
            f"will follow {helper_symbol} in an explosive upward catch-up expansion!"
        )
    elif h_disp_pips <= -10.0 and abs(t_disp_pips) < 5.0:
        is_helper_leading = True
        confluence = "BEARISH_LEADING_CONFIRMATION"
        leading_narrative = (
            f"{helper_symbol} has ALREADY initiated an aggressive Bearish Displacement ({h_disp_pips:.1f} pips), "
            f"while {target_symbol} is lagging near highs ({t_disp_pips:.1f} pips). Strong institutional forecast that "
            f"{target_symbol} is vulnerable to an immediate downward breakdown!"
        )
    elif (h_disp_pips >= 5.0 and t_disp_pips >= 5.0):
        confluence = "PRO_TREND_DUAL_CONFIRMATION"
        leading_narrative = f"Both {target_symbol} and {helper_symbol} moving in synchronized bullish harmony (+{t_disp_pips:.1f} / +{h_disp_pips:.1f} pips)."
    elif (h_disp_pips <= -5.0 and t_disp_pips <= -5.0):
        confluence = "PRO_TREND_DUAL_CONFIRMATION"
        leading_narrative = f"Both {target_symbol} and {helper_symbol} moving in synchronized bearish harmony ({t_disp_pips:.1f} / {h_disp_pips:.1f} pips)."
    elif (h_disp_pips >= 8.0 and t_disp_pips <= -4.0) or (h_disp_pips <= -8.0 and t_disp_pips >= 4.0):
        confluence = "CROSS_PAIR_FRICTION_WARNING"
        leading_narrative = (
            f"WARNING: Cross-pair conflict detected! {helper_symbol} is displacing in the opposite direction "
            f"({h_disp_pips:+.1f} pips vs {target_symbol} {t_disp_pips:+.1f} pips). Proceed with caution or demand stricter confirmation."
        )
    else:
        confluence = "NEUTRAL_COUPLED_DRIFT"
        leading_narrative = f"{helper_symbol} is trading quietly in line with {target_symbol}."

    smt_desc = smt_info.get("summary", "No active SMT divergence.") if smt_info else "N/A"

    return {
        "target_symbol": target_symbol,
        "helper_symbol": helper_symbol,
        "helper_bias": h_bias,
        "helper_disp_pips": round(h_disp_pips, 1),
        "target_disp_pips": round(t_disp_pips, 1),
        "confluence": confluence,
        "is_helper_leading": is_helper_leading,
        "narrative": leading_narrative,
        "smt_summary": smt_desc
    }


def format_symbiotic_prompt(symbiosis: Dict[str, Any]) -> str:
    """Formats cross-pair symbiosis into an institutional prompt block."""
    h_sym = symbiosis.get("helper_symbol", "HELPER")
    lines = [
        f"=== SYMBIOTIC CROSS-PAIR BAROMETER ({h_sym}) ===",
        f"• Helper Symbol: {h_sym} | Structural Flow: [{symbiosis.get('helper_bias', 'NEUTRAL')}]",
        f"• Relative Velocity: {h_sym} ({symbiosis.get('helper_disp_pips', 0.0):+.1f} pips) vs Target ({symbiosis.get('target_disp_pips', 0.0):+.1f} pips)",
        f"• Cross-Pair Confluence Verdict: [{symbiosis.get('confluence', 'NEUTRAL')}]",
        f"• Predictive Symbiotic Intelligence: {symbiosis.get('narrative', '')}",
        f"• Intermarket SMT Divergence State: {symbiosis.get('smt_summary', 'None')}",
        "=================================================="
    ]
    return "\n".join(lines)
