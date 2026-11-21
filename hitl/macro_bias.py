"""
TradingGuard HITL - Fundamental Directional Bias Engine (Facade)
Live Path (target_time is None):
    Delegates to the Evidence-Grounded Multi-Order Causal Fundamental Engine
    (`hitl/fundamental/`), returning live sovereign yield curves, cross-asset
    liquidity diagnostics, CFTC COT positioning, and tape-verified causal chains.

Historical Backtest Path (target_time provided):
    Computes strictly causal point-in-time closed-bar MT5 currency index momentum
    with zero future leakage.
"""

import datetime
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.data_feed import _convert_records
from hitl.fundamental.governor import normalize_fundamental_symbol


def _infer_base_currency(sym_upper: str) -> str:
    if "EUR" in sym_upper and "GBP" not in sym_upper and "JPY" not in sym_upper:
        return "EUR"
    if "GBP" in sym_upper:
        return "GBP"
    if "JPY" in sym_upper:
        return "JPY"
    if "XAU" in sym_upper or "GOLD" in sym_upper:
        return "XAU"
    if "XAG" in sym_upper or "SILVER" in sym_upper:
        return "XAG"
    if "BTC" in sym_upper:
        return "BTC"
    if "ETH" in sym_upper:
        return "ETH"
    if any(k in sym_upper for k in ("NQ", "NAS", "USTEC", "US100")):
        return "NQ"
    if any(k in sym_upper for k in ("SPX", "US500", "SP500")):
        return "SPX"
    if any(k in sym_upper for k in ("OIL", "CRUDE", "WTI", "BRENT")):
        return "OIL"
    return "USD"


def _get_index_trend(
    symbol_index: str,
    target_time: Optional[datetime.datetime] = None,
    lookback_days: int = 15,
) -> Dict[str, Any]:
    """
    Computes causal closed-bar D1 trend and 5-day momentum for an MT5 currency index
    (used strictly for historical point-in-time backtest replay).
    """
    try:
        if not mt5.terminal_info():
            mt5.initialize()
    except Exception:
        pass

    if target_time:
        raw = mt5.copy_rates_from(symbol_index, mt5.TIMEFRAME_D1, target_time, lookback_days + 2)
    else:
        raw = mt5.copy_rates_from_pos(symbol_index, mt5.TIMEFRAME_D1, 0, lookback_days + 2)

    records = _convert_records(raw)
    if target_time and records:
        cutoff_ts = target_time.timestamp() if target_time.tzinfo else target_time.replace(tzinfo=datetime.timezone.utc).timestamp()
        # Only include D1 bars that have completely closed before target_time (open + 86400 <= cutoff)
        closed = [r for r in records if (r["time"] + 86400) <= cutoff_ts]
        if len(closed) >= 5:
            records = closed

    if not records or len(records) < 5:
        return {
            "symbol": symbol_index,
            "status": "INSUFFICIENT_DATA",
            "trend": "NEUTRAL",
            "momentum_5d_pct": 0.0,
            "latest_close": 0.0,
        }

    closes = [b["close"] for b in records]
    latest_close = closes[-1]
    close_5d_ago = closes[-5]
    sma_10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else sum(closes) / len(closes)
    mom_pct = ((latest_close - close_5d_ago) / close_5d_ago) * 100.0 if close_5d_ago else 0.0

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
        "above_sma": latest_close > sma_10,
    }


def _calculate_historical_causal_bias(symbol: str, target_time: datetime.datetime) -> Dict[str, Any]:
    """Point-in-time zero-lookahead historical macro index bias for backtest replay."""
    sym = normalize_fundamental_symbol(symbol)
    base_curr = _infer_base_currency(sym)
    usdx_data = _get_index_trend("USDX", target_time=target_time)
    base_idx_sym = "EURLFX" if base_curr == "EUR" else ("GBPLFX" if base_curr == "GBP" else None)
    base_idx_data = _get_index_trend(base_idx_sym, target_time=target_time) if base_idx_sym else None

    usd_trend = usdx_data.get("trend", "NEUTRAL")
    usd_mom = float(usdx_data.get("momentum_5d_pct", 0.0) or 0.0)
    usd_close = float(usdx_data.get("latest_close", 100.0) or 100.0)

    bias = "NEUTRAL"
    execution_filter = "SELECTIVE_BI_DIRECTIONAL"
    bullets = [f"Historical USDX (closed D1): {usd_close:.2f} [{usd_trend}, 5D: {usd_mom:+.2f}%]"]

    if base_curr in ("EUR", "GBP"):
        b_trend = base_idx_data.get("trend", "NEUTRAL") if base_idx_data else "NEUTRAL"
        b_mom = float(base_idx_data.get("momentum_5d_pct", 0.0) or 0.0) if base_idx_data else 0.0
        bullets.append(f"{base_idx_sym}: [{b_trend}, 5D: {b_mom:+.2f}%]")
        if usd_mom <= -0.30 or ("BEARISH" in usd_trend and "BULLISH" in b_trend):
            bias = "BULLISH"
            execution_filter = "BULLISH_FAVORED"
        elif usd_mom >= 0.30 or ("BULLISH" in usd_trend and "BEARISH" in b_trend):
            bias = "BEARISH"
            execution_filter = "BEARISH_FAVORED"
    elif base_curr in ("XAU", "XAG"):
        if usd_mom <= -0.30:
            bias = "BULLISH"
            execution_filter = "BULLISH_FAVORED"
        elif usd_mom >= 0.30:
            bias = "BEARISH"
            execution_filter = "BEARISH_FAVORED"

    narrative = f"Historical point-in-time currency index posture for {sym}: {bias} (USDX 5D {usd_mom:+.2f}%)."
    return {
        "symbol": sym,
        "base_currency": base_curr,
        "htf_fundamental_bias": bias,
        "execution_filter": execution_filter,
        "usdx_metrics": usdx_data,
        "base_index_metrics": base_idx_data,
        "macro_narrative": narrative,
        "summary_bullets": bullets,
        "analysis_source": "historical_mt5_index_replay",
    }


