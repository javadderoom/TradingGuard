"""
TradingGuard Quantitative Audit: Counter-Trend Setup Failure Aligned with Macro Trend
Hypothesis:
When a setup fails in OPEN AIR (in a chop/range), forward drift is 50/50 noise.
HOWEVER:
When a COUNTER-TREND setup FAILS against the Daily Macro Trend:
- Daily Trend is BEARISH (EMA20 < EMA50 on D1/H1)
- A BULLISH setup triggers (counter-trend pullback)
- The Bullish setup FAILS (breaches invalidation level)
Does the macro trend resumption offer high-conviction, high-win-rate directional drift?
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

    # H1 Trend Classifier
    df_m5['h1_bucket'] = df_m5['timestamp'] // 3600 * 3600
    df_h1 = df_m5.groupby('h1_bucket').agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last')
    ).reset_index().rename(columns={'h1_bucket': 'timestamp'})
    df_h1['ema20'] = df_h1['close'].ewm(span=20, adjust=False).mean()
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df_h1['trend'] = np.where(df_h1['ema20'] > df_h1['ema50'], 1, -1)
    
    # Map H1 trend back to M5
    h1_trend_map = dict(zip(df_h1['timestamp'], df_h1['trend']))
    df_m5['h1_trend'] = df_m5['h1_bucket'].map(h1_trend_map).ffill().bfill()

    return df_m5, df_m1


def audit_macro_aligned_failures(symbol: str):
    df_m5, df_m1 = load_data(symbol)
    m5_records = df_m5.to_dict('records')
    n = len(m5_records)
    min_gap = 1.0 if symbol == "XAUUSD" else (5.0 if symbol == "NQ" else 0.0005)

    aligned_failures = []
    unaligned_failures = []

    for i in range(2, n - 25):
        b0 = m5_records[i-2]
        b1 = m5_records[i-1]
        b2 = m5_records[i]
        h1_trend = b2['h1_trend']

        # 1. Bullish FVG in a BEARISH H1 Trend (Counter-trend attempt)
        if b2['low'] - b0['high'] >= min_gap:
            fvg_bottom = b0['high']
            # Did it fail?
            for j in range(i + 1, min(i + 8, n)):
                if m5_records[j]['close'] < fvg_bottom:
                    # Counter-trend Bullish FVG FAILED in Bearish Macro Trend!
                    c_fail = m5_records[j]['close']
                    c_fwd_1h = m5_records[min(j + 12, n - 1)]['close']
                    c_fwd_2h = m5_records[min(j + 24, n - 1)]['close']
                    drift_1h = ((c_fwd_1h - c_fail) / c_fail) * 100.0
                    drift_2h = ((c_fwd_2h - c_fail) / c_fail) * 100.0
                    
                    event = {
                        "drift_1h": drift_1h,
                        "drift_2h": drift_2h,
                        "pro_trend_dir": -1 # Short
                    }
                    if h1_trend == -1: # Aligned with Bearish Trend!
                        aligned_failures.append(event)
                    else: # FVG failed while trend was Bullish
                        unaligned_failures.append(event)
                    break

        # 2. Bearish FVG in a BULLISH H1 Trend (Counter-trend attempt)
        elif b0['low'] - b2['high'] >= min_gap:
            fvg_top = b0['low']
            for j in range(i + 1, min(i + 8, n)):
                if m5_records[j]['close'] > fvg_top:
                    # Counter-trend Bearish FVG FAILED in Bullish Macro Trend!
                    c_fail = m5_records[j]['close']
                    c_fwd_1h = m5_records[min(j + 12, n - 1)]['close']
                    c_fwd_2h = m5_records[min(j + 24, n - 1)]['close']
                    drift_1h = ((c_fwd_1h - c_fail) / c_fail) * 100.0
                    drift_2h = ((c_fwd_2h - c_fail) / c_fail) * 100.0
                    
                    event = {
                        "drift_1h": drift_1h,
                        "drift_2h": drift_2h,
                        "pro_trend_dir": +1 # Long
                    }
                    if h1_trend == +1: # Aligned with Bullish Trend!
                        aligned_failures.append(event)
                    else:
                        unaligned_failures.append(event)
                    break

    df_aligned = pd.DataFrame(aligned_failures)
    df_unaligned = pd.DataFrame(unaligned_failures)

    # Calculate success: Did price continue in the pro_trend_dir?
    def calc_stats(df):
        if df.empty:
            return {"count": 0, "winrate_1h": 0, "winrate_2h": 0, "avg_drift": 0}
        success_1h = np.where(df['pro_trend_dir'] == 1, df['drift_1h'] > 0, df['drift_1h'] < 0)
        success_2h = np.where(df['pro_trend_dir'] == 1, df['drift_2h'] > 0, df['drift_2h'] < 0)
        return {
            "count": len(df),
            "winrate_1h": round(success_1h.mean() * 100, 1),
            "winrate_2h": round(success_2h.mean() * 100, 1),
            "avg_drift": round(float(np.where(df['pro_trend_dir'] == 1, df['drift_1h'], -df['drift_1h']).mean()), 3)
        }

    return {
        "symbol": symbol,
        "aligned": calc_stats(df_aligned),
        "unaligned": calc_stats(df_unaligned)
    }

def main():
    print("=" * 80)
    print("🔬 AUDIT: COUNTER-TREND SETUP FAILURE ALIGNED WITH MACRO H1 TREND")
    print("=" * 80)
    for sym in ["XAUUSD", "NQ", "GBPUSD"]:
        res = audit_macro_aligned_failures(sym)
        al = res['aligned']
        un = res['unaligned']
        print(f"\n--- {sym} ---")
        print(f"When Counter-Trend Setup FAILS IN THE DIRECTION OF MACRO TREND:")
        print(f"  Events: {al['count']:4d} | 1H Win Rate: {al['winrate_1h']}% | 2H Win Rate: {al['winrate_2h']}% | Avg Pro-Trend Drift: {al['avg_drift']:+.3f}%")
        print(f"When Setup Fails AGAINST the Macro Trend (Noise/Chop):")
        print(f"  Events: {un['count']:4d} | 1H Win Rate: {un['winrate_1h']}% | 2H Win Rate: {un['winrate_2h']}% | Avg Pro-Trend Drift: {un['avg_drift']:+.3f}%")

if __name__ == "__main__":
    main()
