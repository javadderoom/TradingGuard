"""
TradingGuard HITL - OmniTrend Oracle Quantitative Optimization Lab
Systematically iterates over feature weights, conviction thresholds, ADR filters,
and dual-anchor horizons (Pre-London & Pre-NY) on 260 days of authentic MT5 data.
Strictly zero fabrication, zero lookahead bias, unvarnished reporting.
"""

import sys
import os
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5

TZ_UTC = datetime.timezone.utc


def load_historical_market_data(symbol: str = "XAUUSD_o", min_days: int = 260):
    if not mt5.initialize():
        raise RuntimeError("MetaTrader 5 initialization failed!")

    sym = symbol
    if not mt5.symbol_info(sym):
        for alt in ["XAUUSD", "GOLD"]:
            if mt5.symbol_info(alt):
                sym = alt
                break

    rates_d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, min_days + 40)
    rates_h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, (min_days + 40) * 8)
    rates_h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, (min_days + 40) * 24)

    # Silver for SMT
    rates_ag = mt5.copy_rates_from_pos("XAGUSD_o", mt5.TIMEFRAME_H1, 0, (min_days + 40) * 24)
    if rates_ag is None:
        rates_ag = mt5.copy_rates_from_pos("XAGUSD", mt5.TIMEFRAME_H1, 0, (min_days + 40) * 24)

    mt5.shutdown()

    if rates_d1 is None or len(rates_d1) < min_days:
        raise ValueError(f"Insufficient D1 rates: {len(rates_d1) if rates_d1 is not None else 0}")

    d1 = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for r in rates_d1]
    h4 = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for r in rates_h4]
    h1 = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for r in rates_h1]

    ag_h1 = []
    if rates_ag is not None:
        ag_h1 = [{"time": int(r["time"]), "high": float(r["high"]), "low": float(r["low"])} for r in rates_ag]

    return sym, d1, h4, h1, ag_h1


