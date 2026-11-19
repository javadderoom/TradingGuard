"""
TradingGuard Quantitative Research: Inversion Fair Value Gap (IFVG)
Tests whether the FAILURE of a Fair Value Gap creates positive alpha when traded as an Inversion FVG.
Mechanics:
1. Detect confirmed 5M FVG (Bullish: Bar 1 High < Bar 3 Low; Bearish: Bar 1 Low > Bar 3 High).
2. Monitor forward: If price cleanly closes THROUGH the FVG in the opposite direction, the FVG has FAILED.
   - Bullish FVG failed -> Becomes Bearish IFVG (Resistance)
   - Bearish FVG failed -> Becomes Bullish IFVG (Support)
3. Wait for price to retrace and tap the IFVG zone within 12 bars (60 min).
4. Enter on tap in the direction of the breach.
5. SL: Placed just outside the IFVG boundary (tight risk).
6. TP: 1.5R to 2.0R.
"""

import sys
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, Any, List
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def load_data(symbol: str):
    cache_dir = PROJECT_ROOT / "backtest_results" / "cache"
    m5_path = cache_dir / f"{symbol}_M5_1YEAR.parquet"
    if not m5_path.exists():
        m5_path = cache_dir / f"{symbol}_M5_2026.parquet"
    m1_path = cache_dir / f"{symbol}_M1_2026.parquet"
    
    df_m5 = pd.read_parquet(m5_path)
    if 'time' in df_m5.columns:
        df_m5['timestamp'] = df_m5['time'].astype(np.int64)
    else:
        df_m5['timestamp'] = df_m5.index.astype(np.int64) // 10**9
    df_m5 = df_m5.drop_duplicates('timestamp').sort_values('timestamp').reset_index(drop=True)
    df_m5['dt'] = pd.to_datetime(df_m5['timestamp'], unit='s', utc=True)

    df_m1 = pd.read_parquet(m1_path)
    if 'time' in df_m1.columns:
        df_m1['timestamp'] = df_m1['time'].astype(np.int64)
    else:
        df_m1['timestamp'] = df_m1.index.astype(np.int64) // 10**9
    df_m1 = df_m1.drop_duplicates('timestamp').sort_values('timestamp').reset_index(drop=True)
    df_m1['dt'] = pd.to_datetime(df_m1['timestamp'], unit='s', utc=True)
    return df_m5, df_m1


def simulate_trade(df_m1, start_ts, direction, entry, sl, tp, max_hold=120, spread=0.2):
    sub = df_m1[(df_m1['timestamp'] >= start_ts) & (df_m1['timestamp'] <= start_ts + max_hold * 60)]
    if sub.empty:
        return {"outcome": "TIMEOUT", "pnl_r": 0.0}
    risk = abs(entry - sl)
    if risk <= 1e-5:
        return {"outcome": "INVALID", "pnl_r": 0.0}

    for _, row in sub.iterrows():
        if direction == "BUY":
            if row['low'] <= sl:
                return {"outcome": "LOSS", "pnl_r": -1.0 - (spread / risk)}
            if row['high'] >= tp:
                return {"outcome": "WIN", "pnl_r": ((tp - entry) / risk) - (spread / risk)}
        else:
            if row['high'] >= sl:
                return {"outcome": "LOSS", "pnl_r": -1.0 - (spread / risk)}
            if row['low'] <= tp:
                return {"outcome": "WIN", "pnl_r": ((entry - tp) / risk) - (spread / risk)}
    
    last_close = sub.iloc[-1]['close']
    pnl = ((last_close - entry) if direction == "BUY" else (entry - last_close)) / risk - (spread / risk)
    return {"outcome": "TIMEOUT", "pnl_r": pnl}


