"""
TradingGuard HITL - Dual-Session Pre-NY Re-Anchoring Quantitative Benchmark
Evaluates the empirical accuracy of dynamically re-anchoring the OmniTrend Oracle
at Pre-NY (12:30 UTC / 16:00 Tehran) using confirmed London session high/low microstructure
vs static Pre-London predictions across 260 days of authentic MT5 Gold data.
Strictly zero lookahead bias, unvarnished reporting.
"""

import sys
import os
import json
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5

TZ_UTC = datetime.timezone.utc
OUTPUT_DIR = BASE_DIR / "backtest_results" / "trend_oracle_audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_gold_dataset(min_days: int = 260):
    if not mt5.initialize():
        raise RuntimeError("MetaTrader 5 initialization failed!")

    candidate_syms = ["XAUUSD_o", "XAUUSD", "GOLD"]
    sym = None
    for s in candidate_syms:
        if mt5.symbol_info(s):
            sym = s
            break

    if not sym:
        mt5.shutdown()
        raise ValueError("Gold symbol not found in MT5!")

    rates_d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, min_days + 40)
    rates_h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, (min_days + 40) * 24)
    rates_m5 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, (min_days + 40) * 288)

    mt5.shutdown()

    if rates_d1 is None or len(rates_d1) < min_days:
        raise ValueError(f"Insufficient D1 rates: {len(rates_d1) if rates_d1 is not None else 0}")

    d1 = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for r in rates_d1]
    h1 = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for r in rates_h1]
    m5 = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for r in rates_m5]

    return sym, d1, h1, m5