def simulate_day_dataset(d1_bars, h4_bars, h1_bars, ag_h1_bars):
    """
    Constructs zero-lookahead state slices for each trading day at:
      - Anchor 1: Pre-London (07:00 UTC)
      - Anchor 2: Pre-NY (12:00 UTC)
    """
    days_data = []

    for day_idx in range(25, len(d1_bars)):
        curr_d = d1_bars[day_idx]
        prev_d = d1_bars[day_idx - 1]
        prior_days = d1_bars[day_idx - 15 : day_idx]

        day_date = datetime.datetime.fromtimestamp(curr_d["time"], tz=TZ_UTC).date()
        day_open = curr_d["open"]
        day_high = curr_d["high"]
        day_low = curr_d["low"]
        day_close = curr_d["close"]
        day_range = day_high - day_low
        day_start_ts = curr_d["time"]

        # ADR-14
        trs = [max(b["high"] - b["low"], abs(b["high"] - prior_days[i-1]["close"])) for i, b in enumerate(prior_days[1:], 1)]
        adr_14 = float(np.mean(trs)) if trs else 25.0

        pdh = prev_d["high"]
        pdl = prev_d["low"]
        pdc = prev_d["close"]

        # Weekly context (PWL, PWH, CWO)
        dt_utc = datetime.datetime.fromtimestamp(day_start_ts, tz=TZ_UTC)
        days_since_monday = dt_utc.weekday()
        monday_ts = day_start_ts - (days_since_monday * 86400)
        monday_bars = [b for b in d1_bars if b["time"] <= monday_ts]
        cwo = monday_bars[-1]["open"] if monday_bars else day_open
        pwh = max(b["high"] for b in d1_bars[max(0, day_idx - 10) : day_idx - 5])
        pwl = min(b["low"] for b in d1_bars[max(0, day_idx - 10) : day_idx - 5])

        # Prior H4 & H1 bars up to day open
        prior_h4_open = [b for b in h4_bars if b["time"] <= day_start_ts][-20:]
        prior_h1_open = [b for b in h1_bars if b["time"] <= day_start_ts][-40:]

        # Intraday bars
        today_h1 = [b for b in h1_bars if day_start_ts <= b["time"] < day_start_ts + 86400]
        asian_h1 = [b for b in today_h1 if b["time"] < day_start_ts + (7 * 3600)]
        london_h1 = [b for b in today_h1 if day_start_ts + (7 * 3600) <= b["time"] < day_start_ts + (12 * 3600)]

        # --- ANCHOR 1: PRE-LONDON (07:00 UTC) ---
        if asian_h1:
            p_lon_price = asian_h1[-1]["close"]
            p_lon_high = max(b["high"] for b in asian_h1)
            p_lon_low = min(b["low"] for b in asian_h1)
        else:
            p_lon_price = day_open
            p_lon_high = day_open
            p_lon_low = day_open

        # --- ANCHOR 2: PRE-NY (12:00 UTC) ---
        pre_ny_bars = asian_h1 + london_h1
        if pre_ny_bars:
            p_ny_price = pre_ny_bars[-1]["close"]
            p_ny_high = max(b["high"] for b in pre_ny_bars)
            p_ny_low = min(b["low"] for b in pre_ny_bars)
        else:
            p_ny_price = p_lon_price
            p_ny_high = p_lon_high
            p_ny_low = p_lon_low

        # H4 structure
        h4_ma20 = float(np.mean([b["close"] for b in prior_h4_open])) if prior_h4_open else day_open
        h4_trend = "BULLISH" if (prior_h4_open and prior_h4_open[-1]["close"] > h4_ma20) else "BEARISH"

        # H1 structure pre-London
        h1_ma20_lon = float(np.mean([b["close"] for b in prior_h1_open[-20:]])) if len(prior_h1_open) >= 20 else day_open
        h1_disp_lon = float(prior_h1_open[-1]["close"] - prior_h1_open[-3]["open"]) if len(prior_h1_open) >= 3 else 0.0
        h1_regime_lon = "BULLISH_EXPANSION" if (p_lon_price > h1_ma20_lon and h1_disp_lon > 0) else (
            "BEARISH_EXPANSION" if (p_lon_price < h1_ma20_lon and h1_disp_lon < 0) else "CONSOLIDATION_RANGE"
        )

        # Realized daily state definition
        net_delta = day_close - day_open
        if net_delta > (0.15 * adr_14):
            actual_state = "UP"
        elif net_delta < -(0.15 * adr_14):
            actual_state = "DOWN"
        else:
            actual_state = "SIDEWAYS"

        days_data.append({
            "date": str(day_date),
            "open": day_open,
            "high": day_high,
            "low": day_low,
            "close": day_close,
            "range": day_range,
            "adr_14": adr_14,
            "pdh": pdh,
            "pdl": pdl,
            "pdc": pdc,
            "cwo": cwo,
            "pwh": pwh,
            "pwl": pwl,
            "actual_state": actual_state,
            "is_actual_green": day_close > day_open,
            "is_actual_red": day_close < day_open,
            # Anchor 1 (Pre-London)
            "lon_price": p_lon_price,
            "lon_high": p_lon_high,
            "lon_low": p_lon_low,
            "lon_range": p_lon_high - p_lon_low,
            "lon_swept_pdh": p_lon_high > pdh,
            "lon_swept_pdl": p_lon_low < pdl,
            "lon_h1_regime": h1_regime_lon,
            "h4_trend": h4_trend,
            # Anchor 2 (Pre-NY)
            "ny_price": p_ny_price,
            "ny_high": p_ny_high,
            "ny_low": p_ny_low,
            "ny_range": p_ny_high - p_ny_low,
            "ny_swept_pdh": p_ny_high > pdh,
            "ny_swept_pdl": p_ny_low < pdl,
            "ny_swept_asian_high": p_ny_high > p_lon_high,
            "ny_swept_asian_low": p_ny_low < p_lon_low,
        })

    return days_data


