"""
TradingGuard HITL - Confluence Edge Discovery for New York Session
Tests H4 trend alignment, PDH/PDL daily sweeps, SMT, and ADR utilization
to discover high-conviction statistical alpha for the Pre-NY Re-Anchor.
"""

import sys
import datetime
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.audit_pre_ny_reanchoring import load_gold_dataset

sym, d1, h1_bars, m5_bars = load_gold_dataset(min_days=260)
TZ_UTC = datetime.timezone.utc

records = []

for day_idx in range(25, len(d1)):
    curr_d = d1[day_idx]
    prev_d = d1[day_idx - 1]
    prior_days = d1[day_idx - 15 : day_idx]
    day_start_ts = curr_d["time"]

    trs = [max(b["high"] - b["low"], abs(b["high"] - prior_days[i-1]["close"])) for i, b in enumerate(prior_days[1:], 1)]
    adr_14 = float(np.mean(trs)) if trs else 25.0

    pdh = prev_d["high"]
    pdl = prev_d["low"]
    pdc = prev_d["close"]

    # H4 trend
    prior_h1_day = [b for b in h1_bars if b["time"] < day_start_ts][-40:]
    h4_ma20 = float(np.mean([b["close"] for b in prior_h1_day[-20:]]))
    is_htf_bullish = curr_d["open"] > h4_ma20

    today_m5 = [b for b in m5_bars if day_start_ts <= b["time"] < day_start_ts + 86400]
    asian_bars = [b for b in today_m5 if b["time"] < day_start_ts + (6 * 3600)]
    london_bars = [b for b in today_m5 if day_start_ts + (8 * 3600) <= b["time"] < day_start_ts + (12 * 3600)]
    pre_ny_bars = [b for b in today_m5 if b["time"] < day_start_ts + (12 * 3600) + (30 * 60)]
    ny_bars = [b for b in today_m5 if day_start_ts + (13 * 3600) <= b["time"] <= day_start_ts + (20 * 3600)]

    if not asian_bars or not london_bars or not ny_bars:
        continue

    asian_high = max(b["high"] for b in asian_bars)
    asian_low = min(b["low"] for b in asian_bars)

    london_high = max(b["high"] for b in london_bars)
    london_low = min(b["low"] for b in london_bars)
    london_close = london_bars[-1]["close"]
    pre_ny_price = pre_ny_bars[-1]["close"]

    ny_open_p = ny_bars[0]["open"]
    ny_close_p = ny_bars[-1]["close"]
    ny_delta = ny_close_p - ny_open_p
    is_ny_green = ny_close_p > ny_open_p
    is_ny_red = ny_close_p < ny_open_p

    # Sweeps of Previous Day High / Low
    london_swept_pdh = london_high > pdh
    london_swept_pdl = london_low < pdl

    # ADR utilization
    curr_high_pre_ny = max(b["high"] for b in pre_ny_bars)
    curr_low_pre_ny = min(b["low"] for b in pre_ny_bars)
    adr_util_pre_ny = ((curr_high_pre_ny - curr_low_pre_ny) / max(0.1, adr_14)) * 100.0

    # London Session Return
    lon_ret = (london_close - london_bars[0]["open"]) / max(0.1, adr_14)

    records.append({
        "date": str(datetime.datetime.fromtimestamp(day_start_ts, tz=TZ_UTC).date()),
        "is_htf_bullish": is_htf_bullish,
        "london_swept_pdh": london_swept_pdh,
        "london_swept_pdl": london_swept_pdl,
        "london_sfp_pdh": london_swept_pdh and pre_ny_price < pdh,
        "london_sfp_pdl": london_swept_pdl and pre_ny_price > pdl,
        "london_swept_asia_h": london_high > asian_high,
        "london_swept_asia_l": london_low < asian_low,
        "adr_util_pre_ny": adr_util_pre_ny,
        "lon_ret": lon_ret,
        "is_ny_green": is_ny_green,
        "is_ny_red": is_ny_red,
        "ny_delta": ny_delta,
        "adr_14": adr_14
    })

df = pd.DataFrame(records)

print("=" * 85)
print(f"CONFLUENCE ANALYSIS FOR PRE-NY RE-ANCHOR ({len(df)} Days)")
print("=" * 85)

