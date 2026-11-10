"""
TradingGuard HITL - Diagnostic Analysis of London to NY Session Dynamics
Analyzes the statistical transition matrix from London microstructure to New York directional expansion on Gold.
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

sym, d1, h1, m5_bars = load_gold_dataset(min_days=260)

records = []
TZ_UTC = datetime.timezone.utc

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

    today_m5 = [b for b in m5_bars if day_start_ts <= b["time"] < day_start_ts + 86400]
    asian_bars = [b for b in today_m5 if b["time"] < day_start_ts + (6 * 3600)]
    london_bars = [b for b in today_m5 if day_start_ts + (8 * 3600) <= b["time"] < day_start_ts + (12 * 3600)]
    pre_ny_bars = [b for b in today_m5 if b["time"] < day_start_ts + (12 * 3600) + (30 * 60)]
    ny_bars = [b for b in today_m5 if day_start_ts + (13 * 3600) <= b["time"] <= day_start_ts + (20 * 3600)]

    if not asian_bars or not london_bars or not ny_bars:
        continue

    asian_high = max(b["high"] for b in asian_bars)
    asian_low = min(b["low"] for b in asian_bars)
    asian_open = asian_bars[0]["open"]

    london_high = max(b["high"] for b in london_bars)
    london_low = min(b["low"] for b in london_bars)
    london_open = london_bars[0]["open"]
    london_close = london_bars[-1]["close"]
    london_delta = london_close - london_open

    pre_ny_p = pre_ny_bars[-1]["close"]
    ny_open_p = ny_bars[0]["open"]
    ny_close_p = ny_bars[-1]["close"]
    ny_delta = ny_close_p - ny_open_p

    # Classify London Session Archetype
    swept_asia_h = london_high > asian_high
    swept_asia_l = london_low < asian_low

    if swept_asia_h and not swept_asia_l:
        if london_close < asian_high:
            london_arch = "LONDON_SFP_HIGH"  # Swept high and rejected
        else:
            london_arch = "LONDON_BULLISH_BREAKOUT"  # Broke out and held above
    elif swept_asia_l and not swept_asia_h:
        if london_close > asian_low:
            london_arch = "LONDON_SFP_LOW"  # Swept low and rejected
        else:
            london_arch = "LONDON_BEARISH_BREAKOUT"  # Broke out and held below
    elif swept_asia_h and swept_asia_l:
        london_arch = "LONDON_DUAL_SWEEP_WHIPSAW"
    else:
        london_arch = "LONDON_INSIDE_ASIA"

    # NY Session Direction
    if ny_delta > 0.10 * adr_14:
        ny_dir = "GREEN"
    elif ny_delta < -0.10 * adr_14:
        ny_dir = "RED"
    else:
        ny_dir = "FLAT"

    records.append({
        "date": str(datetime.datetime.fromtimestamp(day_start_ts, tz=TZ_UTC).date()),
        "london_arch": london_arch,
        "london_delta": round(london_delta, 2),
        "ny_dir": ny_dir,
        "ny_delta": round(ny_delta, 2),
        "adr_14": round(adr_14, 2)
    })

df = pd.DataFrame(records)

print("=" * 80)
print(f"DIAGNOSTIC: LONDON ARCHETYPE vs NEW YORK DIRECTIONAL DISPLACEMENT ({len(df)} Days)")
print("=" * 80)

for arch in df["london_arch"].unique():
    sub = df[df["london_arch"] == arch]
    n_arch = len(sub)
    n_green = len(sub[sub["ny_dir"] == "GREEN"])
    n_red = len(sub[sub["ny_dir"] == "RED"])
    n_flat = len(sub[sub["ny_dir"] == "FLAT"])
    print(f"\nArchetype: {arch:<26} (Total: {n_arch} days | {n_arch/len(df)*100:.1f}%)")
    print(f"  • NY Green (Up)   : {n_green:>2} ({n_green/n_arch*100:.1f}%)")
    print(f"  • NY Red (Down)   : {n_red:>2} ({n_red/n_arch*100:.1f}%)")
    print(f"  • NY Flat (Chop)  : {n_flat:>2} ({n_flat/n_arch*100:.1f}%)")
