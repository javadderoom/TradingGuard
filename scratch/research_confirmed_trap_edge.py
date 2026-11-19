"""
TradingGuard Quantitative Research: Confirmed Failure Traps (Absorption + Follow-Through)
Tests the strict institutional conditions required to make "fading failed setups" profitable:
1. False Breakout with Absorption Wick (>= 30% upper wick on long breakout, >= 30% lower wick on breakdown)
2. Bar T+1 Follow-Through Displacement (Close back through the range boundary with momentum)
3. Target: Mid-Range Equilibrium (1:1.5 R:R) or Opposite Boundary (1:2.5+ R:R)
4. Risk Management: SL anchored tightly above the false excursion high/low
"""

import sys
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hitl.backtest.session_clock import get_session_times_for_date

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


def audit_confirmed_traps(symbol: str):
    df_m5, df_m1 = load_data(symbol)
    spread = 0.25 if symbol == "XAUUSD" else (1.0 if symbol == "NQ" else 0.00012)
    df_m5['date'] = df_m5['dt'].dt.date
    dates = sorted(df_m5['date'].unique())

    trades = []

    for d in dates:
        sess = get_session_times_for_date(d)
        open_utc = sess["nyse_open"]["utc_time"] if symbol == "NQ" else sess["london"]["utc_time"]
        open_ts = int(open_utc.timestamp())
        range_end_ts = open_ts + 15 * 60

        orb_bars = df_m5[(df_m5['timestamp'] >= open_ts) & (df_m5['timestamp'] < range_end_ts)]
        if len(orb_bars) < 3:
            continue
        range_high = orb_bars['high'].max()
        range_low = orb_bars['low'].min()
        range_size = range_high - range_low
        if range_size <= 1e-4:
            continue

        post_bars = df_m5[(df_m5['timestamp'] >= range_end_ts) & (df_m5['timestamp'] <= range_end_ts + 120 * 60)]
        if len(post_bars) < 4:
            continue

        # Look for False Breakout Trap:
        # Bar i breaches range_high, but prints upper wick >= 30% of total bar range
        # Bar i+1 closes firmly back below range_high (displacement confirmation)
        post_list = post_bars.to_dict('records')
        for i in range(len(post_list) - 1):
            b0 = post_list[i]
            b1 = post_list[i+1]
            b0_high = b0['high']
            b0_low = b0['low']
            b0_close = b0['close']
            b0_open = b0['open']
            b0_range = b0_high - b0_low
            if b0_range <= 1e-5:
                continue

            # Case A: Bullish Breakout Trap (Fade to SHORT)
            if b0_high > range_high:
                upper_wick = b0_high - max(b0_open, b0_close)
                wick_ratio = upper_wick / b0_range
                # Absorption wick >= 30% and Bar T+1 closes back inside
                if wick_ratio >= 0.30 and b1['close'] < range_high and b1['close'] < b0_close:
                    entry = b1['close']
                    sl = b0_high + (0.05 * range_size)
                    tp = range_low # target opposite range boundary
                    risk = sl - entry
                    reward = entry - tp
                    if risk > 0 and (reward / risk) >= 1.5:
                        res = simulate_trade(df_m1, int(b1['timestamp']), "SELL", entry, sl, tp, 120, spread)
                        res['symbol'] = symbol
                        res['date'] = str(d)
                        res['type'] = 'BEARISH_TRAP'
                        trades.append(res)
                        break

            # Case B: Bearish Breakdown Trap (Fade to LONG)
            elif b0_low < range_low:
                lower_wick = min(b0_open, b0_close) - b0_low
                wick_ratio = lower_wick / b0_range
                # Absorption wick >= 30% and Bar T+1 closes back inside
                if wick_ratio >= 0.30 and b1['close'] > range_low and b1['close'] > b0_close:
                    entry = b1['close']
                    sl = b0_low - (0.05 * range_size)
                    tp = range_high
                    risk = entry - sl
                    reward = tp - entry
                    if risk > 0 and (reward / risk) >= 1.5:
                        res = simulate_trade(df_m1, int(b1['timestamp']), "BUY", entry, sl, tp, 120, spread)
                        res['symbol'] = symbol
                        res['date'] = str(d)
                        res['type'] = 'BULLISH_TRAP'
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
    print("CONFIRMED FALSE BREAKOUT TRAPS (ABSORPTION WICK + T+1 CONFIRMATION)")
    print("=" * 70)
    for sym in ["XAUUSD", "NQ", "GBPUSD"]:
        res = audit_confirmed_traps(sym)
        print(f"{sym:<10}: Trades={res['trades']:3d} | WR={res['win_rate']:5.1f}% | Net R={res['net_r']:+7.2f}R | PF={res['pf']:.2f}")

if __name__ == "__main__":
    main()
