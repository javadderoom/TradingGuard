"""
TradingGuard HITL - Higher-Timeframe (HTF) Fundamental Bias Engine
Computes active directional macro bias by analyzing:
1. Sovereign Currency Indexes (USDX, EURLFX, GBPLFX) on D1/H1 timeframes.
2. Central Bank Policy Stance & Rate Differentials (Fed vs ECB vs BoE).
3. Intermarket Yield Pressure & Macro Trend Regimes.
4. Active Directional Execution Filters (BUY_ONLY, SELL_ONLY, SELECTIVE).
"""

import sys
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.data_feed import _convert_records


# Central Bank Policy Rates Benchmark (2026 Macro Easing Cycle)
# Fed is actively easing from 5.25% down to 4.75% -> 4.50%
# ECB Deposit Facility at 3.50% -> 3.25%
# BoE Official Bank Rate at 5.00% -> 4.75%
CENTRAL_BANK_RATES = {
    "USD": 4.75,
    "EUR": 3.25,
    "GBP": 4.75,
}


def _get_index_trend(
    symbol_index: str,
    target_time: Optional[datetime.datetime] = None,
    lookback_days: int = 15
) -> Dict[str, Any]:
    """
    Computes D1 trend and 5-day momentum for a currency index (USDX, EURLFX, GBPLFX).
    """
    try:
        if not mt5.terminal_info():
            mt5.initialize()
    except Exception:
        pass

    if target_time:
        raw = mt5.copy_rates_from(symbol_index, mt5.TIMEFRAME_D1, target_time, lookback_days)
    else:
        raw = mt5.copy_rates_from_pos(symbol_index, mt5.TIMEFRAME_D1, 0, lookback_days)

    records = _convert_records(raw)
    if not records or len(records) < 5:
        return {
            "symbol": symbol_index,
            "status": "INSUFFICIENT_DATA",
            "trend": "NEUTRAL",
            "momentum_5d_pct": 0.0,
            "latest_close": 0.0
        }

    closes = [b["close"] for b in records]
    latest_close = closes[-1]
    close_5d_ago = closes[-5]
    sma_10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else sum(closes) / len(closes)

    mom_pct = ((latest_close - close_5d_ago) / close_5d_ago) * 100

    if latest_close > sma_10 and mom_pct >= 0.35:
        trend = "BULLISH_EXPANSION"
    elif latest_close < sma_10 and mom_pct <= -0.35:
        trend = "BEARISH_EXPANSION"
    elif mom_pct > 0.10:
        trend = "MILD_BULLISH_DRIFT"
    elif mom_pct < -0.10:
        trend = "MILD_BEARISH_DRIFT"
    else:
        trend = "CONSOLIDATION_RANGE"

    return {
        "symbol": symbol_index,
        "status": "OK",
        "trend": trend,
        "momentum_5d_pct": round(mom_pct, 2),
        "latest_close": round(latest_close, 2),
        "sma_10": round(sma_10, 2),
        "above_sma": latest_close > sma_10
    }


