"""
TradingGuard HITL - Testing Pre-NY ADR Exhaustion Filter
Tests whether using the Pre-NY anchor strictly as an ADR Exhaustion Guardian
(converting directional expansion to Sideways/Boundary Mode when ADR >= 60%)
enhances or degrades New York session performance.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.audit_pre_ny_reanchoring import load_gold_dataset

sym, d1, h1_bars, m5_bars = load_gold_dataset(min_days=260)

records = []
import datetime
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
    pre_ny_bars = [b for b in today_m5 if b["time"] < day_start_ts + (12 * 3600) + (30 * 60)]
    ny_bars = [b for b in today_m5 if day_start_ts + (13 * 3600) <= b["time"] <= day_start_ts + (20 * 3600)]

    if not asian_bars or not pre_ny_bars or not ny_bars:
        continue

    asian_high = max(b["high"] for b in asian_bars)
    asian_low = min(b["low"] for b in asian_bars)
    pre_lon_p = asian_bars[-1]["close"]

    prior_h1 = [b for b in h1_bars if b["time"] < day_start_ts][-20:]
    h1_ma20 = float(np.mean([b["close"] for b in prior_h1])) if prior_h1 else curr_d["open"]

    # Model A: Baseline Daily Score
    score_a = 0.0
    if asian_high > pdh and pre_lon_p < pdh: score_a -= 2.5
    elif asian_low < pdl and pre_lon_p > pdl: score_a += 2.5
    if pre_lon_p > pdc + (0.05 * adr_14): score_a += 0.5
    elif pre_lon_p < pdc - (0.05 * adr_14): score_a -= 0.5
    if pre_lon_p > h1_ma20: score_a += 1.8
    else: score_a -= 1.8

    pred_a = "UP" if score_a >= 1.5 else ("DOWN" if score_a <= -1.5 else "SIDEWAYS")

    # Model D: Pre-NY ADR Exhaustion Filter
    # Keeps Model A direction UNLESS ADR before NY has already been exhausted (>= 60%)
    curr_day_h = max(b["high"] for b in pre_ny_bars)
    curr_day_l = min(b["low"] for b in pre_ny_bars)
    adr_util = ((curr_day_h - curr_day_l) / max(0.1, adr_14)) * 100.0

    if adr_util >= 60.0:
        pred_d = "SIDEWAYS"  # Overridden to Sideways/Equilibrium rotation
    else:
        pred_d = pred_a  # Preserves daily macro anchor

    records.append({
        "date": str(datetime.datetime.fromtimestamp(day_start_ts, tz=TZ_UTC).date()),
        "pred_a": pred_a,
        "pred_d": pred_d,
        "adr_util": adr_util
    })

df = pd.DataFrame(records)
map_a = {row['date']: row['pred_a'] for _, row in df.iterrows()}
map_d = {row['date']: row['pred_d'] for _, row in df.iterrows()}

gold_ledger_path = BASE_DIR / "backtest_results" / "gold_annual_4season_master_synthesis" / "annual_master_all_trades_ledger.csv"
trades_df = pd.read_csv(gold_ledger_path)
trades_df = trades_df[trades_df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])].copy()
trades_df['date'] = trades_df['date'].astype(str)
rat_ny = trades_df[(trades_df['session'].str.contains('NY', case=False, na=False)) & (trades_df['archetype_id'].isin(['SETUP-ARCH-001', 'SETUP-ARCH-003', 'SETUP-ARCH-010', 'SETUP-ARCH-014']))].copy()
all_ny = trades_df[trades_df['session'].str.contains('NY', case=False, na=False)].copy()

def simulate_trade_pnl(trade, tp_r, be_trigger_r):
    mfe = float(trade['mfe_r'])
    mae = float(trade['mae_r'])
    if mae >= 1.0 and mfe < be_trigger_r:
        return -1.0, "LOSS"
    if mfe >= tp_r:
        if trade['status'] == 'WIN' or trade['status'] == 'BREAKEVEN' or mae < 1.0:
            return tp_r, "WIN"
        else:
            return -1.0, "LOSS"
    if mfe >= be_trigger_r:
        return 0.0, "BREAKEVEN"
    return -1.0, "LOSS"

def eval_trades(trades_sub, pred_map, name):
    results = []
    for _, t in trades_sub.iterrows():
        d = t['date']
        t_dir = t['direction']
        pred = pred_map.get(d, "SIDEWAYS")
        is_aligned = (t_dir == 'LONG' and pred == 'UP') or (t_dir == 'SHORT' and pred == 'DOWN')
        is_counter = (t_dir == 'LONG' and pred == 'DOWN') or (t_dir == 'SHORT' and pred == 'UP')
        if is_aligned: tp, be = 3.5, 1.5
        elif is_counter: tp, be = 1.5, 1.0
        else: tp, be = 3.5, 1.0
        r, s = simulate_trade_pnl(t, tp, be)
        results.append((r, s))
    w = sum(1 for r, s in results if s == 'WIN')
    l = sum(1 for r, s in results if s == 'LOSS')
    b = sum(1 for r, s in results if s == 'BREAKEVEN')
    net_r = sum(r for r, s in results)
    gw = sum(r for r, s in results if r > 0)
    gl = abs(sum(r for r, s in results if r < 0))
    pf = round(gw / max(0.01, gl), 2)
    print(f"{name:<48} : {len(results)} Fills | {w}W-{l}L-{b}BE | WR: {w/len(results)*100:.1f}% | Net: {net_r:>+6.2f}R | PF: {pf:>4.2f}")

print("=" * 85)
print("TESTING PRE-NY ADR EXHAUSTION GUARDIAN MODEL")
print("=" * 85)
print("\n--- RATIFIED NY TRADES ---")
eval_trades(rat_ny, map_a, "Model A: Static Pre-London Forecast")
eval_trades(rat_ny, map_d, "Model D: Pre-NY ADR Exhaustion Guardian (util>=60%)")

print("\n--- ALL NY TRADES (264 FILLS) ---")
eval_trades(all_ny, map_a, "Model A: Static Pre-London Forecast")
eval_trades(all_ny, map_d, "Model D: Pre-NY ADR Exhaustion Guardian (util>=60%)")