def calculate_htf_fundamental_bias(
    symbol: str = "XAUUSD",
    target_time: Optional[datetime.datetime] = None,
) -> Dict[str, Any]:
    """
    Computes live Evidence-Grounded Causal Fundamental Bias (via hitl/fundamental/)
    when target_time is None, or strict point-in-time historical index bias when
    target_time is provided for historical backtesting.
    """
    if target_time is not None:
        return _calculate_historical_causal_bias(symbol, target_time)

    from hitl.fundamental.causal_engine import fundamental_engine

    norm_sym = normalize_fundamental_symbol(symbol)
    view = fundamental_engine.get_asset_view(norm_sym, force_refresh=False, allow_llm=False)

    score = int(view.get("score", 0) or 0)
    bias = str(view.get("bias", "NEUTRAL")).upper()
    diag = view.get("diagnostics", {}) or {}
    reg = view.get("global_macro_regime", {}) or {}

    if score >= 55:
        exec_filter = "BUY_ONLY"
    elif score <= -55:
        exec_filter = "SELL_ONLY"
    elif score >= 20:
        exec_filter = "BULLISH_FAVORED"
    elif score <= -20:
        exec_filter = "BEARISH_FAVORED"
    else:
        exec_filter = "SELECTIVE_BI_DIRECTIONAL"

    dxy_lvl = float(diag.get("dxy_level") or 0.0)
    dxy_5d = float(diag.get("dxy_5d_pct") or 0.0)
    real_10y = diag.get("real_10y_level")
    real_5d = diag.get("real_10y_5d_bps")
    nom_10y = diag.get("nom_10y_level")

    summary_bullets = [
        f"Global Regime: {reg.get('label', 'N/A')} — {reg.get('dominant_theme', '')}",
        f"Sovereign Rates: US10Y Nom {nom_10y if nom_10y is not None else 'N/A'}% | US10Y Real {real_10y if real_10y is not None else 'N/A'}% ({real_5d:+.1f} bps 5D)"
        if real_5d is not None
        else f"Sovereign Rates: US10Y Nom {nom_10y if nom_10y is not None else 'N/A'}%",
        f"Dollar & Volatility: DXY {dxy_lvl:.2f} ({dxy_5d:+.2f}% 5D) | VIX {diag.get('vix_level', 'N/A')}",
    ]

    return {
        "symbol": norm_sym,
        "base_currency": _infer_base_currency(norm_sym),
        "htf_fundamental_bias": bias,
        "execution_filter": exec_filter,
        "score": score,
        "confidence": float(view.get("confidence", 0.5) or 0.5),
        "horizon_bias": view.get("horizon_bias", {}),
        "dominant_driver": view.get("dominant_driver", ""),
        "dominant_mechanism": view.get("dominant_mechanism", ""),
        "bullish_forces": view.get("bullish_forces", []),
        "bearish_forces": view.get("bearish_forces", []),
        "invalidation_trigger": view.get("invalidation_trigger", ""),
        "execution_posture": view.get("execution_posture", "TWO_WAY_SELECTIVE"),
        "causal_chains": view.get("causal_chains", []),
        "global_macro_regime": reg,
        "diagnostics": diag,
        "treasury_curves": view.get("treasury_curves", {}),
        "cot": view.get("cot"),
        "usdx_metrics": {
            "symbol": "USDX",
            "status": "OK" if dxy_lvl else "UNAVAILABLE",
            "trend": reg.get("dollar_regime", "NEUTRAL"),
            "latest_close": round(dxy_lvl, 2),
            "momentum_5d_pct": round(dxy_5d, 2),
        },
        "base_index_metrics": None,
        "macro_narrative": view.get("dominant_mechanism", "Balanced cross-asset macro drivers."),
        "summary_bullets": summary_bullets,
        "analysis_source": view.get("analysis_source", "fundamental_engine"),
        "raw_view": view,
    }


def format_fundamental_bias_prompt(bias_data: Dict[str, Any]) -> str:
    """Renders structured fundamental intelligence prompt for AI Council Seat #2."""
    if "raw_view" in bias_data or "causal_chains" in bias_data:
        from hitl.fundamental.formatter import format_council_macro_block

        return format_council_macro_block(bias_data.get("raw_view", bias_data), symbol=bias_data.get("symbol"))

    sym = bias_data.get("symbol", "ASSET")
    bias = bias_data.get("htf_fundamental_bias", "NEUTRAL")
    filt = bias_data.get("execution_filter", "SELECTIVE_BI_DIRECTIONAL")
    narrative = bias_data.get("macro_narrative", "")
    bullets = bias_data.get("summary_bullets", [])

    lines = [
        f"=== FUNDAMENTAL DIRECTIONAL BIAS (HISTORICAL): {sym} ===",
        f"• Index Macro Bias: [{bias}] | Execution Posture: [{filt}]",
    ]
    for b in bullets:
        lines.append(f"• {b}")
    lines.append(f"• Summary: {narrative}")
    lines.append("==========================================================")
    return "\n".join(lines)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for test_s in ["XAUUSD", "NQ", "GBPUSD", "BTCUSD"]:
        res = calculate_htf_fundamental_bias(test_s)
        print("\n" + format_fundamental_bias_prompt(res))