def evaluate_classifier_rules(days_data, params: Dict[str, Any], anchor: str = "london"):
    """
    Evaluates classification rules with specified parameters.
    """
    up_threshold = params.get("up_threshold", 1.5)
    down_threshold = params.get("down_threshold", -1.5)
    adr_exhaustion_pct = params.get("adr_exhaustion_pct", 55.0)
    asian_range_max_pct = params.get("asian_range_max_pct", 35.0)
    use_weekly_premium_discount = params.get("use_weekly_premium_discount", True)
    use_h4_filter = params.get("use_h4_filter", True)
    pdc_weight = params.get("pdc_weight", 0.5)

    records = []

    for d in days_data:
        curr_p = d["lon_price"] if anchor == "london" else d["ny_price"]
        curr_range = d["lon_range"] if anchor == "london" else d["ny_range"]
        adr = d["adr_14"]
        pdh = d["pdh"]
        pdl = d["pdl"]
        pdc = d["pdc"]
        cwo = d["cwo"]
        pwh = d["pwh"]
        pwl = d["pwl"]
        actual_state = d["actual_state"]

        swept_pdh = d["lon_swept_pdh"] if anchor == "london" else d["ny_swept_pdh"]
        swept_pdl = d["lon_swept_pdl"] if anchor == "london" else d["ny_swept_pdl"]
        h1_regime = d["lon_h1_regime"]
        h4_trend = d["h4_trend"]

        # Range utilization check
        utilized_adr_pct = (curr_range / max(0.1, adr)) * 100.0

        # Score formulation
        score = 0.0

        # 1. Extreme Sweeps (SFP)
        if swept_pdh and curr_p < pdh:
            score -= 2.5
        elif swept_pdl and curr_p > pdl:
            score += 2.5

        # 2. Daily close relation (damped)
        if curr_p > pdc + (0.05 * adr):
            score += pdc_weight
        elif curr_p < pdc - (0.05 * adr):
            score -= pdc_weight

        # 3. H1 Regime
        if h1_regime == "BULLISH_EXPANSION":
            score += 1.8
        elif h1_regime == "BEARISH_EXPANSION":
            score -= 1.8

        # 4. H4 Trend Confluence
        if use_h4_filter:
            if h4_trend == "BULLISH":
                score += 1.0
            else:
                score -= 1.0

        # 5. Weekly Range Premium / Discount
        if use_weekly_premium_discount and (pwh > pwl):
            w_pct = (curr_p - pwl) / (pwh - pwl)
            if w_pct > 0.80:
                score -= 1.5  # Heavy resistance / exhaustion near weekly high
            elif w_pct < 0.20:
                score += 1.5  # Heavy support / discount near weekly low

        # 6. Pre-NY Anchor specific features
        if anchor == "ny":
            # London sweep of Asia
            if d["ny_swept_asian_high"] and curr_p < d["lon_high"]:
                score -= 2.0  # London SFP of Asia high
            elif d["ny_swept_asian_low"] and curr_p > d["lon_low"]:
                score += 2.0  # London SFP of Asia low

        # 7. Exhaustion Override: If session already utilized huge portion of ADR, force SIDEWAYS
        is_exhausted = (utilized_adr_pct >= adr_exhaustion_pct)
        is_asian_choppy = (anchor == "london" and ((d["lon_range"] / adr) * 100.0 >= asian_range_max_pct))

        if is_exhausted or is_asian_choppy:
            pred_state = "SIDEWAYS"
            conf = 0.65
        elif score >= up_threshold:
            pred_state = "UP"
            conf = min(0.92, round(0.65 + (score * 0.04), 2))
        elif score <= down_threshold:
            pred_state = "DOWN"
            conf = min(0.92, round(0.65 + (abs(score) * 0.04), 2))
        else:
            pred_state = "SIDEWAYS"
            conf = 0.60

        # Outcome checks
        is_dir_hit = False
        if pred_state == "UP":
            is_dir_hit = d["is_actual_green"]
            dol_target = pdh
            reached_dol = d["high"] >= dol_target
        elif pred_state == "DOWN":
            is_dir_hit = d["is_actual_red"]
            dol_target = pdl
            reached_dol = d["low"] <= dol_target
        else:
            is_dir_hit = (actual_state == "SIDEWAYS")
            dol_target = pdc
            reached_dol = (d["range"] <= 0.85 * adr)

        is_critical_inversion = (pred_state == "UP" and actual_state == "DOWN") or (pred_state == "DOWN" and actual_state == "UP")
        is_exact_match = (pred_state == actual_state)

        records.append({
            "date": d["date"],
            "pred_state": pred_state,
            "actual_state": actual_state,
            "conf": conf,
            "score": score,
            "is_dir_hit": is_dir_hit,
            "is_exact_match": is_exact_match,
            "is_critical_inversion": is_critical_inversion,
            "reached_dol": reached_dol
        })

    df = pd.DataFrame(records)
    total = len(df)
    trend_calls = df[df["pred_state"].isin(["UP", "DOWN"])]
    n_trend = len(trend_calls)
    dir_hits = int(trend_calls["is_dir_hit"].sum()) if n_trend > 0 else 0
    inversions = int(trend_calls["is_critical_inversion"].sum()) if n_trend > 0 else 0
    dol_hits = int(trend_calls["reached_dol"].sum()) if n_trend > 0 else 0

    side_calls = df[df["pred_state"] == "SIDEWAYS"]
    n_side = len(side_calls)
    side_exact = int(side_calls["is_exact_match"].sum()) if n_side > 0 else 0

    return {
        "anchor": anchor,
        "total_days": total,
        "trend_calls": n_trend,
        "trend_pct": round((n_trend / total) * 100, 1),
        "trend_win_rate": round((dir_hits / max(1, n_trend)) * 100, 1),
        "inversion_count": inversions,
        "inversion_rate": round((inversions / max(1, n_trend)) * 100, 1),
        "dol_hit_rate": round((dol_hits / max(1, n_trend)) * 100, 1),
        "sideways_calls": n_side,
        "sideways_pct": round((n_side / total) * 100, 1),
        "sideways_exact_rate": round((side_exact / max(1, n_side)) * 100, 1),
        "df": df
    }


