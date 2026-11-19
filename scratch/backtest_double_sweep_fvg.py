"""
Quantitative Microstructure Backtest & Audit:
Double Sweep Reversal with Opposing FVG Displacement (SETUP-ARCH-016 Hypothesis)

Mechanism:
1. Sweep 1: Price sweeps a prominent high/low (H0) from a prior leg, setting Peak H1.
2. Sweep 2: After a minor pullback (forming a swing valley/crest), price pushes to sweep H1, setting Peak H2 (H2 > H1).
3. Opposing FVG: Within 1-5 bars of H2, an opposing FVG is formed via strong displacement.
4. Execution:
   - Entry Mode 1: Market on close of the FVG bar.
   - Entry Mode 2: Limit order at the FVG proximal edge (retest within 10 bars).
5. Invalidation (SL): Beyond H2 (+ spread buffer).
6. Target: Fixed 1:2R, 1:3R, and Liquidity Pool (origin of the leg).
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_backtest_for_symbol(symbol: str, parquet_file: str, spread_pts: float, point_val: float = 1.0, is_gold: bool = False):
    print(f"\n=======================================================")
    print(f"AUDITING DOUBLE SWEEP + FVG ON {symbol}")
    print(f"=======================================================")
    
    df = pd.read_parquet(parquet_file)
    df['dt'] = pd.to_datetime(df['time'], unit='s')
    df = df.sort_values('time').reset_index(drop=True)
    
    n = len(df)
    times = df['time'].values
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    dts = df['dt'].values
    
    min_gap_pts = 0.30 if is_gold else (0.00008 if 'GBP' in symbol else 2.0)
    
    # 1. Pre-compute 3L/3R swing pivots
    swing_highs = []
    swing_lows = []
    
    # We will step through bars causally
    trades_market_2r = []
    trades_market_3r = []
    trades_limit_2r = []
    trades_limit_3r = []
    
    # Track candidate states
    # For bearish setup:
    # State: after a major high H0 is swept by H1 at time t1.
    # Look for H2 sweeping H1 within 5 to 35 bars.
    # Once H2 forms, look for bearish FVG within 1 to 5 bars.
    
    active_h1 = None # dict(time, price, origin_h0_price, bar_idx)
    active_l1 = None
    
    # Rolling swing pivots
    pivot_span = 3
    
    for i in range(10, n - 60):
        # Update swing pivots confirmed at i - pivot_span
        p_idx = i - pivot_span
        if p_idx >= pivot_span:
            # Check if p_idx is a swing high
            is_sh = True
            is_sl = True
            for k in range(p_idx - pivot_span, p_idx + pivot_span + 1):
                if k == p_idx: continue
                if highs[k] >= highs[p_idx]: is_sh = False
                if lows[k] <= lows[p_idx]: is_sl = False
            if is_sh:
                swing_highs.append((times[p_idx], highs[p_idx], p_idx))
                # Keep last 50
                if len(swing_highs) > 50: swing_highs.pop(0)
            if is_sl:
                swing_lows.append((times[p_idx], lows[p_idx], p_idx))
                if len(swing_lows) > 50: swing_lows.pop(0)
                
        # --- Check for Sweep 1 (H0 swept by current bar) ---
        # If no active H1, see if bar i sweeps a prior swing high (separated by at least 10 bars)
        if active_h1 is None:
            for sh_time, sh_price, sh_idx in reversed(swing_highs):
                if i - sh_idx >= 8 and highs[i] > sh_price:
                    # Bar i swept H0
                    active_h1 = {
                        'h1_time': times[i],
                        'h1_price': highs[i],
                        'h0_price': sh_price,
                        'h1_idx': i,
                        'pulled_back': False,
                        'mid_low': lows[i]
                    }
                    break
        else:
            # We have active H1. Check timeout or invalidation
            bars_since = i - active_h1['h1_idx']
            if bars_since > 35 or closes[i] > active_h1['h1_price'] + (highs[i] - lows[i]) * 1.5:
                # Expired or blew way past
                active_h1 = None
            else:
                # Track pullback
                if lows[i] < active_h1['mid_low']:
                    active_h1['mid_low'] = lows[i]
                if active_h1['h1_price'] - lows[i] >= (active_h1['h1_price'] - active_h1['h0_price']) * 0.3:
                    active_h1['pulled_back'] = True
                    
                # Check for Sweep 2: Current bar sweeps H1
                if active_h1['pulled_back'] and highs[i] > active_h1['h1_price']:
                    h2_price = highs[i]
                    h2_time = times[i]
                    h2_idx = i
                    h1_price = active_h1['h1_price']
                    
                    # Look ahead 1 to 5 bars for opposing FVG
                    # Causally simulate forward from i+1 to i+6
                    fvg_found = False
                    entry_bar_idx = -1
                    fvg_top = 0.0
                    fvg_bottom = 0.0
                    
                    for f in range(i + 1, min(i + 7, n - 60)):
                        # If price makes a higher high than H2 before FVG, update H2 or invalidate
                        if highs[f] > h2_price:
                            h2_price = highs[f]
                            h2_idx = f
                            continue
                            
                        # Bearish FVG: low of f-2 > high of f + min_gap
                        if f >= 2 and lows[f - 2] > highs[f] + min_gap_pts:
                            # Bearish displacement body
                            if closes[f - 1] < opens[f - 1]:
                                fvg_found = True
                                entry_bar_idx = f
                                fvg_top = lows[f - 2]
                                fvg_bottom = highs[f]
                                break
                                
                    if fvg_found and entry_bar_idx > 0:
                        # Setup Triggered!
                        sl = h2_price + spread_pts
                        risk_pts = sl - closes[entry_bar_idx]
                        
                        if risk_pts > spread_pts * 1.5:
                            # 1. Market Entry on FVG Close
                            entry_mkt = closes[entry_bar_idx]
                            tp_2r = entry_mkt - 2.0 * risk_pts
                            tp_3r = entry_mkt - 3.0 * risk_pts
                            
                            # Simulate Mkt trade
                            res_2r = None
                            res_3r = None
                            for bar_f in range(entry_bar_idx + 1, min(entry_bar_idx + 120, n)):
                                b_h = highs[bar_f]
                                b_l = lows[bar_f]
                                
                                # Check 2R
                                if res_2r is None:
                                    if b_h >= sl: res_2r = -1.0
                                    elif b_l <= tp_2r: res_2r = 2.0
                                    
                                # Check 3R
                                if res_3r is None:
                                    if b_h >= sl: res_3r = -1.0
                                    elif b_l <= tp_3r: res_3r = 3.0
                                    
                                if res_2r is not None and res_3r is not None:
                                    break
                                    
                            if res_2r is None: res_2r = -0.5 # Expired
                            if res_3r is None: res_3r = -0.5
                            
                            trades_market_2r.append({
                                'time': times[entry_bar_idx],
                                'dt': str(dts[entry_bar_idx]),
                                'side': 'SELL',
                                'entry': entry_mkt,
                                'sl': sl,
                                'risk': risk_pts,
                                'pnl_r': res_2r
                            })
                            trades_market_3r.append({
                                'time': times[entry_bar_idx],
                                'dt': str(dts[entry_bar_idx]),
                                'side': 'SELL',
                                'entry': entry_mkt,
                                'sl': sl,
                                'risk': risk_pts,
                                'pnl_r': res_3r
                            })
                            
                            # 2. Limit Entry at FVG Bottom / Mid
                            limit_entry = fvg_bottom + (fvg_top - fvg_bottom) * 0.5
                            limit_filled = False
                            fill_bar = -1
                            for lf in range(entry_bar_idx + 1, min(entry_bar_idx + 15, n)):
                                if highs[lf] >= limit_entry:
                                    limit_filled = True
                                    fill_bar = lf
                                    break
                                if lows[lf] < entry_mkt - risk_pts:
                                    break # ran away without fill
                                    
                            if limit_filled:
                                l_risk = sl - limit_entry
                                l_tp2 = limit_entry - 2.0 * l_risk
                                l_tp3 = limit_entry - 3.0 * l_risk
                                l_res_2r = None
                                l_res_3r = None
                                for bar_f in range(fill_bar + 1, min(fill_bar + 120, n)):
                                    b_h = highs[bar_f]
                                    b_l = lows[bar_f]
                                    if l_res_2r is None:
                                        if b_h >= sl: l_res_2r = -1.0
                                        elif b_l <= l_tp2: l_res_2r = 2.0
                                    if l_res_3r is None:
                                        if b_h >= sl: l_res_3r = -1.0
                                        elif b_l <= l_tp3: l_res_3r = 3.0
                                    if l_res_2r is not None and l_res_3r is not None:
                                        break
                                if l_res_2r is None: l_res_2r = -0.5
                                if l_res_3r is None: l_res_3r = -0.5
                                trades_limit_2r.append(l_res_2r)
                                trades_limit_3r.append(l_res_3r)
                    
                    # Reset active H1 after Sweep 2 attempt
                    active_h1 = None

    # Print Report
    def calc_stats(trade_list, label):
        if not trade_list:
            print(f"{label}: 0 trades")
            return
        pnls = [t['pnl_r'] if isinstance(t, dict) else t for t in trade_list]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        win_rate = len(wins) / len(pnls) * 100
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses)) if losses else 0.001
        pf = gross_profit / gross_loss
        net_r = sum(pnls)
        print(f"[{label}] Trades: {len(pnls)} | Wins: {len(wins)} | Losses: {len(losses)} | WR: {win_rate:.1f}% | Net: {net_r:+.1f}R | PF: {pf:.2f}")

    calc_stats(trades_market_2r, "Market Entry @ FVG Close (1:2 R:R)")
    calc_stats(trades_market_3r, "Market Entry @ FVG Close (1:3 R:R)")
    calc_stats(trades_limit_2r, "Limit Retest @ FVG 50% (1:2 R:R)")
    calc_stats(trades_limit_3r, "Limit Retest @ FVG 50% (1:3 R:R)")

if __name__ == '__main__':
    run_backtest_for_symbol("XAUUSD_o (Gold 2026 M1)", "backtest_results/cache/M1_XAUUSD_o_2026.parquet", 0.22, is_gold=True)
    run_backtest_for_symbol("GBPUSD_o (Cable 2026 M1)", "backtest_results/cache/M1_GBPUSD_o_2026.parquet", 0.00006, is_gold=False)
    run_backtest_for_symbol("NQ (Nasdaq 2026 M1)", "backtest_results/cache/NQ_M1_EXTENDED_2026.parquet", 1.0, is_gold=False)
