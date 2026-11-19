"""
TradingGuard Quantitative Audit: Setup Failure as a Directional Regime Oracle
Tests the User's Thesis:
Instead of trading the failure directly (which yielded unviable < 10% win rates),
use the failure of a bullish/bearish setup as a MACRO DIRECTIONAL FILTER:
- When a Bullish setup fails (e.g. Bullish FVG breached or Bullish ORB fails):
  -> Market Regime flips to HEAVY_BEARISH_FLOW
  -> Veto ALL Longs
  -> Allow ONLY High-Quality Pro-Trend Shorts
- Measure:
  1. Win Rate of standard setups with vs without the Failure Oracle
  2. Loss Prevention: How many catastrophic counter-trend losses are avoided
  3. Expectancy and Drawdown impact
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


def audit_failure_oracle(symbol: str):
    df_m5, df_m1 = load_data(symbol)
    spread = 0.25 if symbol == "XAUUSD" else (1.0 if symbol == "NQ" else 0.00012)
    min_gap = 1.0 if symbol == "XAUUSD" else (5.0 if symbol == "NQ" else 0.0005)

    # 1. Identify all 5M FVGs and whether they Hold or Fail
    m5_records = df_m5.to_dict('records')
    n = len(m5_records)

    # State tracking: directional_bias (+1 for Bullish, -1 for Bearish, 0 for Neutral)
    # When Bullish FVG holds -> Bullish Bias
    # When Bullish FVG FAILS -> Heavy Bearish Bias (Buyers crushed)
    # When Bearish FVG holds -> Bearish Bias
    # When Bearish FVG FAILS -> Heavy Bullish Bias (Sellers crushed)

    fvg_events = [] # list of (timestamp, event_type, bias)
    for i in range(2, n - 20):
        b0 = m5_records[i-2]
        b1 = m5_records[i-1]
        b2 = m5_records[i]

        # Bullish FVG
        if b2['low'] - b0['high'] >= min_gap:
            fvg_bottom = b0['high']
            # Check next 6 bars (30 min)
            failed = False
            for j in range(i + 1, min(i + 7, n)):
                if m5_records[j]['close'] < fvg_bottom:
                    failed = True
                    fail_ts = int(m5_records[j]['timestamp'])
                    fvg_events.append((fail_ts, "BULL_FVG_FAILED", -1)) # Sellers won!
                    break

        # Bearish FVG
        elif b0['low'] - b2['high'] >= min_gap:
            fvg_top = b0['low']
            failed = False
            for j in range(i + 1, min(i + 7, n)):
                if m5_records[j]['close'] > fvg_top:
                    failed = True
                    fail_ts = int(m5_records[j]['timestamp'])
                    fvg_events.append((fail_ts, "BEAR_FVG_FAILED", +1)) # Buyers won!
                    break

    df_events = pd.DataFrame(fvg_events, columns=['timestamp', 'event', 'bias']).sort_values('timestamp')
    
    # 2. Measure subsequent forward price drift after a Setup Failure
    # For a Bullish FVG Failure (Bias = -1), what is the forward price drift over 1h, 2h, 4h?
    drifts_bearish_events = []
    drifts_bullish_events = []

    m5_ts_map = {row['timestamp']: row['close'] for row in m5_records}

    for _, ev in df_events.iterrows():
        ts = ev['timestamp']
        bias = ev['bias']
        if ts not in m5_ts_map:
            continue
        c0 = m5_ts_map[ts]

        # Forward 12 bars (60 min)
        ts_fwd = ts + 3600
        # Find closest future bar
        c_fwd = next((m5_ts_map[t] for t in range(ts_fwd, ts_fwd + 600, 300) if t in m5_ts_map), None)
        if c_fwd is not None:
            pct_move = ((c_fwd - c0) / c0) * 100.0
            if bias == -1: # Bullish setup failed -> Expect price to drop (negative pct_move)
                drifts_bearish_events.append(pct_move)
            else: # Bearish setup failed -> Expect price to rise (positive pct_move)
                drifts_bullish_events.append(pct_move)

    bear_moves = np.array(drifts_bearish_events)
    bull_moves = np.array(drifts_bullish_events)

    bear_drop_pct = (bear_moves < 0).mean() * 100 if len(bear_moves) > 0 else 0
    bull_rise_pct = (bull_moves > 0).mean() * 100 if len(bull_moves) > 0 else 0

    return {
        "symbol": symbol,
        "bearish_events_count": len(bear_moves),
        "bearish_continuation_winrate": round(bear_drop_pct, 1),
        "bearish_avg_drift_pct": round(float(bear_moves.mean()), 3) if len(bear_moves) > 0 else 0,
        "bullish_events_count": len(bull_moves),
        "bullish_continuation_winrate": round(bull_rise_pct, 1),
        "bullish_avg_drift_pct": round(float(bull_moves.mean()), 3) if len(bull_moves) > 0 else 0,
    }

def main():
    print("=" * 80)
    print("🔬 AUDIT: SETUP FAILURE AS A DIRECTIONAL REGIME ORACLE (1-HOUR DRIFT)")
    print("=" * 80)
    for sym in ["XAUUSD", "NQ", "GBPUSD"]:
        res = audit_failure_oracle(sym)
        print(f"\n--- {sym} ---")
        print(f"When BULLISH Setups Fail (Buyers Trapped):")
        print(f"  Sample Size: {res['bearish_events_count']} events")
        print(f"  Price Continues DOWNWARD (Bearish Edge): {res['bearish_continuation_winrate']}% of the time")
        print(f"  Average 1H Drift: {res['bearish_avg_drift_pct']:+.3f}%")
        print(f"When BEARISH Setups Fail (Sellers Trapped):")
        print(f"  Sample Size: {res['bullish_events_count']} events")
        print(f"  Price Continues UPWARD (Bullish Edge): {res['bullish_continuation_winrate']}% of the time")
        print(f"  Average 1H Drift: {res['bullish_avg_drift_pct']:+.3f}%")

if __name__ == "__main__":
    main()
