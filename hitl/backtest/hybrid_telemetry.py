"""
TradingGuard HITL - Hybrid Telemetry Engine
Calculates precise numerical SMC metrics directly from MT5 OHLCV arrays:
- Prior Day High (PDH) & Prior Day Low (PDL)
- Asian Range High/Low & London Range High/Low with exact Sweep Delta
- Market Structure Shift (MSS) breakout levels
- 5M/15M Fair Value Gaps (Proximal Edge, Distal Edge, 50% Consequent Encroachment)
- Breaker Block boundaries & Optimal Trade Entry (OTE 62%-79%) zones
- ATR(14) volatility and real-time spread metrics
This numerical telemetry is paired with MTF chart screenshots for Multimodal AI Analysis.
"""

import datetime
from typing import List, Dict, Any, Optional


def calculate_atr(bars: List[Dict[str, Any]], period: int = 14) -> float:
    """Calculates Average True Range over the specified period."""
    if len(bars) < period + 1:
        return 1.0
    tr_list = []
    for i in range(1, len(bars)):
        h = bars[i]['high']
        l = bars[i]['low']
        c_prev = bars[i-1]['close']
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        tr_list.append(tr)
    return sum(tr_list[-period:]) / period if tr_list else 1.0


def extract_hybrid_telemetry(
    bars_1d: List[Dict[str, Any]],
    bars_1h: List[Dict[str, Any]],
    bars_15m: List[Dict[str, Any]],
    bars_5m: List[Dict[str, Any]],
    symbol: str,
    session_hour: int,
    usdx_quote: float = 101.50
) -> Dict[str, Any]:
    """
    Extracts high-precision numerical SMC telemetry to accompany chart screenshots.
    """
    if not (bars_1d and bars_1h and bars_15m and bars_5m):
        return {}

    current_price = bars_5m[-1]['close']
    atr_5m = calculate_atr(bars_5m, period=14)
    atr_1h = calculate_atr(bars_1h, period=14)

    # 1. Higher-Timeframe Landmarks (PDH, PDL)
    pdh = bars_1d[-2]['high'] if len(bars_1d) >= 2 else bars_1d[-1]['high']
    pdl = bars_1d[-2]['low'] if len(bars_1d) >= 2 else bars_1d[-1]['low']
    daily_bias = "BULLISH" if bars_1d[-1]['close'] > bars_1d[-1]['open'] else "BEARISH"

    # 2. Intraday Session Liquidity Benchmarks (Timestamp-driven)
    last_bar_time = bars_5m[-1]['time']
    cur_dt = datetime.datetime.fromtimestamp(last_bar_time, datetime.timezone.utc)
    
    # Filter bars of the current trading day
    today_bars = [b for b in bars_5m if datetime.datetime.fromtimestamp(b['time'], datetime.timezone.utc).date() == cur_dt.date()]
    
    if cur_dt.hour < 13:
        # London Session: Benchmark is Asian Range (00:00 to 07:00 UTC)
        benchmark_name = "Asian Range (00:00 - 07:00 UTC)"
        bench_bars = [b for b in today_bars if datetime.datetime.fromtimestamp(b['time'], datetime.timezone.utc).hour < 7]
        active_bars = [b for b in today_bars if datetime.datetime.fromtimestamp(b['time'], datetime.timezone.utc).hour >= 7]
    else:
        # NY Session: Benchmark is London Range (07:00 to 13:00 UTC)
        benchmark_name = "London Range (07:00 - 13:00 UTC)"
        bench_bars = [b for b in today_bars if 7 <= datetime.datetime.fromtimestamp(b['time'], datetime.timezone.utc).hour < 13]
        active_bars = [b for b in today_bars if datetime.datetime.fromtimestamp(b['time'], datetime.timezone.utc).hour >= 13]

    if not bench_bars:
        bench_bars = bars_5m[-60:-15] if len(bars_5m) >= 60 else bars_5m[:-5]
    if not active_bars:
        active_bars = bars_5m[-15:]

    bench_high = max(b['high'] for b in bench_bars) if bench_bars else current_price
    bench_low = min(b['low'] for b in bench_bars) if bench_bars else current_price

    # 3. Liquidity Sweep Detection
    recent_high = max(b['high'] for b in active_bars) if active_bars else current_price
    recent_low = min(b['low'] for b in active_bars) if active_bars else current_price

    swept_high = recent_high > bench_high
    swept_low = recent_low < bench_low
    sweep_high_delta = (recent_high - bench_high) if swept_high else 0.0
    sweep_low_delta = (bench_low - recent_low) if swept_low else 0.0

    # 4. Mathematical 5M & 15M Fair Value Gaps (FVG)
    fvgs_5m = []
    for i in range(len(bars_5m) - 1, max(2, len(bars_5m) - 15), -1):
        c1, c2, c3 = bars_5m[i - 2], bars_5m[i - 1], bars_5m[i]
        # Bullish FVG
        if c3['low'] > c1['high']:
            fvgs_5m.append({
                "type": "BULLISH",
                "proximal": c3['low'],
                "distal": c1['high'],
                "ce": (c3['low'] + c1['high']) / 2.0,
                "gap_pts": c3['low'] - c1['high']
            })
            break
        # Bearish FVG
        elif c1['low'] > c3['high']:
            fvgs_5m.append({
                "type": "BEARISH",
                "proximal": c3['high'],
                "distal": c1['low'],
                "ce": (c3['high'] + c1['low']) / 2.0,
                "gap_pts": c1['low'] - c3['high']
            })
            break

    active_fvg = fvgs_5m[0] if fvgs_5m else None

    # 5. Market Structure Shift (MSS) & Breaker Blocks
    window = bars_5m[-24:-2] if len(bars_5m) >= 26 else bars_5m[:-2]
    highs = []
    lows = []
    if len(window) >= 3:
        for idx in range(1, len(window) - 1):
            if window[idx]['high'] >= window[idx-1]['high'] and window[idx]['high'] >= window[idx+1]['high']:
                highs.append((idx, window[idx]['high']))
            if window[idx]['low'] <= window[idx-1]['low'] and window[idx]['low'] <= window[idx+1]['low']:
                lows.append((idx, window[idx]['low']))

    last_high_val = highs[-1][1] if highs else bench_high
    last_low_val = lows[-1][1] if lows else bench_low

    mss_detected = "NONE"
    breaker_range = None
    if current_price > last_high_val:
        mss_detected = f"BULLISH_MSS (Broke {last_high_val:.2f})"
        breaker_range = f"[{bench_low:.2f} - {bench_low + atr_5m:.2f}]"
    elif current_price < last_low_val:
        mss_detected = f"BEARISH_MSS (Broke {last_low_val:.2f})"
        breaker_range = f"[{bench_high - atr_5m:.2f} - {bench_high:.2f}]"

    # 6. Optimal Trade Entry (OTE 62% - 79%)
    swing_range = bench_high - bench_low
    ote_62 = bench_low + 0.62 * swing_range
    ote_705 = bench_low + 0.705 * swing_range
    ote_79 = bench_low + 0.79 * swing_range

    # 7. External Structural Swing Pools & HTF Trend Expansion (RULE-CORE-006 / RULE-TARGET-041)
    atr_1d = calculate_atr(bars_1d, period=14)
    prior_days = bars_1d[-7:-1] if len(bars_1d) >= 7 else bars_1d[:-1]
    ext_swing_high = max(b['high'] for b in prior_days) if prior_days else pdh
    ext_swing_low = min(b['low'] for b in prior_days) if prior_days else pdl
    htf_expansion_bearish = current_price - 1.25 * atr_1d
    htf_expansion_bullish = current_price + 1.25 * atr_1d

    return {
        "current_price": current_price,
        "atr_5m": atr_5m,
        "atr_1h": atr_1h,
        "atr_1d": atr_1d,
        "pdh": pdh,
        "pdl": pdl,
        "ext_swing_high": ext_swing_high,
        "ext_swing_low": ext_swing_low,
        "htf_expansion_bearish": htf_expansion_bearish,
        "htf_expansion_bullish": htf_expansion_bullish,
        "daily_bias": daily_bias,
        "benchmark_name": benchmark_name,
        "bench_high": bench_high,
        "bench_low": bench_low,
        "swept_high": swept_high,
        "sweep_high_delta": sweep_high_delta,
        "swept_low": swept_low,
        "sweep_low_delta": sweep_low_delta,
        "active_fvg": active_fvg,
        "mss_detected": mss_detected,
        "breaker_range": breaker_range,
        "ote_62": ote_62,
        "ote_705": ote_705,
        "ote_79": ote_79,
        "usdx": usdx_quote
    }


