"""
TradingGuard HITL - Nested Double MSS (Macro MSS + Pullback MSS) Quantitative Audit
Tests the user's exact uploaded chart pattern on Gold (XAUUSD_o, Sep 1 - Nov 4, 2026):
Pattern Anatomy:
1. Macro Sweep & 1st Shift: Price sweeps L1 to L2, then displaces above H1 (1st Orange Line) to H2.
2. Complex Retracement: Price drops H2 -> L3 -> H3 -> L4 (sub-downtrend).
3. Internal 2nd Shift: Price breaks above H3 (2nd Orange Line) to H4.
4. Entry & Execution: Entry on retest at L5 (Retest of H3 / FVG). SL anchored below L4.
"""

import sys
import json
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

OUTPUT_DIR = BASE_DIR / "backtest_results" / "nested_double_mss_audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_UTC = datetime.timezone.utc


def audit_nested_double_mss():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 85)
    print("🔬 TRADINGGUARD - NESTED DOUBLE MSS (MACRO + PULLBACK MSS) AUDIT")
    print("Exact Pattern: L1->H1->L2(Sweep)->H2(1st MSS)->L3->H3->L4->H4(2nd MSS)->L5(Entry)")
    print("Instrument: XAUUSD (Gold Standalone) | Horizon: Sep 1 - Nov 4, 2026")
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

    scope_start_ts = int(datetime.datetime(2026, 9, 1, 0, 0, tzinfo=TZ_UTC).timestamp())
    scope_end_ts = int(datetime.datetime(2026, 11, 4, 13, 0, tzinfo=TZ_UTC).timestamp())

    m5_indices = [i for i, b in enumerate(bars_m5) if scope_start_ts <= b['time'] <= scope_end_ts]
    print(f"Total M5 bars to scan: {len(m5_indices)}")

    detected_patterns = []
    last_pattern_time = 0

    for i in m5_indices:
        b_curr = bars_m5[i]
        curr_time = b_curr['time']
        curr_dt = b_curr['dt']

        # Scan across prime institutional hours (07:00 UTC to 16:00 UTC)
        if curr_dt.hour < 7 or curr_dt.hour > 16:
            continue

        # Need at least 50 bars lookback (~4 hours) to identify the full nested pattern
        hist_window = bars_m5[max(0, i - 60):i + 1]
        if len(hist_window) < 30:
            continue

        sh_list, sl_list = find_swing_points(hist_window, window=2)
        if len(sh_list) < 3 or len(sl_list) < 3:
            continue

        # Check Bullish Nested Pattern:
        # We need:
        # L1, H1, L2 (Sweep of L1), H2 (Breaks H1: 1st MSS),
        # L3, H3 (Internal High), L4 (Internal Low), H4 (Breaks H3: 2nd MSS)
        # Current bar b_curr is breaking H3 or just broke H3!
        c = b_curr['close']

        is_bullish_nested = False
        is_bearish_nested = False

        bullish_entry = 0.0
        bullish_sl = 0.0
        bullish_sweep = False
        bullish_sweep_desc = "None"

        bearish_entry = 0.0
        bearish_sl = 0.0
        bearish_sweep = False
        bearish_sweep_desc = "None"

        # --- BULLISH DETECTION ---
        # Find if the most recent swing high (H3) was broken by current bar
        recent_h = sh_list[-1]
        h3_price = recent_h['price']
        h3_idx = recent_h['idx']

        # Did current bar close above H3?
        if c > h3_price and b_curr['close'] > b_curr['open']:
            # Find L4: lowest low between H3 and current bar
            bars_after_h3 = hist_window[h3_idx:]
            if len(bars_after_h3) >= 2:
                l4_price = min(b['low'] for b in bars_after_h3)
                # Look back before H3 to find H2, L3, H1, L2, L1
                prior_sh = [s for s in sh_list if s['idx'] < h3_idx]
                prior_sl = [s for s in sl_list if s['idx'] < h3_idx]

                if len(prior_sh) >= 2 and len(prior_sl) >= 2:
                    h2_cand = prior_sh[-1]
                    h1_cand = prior_sh[-2]
                    l3_cand = prior_sl[-1]
                    l2_cand = prior_sl[-2]

                    # Pattern conditions:
                    # 1. H2 > H1 (Macro 1st MSS happened!)
                    # 2. H3 < H2 (Internal pullback formed lower peak)
                    # 3. L3 > l2_cand['price'] (Pullback is holding above macro low L2)
                    # 4. l4_price > l2_cand['price'] (Internal low L4 also held above L2)
                    if (h2_cand['price'] > h1_cand['price'] + 1.0) and \
                       (h3_price < h2_cand['price'] - 1.0) and \
                       (l3_cand['price'] > l2_cand['price']) and \
                       (l4_price > l2_cand['price']):
                        
                        is_bullish_nested = True
                        bullish_entry = h3_price  # Entry on retest of the 2nd orange line
                        bullish_sl = l4_price - 1.50 # SL pinned below L4

                        # Check if L2 swept L1 or a macro level
                        if len(prior_sl) >= 3 and l2_cand['price'] < prior_sl[-3]['price']:
                            bullish_sweep = True
                            bullish_sweep_desc = "L2_Swept_L1_Swing"

        # --- BEARISH DETECTION ---
        # Inverse: L2 sweeps L1 (higher), drops below L1 (1st MSS to L2). Pullback L3 -> H3 -> L4 (higher low) -> drops below L3 (2nd MSS to L4).
        recent_l = sl_list[-1]
        l3_price = recent_l['price']
        l3_idx = recent_l['idx']

        if c < l3_price and b_curr['close'] < b_curr['open']:
            bars_after_l3 = hist_window[l3_idx:]
            if len(bars_after_l3) >= 2:
                h4_price = max(b['high'] for b in bars_after_l3)
                prior_sh = [s for s in sh_list if s['idx'] < l3_idx]
                prior_sl = [s for s in sl_list if s['idx'] < l3_idx]

                if len(prior_sh) >= 2 and len(prior_sl) >= 2:
                    l2_cand = prior_sl[-1]
                    l1_cand = prior_sl[-2]
                    h3_cand = prior_sh[-1]
                    h2_cand = prior_sh[-2]

                    # 1. L2 < L1 (Macro 1st MSS down)
                    # 2. L3 > L2 (Internal pullback higher trough)
                    # 3. H3 < h2_cand['price'] (Lower peak)
                    # 4. h4_price < h2_cand['price'] (H4 held below macro high H2)
                    if (l2_cand['price'] < l1_cand['price'] - 1.0) and \
                       (l3_price > l2_cand['price'] + 1.0) and \
                       (h3_cand['price'] < h2_cand['price']) and \
                       (h4_price < h2_cand['price']):

                        is_bearish_nested = True
                        bearish_entry = l3_price
                        bearish_sl = h4_price + 1.50

                        if len(prior_sh) >= 3 and h2_cand['price'] > prior_sh[-3]['price']:
                            bearish_sweep = True
                            bearish_sweep_desc = "H2_Swept_H1_Swing"

        if not (is_bullish_nested or is_bearish_nested):
            continue

        if (curr_time - last_pattern_time) < 2400:  # 40-minute debounce
            continue

        direction = "LONG" if is_bullish_nested else "SHORT"
        entry_p = bullish_entry if is_bullish_nested else bearish_entry
        sl_p = bullish_sl if is_bullish_nested else bearish_sl
        has_sweep = bullish_sweep if is_bullish_nested else bearish_sweep
        sweep_desc = bullish_sweep_desc if is_bullish_nested else bearish_sweep_desc

        # Check macro PDH/PDL sweeps
        hist_d1 = [b for b in bars_d1 if b['time'] < curr_time]
        hist_h1 = [b for b in bars_h1 if b['time'] < curr_time]

        pdh = hist_d1[-1]['high'] if hist_d1 else None
        pdl = hist_d1[-1]['low'] if hist_d1 else None

        # Check if macro sweep occurred at the origin
        if direction == "LONG" and pdl and abs(sl_p - pdl) <= 3.0:
            has_sweep = True
            sweep_desc = "PDL_Macro_Sweep"
        elif direction == "SHORT" and pdh and abs(sl_p - pdh) <= 3.0:
            has_sweep = True
            sweep_desc = "PDH_Macro_Sweep"

        # Check HTF alignment (1H MSS)
        mtf_state = analyze_mtf_state(bars_1d=hist_d1, bars_1h=hist_h1, bars_5m=hist_window, symbol="XAUUSD")
        h1_state = mtf_state.get('h1_state', 'NEUTRAL')
        is_htf_aligned = (direction == "LONG" and 'BULLISH' in h1_state) or (direction == "SHORT" and 'BEARISH' in h1_state)

        # Enforce SL bracket ($3.50 to $8.00)
        risk_dist = abs(entry_p - sl_p)
        if risk_dist < 3.50:
            sl_p = (entry_p - 3.50) if direction == "LONG" else (entry_p + 3.50)
        elif risk_dist > 8.00:
            sl_p = (entry_p - 8.00) if direction == "LONG" else (entry_p + 8.00)

        last_pattern_time = curr_time

        # Forward M1 Simulation (Target: 3.5R, BE: 1.8R)
        m1_idx = m1_time_map.get(curr_time)
        if m1_idx is None:
            cands = [idx for idx, b in enumerate(bars_m1) if b['time'] >= curr_time]
            if not cands:
                continue
            m1_idx = cands[0]

        forward_m1 = bars_m1[m1_idx:m1_idx + 720]
        if len(forward_m1) < 60:
            continue

        sim_res = simulate_trade_execution(
            entry_price=entry_p,
            sl_price=sl_p,
            direction=direction,
            forward_m1=forward_m1,
            target_rr=3.5,
            be_rr=1.8,
            spread_usd=0.20
        )

        # Structural continuation: did it reach >= 3.0R without reverse MSS?
        fwd_m5 = bars_m5[i + 1:i + 37]
        reverse_mss = False
        if fwd_m5:
            if direction == "LONG":
                reverse_mss = any(b['close'] < sl_p for b in fwd_m5)
            else:
                reverse_mss = any(b['close'] > sl_p for b in fwd_m5)

        continuation_held = (sim_res['mfe_r'] >= 3.0) and not reverse_mss

        record = {
            'timestamp': curr_dt.strftime("%Y-%m-%d %H:%M"),
            'direction': direction,
            'has_sweep': has_sweep,
            'sweep_desc': sweep_desc,
            'is_htf_aligned': is_htf_aligned,
            'h1_state': h1_state,
            'entry': round(entry_p, 2),
            'sl': round(sl_p, 2),
            'risk_usd': round(abs(entry_p - sl_p), 2),
            'status': sim_res['status'],
            'net_r': sim_res['net_r'],
            'mae_r': sim_res['mae_r'],
            'mfe_r': sim_res['mfe_r'],
            'continuation_held': continuation_held,
            'reverse_mss_occurred': reverse_mss
        }
        detected_patterns.append(record)

    print(f"\n✅ Total Nested Double MSS Setups Detected: {len(detected_patterns)}")

    # Helper function to compile stats
    def _eval(recs: List[Dict[str, Any]], label: str):
        tot = len(recs)
        filled = [r for r in recs if r['status'] in ('WIN', 'LOSS', 'BREAKEVEN', 'WIN_PARTIAL')]
        n_fill = len(filled)
        if n_fill == 0:
            return {'label': label, 'total': tot, 'filled': 0, 'wins': 0, 'losses': 0, 'be': 0, 'wr': 0.0, 'net_r': 0.0, 'pf': 0.0, 'cont_rate': 0.0}

        w = sum(1 for r in filled if r['status'] == 'WIN')
        l = sum(1 for r in filled if r['status'] == 'LOSS')
        be = sum(1 for r in filled if r['status'] == 'BREAKEVEN')
        net = (w * 3.5) - l
        pf = (w * 3.5) / l if l > 0 else (99.0 if w > 0 else 0.0)
        wr = (w / n_fill) * 100
        cont = sum(1 for r in filled if r['continuation_held']) / n_fill * 100
        rev = sum(1 for r in filled if r['reverse_mss_occurred']) / n_fill * 100

        return {
            'label': label,
            'total': tot,
            'filled': n_fill,
            'fill_rate': round(n_fill / tot * 100, 1) if tot > 0 else 0,
            'wins': w,
            'losses': l,
            'be': be,
            'wr': round(wr, 1),
            'net_r': round(net, 1),
            'pf': round(pf, 2),
            'cont_rate': round(cont, 1),
            'rev_rate': round(rev, 1)
        }

    # 1. Version 1: Without HTF Filter (All nested double MSS)
    v1_no_htf = _eval(detected_patterns, "Nested Double MSS (No HTF Filter)")

    # 2. Version 2: With HTF Filter (1H MSS Aligned)
    v2_with_htf = _eval([r for r in detected_patterns if r['is_htf_aligned']], "Nested Double MSS (WITH 1H Filter)")

    # 3. Sweep Breakdown
    v3_with_sweep = _eval([r for r in detected_patterns if r['has_sweep']], "Nested Double MSS (With Sweep)")
    v3_no_sweep = _eval([r for r in detected_patterns if not r['has_sweep']], "Nested Double MSS (Without Sweep)")

    # 4. Holy Grail (Nested Double MSS + Sweep + HTF Aligned)
    v4_holy_grail = _eval([r for r in detected_patterns if r['has_sweep'] and r['is_htf_aligned']], "Nested Double MSS + Sweep + HTF")

    report = {
        'v1_no_htf': v1_no_htf,
        'v2_with_htf': v2_with_htf,
        'v3_with_sweep': v3_with_sweep,
        'v3_no_sweep': v3_no_sweep,
        'v4_holy_grail': v4_holy_grail,
        'patterns': detected_patterns
    }

    res_file = OUTPUT_DIR / "nested_double_mss_results.json"
    with open(res_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 95)
    print("🏆 FINAL RESULTS: USER'S EXACT NESTED DOUBLE MSS PATTERN AUDIT")
    print("=" * 95)
    headers = f"{'Configuration':<35} {'Fills':<7} {'Wins':<5} {'Losses':<7} {'BE':<4} {'Win Rate':<10} {'Net PnL':<11} {'PF':<6} {'Continuation %':<14}"
    print(headers)
    print("-" * 95)
    for res in [v1_no_htf, v2_with_htf, v3_no_sweep, v3_with_sweep, v4_holy_grail]:
        print(f"{res['label']:<35} {res['filled']:<7} {res['wins']:<5} {res['losses']:<7} {res['be']:<4} {res['wr']:<10.1f}% {res['net_r']:<+11.1f}R {res['pf']:<6.2f} {res['cont_rate']:<14.1f}%")
    print("=" * 95)


if __name__ == "__main__":
    audit_nested_double_mss()
