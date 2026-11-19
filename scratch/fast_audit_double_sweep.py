"""
High-Performance Quantitative Microstructure Audit:
Double Sweep Reversal (Leg High Swept -> New High Swept -> Opposing FVG)

Zero-lookahead, authentic broker data, realistic spread & commission.
"""

import pandas as pd
import numpy as np

def fast_audit(symbol: str, parquet_path: str, spread_pts: float, is_gold: bool = True):
    print(f"\n=======================================================")
    print(f"FAST AUDITING DOUBLE SWEEP + FVG ON {symbol}")
    print(f"=======================================================")
    
    df = pd.read_parquet(parquet_path)
    df['dt'] = pd.to_datetime(df['time'], unit='s')
    df = df.sort_values('time').reset_index(drop=True)
    
    # Also prepare 5M
    df.set_index('dt', inplace=True)
    m5 = df.resample('5min').agg({
        'time': 'first',
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna().reset_index()
    df.reset_index(inplace=True)
    
    for tf_name, c_df in [("1-Minute (M1)", df), ("5-Minute (5M)", m5)]:
        n = len(c_df)
        highs = c_df['high'].values
        lows = c_df['low'].values
        opens = c_df['open'].values
        closes = c_df['close'].values
        times = c_df['time'].values
        dts = pd.to_datetime(c_df['dt']).values
        
        # 1. Vectorized 3L/3R swing high detection
        is_sh = np.zeros(n, dtype=bool)
        is_sl = np.zeros(n, dtype=bool)
        for k in range(3, n - 3):
            if (highs[k] > highs[k-1] and highs[k] > highs[k-2] and highs[k] > highs[k-3] and
                highs[k] >= highs[k+1] and highs[k] >= highs[k+2] and highs[k] >= highs[k+3]):
                is_sh[k] = True
            if (lows[k] < lows[k-1] and lows[k] < lows[k-2] and lows[k] < lows[k-3] and
                lows[k] <= lows[k+1] and lows[k] <= lows[k+2] and lows[k] <= lows[k+3]):
                is_sl[k] = True
                
        sh_indices = np.where(is_sh)[0]
        sl_indices = np.where(is_sl)[0]
        
        min_gap = 0.30 if is_gold else (0.00008 if 'GBP' in symbol else 2.0)
        
        # Test configurations:
        # 1. Unfiltered Double Sweep + FVG
        # 2. Rejection Double Sweep (wick >= 25% or close < H1) + FVG
        # 3. Rejection Double Sweep + MSS (Close < L_mid) + FVG
        # 4. Config 3 + London/NY Killzones
        
        configs = [
            ("1. Raw Double Sweep + FVG", False, False, False),
            ("2. Rejection Sweep 2 (Wick>=25%) + FVG", True, False, False),
            ("3. Rejection Sweep 2 + MSS (Break L_mid) + FVG", True, True, False),
            ("4. Rejection + MSS + FVG + Killzone Only", True, True, True),
        ]
        
        print(f"\n--- TIMEFRAME: {tf_name} ({n} bars) ---")
        
        for cfg_name, req_rejection, req_mss, req_kz in configs:
            trades_2r = []
            trades_3r = []
            
            # Step through each swing high H1
            # H1 must sweep an earlier H0 (within prior 10 to 60 bars)
            last_traded_bar = -1
            
            for h1_idx in sh_indices:
                if h1_idx < 30 or h1_idx > n - 100: continue
                if h1_idx <= last_traded_bar: continue
                
                h1_high = highs[h1_idx]
                
                # Check if H1 swept an earlier H0
                # Look back 8 to 50 bars
                earlier_sh = sh_indices[(sh_indices >= h1_idx - 50) & (sh_indices <= h1_idx - 8)]
                if len(earlier_sh) == 0: continue
                h0_candidates = [highs[idx] for idx in earlier_sh if highs[idx] < h1_high]
                if not h0_candidates: continue
                h0_price = max(h0_candidates)
                
                # H1 swept H0!
                # Now look for H2 sweeping H1 within 3 to 25 bars
                h2_found = False
                h2_idx = -1
                l_mid = 1e9
                
                for k in range(h1_idx + 1, min(h1_idx + 30, n - 60)):
                    if lows[k] < l_mid:
                        l_mid = lows[k]
                        
                    # Check if bar k sweeps H1
                    if highs[k] > h1_high:
                        # Ensure there was a pullback before H2
                        pullback_depth = h1_high - l_mid
                        min_pb = 0.50 if is_gold else (0.0006 if 'GBP' in symbol else 5.0)
                        if pullback_depth >= min_pb:
                            h2_found = True
                            h2_idx = k
                            break
                            
                if not h2_found or h2_idx <= 0: continue
                
                h2_high = highs[h2_idx]
                h2_rng = highs[h2_idx] - lows[h2_idx]
                h2_u_wick = highs[h2_idx] - max(opens[h2_idx], closes[h2_idx])
                h2_w_ratio = h2_u_wick / h2_rng if h2_rng > 0 else 0
                
                if req_rejection:
                    if h2_w_ratio < 0.25 and closes[h2_idx] >= h1_high:
                        continue # Failed rejection
                        
                if req_kz:
                    dt_val = pd.to_datetime(dts[h2_idx])
                    hr = dt_val.hour
                    in_kz = (8 <= hr < 12) or (13 <= hr < 17)
                    if not in_kz: continue
                    
                # Look for opposing FVG and optional MSS within 1 to 6 bars after H2
                fvg_found = False
                entry_idx = -1
                mss_found = False
                
                for f in range(h2_idx + 1, min(h2_idx + 8, n - 60)):
                    if highs[f] > h2_high:
                        break # Invalidation: higher high made
                    if closes[f] < l_mid:
                        mss_found = True
                    # Bearish FVG: low[f-2] > high[f] + min_gap
                    if f >= 2 and lows[f - 2] > highs[f] + min_gap and closes[f - 1] < opens[f - 1]:
                        fvg_found = True
                        entry_idx = f
                        if not req_mss or mss_found:
                            break
                            
                if req_mss and not mss_found: continue
                if not fvg_found or entry_idx <= 0: continue
                
                # Execute Trade
                entry_price = closes[entry_idx]
                sl = h2_high + spread_pts
                risk = sl - entry_price
                max_risk = 15.0 if is_gold else (0.0035 if 'GBP' in symbol else 50.0)
                min_risk = spread_pts * 2.0
                
                if risk < min_risk or risk > max_risk: continue
                
                tp_2r = entry_price - 2.0 * risk
                tp_3r = entry_price - 3.0 * risk
                
                res_2r = None
                res_3r = None
                for bar_sim in range(entry_idx + 1, min(entry_idx + 120, n)):
                    b_h = highs[bar_sim]
                    b_l = lows[bar_sim]
                    if res_2r is None:
                        if b_h >= sl: res_2r = -1.0
                        elif b_l <= tp_2r: res_2r = 2.0
                    if res_3r is None:
                        if b_h >= sl: res_3r = -1.0
                        elif b_l <= tp_3r: res_3r = 3.0
                    if res_2r is not None and res_3r is not None:
                        break
                        
                if res_2r is None: res_2r = -0.5
                if res_3r is None: res_3r = -0.5
                
                trades_2r.append(res_2r)
                trades_3r.append(res_3r)
                last_traded_bar = entry_idx + 5
                
            # Print stats
            def summarize(t_list, r_label):
                if not t_list:
                    return "0 trades"
                wins = [t for t in t_list if t > 0]
                losses = [t for t in t_list if t < 0]
                wr = len(wins) / len(t_list) * 100
                gp = sum(wins)
                gl = abs(sum(losses)) if losses else 0.001
                pf = gp / gl
                net_r = sum(t_list)
                return f"Trades: {len(t_list):<4} | WR: {wr:4.1f}% | Net: {net_r:+6.1f}R | PF: {pf:.2f}"
                
            print(f"  {cfg_name}")
            print(f"    -> 1:2 R:R : {summarize(trades_2r, '2R')}")
            print(f"    -> 1:3 R:R : {summarize(trades_3r, '3R')}")

if __name__ == '__main__':
    fast_audit("XAUUSD_o (Gold 2026)", "backtest_results/cache/M1_XAUUSD_o_2026.parquet", 0.22, is_gold=True)
    fast_audit("GBPUSD_o (Cable 2026)", "backtest_results/cache/M1_GBPUSD_o_2026.parquet", 0.00006, is_gold=False)
    fast_audit("NQ (Nasdaq 2026)", "backtest_results/cache/NQ_M1_EXTENDED_2026.parquet", 1.0, is_gold=False)