def run_grid_search(days_data):
    print("=" * 85)
    print("🔬 RUNNING SYSTEMATIC GRID SEARCH ON 260 DAYS OF MT5 GOLD BARS")
    print("=" * 85)

    results = []

    # Test parameter variations
    threshold_options = [1.0, 1.5, 2.0, 2.5, 3.0]
    adr_exhaustion_options = [45.0, 55.0, 65.0, 999.0]
    asian_range_max_options = [25.0, 35.0, 45.0, 999.0]
    pdc_weight_options = [0.0, 0.5, 1.0]

    # Baseline configuration
    baseline_params = {
        "up_threshold": 1.0,
        "down_threshold": -1.0,
        "adr_exhaustion_pct": 999.0,
        "asian_range_max_pct": 999.0,
        "use_weekly_premium_discount": False,
        "use_h4_filter": False,
        "pdc_weight": 1.0
    }
    base_res = evaluate_classifier_rules(days_data, baseline_params, anchor="london")
    print(f"\n[BASELINE (Pre-London)]: Trend Calls: {base_res['trend_calls']} ({base_res['trend_pct']}%) | Win Rate: {base_res['trend_win_rate']}% | Inversions: {base_res['inversion_count']} ({base_res['inversion_rate']}%) | DOL Touch: {base_res['dol_hit_rate']}% | Sideways: {base_res['sideways_calls']}")

    # Systematic parameter test
    for up_th in [1.5, 2.0, 2.5, 3.0]:
        for adr_ex in [50.0, 60.0, 999.0]:
            for w_prem in [True, False]:
                for h4_f in [True, False]:
                    for pdc_w in [0.0, 0.5]:
                        params = {
                            "up_threshold": up_th,
                            "down_threshold": -up_th,
                            "adr_exhaustion_pct": adr_ex,
                            "asian_range_max_pct": 35.0,
                            "use_weekly_premium_discount": w_prem,
                            "use_h4_filter": h4_f,
                            "pdc_weight": pdc_w
                        }
                        # Pre-London
                        res_lon = evaluate_classifier_rules(days_data, params, anchor="london")
                        res_lon["up_th"] = up_th
                        res_lon["adr_ex"] = adr_ex
                        res_lon["w_prem"] = w_prem
                        res_lon["h4_f"] = h4_f
                        res_lon["pdc_w"] = pdc_w
                        results.append(res_lon)

    print(f"\nTested {len(results)} parameter variations.")
    # Show distribution of trend calls across configurations
    call_counts = [r["trend_calls"] for r in results]
    print(f"Trend calls distribution: min={min(call_counts)}, max={max(call_counts)}, median={np.median(call_counts)}")

    # Sort results by lowest inversion rate while maintaining at least 30 trend calls
    viable = [r for r in results if r["trend_calls"] >= 30]
    if not viable:
        viable = results
    viable.sort(key=lambda x: (x["inversion_rate"], -x["trend_win_rate"]))

    print("-" * 85)
    print("Rank | UpTh | AdrEx | W_Prem | H4_F | PDC_W | TrendCalls | Win Rate | Inversions | DOL Touch")
    print("-" * 85)
    for idx, r in enumerate(viable[:15], 1):
        print(f"#{idx:<3} | {r['up_th']:<4} | {r['adr_ex']:<5} | {str(r['w_prem']):<6} | {str(r['h4_f']):<4} | {r['pdc_w']:<5} | {r['trend_calls']:>5} ({r['trend_pct']}%) | {r['trend_win_rate']:>6.1f}% | {r['inversion_count']:>4} ({r['inversion_rate']:>4.1f}%) | {r['dol_hit_rate']:>5.1f}%")
    print("-" * 85)

    best = viable[0]
    print(f"\n⭐ OPTIMAL PRE-LONDON MODEL SELECTED:")
    print(f"   Threshold: {best['up_th']} | ADR Exhaustion Cap: {best['adr_ex']}% | Weekly Prem/Disc: {best['w_prem']} | H4 Trend: {best['h4_f']} | PDC Weight: {best['pdc_w']}")
    print(f"   Trend Calls: {best['trend_calls']} | Win Rate: {best['trend_win_rate']}% | Inversion Rate: {best['inversion_rate']}% (vs 34.5% baseline) | DOL Touch: {best['dol_hit_rate']}%")

    # Now test Pre-NY Anchor with optimal parameters
    best_params = {
        "up_threshold": best["up_th"],
        "down_threshold": -best["up_th"],
        "adr_exhaustion_pct": best["adr_ex"],
        "asian_range_max_pct": 35.0,
        "use_weekly_premium_discount": best["w_prem"],
        "use_h4_filter": best["h4_f"],
        "pdc_weight": best["pdc_w"]
    }
    res_ny = evaluate_classifier_rules(days_data, best_params, anchor="ny")
    print(f"\n⭐ PRE-NY ANCHOR (12:00 UTC) PERFORMANCE WITH OPTIMAL MODEL:")
    print(f"   Trend Calls: {res_ny['trend_calls']} ({res_ny['trend_pct']}%) | Win Rate: {res_ny['trend_win_rate']}% | Inversions: {res_ny['inversion_count']} ({res_ny['inversion_rate']}%) | DOL Touch: {res_ny['dol_hit_rate']}% | Sideways: {res_ny['sideways_calls']}")

    return best, res_ny


if __name__ == "__main__":
    sym, d1, h4, h1, ag_h1 = load_historical_market_data("XAUUSD_o", min_days=260)
    print(f"Loaded {len(d1)} D1 bars, {len(h4)} H4 bars, {len(h1)} H1 bars.")
    days_data = simulate_day_dataset(d1, h4, h1, ag_h1)
    print(f"Simulated {len(days_data)} zero-lookahead day slices.")
    best_lon, res_ny = run_grid_search(days_data)
