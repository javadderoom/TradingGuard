"""
TradingGuard HITL - Quantitative Double MSS / ChoCh & Liquidity Sweep Audit
Examines the 2-Month Broker Dataset on Gold (XAUUSD_o, Sep 1 - Nov 4, 2026):
1. Single MSS vs Double MSS / ChoCh
2. With Prior Liquidity Sweep vs Without Sweep (Reversal in open air)
3. Without HTF Filter (Pure LTF) vs With HTF Alignment (1H MSS / DOL)
4. Continuation Rate: How many structure shifts held and continued vs failed into reverse MSS.
"""

import sys
import json
import math
import time
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Tuple, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.session_clock import get_session_times_for_date
from hitl.backtest.mtf_structure import analyze_mtf_state
from hitl.backtest.gold_master_quant_audit import load_mt5_historical_bars, simulate_trade_execution, find_swing_points, get_atr

OUTPUT_DIR = BASE_DIR / "backtest_results" / "double_mss_audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_UTC = datetime.timezone.utc


def audit_double_mss_and_sweeps():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    t_start = time.time()
    print("=" * 85)
    print("🔬 TRADINGGUARD - DOUBLE MSS / CHOCH & LIQUIDITY SWEEP AUDIT")
    print("Instrument: XAUUSD (Gold Standalone) | Horizon: Sep 1 - Nov 4, 2026")
    print("Scope: Single MSS vs Double MSS | With Sweep vs Without Sweep | HTF vs No-HTF")
    print("=" * 85)

    if not mt5.initialize():
        print("❌ Error: MT5 initialization failed.")
        return

    data = load_mt5_historical_bars("XAUUSD_o")
    bars_d1 = data['d1']
    bars_h1 = data['h1']
    bars_m15 = data['m15']
    bars_m5 = data['m5']
    bars_m1 = data['m1']

    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    # Sweep through all M5 bars from Sep 1 to Nov 4 during trading hours
    # Identify every single Market Structure Shift (MSS) on M5:
    # Track:
    # 1. Is it a Single MSS or Double MSS?
    # 2. Was there a prior liquidity sweep (Asian H/L, PDH/PDL, Prominent Swing)?
    # 3. What is the 1H MSS state at the moment of shift?
    # 4. Forward execution outcome (Target: 3.5R, BE: 1.8R, SL: $4.50-$6.50)
    # 5. Did price continue without a reverse MSS, or did a reverse MSS occur first?

    scope_start_ts = int(datetime.datetime(2026, 9, 1, 0, 0, tzinfo=TZ_UTC).timestamp())
    scope_end_ts = int(datetime.datetime(2026, 11, 4, 13, 0, tzinfo=TZ_UTC).timestamp())

    # Filter M5 bars in scope
    m5_indices = [i for i, b in enumerate(bars_m5) if scope_start_ts <= b['time'] <= scope_end_ts]
    print(f"Total M5 bars to scan: {len(m5_indices)}")

    all_shifts = []

    # Keep track of last detected shift to avoid duplicate detections on consecutive bars
    last_shift_time = 0

    for i in m5_indices:
        b_curr = bars_m5[i]
        curr_time = b_curr['time']
        curr_dt = b_curr['dt']

        # Enforce prime institutional hours (London Open 07:00 UTC to NY close 16:00 UTC)
        # Avoid low-volume dead zone hours (18:00 - 06:00 UTC)
        if curr_dt.hour < 7 or curr_dt.hour > 16:
            continue

        # Look back 40 M5 bars (~3.3 hours) for swing points
        hist_window = bars_m5[max(0, i - 40):i + 1]
        if len(hist_window) < 15:
            continue

        sh_list, sl_list = find_swing_points(hist_window, window=2)
        if len(sh_list) < 2 or len(sl_list) < 2:
            continue

        # Look for Bullish Structure Shift:
        # Prior structure had lower highs: sh_list[-2] vs sh_list[-1]
        # Current bar decisively closes above the last swing high
        c = b_curr['close']
        last_sh = sh_list[-1]['price']
        penult_sh = sh_list[-2]['price']
        last_sl = sl_list[-1]['price']
        penult_sl = sl_list[-2]['price']

        is_bullish_mss = False
        is_double_bullish = False
        bullish_entry = 0.0
        bullish_sl = 0.0

        is_bearish_mss = False
        is_double_bearish = False
        bearish_entry = 0.0
        bearish_sl = 0.0

        # Check Bullish MSS:
        # Bar closes above last swing high with a full candle body (close > open)
        if c > last_sh and b_curr['close'] > b_curr['open'] and (c - last_sh) >= 0.50:
            # Check displacement from lowest low
            trough_low = min(b['low'] for b in hist_window[-10:])
            disp = c - trough_low
            if disp >= 4.0:  # Valid displacement
                is_bullish_mss = True
                bullish_entry = last_sh
                bullish_sl = trough_low - 1.50
                # Double MSS check:
                # Did this move ALSO break the penultimate swing high (penult_sh)?
                # OR did price already break a minor swing high, form a higher low, and now break the 2nd swing high?
                if c > penult_sh or (last_sl > penult_sl and len(sh_list) >= 3):
                    is_double_bullish = True

        # Check Bearish MSS:
        if c < last_sl and b_curr['close'] < b_curr['open'] and (last_sl - c) >= 0.50:
            crest_high = max(b['high'] for b in hist_window[-10:])
            disp = crest_high - c
            if disp >= 4.0:
                is_bearish_mss = True
                bearish_entry = last_sl
                bearish_sl = crest_high + 1.50
                if c < penult_sl or (last_sh < penult_sh and len(sl_list) >= 3):
                    is_double_bearish = True

        if not (is_bullish_mss or is_bearish_mss):
            continue

        # Prevent duplicate shifts within 30 minutes
        if (curr_time - last_shift_time) < 1800:
            continue

        direction = "LONG" if is_bullish_mss else "SHORT"
        is_double = is_double_bullish if is_bullish_mss else is_double_bearish
        entry_p = bullish_entry if is_bullish_mss else bearish_entry
        sl_p = bullish_sl if is_bullish_mss else bearish_sl

        # Calibrate SL bracket ($3.50 to $8.00)
        risk_dist = abs(entry_p - sl_p)
        if risk_dist < 3.50:
            sl_p = (entry_p - 3.50) if direction == "LONG" else (entry_p + 3.50)
        elif risk_dist > 8.00:
            sl_p = (entry_p - 8.00) if direction == "LONG" else (entry_p + 8.00)

        last_shift_time = curr_time

        # --- LIQUIDITY SWEEP CHECK ---
        # Did the move immediately prior to this shift sweep a significant level?
        # Check Asian High/Low, PDH/PDL, or previous prominent fractal swing
        hist_d1 = [b for b in bars_d1 if b['time'] < curr_time]
        hist_h1 = [b for b in bars_h1 if b['time'] < curr_time]

        pdh = hist_d1[-1]['high'] if hist_d1 else None
        pdl = hist_d1[-1]['low'] if hist_d1 else None

        # Asian High/Low today
        day_date = curr_dt.date()
        asian_bars = [b for b in bars_m5 if b['dt'].date() == day_date and b['dt'].hour < 7]
        asian_high = max(b['high'] for b in asian_bars) if asian_bars else None
        asian_low = min(b['low'] for b in asian_bars) if asian_bars else None

        has_sweep = False
        sweep_desc = "None"

        # Check recent 12 bars prior to displacement
        pre_impulse_bars = hist_window[-12:]
        pre_low = min(b['low'] for b in pre_impulse_bars)
        pre_high = max(b['high'] for b in pre_impulse_bars)

        if direction == "LONG":
            # Bullish shift: Did the low sweep Asian Low, PDL, or prior prominent low?
            if asian_low and (pre_low <= asian_low <= pre_low + 2.0):
                has_sweep = True
                sweep_desc = "Asian_Low_Sweep"
            elif pdl and (pre_low <= pdl <= pre_low + 2.5):
                has_sweep = True
                sweep_desc = "PDL_Sweep"
            elif len(sl_list) >= 3 and pre_low < sl_list[-3]['price']:
                has_sweep = True
                sweep_desc = "Prior_Swing_Low_Sweep"
        else:
            # Bearish shift: Did the high sweep Asian High, PDH, or prior prominent high?
            if asian_high and (pre_high >= asian_high >= pre_high - 2.0):
                has_sweep = True
                sweep_desc = "Asian_High_Sweep"
            elif pdh and (pre_high >= pdh >= pre_high - 2.5):
                has_sweep = True
                sweep_desc = "PDH_Sweep"
            elif len(sh_list) >= 3 and pre_high > sh_list[-3]['price']:
                has_sweep = True
                sweep_desc = "Prior_Swing_High_Sweep"

        # --- HTF ALIGNMENT CHECK ---
        mtf_state = analyze_mtf_state(bars_1d=hist_d1, bars_1h=hist_h1, bars_5m=hist_window, symbol="XAUUSD")
        h1_state = mtf_state.get('h1_state', 'NEUTRAL')
        is_htf_aligned = (direction == "LONG" and 'BULLISH' in h1_state) or (direction == "SHORT" and 'BEARISH' in h1_state)

        # --- FORWARD M1 EXECUTION SIMULATION ---
        m1_idx = m1_time_map.get(curr_time)
        if m1_idx is None:
            cands = [idx for idx, b in enumerate(bars_m1) if b['time'] >= curr_time]
            if not cands:
                continue
            m1_idx = cands[0]

        forward_m1 = bars_m1[m1_idx:m1_idx + 720]
        if len(forward_m1) < 60:
            continue

        # Simulate execution with optimal parameters: Target 3.5R, BE 1.8R
        sim_res = simulate_trade_execution(
            entry_price=entry_p,
            sl_price=sl_p,
            direction=direction,
            forward_m1=forward_m1,
            target_rr=3.5,
            be_rr=1.8,
            spread_usd=0.20
        )

        # --- STRUCTURAL CONTINUATION TRACKING ---
        # Did price continue in the shift direction to reach >= 3.0R without printing an opposing structure break?
        # Check forward M5 bars (next 36 bars = 3 hours) for a reverse MSS
        fwd_m5 = bars_m5[i + 1:i + 37]
        reverse_mss_occurred = False
        continuation_reached = (sim_res['mfe_r'] >= 3.0)

        if fwd_m5 and len(fwd_m5) >= 5:
            if direction == "LONG":
                # Reverse MSS if price breaks below the invalidation trough
                rev_break = any(b['close'] < (sl_p + 1.50) for b in fwd_m5)
                if rev_break:
                    reverse_mss_occurred = True
            else:
                rev_break = any(b['close'] > (sl_p - 1.50) for b in fwd_m5)
                if rev_break:
                    reverse_mss_occurred = True

        shift_record = {
            'timestamp': curr_dt.strftime("%Y-%m-%d %H:%M"),
            'direction': direction,
            'is_double_mss': is_double,
            'mss_type': "DOUBLE_MSS" if is_double else "SINGLE_MSS",
            'has_sweep': has_sweep,
            'sweep_desc': sweep_desc,
            'is_htf_aligned': is_htf_aligned,
            'h1_state': h1_state,
            'entry': round(entry_p, 2),
            'sl': round(sl_p, 2),
            'risk_usd': round(abs(entry_p - sl_p), 2),
            'sim_status': sim_res['status'],
            'net_r': sim_res['net_r'],
            'mae_r': sim_res['mae_r'],
            'mfe_r': sim_res['mfe_r'],
            'continuation_held': continuation_reached and not reverse_mss_occurred,
            'reverse_mss_occurred': reverse_mss_occurred
        }
        all_shifts.append(shift_record)

    print(f"\n✅ Total Distinct Structure Shifts Identified: {len(all_shifts)}")

    # --- COMPILING THE QUANTITATIVE STUDY MATRIX ---
    def _evaluate_subset(records: List[Dict[str, Any]], name: str):
        total = len(records)
        filled = [r for r in records if r['sim_status'] in ('WIN', 'LOSS', 'BREAKEVEN', 'WIN_PARTIAL')]
        n_fill = len(filled)
        if n_fill == 0:
            return {'name': name, 'total': total, 'filled': 0, 'wins': 0, 'losses': 0, 'be': 0, 'win_rate': 0.0, 'net_r': 0.0, 'pf': 0.0, 'cont_rate': 0.0}

        wins = [r for r in filled if r['sim_status'] == 'WIN']
        losses = [r for r in filled if r['sim_status'] == 'LOSS']
        bes = [r for r in filled if r['sim_status'] == 'BREAKEVEN']

        n_w = len(wins)
        n_l = len(losses)
        n_be = len(bes)

        gross_w = n_w * 3.5
        gross_l = float(n_l)
        net_r = gross_w - gross_l
        pf = round(gross_w / gross_l, 2) if gross_l > 0 else (99.0 if gross_w > 0 else 0.0)
        wr = round((n_w / n_fill) * 100, 1)

        # Continuation rate: how many reached target / held structure without reverse MSS
        cont_count = sum(1 for r in filled if r['continuation_held'])
        cont_rate = round((cont_count / n_fill) * 100, 1)

        # Failed structure count: how many suffered a reverse MSS
        failed_count = sum(1 for r in filled if r['reverse_mss_occurred'])
        failed_rate = round((failed_count / n_fill) * 100, 1)

        return {
            'name': name,
            'total_setups': total,
            'filled': n_fill,
            'fill_rate': round(n_fill / total * 100, 1) if total > 0 else 0,
            'wins': n_w,
            'losses': n_l,
            'be': n_be,
            'win_rate': wr,
            'net_r': round(net_r, 1),
            'profit_factor': pf,
            'expectancy_r': round(net_r / n_fill, 2),
            'continuation_held_count': cont_count,
            'continuation_rate': cont_rate,
            'reverse_mss_count': failed_count,
            'reverse_mss_rate': failed_rate
        }

    # 1. Single MSS vs Double MSS (Without HTF filter)
    single_no_htf = _evaluate_subset([r for r in all_shifts if not r['is_double_mss']], "Single MSS (No HTF Filter)")
    double_no_htf = _evaluate_subset([r for r in all_shifts if r['is_double_mss']], "Double MSS (No HTF Filter)")

    # 2. Single MSS vs Double MSS (WITH HTF filter)
    single_with_htf = _evaluate_subset([r for r in all_shifts if not r['is_double_mss'] and r['is_htf_aligned']], "Single MSS (WITH HTF Filter)")
    double_with_htf = _evaluate_subset([r for r in all_shifts if r['is_double_mss'] and r['is_htf_aligned']], "Double MSS (WITH HTF Filter)")

    # 3. Liquidity Sweep vs No-Sweep Comparison
    sweep_present = _evaluate_subset([r for r in all_shifts if r['has_sweep']], "With Prior Liquidity Sweep")
    sweep_absent = _evaluate_subset([r for r in all_shifts if not r['has_sweep']], "Without Liquidity Sweep (Open Air)")

    # 4. The Institutional Holy Grail: Double MSS + Sweep + HTF Aligned
    holy_grail = _evaluate_subset([r for r in all_shifts if r['is_double_mss'] and r['has_sweep'] and r['is_htf_aligned']], "Double MSS + Sweep + HTF Aligned")

    results_summary = {
        'single_no_htf': single_no_htf,
        'double_no_htf': double_no_htf,
        'single_with_htf': single_with_htf,
        'double_with_htf': double_with_htf,
        'sweep_present': sweep_present,
        'sweep_absent': sweep_absent,
        'holy_grail': holy_grail,
        'all_shifts': all_shifts
    }

    json_file = OUTPUT_DIR / "double_mss_quant_results.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(results_summary, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Saved full audit ledgers to {json_file}")

    print("\n" + "=" * 95)
    print("📊 EMPIRICAL RESEARCH RESULTS: DOUBLE MSS / CHOCH & SWEEP AUDIT")
    print("=" * 95)
    headers = f"{'Configuration':<35} {'Fills':<7} {'Wins':<5} {'Losses':<7} {'BE':<4} {'Win Rate':<10} {'Net PnL':<11} {'PF':<6} {'Continuation %':<14}"
    print(headers)
    print("-" * 95)
    for res in [single_no_htf, double_no_htf, single_with_htf, double_with_htf, sweep_absent, sweep_present, holy_grail]:
        print(f"{res['name']:<35} {res['filled']:<7} {res['wins']:<5} {res['losses']:<7} {res['be']:<4} {res['win_rate']:<10.1f}% {res['net_r']:<+11.1f}R {res['profit_factor']:<6.2f} {res['continuation_rate']:<14.1f}%")
    print("=" * 95)


if __name__ == "__main__":
    audit_double_mss_and_sweeps()
