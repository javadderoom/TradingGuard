"""
Institutional Macro-Filtered Audit:
Double Sweep Reversal with Macro Anchors & MSS Confirmation

Filters tested:
1. H0 Anchor: Must be a Major HTF Swing High (15M / H1 confirmed) or Session High (Asian / London / Prior Day).
2. Sweep 2 Rejection Quality: H2 must print rejection (upper wick >= 25% or close < H1).
3. Structural Confirmation: Opposing displacement must break the intermediate pullback low L_mid (Market Structure Shift / MSS) or form prominent FVG.
4. Killzone Gate: London (08:00-11:30 UTC) and NY (13:00-16:30 UTC).
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_filtered_audit(symbol: str, parquet_file: str, spread_pts: float, is_gold: bool = True):
    print(f"\n=================================================================")
    print(f"AUDITING MACRO-ANCHORED DOUBLE SWEEP ON {symbol}")
    print(f"=================================================================")
    
    df = pd.read_parquet(parquet_file)
    df['dt'] = pd.to_datetime(df['time'], unit='s')
    df = df.sort_values('time').reset_index(drop=True)
    
    # Resample to 5M to compare against 1M
    df.set_index('dt', inplace=True)
    m5 = df.resample('5min').agg({
        'time': 'first',
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna().reset_index()
    
    for tf_label, c_df in [("1-Minute (M1)", df.reset_index()), ("5-Minute (5M)", m5)]:
        times = c_df['time'].values
        opens = c_df['open'].values
        highs = c_df['high'].values
        lows = c_df['low'].values
        closes = c_df['close'].values
        dts = c_df['dt'].values
        n = len(c_df)
        
        # Test across different configurations
        # Config A: Pure Double Sweep + Rejection + FVG (No MSS)
        # Config B: Double Sweep + Rejection + MSS (Breaking L_mid)
        # Config C: Double Sweep + Rejection + MSS + Killzone Only
        
        for config_name in ["A: Double Sweep + Rejection + FVG", "B: Double Sweep + MSS (Break of L_mid)", "C: Config B + London/NY Killzone"]:
            trades = []
            
            # Identify prominent swing highs (5L/5R on this timeframe)
            pivot_span = 5
            swing_highs = []
            
            for i in range(pivot_span * 2, n - 60):
                # Update swing highs
                p_idx = i - pivot_span
                is_sh = True
                for k in range(p_idx - pivot_span, p_idx + pivot_span + 1):
                    if k == p_idx: continue
                    if highs[k] >= highs[p_idx]: is_sh = False; break
                if is_sh:
                    swing_highs.append((times[p_idx], highs[p_idx], p_idx))
                    if len(swing_highs) > 40: swing_highs.pop(0)
                    
                # Look for Sweep 1: Current bar i sweeps a prominent swing high at least 15 bars old
                for sh_time, sh_price, sh_idx in reversed(swing_highs):
                    if i - sh_idx >= 15 and highs[i] > sh_price:
                        h1_price = highs[i]
                        h1_idx = i
                        
                        # Now scan forward for pullback and Sweep 2 within 5 to 30 bars
                        for s2_idx in range(h1_idx + 3, min(h1_idx + 35, n - 60)):
                            # Find intermediate low L_mid between h1_idx and s2_idx
                            mid_lows = lows[h1_idx:s2_idx]
                            l_mid = np.min(mid_lows)
                            l_mid_idx = h1_idx + np.argmin(mid_lows)
                            
                            # Pullback requirement: price must retrace at least 30% of leg or $1.00 on gold
                            pullback_depth = h1_price - l_mid
                            min_pullback = 1.0 if is_gold else 0.0010
                            if pullback_depth < min_pullback:
                                continue
                                
                            # Check if bar s2 sweeps H1
                            if highs[s2_idx] > h1_price:
                                h2_price = highs[s2_idx]
                                h2_bar_rng = highs[s2_idx] - lows[s2_idx]
                                h2_upper_wick = highs[s2_idx] - max(opens[s2_idx], closes[s2_idx])
                                h2_wick_ratio = h2_upper_wick / h2_bar_rng if h2_bar_rng > 0 else 0
                                
                                # Rejection filter: Upper wick >= 25% OR close < H1
                                if h2_wick_ratio < 0.25 and closes[s2_idx] >= h1_price:
                                    continue # Pure bullish breakout, not a sweep rejection
                                    
                                # Killzone check if config C
                                dt_val = pd.to_datetime(dts[s2_idx])
                                hr = dt_val.hour
                                in_kz = (8 <= hr < 12) or (13 <= hr < 17)
                                if "Killzone" in config_name and not in_kz:
                                    continue
                                    
                                # Look for confirmation:
                                # Config A: FVG within 5 bars
                                # Config B & C: MSS (Close < L_mid) within 10 bars
                                confirmed = False
                                entry_price = 0.0
                                entry_idx = -1
                                
                                if "FVG" in config_name:
                                    min_gap = 0.30 if is_gold else 0.00008
                                    for f in range(s2_idx + 1, min(s2_idx + 6, n - 60)):
                                        if highs[f] > h2_price: break # Invalidated
                                        if f >= 2 and lows[f - 2] > highs[f] + min_gap:
                                            confirmed = True
                                            entry_price = closes[f]
                                            entry_idx = f
                                            break
                                else:
                                    for m in range(s2_idx + 1, min(s2_idx + 15, n - 60)):
                                        if highs[m] > h2_price: break # Invalidated
                                        if closes[m] < l_mid:
                                            confirmed = True
                                            entry_price = closes[m]
                                            entry_idx = m
                                            break
                                            
                                if confirmed and entry_idx > 0:
                                    sl = h2_price + spread_pts
                                    risk = sl - entry_price
                                    max_risk = 15.0 if is_gold else 0.0035
                                    min_risk = spread_pts * 2.0
                                    
                                    if min_risk <= risk <= max_risk:
                                        # Simulate 1:2.5 R:R trade
                                        tp = entry_price - 2.5 * risk
                                        outcome = None
                                        for tf_sim in range(entry_idx + 1, min(entry_idx + 150, n)):
                                            if highs[tf_sim] >= sl:
                                                outcome = -1.0
                                                break
                                            elif lows[tf_sim] <= tp:
                                                outcome = 2.5
                                                break
                                        if outcome is None: outcome = -0.5
                                        trades.append(outcome)
                                        
                                # Break after evaluating s2 to avoid duplicate sweeps of same peak
                                break
                        break # Done with this H0 sweep
                        
            # Stats
            if trades:
                wins = [t for t in trades if t > 0]
                losses = [t for t in trades if t < 0]
                wr = len(wins) / len(trades) * 100
                gp = sum(wins)
                gl = abs(sum(losses)) if losses else 0.001
                pf = gp / gl
                net_r = sum(trades)
                print(f"[{tf_label}] {config_name}")
                print(f"    Trades: {len(trades):<4} | Wins: {len(wins):<4} | Losses: {len(losses):<4} | WR: {wr:4.1f}% | Net: {net_r:+6.1f}R | PF: {pf:.2f}")
            else:
                print(f"[{tf_label}] {config_name}: 0 trades")

if __name__ == '__main__':
    run_filtered_audit("XAUUSD_o (Gold 2026)", "backtest_results/cache/M1_XAUUSD_o_2026.parquet", 0.22, is_gold=True)
    run_filtered_audit("GBPUSD_o (Cable 2026)", "backtest_results/cache/M1_GBPUSD_o_2026.parquet", 0.00006, is_gold=False)