def run_dual_session_benchmark(d1_bars, h1_bars, m5_bars):
    """
    Evaluates New York Session directional outcomes under:
      A. Static Pre-London Prediction (07:00 UTC)
      B. Dynamic Pre-NY Re-Anchored Prediction (12:30 UTC)
    """
    records = []

    for day_idx in range(25, len(d1_bars)):
        curr_d = d1_bars[day_idx]
        prev_d = d1_bars[day_idx - 1]
        prior_days = d1_bars[day_idx - 15 : day_idx]

        day_date = datetime.datetime.fromtimestamp(curr_d["time"], tz=TZ_UTC).date()
        day_open = curr_d["open"]
        day_high = curr_d["high"]
        day_low = curr_d["low"]
        day_close = curr_d["close"]
        day_start_ts = curr_d["time"]

        # ADR-14
        trs = [max(b["high"] - b["low"], abs(b["high"] - prior_days[i-1]["close"])) for i, b in enumerate(prior_days[1:], 1)]
        adr_14 = float(np.mean(trs)) if trs else 25.0

        pdh = prev_d["high"]
        pdl = prev_d["low"]
        pdc = prev_d["close"]

        # Today's bars
        today_m5 = [b for b in m5_bars if day_start_ts <= b["time"] < day_start_ts + 86400]
        if not today_m5:
            continue

        # Asian Session: 00:00 to 06:00 UTC
        asian_bars = [b for b in today_m5 if b["time"] < day_start_ts + (6 * 3600)]
        # London Session: 08:00 to 12:00 UTC
        london_bars = [b for b in today_m5 if day_start_ts + (8 * 3600) <= b["time"] < day_start_ts + (12 * 3600)]
        # Pre-NY Cutoff: 12:30 UTC
        pre_ny_bars = [b for b in today_m5 if b["time"] < day_start_ts + (12 * 3600) + (30 * 60)]
        # New York Session: 13:00 to 20:00 UTC (The evaluation window)
        ny_bars = [b for b in today_m5 if day_start_ts + (13 * 3600) <= b["time"] <= day_start_ts + (20 * 3600)]

        if not asian_bars or not london_bars or not ny_bars:
            continue

        asian_high = max(b["high"] for b in asian_bars)
        asian_low = min(b["low"] for b in asian_bars)

        london_high = max(b["high"] for b in london_bars)
        london_low = min(b["low"] for b in london_bars)
        london_close = london_bars[-1]["close"]

        pre_london_price = asian_bars[-1]["close"]
        pre_ny_price = pre_ny_bars[-1]["close"]

        # Realized New York Session Facts
        ny_open_price = ny_bars[0]["open"]
        ny_high = max(b["high"] for b in ny_bars)
        ny_low = min(b["low"] for b in ny_bars)
        ny_close = ny_bars[-1]["close"]
        ny_delta = ny_close - ny_open_price
        is_ny_green = ny_close > ny_open_price
        is_ny_red = ny_close < ny_open_price

        # --- MODEL A: STATIC PRE-LONDON FORECAST (07:00 UTC) ---
        # Evaluate state up to 07:00 UTC
        score_a = 0.0
        swept_pdh_asia = asian_high > pdh
        swept_pdl_asia = asian_low < pdl

        if swept_pdh_asia and pre_london_price < pdh:
            score_a -= 2.5
        elif swept_pdl_asia and pre_london_price > pdl:
            score_a += 2.5

        if pre_london_price > pdc + (0.05 * adr_14):
            score_a += 0.5
        elif pre_london_price < pdc - (0.05 * adr_14):
            score_a -= 0.5

        # Prior H1 structure
        prior_h1 = [b for b in h1_bars if b["time"] < day_start_ts][-20:]
        h1_ma20 = float(np.mean([b["close"] for b in prior_h1])) if prior_h1 else day_open
        if pre_london_price > h1_ma20:
            score_a += 1.8
        else:
            score_a -= 1.8

        if score_a >= 1.5:
            pred_a = "UP"
            dol_a = pdh
        elif score_a <= -1.5:
            pred_a = "DOWN"
            dol_a = pdl
        else:
            pred_a = "SIDEWAYS"
            dol_a = pdc

        # --- MODEL B: DYNAMIC PRE-NY RE-ANCHORED FORECAST (12:30 UTC) ---
        # Incorporates London session facts:
        # Did London sweep Asian High / Low?
        london_swept_asian_high = london_high > asian_high
        london_swept_asian_low = london_low < asian_low

        # ADR utilized up to Pre-NY
        curr_day_high_pre_ny = max(b["high"] for b in pre_ny_bars)
        curr_day_low_pre_ny = min(b["low"] for b in pre_ny_bars)
        adr_util_pre_ny = ((curr_day_high_pre_ny - curr_day_low_pre_ny) / max(0.1, adr_14)) * 100.0

        score_b = 0.0

        # Feature 1: London SFP (Judas Swing) of Asian Extreme
        # If London swept Asian high and closed back below Asian high -> Bearish London Judas
        if london_swept_asian_high and pre_ny_price < asian_high:
            score_b -= 2.8
            dol_b = min(asian_low, pdl)
        # If London swept Asian low and closed back above Asian low -> Bullish London Judas
        elif london_swept_asian_low and pre_ny_price > asian_low:
            score_b += 2.8
            dol_b = max(asian_high, pdh)
        # Feature 2: Daily Extreme Sweeps by London
        elif curr_day_high_pre_ny > pdh and pre_ny_price < pdh:
            score_b -= 2.5
            dol_b = pdl
        elif curr_day_low_pre_ny < pdl and pre_ny_price > pdl:
            score_b += 2.5
            dol_b = pdh
        # Feature 3: London Unilateral Displacement
        elif london_close > asian_high + 2.0 and pre_ny_price > asian_high:
            score_b += 2.0
            dol_b = pdh
        elif london_close < asian_low - 2.0 and pre_ny_price < asian_low:
            score_b -= 2.0
            dol_b = pdl
        else:
            # Trapped inside Asian range
            if pre_ny_price > pdc:
                score_b += 0.5
            else:
                score_b -= 0.5
            dol_b = pdc

        # Feature 4: ADR Exhaustion Check
        # If London already utilized > 60% of ADR, NY is prone to chop / mean reversion
        if adr_util_pre_ny >= 60.0:
            pred_b = "SIDEWAYS"
            dol_b = pdc
        elif score_b >= 1.5:
            pred_b = "UP"
        elif score_b <= -1.5:
            pred_b = "DOWN"
        else:
            pred_b = "SIDEWAYS"

        # --- EVALUATION ON NEW YORK SESSION REALIZED MOVE ---
        # 1. Did Model A hit NY directional move?
        hit_a = (pred_a == "UP" and is_ny_green) or (pred_a == "DOWN" and is_ny_red) or (pred_a == "SIDEWAYS" and abs(ny_delta) <= 0.15 * adr_14)
        inv_a = (pred_a == "UP" and is_ny_red) or (pred_a == "DOWN" and is_ny_green)
        dol_touch_a = (pred_a == "UP" and ny_high >= dol_a) or (pred_a == "DOWN" and ny_low <= dol_a) or (pred_a == "SIDEWAYS" and (ny_high - ny_low) <= 0.75 * adr_14)

        # 2. Did Model B hit NY directional move?
        hit_b = (pred_b == "UP" and is_ny_green) or (pred_b == "DOWN" and is_ny_red) or (pred_b == "SIDEWAYS" and abs(ny_delta) <= 0.15 * adr_14)
        inv_b = (pred_b == "UP" and is_ny_red) or (pred_b == "DOWN" and is_ny_green)
        dol_touch_b = (pred_b == "UP" and ny_high >= dol_b) or (pred_b == "DOWN" and ny_low <= dol_b) or (pred_b == "SIDEWAYS" and (ny_high - ny_low) <= 0.75 * adr_14)

        records.append({
            "date": str(day_date),
            "pred_a": pred_a,
            "pred_b": pred_b,
            "is_ny_green": is_ny_green,
            "is_ny_red": is_ny_red,
            "ny_delta": round(ny_delta, 2),
            "hit_a": hit_a,
            "inv_a": inv_a,
            "dol_touch_a": dol_touch_a,
            "hit_b": hit_b,
            "inv_b": inv_b,
            "dol_touch_b": dol_touch_b,
            "adr_util_pre_ny": round(adr_util_pre_ny, 1)
        })

    df = pd.DataFrame(records)
    n = len(df)

    # Metrics for Model A
    trend_a = df[df["pred_a"].isin(["UP", "DOWN"])]
    n_trend_a = len(trend_a)
    dir_hits_a = int(trend_a["hit_a"].sum()) if n_trend_a > 0 else 0
    inv_a_cnt = int(trend_a["inv_a"].sum()) if n_trend_a > 0 else 0
    dol_a_cnt = int(trend_a["dol_touch_a"].sum()) if n_trend_a > 0 else 0

    # Metrics for Model B
    trend_b = df[df["pred_b"].isin(["UP", "DOWN"])]
    n_trend_b = len(trend_b)
    dir_hits_b = int(trend_b["hit_b"].sum()) if n_trend_b > 0 else 0
    inv_b_cnt = int(trend_b["inv_b"].sum()) if n_trend_b > 0 else 0
    dol_b_cnt = int(trend_b["dol_touch_b"].sum()) if n_trend_b > 0 else 0

    print("=" * 90)
    print("📊 DUAL-SESSION RE-ANCHORING BENCHMARK: NEW YORK SESSION FORECAST ACCURACY")
    print(f"   Evaluated across {n} Consecutive Trading Days on Gold (XAUUSD)")
    print("=" * 90)
    print(f"Metric                               | Model A: Static Pre-London | Model B: Dynamic Pre-NY Re-Anchor | Delta")
    print("-" * 90)
    print(f"Total Trading Days Audited           | {n:<26} | {n:<33} | —")
    print(f"NY Trend Calls (UP / DOWN)           | {n_trend_a} ({n_trend_a/n*100:.1f}%)                | {n_trend_b} ({n_trend_b/n*100:.1f}%)                  | {n_trend_b - n_trend_a:+d} calls")
    print(f"NY Directional Win Rate (Hits)       | {dir_hits_a}/{n_trend_a} ({dir_hits_a/max(1,n_trend_a)*100:.1f}%)          | {dir_hits_b}/{n_trend_b} ({dir_hits_b/max(1,n_trend_b)*100:.1f}%)            | {dir_hits_b/max(1,n_trend_b)*100 - dir_hits_a/max(1,n_trend_a)*100:+5.1f}%")
    print(f"NY Critical Inversions (Total Flops) | {inv_a_cnt}/{n_trend_a} ({inv_a_cnt/max(1,n_trend_a)*100:.1f}%)          | {inv_b_cnt}/{n_trend_b} ({inv_b_cnt/max(1,n_trend_b)*100:.1f}%)            | {inv_b_cnt/max(1,n_trend_b)*100 - inv_a_cnt/max(1,n_trend_a)*100:+5.1f}%")
    print(f"NY Draw on Liquidity (DOL) Touch     | {dol_a_cnt}/{n_trend_a} ({dol_a_cnt/max(1,n_trend_a)*100:.1f}%)          | {dol_b_cnt}/{n_trend_b} ({dol_b_cnt/max(1,n_trend_b)*100:.1f}%)            | {dol_b_cnt/max(1,n_trend_b)*100 - dol_a_cnt/max(1,n_trend_a)*100:+5.1f}%")
    print("-" * 90)

    # Save summary
    summary = {
        "days": n,
        "model_a_pre_london": {
            "trend_calls": n_trend_a,
            "win_rate": round(dir_hits_a / max(1, n_trend_a) * 100, 1),
            "inversion_rate": round(inv_a_cnt / max(1, n_trend_a) * 100, 1),
            "dol_rate": round(dol_a_cnt / max(1, n_trend_a) * 100, 1)
        },
        "model_b_pre_ny_reanchor": {
            "trend_calls": n_trend_b,
            "win_rate": round(dir_hits_b / max(1, n_trend_b) * 100, 1),
            "inversion_rate": round(inv_b_cnt / max(1, n_trend_b) * 100, 1),
            "dol_rate": round(dol_b_cnt / max(1, n_trend_b) * 100, 1)
        }
    }
    with open(OUTPUT_DIR / "pre_ny_reanchoring_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return df, summary


if __name__ == "__main__":
    sym, d1, h1, m5 = load_gold_dataset(min_days=260)
    print(f"Loaded {len(d1)} D1 bars, {len(h1)} H1 bars, and {len(m5)} M5 bars for {sym}.")
    df, summary = run_dual_session_benchmark(d1, h1, m5)
