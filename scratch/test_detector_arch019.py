import pandas as pd
import numpy as np
import datetime
from hitl.backtest.session_clock import get_session_times_for_date

def detect_gold_double_sweep_reversal(
    bars_5m,
    bars_1h=None,
    bars_1d=None,
    symbol="XAUUSD"
):
    if "XAU" not in symbol.upper():
        return False, "NONE", 0.0, 0.0, ""
    if not bars_5m or len(bars_5m) < 25:
        return False, "NONE", 0.0, 0.0, ""

    offset_sec = 7200
    try:
        from hitl.backtest.chart_renderer import get_broker_utc_offset_seconds
        offset_sec = get_broker_utc_offset_seconds()
    except Exception:
        pass

    cur = bars_5m[-1]
    sig_utc = int(cur['time']) - offset_sec
    sig_dt = datetime.datetime.fromtimestamp(sig_utc, tz=datetime.timezone.utc)
    stimes = get_session_times_for_date(sig_dt.date())
    lon_utc = int(stimes["london"]["utc_time"].timestamp())
    ny_utc = int(stimes["new_york"]["utc_time"].timestamp())
    nyse_utc = int(stimes["nyse_open"]["utc_time"].timestamp())

    # Active during London Open through late NY (up to NYSE + 120m)
    if not (lon_utc <= sig_utc <= nyse_utc + 7200):
        return False, "NONE", 0.0, 0.0, ""

    # Current bar must form or immediately confirm an opposing 5M FVG
    # 5M FVG check at current bar (index -1) or prior bar (-2)
    min_gap = 0.30
    sl_buffer = 1.20
    max_risk = 10.00
    min_risk = 1.50

    # 1. Check Bearish Double Sweep Setup
    # Current bar or bar[-2] is the 3rd bar of a bearish FVG
    # Bearish FVG: bars[-3]['low'] > bars[-1]['high'] + min_gap
    # and displacement candle bars[-2]['close'] < bars[-2]['open']
    has_bear_fvg = False
    fvg_top = 0.0
    fvg_bottom = 0.0
    fvg_mid = 0.0
    
    if len(bars_5m) >= 4:
        # Check current bar as bar 3
        b1, b2, b3 = bars_5m[-3], bars_5m[-2], bars_5m[-1]
        if b1['low'] > b3['high'] + min_gap and b2['close'] < b2['open']:
            has_bear_fvg = True
            fvg_top = b1['low']
            fvg_bottom = b3['high']
            fvg_mid = (fvg_top + fvg_bottom) / 2.0
        else:
            # Check bar[-2] as bar 3 (retest candle is bar[-1])
            b0, b1, b2 = bars_5m[-4], bars_5m[-3], bars_5m[-2]
            if b0['low'] > b2['high'] + min_gap and b1['close'] < b1['open']:
                has_bear_fvg = True
                fvg_top = b0['low']
                fvg_bottom = b2['high']
                fvg_mid = (fvg_top + fvg_bottom) / 2.0

    if has_bear_fvg:
        # Scan backward from -2 to -8 to find H2 (the peak that swept H1)
        # Look for local peak H2 in the last 7 bars
        h2_candidates = []
        for idx in range(len(bars_5m) - 2, max(len(bars_5m) - 8, 5), -1):
            bar = bars_5m[idx]
            # Must be a crest relative to immediately adjacent bars or top bar of cluster
            if bar['high'] >= bars_5m[idx - 1]['high']:
                rng = bar['high'] - bar['low']
                u_wick = bar['high'] - max(bar['open'], bar['close'])
                w_ratio = u_wick / rng if rng > 0 else 0
                h2_candidates.append((idx, bar['high'], w_ratio, bar['close']))

        for h2_idx, h2_price, h2_w_ratio, h2_close in h2_candidates:
            # Ensure no bar after h2 exceeded h2
            if any(b['high'] > h2_price for b in bars_5m[h2_idx + 1:]):
                continue

            # Now find H1 (the prior peak that H2 swept) located 3 to 25 bars before H2
            h1_found = False
            for h1_idx in range(h2_idx - 2, max(h2_idx - 25, 3), -1):
                h1_bar = bars_5m[h1_idx]
                if h1_bar['high'] < h2_price:
                    # Intermediate pullback between H1 and H2
                    mid_lows = [b['low'] for b in bars_5m[h1_idx:h2_idx]]
                    l_mid = min(mid_lows)
                    pullback_depth = h1_bar['high'] - l_mid
                    if pullback_depth >= 0.80:
                        # Rejection on H2: Upper wick >= 25% OR close < H1
                        if h2_w_ratio >= 0.25 or h2_close <= h1_bar['high'] + 0.30:
                            # Verify H1 itself swept an earlier high H0 (at least 5 bars before H1)
                            earlier_highs = [b['high'] for b in bars_5m[max(0, h1_idx - 35):h1_idx - 4]]
                            if earlier_highs and max(earlier_highs) < h1_bar['high'] and (h1_bar['high'] - max(earlier_highs)) >= 0.20:
                                # H1 swept H0, H2 swept H1, FVG formed!
                                sl = round(h2_price + sl_buffer, 2)
                                entry = round(fvg_mid, 2)
                                risk = sl - entry
                                if risk > max_risk:
                                    entry = round(sl - max_risk, 2)
                                    risk = max_risk
                                if risk >= min_risk:
                                    desc = f"Gold Double Sweep Reversal: H2 {h2_price:.2f} swept H1 {h1_bar['high']:.2f} (swept H0 {max(earlier_highs):.2f}) with {h2_w_ratio*100:.1f}% wick, opposing 5M FVG [{fvg_bottom:.2f} - {fvg_top:.2f}]"
                                    return True, "BEARISH", entry, sl, desc

    # 2. Check Bullish Double Sweep Setup (Symmetrical)
    has_bull_fvg = False
    if len(bars_5m) >= 4:
        b1, b2, b3 = bars_5m[-3], bars_5m[-2], bars_5m[-1]
        if b1['high'] < b3['low'] - min_gap and b2['close'] > b2['open']:
            has_bull_fvg = True
            fvg_top = b3['low']
            fvg_bottom = b1['high']
            fvg_mid = (fvg_top + fvg_bottom) / 2.0
        else:
            b0, b1, b2 = bars_5m[-4], bars_5m[-3], bars_5m[-2]
            if b0['high'] < b2['low'] - min_gap and b1['close'] > b1['open']:
                has_bull_fvg = True
                fvg_top = b2['low']
                fvg_bottom = b0['high']
                fvg_mid = (fvg_top + fvg_bottom) / 2.0

    if has_bull_fvg:
        l2_candidates = []
        for idx in range(len(bars_5m) - 2, max(len(bars_5m) - 8, 5), -1):
            bar = bars_5m[idx]
            if bar['low'] <= bars_5m[idx - 1]['low']:
                rng = bar['high'] - bar['low']
                l_wick = min(bar['open'], bar['close']) - bar['low']
                w_ratio = l_wick / rng if rng > 0 else 0
                l2_candidates.append((idx, bar['low'], w_ratio, bar['close']))

        for l2_idx, l2_price, l2_w_ratio, l2_close in l2_candidates:
            if any(b['low'] < l2_price for b in bars_5m[l2_idx + 1:]):
                continue

            for l1_idx in range(l2_idx - 2, max(l2_idx - 25, 3), -1):
                l1_bar = bars_5m[l1_idx]
                if l1_bar['low'] > l2_price:
                    mid_highs = [b['high'] for b in bars_5m[l1_idx:l2_idx]]
                    h_mid = max(mid_highs)
                    rally_depth = h_mid - l1_bar['low']
                    if rally_depth >= 0.80:
                        if l2_w_ratio >= 0.25 or l2_close >= l1_bar['low'] - 0.30:
                            earlier_lows = [b['low'] for b in bars_5m[max(0, l1_idx - 35):l1_idx - 4]]
                            if earlier_lows and min(earlier_lows) > l1_bar['low'] and (min(earlier_lows) - l1_bar['low']) >= 0.20:
                                sl = round(l2_price - sl_buffer, 2)
                                entry = round(fvg_mid, 2)
                                risk = entry - sl
                                if risk > max_risk:
                                    entry = round(sl + max_risk, 2)
                                    risk = max_risk
                                if risk >= min_risk:
                                    desc = f"Gold Double Sweep Reversal: L2 {l2_price:.2f} swept L1 {l1_bar['low']:.2f} (swept L0 {min(earlier_lows):.2f}) with {l2_w_ratio*100:.1f}% wick, opposing 5M FVG [{fvg_bottom:.2f} - {fvg_top:.2f}]"
                                    return True, "BULLISH", entry, sl, desc

    return False, "NONE", 0.0, 0.0, ""