def calculate_htf_fundamental_bias(
    symbol: str,
    target_time: Optional[datetime.datetime] = None
) -> Dict[str, Any]:
    """
    Synthesizes currency index trends, central bank divergence, and yield pressure
    to compute an actionable Higher-Timeframe Fundamental Bias and Execution Filter.
    """
    sym = symbol.upper()

    # 1. Evaluate US Dollar Index (USDX)
    usdx_data = _get_index_trend("USDX", target_time=target_time)

    # 2. Evaluate Base Currency Index
    base_idx_sym = None
    if "EUR" in sym:
        base_idx_sym = "EURLFX"
        base_curr = "EUR"
    elif "GBP" in sym:
        base_idx_sym = "GBPLFX"
        base_curr = "GBP"
    elif "XAU" in sym or "GOLD" in sym:
        base_curr = "XAU"
    elif "XAG" in sym or "SILVER" in sym:
        base_curr = "XAG"
    else:
        base_curr = "USD"

    base_idx_data = _get_index_trend(base_idx_sym, target_time=target_time) if base_idx_sym else None

    # 3. Macro Rate Differential
    fed_rate = CENTRAL_BANK_RATES["USD"]
    base_rate = CENTRAL_BANK_RATES.get(base_curr, 0.0)
    rate_diff = base_rate - fed_rate

    # 4. Composite Directional Score & Bias Calculation
    bias = "NEUTRAL"
    execution_filter = "SELECTIVE_BI_DIRECTIONAL"
    narrative_points = []

    # Trend of Dollar Index
    usd_trend = usdx_data.get("trend", "NEUTRAL")
    usd_mom = usdx_data.get("momentum_5d_pct", 0.0)
    usd_close = usdx_data.get("latest_close", 100.0)

    narrative_points.append(f"US Dollar Index (USDX) is at {usd_close:.2f} [{usd_trend}, 5D Momentum: {usd_mom:+.2f}%].")

    if base_curr in ("EUR", "GBP"):
        b_trend = base_idx_data.get("trend", "NEUTRAL") if base_idx_data else "NEUTRAL"
        b_mom = base_idx_data.get("momentum_5d_pct", 0.0) if base_idx_data else 0.0
        b_name = "Euro Index (EURLFX)" if base_curr == "EUR" else "Pound Index (GBPLFX)"
        narrative_points.append(f"{b_name} prints [{b_trend}, 5D Momentum: {b_mom:+.2f}%].")
        narrative_points.append(f"Central Bank Policy Spread ({base_curr} vs Fed): {base_rate:.2f}% vs {fed_rate:.2f}% (Spread: {rate_diff:+.2f}%).")

        # Alignment Logic: Only emit hard directional locks on decisive macro trends (>0.25% momentum)
        if "BEARISH" in usd_trend and "BULLISH" in b_trend and usd_mom < -0.20:
            bias = "STRONG_BULLISH"
            execution_filter = "BUY_ONLY"
            narrative = (
                f"Sovereign Capital Tailwinds: USDX is in a confirmed markdown phase ({usd_mom:+.2f}%) while {base_curr} "
                f"currency index displays aggressive bullish expansion (+{b_mom:.2f}%). HTF macro order flow is overwhelmingly BULLISH. "
                f"Counter-trend shorting at session highs is strictly prohibited. Desk is mandated to buy discount pullbacks only."
            )
        elif "BULLISH" in usd_trend and "BEARISH" in b_trend and usd_mom > 0.20:
            bias = "STRONG_BEARISH"
            execution_filter = "SELL_ONLY"
            narrative = (
                f"Sovereign Distribution Warning: US Dollar is in aggressive markup ({usd_mom:+.2f}%) while {base_curr} index "
                f"is breaking down ({b_mom:+.2f}%). HTF macro order flow is overwhelmingly BEARISH. "
                f"Counter-trend long entries at session lows are strictly prohibited. Desk is mandated to sell premium retracements only."
            )
        elif usd_mom > 0.30:
            bias = "BEARISH"
            execution_filter = "SELL_ONLY"
            narrative = (
                f"Bearish Macro Headwind: Resilient US Dollar strength ({usd_trend}, {usd_mom:+.2f}%) exerts downside pressure on {sym}. "
                f"Execution mandate restricts long fading and authorizes short trend continuations at premium breaker blocks."
            )
        elif usd_mom < -0.30:
            bias = "BULLISH"
            execution_filter = "BUY_ONLY"
            narrative = (
                f"Bullish Macro Alignment: Softening US Dollar Index ({usd_trend}, {usd_mom:+.2f}%) supports {sym} higher-timeframe appreciation. "
                f"Execution mandate prioritizes long entries at FVG proximal edges and session discount liquidity purges."
            )
        else:
            bias = "NEUTRAL"
            execution_filter = "SELECTIVE_BI_DIRECTIONAL"
            narrative = (
                f"Balanced Macro Consolidation: Currency indexes display coupled drift or mixed signals ({usd_trend}, {usd_mom:+.2f}%). "
                f"Two-way execution permitted strictly upon confirmed technical structure shifts (MSS) and liquidity sweeps."
            )

    elif base_curr in ("XAU", "XAG"):
        # Metals Macro Dynamics (Inverse USDX + Real Yields + Safe Haven)
        asset_name = "Gold" if base_curr == "XAU" else "Silver"
        narrative_points.append(f"Global Easing Regime: Fed policy rate at {fed_rate:.2f}% with yield curve steepening.")

        if "BEARISH" in usd_trend:
            bias = "STRONG_BULLISH"
            execution_filter = "BUY_ONLY"
            narrative = (
                f"Metals Macro Super-Cycle: US Dollar weakness ({usd_trend}, {usd_mom:+.2f}%) combined with global rate cuts "
                f"fuels structural sovereign demand for {asset_name}. All intraday shorts are hard-vetoed. "
                f"Mandate is to buy Asian/London Judas purges into discount Fair Value Gaps."
            )
        elif usd_mom < -0.10 or usd_trend == "CONSOLIDATION_RANGE":
            bias = "BULLISH"
            execution_filter = "BUY_ONLY"
            narrative = (
                f"Pro-Metals Inflation Hedge: Soft dollar momentum keeps {asset_name} order flow supported on HTF daily charts. "
                f"Prioritize long limit orders anchored to confirmed Breaker Blocks."
            )
        elif "BULLISH" in usd_trend:
            bias = "BEARISH"
            execution_filter = "SELL_ONLY"
            narrative = (
                f"Macro Liquidity Squeeze: US Dollar surge ({usd_mom:+.2f}%) raises opportunity cost for holding zero-yield {asset_name}. "
                f"Veto bottom-fishing longs. Short entries authorized only on confirmed Bearish Metals SMT Divergence."
            )
        else:
            bias = "NEUTRAL"
            execution_filter = "SELECTIVE_BI_DIRECTIONAL"
            narrative = (
                f"Neutral Macro Equilibrium: Dollar index range-bound. "
                f"Execute only on textbook Judas sweeps with immediate 5M counter-displacement."
            )

    else:
        bias = "NEUTRAL"
        execution_filter = "SELECTIVE_BI_DIRECTIONAL"
        narrative = f"Standard macro environment for {sym}."

    return {
        "symbol": sym,
        "base_currency": base_curr,
        "htf_fundamental_bias": bias,
        "execution_filter": execution_filter,
        "usdx_metrics": usdx_data,
        "base_index_metrics": base_idx_data,
        "rate_differential_pct": round(rate_diff, 2),
        "macro_narrative": narrative,
        "summary_bullets": narrative_points
    }


