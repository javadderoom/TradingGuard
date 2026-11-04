"""
TradingGuard HITL - Spring 2026 Double MSS & Nested Double MSS Continuous Audit
Period: March 1, 2026 - April 30, 2026 (Spring Season & Dynamic DST)
Instrument: XAUUSD_o (Gold Standalone)
Evaluates every single 5M bar across Spring institutional hours (08:00 - 17:00 UTC / dynamic London to NY close):
1. Single MSS vs Double MSS Continuation & Failure Rates
2. Nested Double MSS (SETUP-ARCH-011) Performance
3. Macro Sweep Hierarchy in Spring
"""

import sys
import json
import time
import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.gold_spring_2month_audit import load_spring_bars_and_resample_m1, find_swing_points, simulate_trade_execution, get_atr
from hitl.backtest.mtf_structure import analyze_mtf_state

OUTPUT_DIR = BASE_DIR / "backtest_results" / "gold_spring_nested_double_mss"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_UTC = datetime.timezone.utc


def audit_spring_double_and_nested_mss():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 85)
    print("🌱 TRADINGGUARD - SPRING 2026 DOUBLE MSS & NESTED DOUBLE MSS CONTINUOUS AUDIT")
    print("Period: March 1, 2026 - April 30, 2026 (Dynamic DST Schedule: London to NY)")
    print("=" * 85)

    if not mt5.initialize():
        print("❌ Error: MT5 initialization failed.")
        return

    data = load_spring_bars_and_resample_m1("XAUUSD_o")
    bars_d1 = data['d1']
    bars_h1 = data['h1']
    bars_m5 = data['m5']
    bars_m1 = data['m1']

    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    scope_start_ts = int(datetime.datetime(2026, 3, 1, 0, 0, tzinfo=TZ_UTC).timestamp())
    scope_end_ts = int(datetime.datetime(2026, 4, 30, 23, 59, tzinfo=TZ_UTC).timestamp())

    m5_indices = [i for i, b in enumerate(bars_m5) if scope_start_ts <= b['time'] <= scope_end_ts]
    print(f"Total M5 bars to scan across Spring: {len(m5_indices)}")

    nested_patterns = []
    last_nested_time = 0

    all_shifts = []
    last_shift_time = 0

    for i in m5_indices:
        b_curr = bars_m5[i]
        curr_time = b_curr['time']
        curr_dt = b_curr['dt']

        # Spring institutional hours: 07:00/08:00 UTC to 17:00 UTC
        if curr_dt.hour < 7 or curr_dt.hour > 17:
            continue

        hist_window = bars_m5[max(0, i - 60):i + 1]
        if len(hist_window) < 30:
            continue

        sh_list, sl_list = find_swing_points(hist_window, window=2)
        if len(sh_list) < 3 or len(sl_list) < 3:
            continue

        c = b_curr['close']

        m1_idx = m1_time_map.get(curr_time)
        if m1_idx is None:
            cands = [idx for idx, b in enumerate(bars_m1) if b['time'] >= curr_time]
            if not cands: continue
            m1_idx = cands[0]

        forward_m1 = bars_m1[m1_idx:m1_idx + 720]
        if len(forward_m1) < 120:
            continue

        hist_d1 = [b for b in bars_d1 if b['time'] < curr_time]
        hist_h1 = [b for b in bars_h1 if b['time'] < curr_time]
        mtf_info = analyze_mtf_state(bars_1d=hist_d1, bars_1h=hist_h1, bars_5m=hist_window, symbol="XAUUSD")
        h1_state = mtf_info.get('h1_state', 'NEUTRAL')

        pdh = hist_d1[-1]['high'] if hist_d1 else 0.0
        pdl = hist_d1[-1]['low'] if hist_d1 else 0.0

        day_date = curr_dt.date()
        asian_bars = [b for b in hist_window if b['dt'].date() == day_date and b['dt'].hour < 7]
        asian_high = max(b['high'] for b in asian_bars) if asian_bars else 0.0
        asian_low = min(b['low'] for b in asian_bars) if asian_bars else 0.0

        # Part A: Nested Double MSS
        h3 = sh_list[-1]
        if c > h3['price'] and (curr_time - last_nested_time >= 1800):
            bars_after_h3 = [b for b in hist_window if b['time'] >= h3['time']]
            if len(bars_after_h3) >= 2:
                l4_price = min(b['low'] for b in bars_after_h3)
                prior_h = [h for h in sh_list if h['time'] < h3['time']]
                prior_l = [l for l in sl_list if l['time'] < h3['time']]

                if len(prior_h) >= 2 and len(prior_l) >= 2:
                    h2 = prior_h[-1]
                    h1 = prior_h[-2]
                    l3 = prior_l[-1]
                    l2 = prior_l[-2]

                    has_macro_sweep = (l2['price'] < prior_l[0]['price']) or (pdl > 0 and l2['price'] < pdl) or (asian_low > 0 and l2['price'] < asian_low)
                    sweep_source = "None"
                    if pdl > 0 and l2['price'] < pdl: sweep_source = "PDL"
                    elif asian_low > 0 and l2['price'] < asian_low: sweep_source = "Asian_Low"
                    elif l2['price'] < prior_l[0]['price']: sweep_source = "Swing_Low"

                    if (h2['price'] > h1['price'] + 1.0) and (h3['price'] < h2['price'] - 1.0) and (l3['price'] > l2['price']) and (l4_price > l2['price']):
                        entry = h3['price']
                        sl = l4_price - 1.50
                        dist = abs(entry - sl)
                        if dist < 3.50: sl = entry - 3.50
                        elif dist > 8.00: sl = entry - 8.00

                        nested_patterns.append({
                            'time': curr_dt.strftime("%Y-%m-%d %H:%M"),
                            'direction': 'LONG',
                            'entry': round(entry, 2),
                            'sl': round(sl, 2),
                            'has_sweep': has_macro_sweep,
                            'sweep_source': sweep_source,
                            'h1_aligned': (h1_state == "BULLISH_MSS"),
                            'forward_m1': forward_m1
                        })
                        last_nested_time = curr_time

        l3_item = sl_list[-1]
        if c < l3_item['price'] and (curr_time - last_nested_time >= 1800):
            bars_after_l3 = [b for b in hist_window if b['time'] >= l3_item['time']]
            if len(bars_after_l3) >= 2:
                h4_price = max(b['high'] for b in bars_after_l3)
                prior_h = [h for h in sh_list if h['time'] < l3_item['time']]
                prior_l = [l for l in sl_list if l['time'] < l3_item['time']]

                if len(prior_h) >= 2 and len(prior_l) >= 2:
                    l2 = prior_l[-1]
                    l1 = prior_l[-2]
                    h3_val = prior_h[-1]
                    h2 = prior_h[-2]

                    has_macro_sweep = (h2['price'] > prior_h[0]['price']) or (pdh > 0 and h2['price'] > pdh) or (asian_high > 0 and h2['price'] > asian_high)
                    sweep_source = "None"
                    if pdh > 0 and h2['price'] > pdh: sweep_source = "PDH"
                    elif asian_high > 0 and h2['price'] > asian_high: sweep_source = "Asian_High"
                    elif h2['price'] > prior_h[0]['price']: sweep_source = "Swing_High"

                    if (l2['price'] < l1['price'] - 1.0) and (l3_item['price'] > l2['price'] + 1.0) and (h3_val['price'] < h2['price']) and (h4_price < h2['price']):
                        entry = l3_item['price']
                        sl = h4_price + 1.50
                        dist = abs(entry - sl)
                        if dist < 3.50: sl = entry + 3.50
                        elif dist > 8.00: sl = entry + 8.00

                        nested_patterns.append({
                            'time': curr_dt.strftime("%Y-%m-%d %H:%M"),
                            'direction': 'SHORT',
                            'entry': round(entry, 2),
                            'sl': round(sl, 2),
                            'has_sweep': has_macro_sweep,
                            'sweep_source': sweep_source,
                            'h1_aligned': (h1_state == "BEARISH_MSS"),
                            'forward_m1': forward_m1
                        })
                        last_nested_time = curr_time

        # Part B: Double MSS vs Single MSS
        if curr_time - last_shift_time >= 900:
            if len(sh_list) >= 2:
                sh_last = sh_list[-1]['price']
                sh_prev = sh_list[-2]['price']
                if c > sh_last and hist_window[-2]['close'] <= sh_last:
                    entry = sh_last
                    sl = sl_list[-1]['price'] - 1.50
                    dist = abs(entry - sl)
                    if 3.50 <= dist <= 12.0:
                        is_double = (c > sh_prev) or (len(sl_list) >= 2 and sl_list[-1]['price'] > sl_list[-2]['price'])
                        has_sw = (pdl > 0 and sl_list[-1]['price'] < pdl) or (asian_low > 0 and sl_list[-1]['price'] < asian_low)
                        sw_type = "PDL" if (pdl > 0 and sl_list[-1]['price'] < pdl) else ("Asian_Low" if (asian_low > 0 and sl_list[-1]['price'] < asian_low) else "Minor_Low")

                        all_shifts.append({
                            'time': curr_dt.strftime("%Y-%m-%d %H:%M"),
                            'direction': 'LONG',
                            'entry': round(entry, 2),
                            'sl': round(sl, 2),
                            'is_double': is_double,
                            'has_sweep': has_sw,
                            'sweep_type': sw_type if has_sw else "Open_Air",
                            'h1_aligned': (h1_state == "BULLISH_MSS"),
                            'forward_m1': forward_m1
                        })
                        last_shift_time = curr_time

            if len(sl_list) >= 2:
                sl_last = sl_list[-1]['price']
                sl_prev = sl_list[-2]['price']
                if c < sl_last and hist_window[-2]['close'] >= sl_last:
                    entry = sl_last
                    sl = sh_list[-1]['price'] + 1.50
                    dist = abs(entry - sl)
                    if 3.50 <= dist <= 12.0:
                        is_double = (c < sl_prev) or (len(sh_list) >= 2 and sh_list[-1]['price'] < sh_list[-2]['price'])
                        has_sw = (pdh > 0 and sh_list[-1]['price'] > pdh) or (asian_high > 0 and sh_list[-1]['price'] > asian_high)
                        sw_type = "PDH" if (pdh > 0 and sh_list[-1]['price'] > pdh) else ("Asian_High" if (asian_high > 0 and sh_list[-1]['price'] > asian_high) else "Minor_High")

                        all_shifts.append({
                            'time': curr_dt.strftime("%Y-%m-%d %H:%M"),
                            'direction': 'SHORT',
                            'entry': round(entry, 2),
                            'sl': round(sl, 2),
                            'is_double': is_double,
                            'has_sweep': has_sw,
                            'sweep_type': sw_type if has_sw else "Open_Air",
                            'h1_aligned': (h1_state == "BEARISH_MSS"),
                            'forward_m1': forward_m1
                        })
                        last_shift_time = curr_time

    # Nested Double MSS Results
    print(f"\n📊 Total Nested Double MSS in Spring: {len(nested_patterns)}")
    nested_res = []
    for p in nested_patterns:
        sim = simulate_trade_execution(
            entry_price=p['entry'], sl_price=p['sl'], direction=p['direction'], forward_m1=p['forward_m1'],
            target_rr=3.5, be_rr=1.8, spread_usd=0.15
        )
        row = {k: v for k, v in p.items() if k != 'forward_m1'}
        row.update(sim)
        nested_res.append(row)

    df_nest = pd.DataFrame(nested_res)
    df_nest.to_csv(OUTPUT_DIR / "spring_nested_double_mss_trades.csv", index=False)

    def stats(df_sub):
        n = len(df_sub)
        if n == 0: return {'fills': 0, 'wins': 0, 'losses': 0, 'be': 0, 'wr': 0.0, 'net_r': 0.0, 'pf': 0.0}
        w = len(df_sub[df_sub['status'] == 'WIN'])
        l = len(df_sub[df_sub['status'] == 'LOSS'])
        b = len(df_sub[df_sub['status'] == 'BREAKEVEN'])
        net_r = df_sub['net_r'].sum()
        gw = df_sub[df_sub['net_r'] > 0]['net_r'].sum()
        gl = abs(df_sub[df_sub['net_r'] < 0]['net_r'].sum())
        pf = round(gw / max(0.001, gl), 2)
        wr = round((w / n) * 100.0, 1)
        return {'fills': n, 'wins': w, 'losses': l, 'be': b, 'wr': wr, 'net_r': round(net_r, 2), 'pf': pf}

    df_nest_fills = df_nest[df_nest['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
    st_nest_all = stats(df_nest_fills)
    st_nest_sw = stats(df_nest_fills[df_nest_fills['has_sweep'] == True])
    st_nest_nosw = stats(df_nest_fills[df_nest_fills['has_sweep'] == False])

    print("\n" + "=" * 90)
    print("🌱 NESTED DOUBLE MSS (SETUP-ARCH-011) SPRING 2026 PERFORMANCE:")
    print("=" * 90)
    print(f"All Nested Setups:            {st_nest_all['fills']} Fills | {st_nest_all['wins']}W - {st_nest_all['losses']}L - {st_nest_all['be']}BE | WR: {st_nest_all['wr']}% | Net: {st_nest_all['net_r']:+0.1f}R | PF: {st_nest_all['pf']}")
    print(f"WITH Prior Liquidity Sweep:   {st_nest_sw['fills']} Fills | {st_nest_sw['wins']}W - {st_nest_sw['losses']}L - {st_nest_sw['be']}BE | WR: {st_nest_sw['wr']}% | Net: {st_nest_sw['net_r']:+0.1f}R | PF: {st_nest_sw['pf']}")
    print(f"WITHOUT Sweep (Open Air):     {st_nest_nosw['fills']} Fills | {st_nest_nosw['wins']}W - {st_nest_nosw['losses']}L - {st_nest_nosw['be']}BE | WR: {st_nest_nosw['wr']}% | Net: {st_nest_nosw['net_r']:+0.1f}R | PF: {st_nest_nosw['pf']}")
    print("=" * 90)

    # General Double MSS Results
    print(f"\n📊 Total Shifts in Spring: {len(all_shifts)}")
    shift_res = []
    for s in all_shifts:
        sim = simulate_trade_execution(
            entry_price=s['entry'], sl_price=s['sl'], direction=s['direction'], forward_m1=s['forward_m1'],
            target_rr=3.5, be_rr=1.8, spread_usd=0.15
        )
        row = {k: v for k, v in s.items() if k != 'forward_m1'}
        row.update(sim)
        shift_res.append(row)

    df_sh = pd.DataFrame(shift_res)
    df_sh.to_csv(OUTPUT_DIR / "spring_all_shifts_trades.csv", index=False)

    df_sh_fills = df_sh[df_sh['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
    st_single = stats(df_sh_fills[df_sh_fills['is_double'] == False])
    st_double = stats(df_sh_fills[df_sh_fills['is_double'] == True])

    print("\n" + "=" * 90)
    print("🌱 DOUBLE MSS VS SINGLE MSS SPRING 2026 PERFORMANCE:")
    print("=" * 90)
    print(f"Single MSS:   {st_single['fills']} Fills | {st_single['wins']}W - {st_single['losses']}L - {st_single['be']}BE | WR: {st_single['wr']}% | Net: {st_single['net_r']:+0.1f}R | PF: {st_single['pf']}")
    print(f"DOUBLE MSS:   {st_double['fills']} Fills | {st_double['wins']}W - {st_double['losses']}L - {st_double['be']}BE | WR: {st_double['wr']}% | Net: {st_double['net_r']:+0.1f}R | PF: {st_double['pf']}")
    print("=" * 90)


if __name__ == "__main__":
    audit_spring_double_and_nested_mss()