# Hypothesis 1: London SFP of Previous Day Extremes (PDH / PDL)
sfp_pdh = df[df["london_sfp_pdh"] == True]
print(f"\n1. London SFP of PDH (Swept PDH & closed back under PDH) [N={len(sfp_pdh)}]:")
if len(sfp_pdh) > 0:
    print(f"   NY Red (Down)   : {len(sfp_pdh[sfp_pdh['is_ny_red']])} ({len(sfp_pdh[sfp_pdh['is_ny_red']])/len(sfp_pdh)*100:.1f}%)")
    print(f"   NY Green (Up)   : {len(sfp_pdh[sfp_pdh['is_ny_green']])} ({len(sfp_pdh[sfp_pdh['is_ny_green']])/len(sfp_pdh)*100:.1f}%)")

sfp_pdl = df[df["london_sfp_pdl"] == True]
print(f"\n2. London SFP of PDL (Swept PDL & closed back above PDL) [N={len(sfp_pdl)}]:")
if len(sfp_pdl) > 0:
    print(f"   NY Green (Up)   : {len(sfp_pdl[sfp_pdl['is_ny_green']])} ({len(sfp_pdl[sfp_pdl['is_ny_green']])/len(sfp_pdl)*100:.1f}%)")
    print(f"   NY Red (Down)   : {len(sfp_pdl[sfp_pdl['is_ny_red']])} ({len(sfp_pdl[sfp_pdl['is_ny_red']])/len(sfp_pdl)*100:.1f}%)")

# Hypothesis 2: HTF Alignment + London Expansion Continuation
htf_bull_continuation = df[(df["is_htf_bullish"] == True) & (df["lon_ret"] > 0.15) & (df["adr_util_pre_ny"] < 60.0)]
print(f"\n3. Bullish HTF + London Bullish Displacement (lon_ret > 0.15 ADR & ADR util < 60%) [N={len(htf_bull_continuation)}]:")
if len(htf_bull_continuation) > 0:
    print(f"   NY Green (Continuation) : {len(htf_bull_continuation[htf_bull_continuation['is_ny_green']])} ({len(htf_bull_continuation[htf_bull_continuation['is_ny_green']])/len(htf_bull_continuation)*100:.1f}%)")
    print(f"   NY Red (Pullback)       : {len(htf_bull_continuation[htf_bull_continuation['is_ny_red']])} ({len(htf_bull_continuation[htf_bull_continuation['is_ny_red']])/len(htf_bull_continuation)*100:.1f}%)")

htf_bear_continuation = df[(df["is_htf_bullish"] == False) & (df["lon_ret"] < -0.15) & (df["adr_util_pre_ny"] < 60.0)]
print(f"\n4. Bearish HTF + London Bearish Displacement (lon_ret < -0.15 ADR & ADR util < 60%) [N={len(htf_bear_continuation)}]:")
if len(htf_bear_continuation) > 0:
    print(f"   NY Red (Continuation)   : {len(htf_bear_continuation[htf_bear_continuation['is_ny_red']])} ({len(htf_bear_continuation[htf_bear_continuation['is_ny_red']])/len(htf_bear_continuation)*100:.1f}%)")
    print(f"   NY Green (Pullback)     : {len(htf_bear_continuation[htf_bear_continuation['is_ny_green']])} ({len(htf_bear_continuation[htf_bear_continuation['is_ny_green']])/len(htf_bear_continuation)*100:.1f}%)")

# Hypothesis 3: London ADR Exhaustion (util >= 60%)
exhausted = df[df["adr_util_pre_ny"] >= 60.0]
print(f"\n5. ADR Exhaustion at London Close (ADR util >= 60%) [N={len(exhausted)}]:")
if len(exhausted) > 0:
    mean_ny_move = abs(exhausted["ny_delta"]).mean()
    mean_all_move = abs(df["ny_delta"]).mean()
    print(f"   Mean NY Move on Exhausted Days : {mean_ny_move:.2f} pts vs Normal Days : {mean_all_move:.2f} pts")
    # Proportion of days where NY was FLAT or opposite to London
    opp_or_flat = 0
    for _, r in exhausted.iterrows():
        if (r["lon_ret"] > 0 and r["is_ny_red"]) or (r["lon_ret"] < 0 and r["is_ny_green"]) or (abs(r["ny_delta"]) <= 0.10 * r["adr_14"]):
            opp_or_flat += 1
    print(f"   NY Inversion or Range Compression Rate : {opp_or_flat}/{len(exhausted)} ({opp_or_flat/len(exhausted)*100:.1f}%)")