# Test on 2026 Gold 5M
df = pd.read_parquet('backtest_results/cache/M1_XAUUSD_o_2026.parquet')
df['dt'] = pd.to_datetime(df['time'], unit='s')
df.set_index('dt', inplace=True)
m5 = df.resample('5min').agg({'time': 'first', 'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna().reset_index()

candles = m5.to_dict(orient='records')
print(f"Testing on {len(candles)} 5M bars...")

signals = []
for i in range(40, len(candles)):
    slice_5m = candles[max(0, i - 120):i+1]
    has_setup, s_dir, s_entry, s_sl, s_desc = detect_gold_double_sweep_reversal(slice_5m, symbol="XAUUSD")
    if has_setup:
        # Check cooldown
        if not signals or (candles[i]['time'] - signals[-1]['time']) >= 1800:
            signals.append({
                'bar_idx': i,
                'time': candles[i]['time'],
                'dt': str(pd.to_datetime(candles[i]['time'], unit='s')),
                'direction': s_dir,
                'entry': s_entry,
                'sl': s_sl,
                'risk': abs(s_entry - s_sl),
                'desc': s_desc
            })

print(f"Total authentic signals found in 2026: {len(signals)}")
if signals:
    print("\nSample first 5 signals:")
    for s in signals[:5]:
        print(s['dt'], s['direction'], f"Entry: {s['entry']}, SL: {s['sl']}, Risk: ${s['risk']:.2f}")
        print("  ", s['desc'])
        
    print("\nSample last 5 signals:")
    for s in signals[-5:]:
        print(s['dt'], s['direction'], f"Entry: {s['entry']}, SL: {s['sl']}, Risk: ${s['risk']:.2f}")
        print("  ", s['desc'])

# Quick outcome evaluation
wins = 0
losses = 0
pnls = []
for s in signals:
    idx = s['bar_idx']
    entry = s['entry']
    sl = s['sl']
    risk = s['risk']
    direction = s['direction']
    tp = entry - 3.0 * risk if direction == "BEARISH" else entry + 3.0 * risk
    
    # Simulate fill
    filled = False
    fill_idx = -1
    for f in range(idx + 1, min(idx + 24, len(candles))):
        c = candles[f]
        if direction == "BEARISH" and c['high'] >= entry:
            filled = True; fill_idx = f; break
        elif direction == "BULLISH" and c['low'] <= entry:
            filled = True; fill_idx = f; break
            
    if not filled:
        continue
        
    outcome = None
    for f in range(fill_idx + 1, min(fill_idx + 150, len(candles))):
        c = candles[f]
        if direction == "BEARISH":
            if c['high'] >= sl: outcome = -1.0; break
            elif c['low'] <= tp: outcome = 3.0; break
        else:
            if c['low'] <= sl: outcome = -1.0; break
            elif c['high'] >= tp: outcome = 3.0; break
            
    if outcome is None: outcome = -0.5
    pnls.append(outcome)
    if outcome > 0: wins += 1
    elif outcome < 0: losses += 1

if pnls:
    wr = wins / len(pnls) * 100
    gp = sum(p for p in pnls if p > 0)
    gl = abs(sum(p for p in pnls if p < 0))
    pf = gp / gl if gl > 0 else 999.0
    net_r = sum(pnls)
    print(f"\n--- 2026 OUTCOME SIMULATION ---")
    print(f"Fills: {len(pnls)} | Wins: {wins} | Losses: {losses} | WR: {wr:.1f}% | Net: {net_r:+.1f}R | PF: {pf:.2f}")