def format_fundamental_bias_prompt(bias_data: Dict[str, Any]) -> str:
    """
    Renders an institutional prompt block to be injected directly into Council deliberations.
    """
    sym = bias_data.get("symbol", "ASSET")
    bias = bias_data.get("htf_fundamental_bias", "NEUTRAL")
    filt = bias_data.get("execution_filter", "SELECTIVE_BI_DIRECTIONAL")
    narrative = bias_data.get("macro_narrative", "")
    bullets = bias_data.get("summary_bullets", [])

    lines = [
        f"=== HIGHER-TIMEFRAME (HTF) FUNDAMENTAL DIRECTIONAL BIAS: {sym} ===",
        f"• 🏛️ Sovereign Macro Bias: [{bias}]",
        f"• 🎯 Macro Baseline Execution Filter: [{filt}] (Intraday counter-trend authorized on prominent session sweeps with displacement MSS)",
    ]
    for b in bullets:
        lines.append(f"• {b}")
    lines.append(f"• 🧭 Macro Strategic Directive: {narrative}")
    lines.append("==================================================================")

    return "\n".join(lines)


if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    mt5.initialize()
    print("Testing HTF Fundamental Bias Engine...")
    for test_s in ["EURUSD", "GBPUSD", "XAUUSD"]:
        res = calculate_htf_fundamental_bias(test_s)
        print("\n" + format_fundamental_bias_prompt(res))