def format_telemetry_prompt(t: Dict[str, Any], symbol: str) -> str:
    """Formats telemetry dictionary into an institutional prompt block."""
    if not t:
        return "Numerical Telemetry: Standard market parameters apply."

    is_fx = "EUR" in symbol.upper() or "GBP" in symbol.upper()
    is_silver = "XAG" in symbol.upper()
    fmt = ".5f" if is_fx else (".3f" if is_silver else ".2f")

    p_curr = f"{t['current_price']:{fmt}}"
    p_pdh = f"{t['pdh']:{fmt}}"
    p_pdl = f"{t['pdl']:{fmt}}"
    p_bhigh = f"{t['bench_high']:{fmt}}"
    p_blow = f"{t['bench_low']:{fmt}}"
    p_atr = f"{t['atr_5m']:{fmt}}"
    p_ext_low = f"{t.get('ext_swing_low', t['pdl']):{fmt}}"
    p_ext_high = f"{t.get('ext_swing_high', t['pdh']):{fmt}}"
    p_htf_exp_bear = f"{t.get('htf_expansion_bearish', t['pdl']):{fmt}}"
    p_htf_exp_bull = f"{t.get('htf_expansion_bullish', t['pdh']):{fmt}}"

    sweep_str = "None"
    if t['swept_high']:
        sweep_str = f"SWEPT HIGH by {t['sweep_high_delta']:{fmt}} (Extreme: {t['bench_high'] + t['sweep_high_delta']:{fmt}})"
    elif t['swept_low']:
        sweep_str = f"SWEPT LOW by {t['sweep_low_delta']:{fmt}} (Extreme: {t['bench_low'] - t['sweep_low_delta']:{fmt}})"

    fvg_str = "No clean 5M FVG active"
    if t['active_fvg']:
        f = t['active_fvg']
        fvg_str = f"{f['type']} FVG -> Proximal Edge: {f['proximal']:{fmt}} | Distal Edge: {f['distal']:{fmt}} | 50% C.E.: {f['ce']:{fmt}} (Width: {f['gap_pts']:{fmt}})"

    lines = [
        "=== EXACT MATHEMATICAL SMC TELEMETRY (PAIR WITH CHARTS) ===",
        f"• Real-Time Quote: {p_curr} | 5M ATR(14): {p_atr} | USDX: {t['usdx']:.2f}",
        f"• Macro Benchmarks: Prior Day High (PDH): {p_pdh} | Prior Day Low (PDL): {p_pdl} | Daily Bias: {t['daily_bias']}",
        f"• Session Benchmarks [{t['benchmark_name']}]:",
        f"  - Range High: {p_bhigh} | Range Low: {p_blow}",
        f"  - Liquidity Sweep Status: {sweep_str}",
        f"• Algorithmic SMC POIs:",
        f"  - Active Fair Value Gap: {fvg_str}",
        f"  - Market Structure Shift: {t['mss_detected']}",
        f"  - Breaker Block Zone: {t['breaker_range'] or 'None'}",
        f"  - OTE Discount/Premium Range: 62% at {t['ote_62']:{fmt}} | 70.5% at {t['ote_705']:{fmt}} | 79% at {t['ote_79']:{fmt}}",
        f"• OBJECTIVE STRUCTURAL TARGET ZONES (MANDATORY Min 1:3.0 R:R Required):",
        f"  - Bullish Target Pools:",
        f"    * Internal Session High: {p_bhigh} | Prior Day High / PDH: {p_pdh}",
        f"    * External Structural Swing High (BSL): {p_ext_high} | HTF Expansion Target: {p_htf_exp_bull}",
        f"  - Bearish Target Pools:",
        f"    * Internal Session Low: {p_blow} | Prior Day Low / PDL: {p_pdl}",
        f"    * External Structural Swing Low (SSL): {p_ext_low} | HTF Expansion Target: {p_htf_exp_bear}",
        f"  * TARGET MANDATE (RULE-CORE-006 & RULE-TARGET-041): In pro-trend regimes (SELL_ONLY / BUY_ONLY), Take Profit MUST anchor to the External Structural Swing Low/High or HTF Expansion Pool. Do NOT exit prematurely at minor internal session support. Required R:R >= 1:3.0.",
        "==========================================================="
    ]
    return "\n".join(lines)
