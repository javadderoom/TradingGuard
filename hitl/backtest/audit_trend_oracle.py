"""
TradingGuard HITL - OmniTrend Oracle Quantitative Backtest & Accuracy Audit
Evaluates the 3-state predictive accuracy (UP / DOWN / SIDEWAYS) of OmniTrend Oracle
over 250+ trading days (trailing 12 months) of authentic MT5 tick and bar data on Gold (XAUUSD).
Strictly adheres to Zero Lookahead Bias and the Unvarnished Brutal Truth Mandate.
"""

import sys
import os
import json
import time
import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5

from hitl.trend.snap_trend_classifier import SnapTrendClassifier

OUTPUT_DIR = BASE_DIR / "backtest_results" / "trend_oracle_audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_UTC = datetime.timezone.utc
TZ_TEHRAN = ZoneInfo("Asia/Tehran")


def run_trend_oracle_historical_audit(symbol: str = "XAUUSD_o", min_days: int = 250) -> Dict[str, Any]:
    """
    Runs historical zero-lookahead audit of OmniTrend Oracle daily and session predictions.
    """
    print("=" * 85)
    print(f"🚀 OMNITREND ORACLE 3-STATE PREDICTIVE ACCURACY AUDIT ({symbol})")
    print("   Evaluating: UP (Bullish) | DOWN (Bearish) | SIDEWAYS (Consolidation)")
    print("   Enforcing: Zero Lookahead Bias | Authentic Broker Rates | Strict Outcomes")
    print("=" * 85)

    if not mt5.initialize():
        print("❌ MetaTrader 5 initialization failed!")
        return {}

    # Check available symbol
    sym = symbol
    if not mt5.symbol_info(sym):
        for alt in ["XAUUSD", "GOLD"]:
            if mt5.symbol_info(alt):
                sym = alt
                break

    # Fetch daily bars
    rates_d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, min_days + 30)
    rates_h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, (min_days + 30) * 24)
    rates_m5 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, (min_days + 30) * 120)

    mt5.shutdown()

    if rates_d1 is None or len(rates_d1) < min_days:
        print(f"❌ Insufficient D1 rates fetched: {len(rates_d1) if rates_d1 is not None else 0}")
        return {}

    print(f"✅ Loaded {len(rates_d1)} Daily bars, {len(rates_h1)} H1 bars, and {len(rates_m5)} M5 bars.")

    d1_bars = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for r in rates_d1]
    h1_bars = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for r in rates_h1]

    # Map timestamps
    h1_by_time = {b["time"]: b for b in h1_bars}

    # Force deterministic institutional matrix for fast, 100% reproducible historical audit
    classifier = SnapTrendClassifier(api_key="", api_url="")

    records = []
    # Start after 20 days of burn-in for ADR
    for day_idx in range(20, len(d1_bars)):
        curr_d = d1_bars[day_idx]
        prev_d = d1_bars[day_idx - 1]
        prior_days = d1_bars[day_idx - 15 : day_idx]

        day_date = datetime.datetime.fromtimestamp(curr_d["time"], tz=TZ_UTC).date()
        day_open = curr_d["open"]
        day_high = curr_d["high"]
        day_low = curr_d["low"]
        day_close = curr_d["close"]
        day_range = day_high - day_low

        # Calculate ADR-14 strictly from prior days
        trs = [max(b["high"] - b["low"], abs(b["high"] - prior_days[i-1]["close"])) for i, b in enumerate(prior_days[1:], 1)]
        adr_14 = float(np.mean(trs)) if trs else 25.0

        pdh = prev_d["high"]
        pdl = prev_d["low"]
        pdc = prev_d["close"]

        # H1 context up to the open of current day
        day_start_ts = curr_d["time"]
        prior_h1 = [b for b in h1_bars if b["time"] < day_start_ts][-40:]
        if len(prior_h1) < 15:
            continue

        h1_ma20 = float(np.mean([b["close"] for b in prior_h1[-20:]]))
        h1_disp = float(prior_h1[-1]["close"] - prior_h1[-3]["open"])
        h1_regime = "BULLISH_EXPANSION" if (prior_h1[-1]["close"] > h1_ma20 and h1_disp > 0) else (
            "BEARISH_EXPANSION" if (prior_h1[-1]["close"] < h1_ma20 and h1_disp < 0) else "CONSOLIDATION_RANGE"
        )

        # Weekly Open (Monday 00:00 UTC)
        # Find closest Monday
        dt_utc = datetime.datetime.fromtimestamp(day_start_ts, tz=TZ_UTC)
        days_since_monday = dt_utc.weekday()
        monday_ts = day_start_ts - (days_since_monday * 86400)
        monday_bars = [b for b in d1_bars if b["time"] <= monday_ts]
        cwo = monday_bars[-1]["open"] if monday_bars else day_open

        # Simulate Asian Session Range (00:00 to 06:00 UTC of current day)
        asian_h1 = [b for b in h1_bars if day_start_ts <= b["time"] <= day_start_ts + (6 * 3600)]
        if asian_h1:
            asian_high = max(b["high"] for b in asian_h1)
            asian_low = min(b["low"] for b in asian_h1)
        else:
            asian_high = day_open + (0.2 * adr_14)
            asian_low = day_open - (0.2 * adr_14)

        # Check if Asian session swept PDH or PDL before London Open
        swept_pdh = asian_high > pdh
        swept_pdl = asian_low < pdl

        # Assemble zero-lookahead on-chart vector evaluated at European Morning (07:00 UTC)
        curr_price_pre_london = asian_h1[-1]["close"] if asian_h1 else day_open
        on_chart_state = {
            "symbol": "XAUUSD",
            "current_price": curr_price_pre_london,
            "daily_structure": {
                "pdh": pdh,
                "pdl": pdl,
                "pdc": pdc,
                "daily_open": day_open,
                "daily_high": asian_high,
                "daily_low": asian_low,
                "daily_range": asian_high - asian_low,
                "adr_14": adr_14,
                "adr_utilization_pct": round(((asian_high - asian_low) / adr_14) * 100, 1),
                "has_swept_pdh": swept_pdh,
                "has_swept_pdl": swept_pdl
            },
            "weekly_structure": {
                "pwh": max(b["high"] for b in d1_bars[max(0, day_idx - 10) : day_idx - 5]),
                "pwl": min(b["low"] for b in d1_bars[max(0, day_idx - 10) : day_idx - 5]),
                "cwo": cwo,
                "relation_to_weekly_open": "ABOVE_WEEKLY_OPEN" if curr_price_pre_london > cwo else "BELOW_WEEKLY_OPEN"
            },
            "session_ranges": {
                "asian_high": asian_high,
                "asian_low": asian_low,
                "asian_range": asian_high - asian_low
            },
            "draw_on_liquidity": {
                "type": "BUY_SIDE_LIQUIDITY" if curr_price_pre_london > pdc else "SELL_SIDE_LIQUIDITY",
                "target_price": round(pdh if curr_price_pre_london > pdc else pdl, 2),
                "distance_pts": round(abs(curr_price_pre_london - (pdh if curr_price_pre_london > pdc else pdl)), 2)
            },
            "htf_trend": {
                "h1_regime": h1_regime,
                "h1_displacement_3bar": h1_disp
            },
            "smt_divergence": {
                "has_smt": False,
                "type": "NONE"
            }
        }

        off_chart_state = {
            "catalysts": {"session_risk": "LOW", "day_risk": "LOW"},
            "retail_sentiment": {"retail_long_pct": 50.0, "retail_short_pct": 50.0}
        }

        # Run Prediction
        pred = classifier.classify_trend(on_chart_state, off_chart_state)
        day_pred = pred["horizons"]["day"]
        predicted_bias = day_pred["bias"]  # BULLISH (UP), BEARISH (DOWN), CONSOLIDATION (SIDEWAYS)
        confidence = day_pred["confidence"]
        dol_target = day_pred["daily_dol"]["target"]
        invalidation = day_pred["invalidation"]

        # Map to 3-state naming
        if predicted_bias == "BULLISH":
            pred_state = "UP"
        elif predicted_bias == "BEARISH":
            pred_state = "DOWN"
        else:
            pred_state = "SIDEWAYS"

        # Evaluate Actual Day Outcome
        net_delta = day_close - day_open
        delta_pct_adr = abs(net_delta) / adr_14

        # Realized daily state definition:
        # UP: Closed green with displacement (close > open + 0.15 ADR)
        # DOWN: Closed red with displacement (close < open - 0.15 ADR)
        # SIDEWAYS: Closed near open (|close - open| <= 0.15 ADR) OR compressed inside-day range (< 0.65 ADR)
        if net_delta > (0.15 * adr_14):
            actual_state = "UP"
        elif net_delta < -(0.15 * adr_14):
            actual_state = "DOWN"
        else:
            actual_state = "SIDEWAYS"

        # Check DOL hit
        if pred_state == "UP":
            reached_dol = day_high >= dol_target
            hit_invalidation = day_low <= invalidation
            # Exact Directional Hit: Did day close green?
            is_directional_hit = (day_close > day_open)
        elif pred_state == "DOWN":
            reached_dol = day_low <= dol_target
            hit_invalidation = day_high >= invalidation
            # Exact Directional Hit: Did day close red?
            is_directional_hit = (day_close < day_open)
        else:
            reached_dol = (day_range <= 0.75 * adr_14)
            hit_invalidation = (day_range >= 1.25 * adr_14)
            is_directional_hit = (actual_state == "SIDEWAYS")

        # Exact 3-State Match: Did predicted 3-state match actual 3-state?
        is_exact_3state_match = (pred_state == actual_state)

        # Misclassification Severity:
        # Critical Error: Predicted UP but actual was DOWN, or Predicted DOWN but actual was UP
        is_critical_inversion = (pred_state == "UP" and actual_state == "DOWN") or (pred_state == "DOWN" and actual_state == "UP")

        records.append({
            "date": str(day_date),
            "open": day_open,
            "high": day_high,
            "low": day_low,
            "close": day_close,
            "range": round(day_range, 2),
            "adr_14": round(adr_14, 2),
            "pred_state": pred_state,
            "actual_state": actual_state,
            "confidence": confidence,
            "dol_target": dol_target,
            "reached_dol": reached_dol,
            "hit_inval": hit_invalidation,
            "is_directional_hit": is_directional_hit,
            "is_exact_3state_match": is_exact_3state_match,
            "is_critical_inversion": is_critical_inversion
        })

    df = pd.DataFrame(records)
    csv_path = OUTPUT_DIR / "omnitrend_3state_daily_accuracy_ledger.csv"
    df.to_csv(csv_path, index=False)

    total_days = len(df)
    exact_matches = int(df["is_exact_3state_match"].sum())
    directional_hits = int(df["is_directional_hit"].sum())
    dol_reaches = int(df["reached_dol"].sum())
    critical_inversions = int(df["is_critical_inversion"].sum())

    # Filtered by Directional Calls Only (UP & DOWN, ignoring SIDEWAYS)
    trend_calls = df[df["pred_state"].isin(["UP", "DOWN"])]
    trend_total = len(trend_calls)
    trend_dir_hits = int(trend_calls["is_directional_hit"].sum())
    trend_dol_hits = int(trend_calls["reached_dol"].sum())

    # Sideways Calls
    sideways_calls = df[df["pred_state"] == "SIDEWAYS"]
    sideways_total = len(sideways_calls)
    sideways_hits = int(sideways_calls["is_exact_3state_match"].sum())

    summary = {
        "audit_scope": f"OmniTrend Oracle Historical Accuracy Audit ({symbol})",
        "total_trading_days": total_days,
        "date_range": f"{df['date'].iloc[0]} to {df['date'].iloc[-1]}",
        "overall_3state_exact_match_rate": round((exact_matches / total_days) * 100.0, 1),
        "overall_directional_hit_rate": round((directional_hits / total_days) * 100.0, 1),
        "overall_dol_touch_rate": round((dol_reaches / total_days) * 100.0, 1),
        "critical_inversion_rate": round((critical_inversions / total_days) * 100.0, 1),
        "trend_calls_breakdown": {
            "total_trend_calls": trend_total,
            "directional_win_rate": round((trend_dir_hits / max(1, trend_total)) * 100.0, 1),
            "dol_touch_rate": round((trend_dol_hits / max(1, trend_total)) * 100.0, 1),
            "up_calls_count": int(len(df[df["pred_state"] == "UP"])),
            "up_calls_win_rate": round((int(df[(df["pred_state"] == "UP") & (df["is_directional_hit"] == True)].shape[0]) / max(1, len(df[df["pred_state"] == "UP"]))) * 100.0, 1),
            "down_calls_count": int(len(df[df["pred_state"] == "DOWN"])),
            "down_calls_win_rate": round((int(df[(df["pred_state"] == "DOWN") & (df["is_directional_hit"] == True)].shape[0]) / max(1, len(df[df["pred_state"] == "DOWN"]))) * 100.0, 1)
        },
        "sideways_calls_breakdown": {
            "total_sideways_calls": sideways_total,
            "exact_compression_match_rate": round((sideways_hits / max(1, sideways_total)) * 100.0, 1)
        }
    }

    with open(OUTPUT_DIR / "omnitrend_3state_accuracy_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Print Unvarnished Report
    print("\n" + "=" * 85)
    print("📊 OMNITREND ORACLE 3-STATE HISTORICAL ACCURACY BENCHMARK:")
    print("=" * 85)
    print(f"Total Trading Days Audited    : {total_days} Days ({summary['date_range']})")
    print(f"Overall 3-State Exact Match   : {exact_matches}/{total_days} ({summary['overall_3state_exact_match_rate']}%)")
    print(f"Overall Directional Hit Rate  : {directional_hits}/{total_days} ({summary['overall_directional_hit_rate']}%)")
    print(f"Draw on Liquidity (DOL) Touch : {dol_reaches}/{total_days} ({summary['overall_dol_touch_rate']}%)")
    print(f"Critical Inversion Rate (Flop): {critical_inversions}/{total_days} ({summary['critical_inversion_rate']}%)")
    print("-" * 85)
    print("📈 BREAKDOWN BY PREDICTED REGIME:")
    print(f"  • UP Calls       : {summary['trend_calls_breakdown']['up_calls_count']} days | Win Rate: {summary['trend_calls_breakdown']['up_calls_win_rate']}%")
    print(f"  • DOWN Calls     : {summary['trend_calls_breakdown']['down_calls_count']} days | Win Rate: {summary['trend_calls_breakdown']['down_calls_win_rate']}%")
    print(f"  • SIDEWAYS Calls : {summary['sideways_calls_breakdown']['total_sideways_calls']} days | Compression Rate: {summary['sideways_calls_breakdown']['exact_compression_match_rate']}%")
    print("=" * 85)

    return summary


if __name__ == "__main__":
    run_trend_oracle_historical_audit("XAUUSD_o", min_days=250)