def audit_ifvg(symbol: str, target_r: float = 1.5):
    df_m5, df_m1 = load_data(symbol)
    spread = 0.25 if symbol == "XAUUSD" else (1.0 if symbol == "NQ" else 0.00012)
    min_gap = 1.0 if symbol == "XAUUSD" else (5.0 if symbol == "NQ" else 0.0005)

    trades = []
    m5_records = df_m5.to_dict('records')
    n = len(m5_records)

    # Scan for FVGs and track failure
    for i in range(2, n - 25):
        b0 = m5_records[i-2]
        b1 = m5_records[i-1]
        b2 = m5_records[i]

        # 1. Bullish FVG: b0['high'] < b2['low']
        if b2['low'] - b0['high'] >= min_gap:
            fvg_top = b2['low']
            fvg_bottom = b0['high']
            
            # Look forward for breach (bar closing below fvg_bottom)
            breach_found = False
            breach_idx = None
            for j in range(i + 1, min(i + 15, n)):
                if m5_records[j]['close'] < fvg_bottom:
                    breach_found = True
                    breach_idx = j
                    break

            if breach_found:
                # FVG has failed -> Now Bearish IFVG!
                # Look for retest of fvg_bottom from below
                for k in range(breach_idx + 1, min(breach_idx + 12, n)):
                    bar_k = m5_records[k]
                    # Retest tap into the IFVG zone
                    if bar_k['high'] >= fvg_bottom and bar_k['open'] < fvg_bottom:
                        entry = fvg_bottom
                        sl = fvg_top + (0.2 * (fvg_top - fvg_bottom))
                        risk = sl - entry
                        tp = entry - target_r * risk
                        res = simulate_trade(df_m1, int(bar_k['timestamp']), "SELL", entry, sl, tp, 180, spread)
                        res['symbol'] = symbol
                        res['type'] = 'BEARISH_IFVG'
                        trades.append(res)
                        break

        # 2. Bearish FVG: b0['low'] > b2['high']
        elif b0['low'] - b2['high'] >= min_gap:
            fvg_top = b0['low']
            fvg_bottom = b2['high']

            # Look forward for breach (bar closing above fvg_top)
            breach_found = False
            breach_idx = None
            for j in range(i + 1, min(i + 15, n)):
                if m5_records[j]['close'] > fvg_top:
                    breach_found = True
                    breach_idx = j
                    break

            if breach_found:
                # FVG has failed -> Now Bullish IFVG!
                # Look for retest of fvg_top from above
                for k in range(breach_idx + 1, min(breach_idx + 12, n)):
                    bar_k = m5_records[k]
                    if bar_k['low'] <= fvg_top and bar_k['open'] > fvg_top:
                        entry = fvg_top
                        sl = fvg_bottom - (0.2 * (fvg_top - fvg_bottom))
                        risk = entry - sl
                        tp = entry + target_r * risk
                        res = simulate_trade(df_m1, int(bar_k['timestamp']), "BUY", entry, sl, tp, 180, spread)
                        res['symbol'] = symbol
                        res['type'] = 'BULLISH_IFVG'
                        trades.append(res)
                        break

    if not trades:
        return {"trades": 0, "win_rate": 0, "net_r": 0, "pf": 0}
    df = pd.DataFrame(trades)
    total = len(df)
    wins = len(df[df['outcome'] == 'WIN'])
    losses = len(df[df['outcome'] == 'LOSS'])
    net_r = df['pnl_r'].sum()
    gp = df[df['pnl_r'] > 0]['pnl_r'].sum()
    gl = abs(df[df['pnl_r'] < 0]['pnl_r'].sum())
    pf = round(gp / (gl + 1e-9), 2)
    wr = round(wins / total * 100, 1)
    return {
        "symbol": symbol,
        "trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": wr,
        "net_r": round(net_r, 2),
        "pf": pf
    }

def main():
    print("=" * 70)
    print("INVERSION FAIR VALUE GAP (IFVG) - TRADING THE BREACH OF FAILED FVGS")
    print("=" * 70)
    for sym in ["XAUUSD", "NQ", "GBPUSD"]:
        res = audit_ifvg(sym)
        print(f"{sym:<10}: Trades={res['trades']:4d} | WR={res['win_rate']:5.1f}% | Net R={res['net_r']:+8.2f}R | PF={res['pf']:.2f}")

if __name__ == "__main__":
    main()
