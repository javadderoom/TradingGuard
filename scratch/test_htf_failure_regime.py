"""
TradingGuard Quantitative Audit: HTF Structural Failure as a Regime Filter
Tests:
1. What happens when a 1H Market Structure Shift (MSS) FAILS?
   (A Bullish MSS fails when price breaks below its structural swing trough)
2. What happens when an Asian Range Breakout FAILS at London Open?
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
    
    df_m5 = pd.read_parquet(m5_path)
    if 'time' in df_m5.columns:
        df_m5['timestamp'] = df_m5['time'].astype(np.int64)
    else:
        df_m5['timestamp'] = df_m5.index.astype(np.int64) // 10**9
    df_m5 = df_m5.drop_duplicates('timestamp').sort_values('timestamp').reset_index(drop=True)
    df_m5['dt'] = pd.to_datetime(df_m5['timestamp'], unit='s', utc=True)

    # Build H1
    df_m5['h1_bucket'] = df_m5['timestamp'] // 3600 * 3600
    df_h1 = df_m5.groupby('h1_bucket').agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last')
    ).reset_index().rename(columns={'h1_bucket': 'timestamp'})
    df_h1['dt'] = pd.to_datetime(df_h1['timestamp'], unit='s', utc=True)
    return df_m5, df_h1


def audit_htf_mss_failure(symbol: str):
    df_m5, df_h1 = load_data(symbol)
    h1 = df_h1.to_dict('records')
    n = len(h1)

    # Simple 5-bar fractal swings
    bull_mss_failures = []
    bear_mss_failures = []

    for i in range(5, n - 24):
        # Swing High at i-2
        if (h1[i-2]['high'] > h1[i-4]['high'] and 
            h1[i-2]['high'] > h1[i-3]['high'] and 
            h1[i-2]['high'] > h1[i-1]['high'] and 
            h1[i-2]['high'] > h1[i]['high']):
            sh_price = h1[i-2]['high']
            
            # Lowest low preceding this swing high
            sl_trough = min(h1[k]['low'] for k in range(max(0, i-8), i-2))

            # Look forward: Does price break SH (Bullish MSS)?
            for j in range(i + 1, min(i + 15, n)):
                if h1[j]['close'] > sh_price:
                    # Bullish MSS triggered! Invalidation level is sl_trough
                    # Now check: Does this Bullish MSS FAIL by breaking below sl_trough?
                    for k in range(j + 1, min(j + 24, n)):
                        if h1[k]['close'] < sl_trough:
                            # FAILED Bullish MSS!
                            # Trapped buyers offside. What is the 4H/8H forward drift?
                            c_fail = h1[k]['close']
                            c_fwd_4h = h1[min(k + 4, n - 1)]['close']
                            c_fwd_8h = h1[min(k + 8, n - 1)]['close']
                            drift_4h = ((c_fwd_4h - c_fail) / c_fail) * 100.0
                            drift_8h = ((c_fwd_8h - c_fail) / c_fail) * 100.0
                            bull_mss_failures.append({
                                "drift_4h": drift_4h,
                                "drift_8h": drift_8h
                            })
                            break
                    break

        # Swing Low at i-2
        if (h1[i-2]['low'] < h1[i-4]['low'] and 
            h1[i-2]['low'] < h1[i-3]['low'] and 
            h1[i-2]['low'] < h1[i-1]['low'] and 
            h1[i-2]['low'] < h1[i]['low']):
            sl_price = h1[i-2]['low']
            sh_crest = max(h1[k]['high'] for k in range(max(0, i-8), i-2))

            for j in range(i + 1, min(i + 15, n)):
                if h1[j]['close'] < sl_price:
                    # Bearish MSS triggered!
                    for k in range(j + 1, min(j + 24, n)):
                        if h1[k]['close'] > sh_crest:
                            # FAILED Bearish MSS!
                            c_fail = h1[k]['close']
                            c_fwd_4h = h1[min(k + 4, n - 1)]['close']
                            c_fwd_8h = h1[min(k + 8, n - 1)]['close']
                            drift_4h = ((c_fwd_4h - c_fail) / c_fail) * 100.0
                            drift_8h = ((c_fwd_8h - c_fail) / c_fail) * 100.0
                            bear_mss_failures.append({
                                "drift_4h": drift_4h,
                                "drift_8h": drift_8h
                            })
                            break
                    break

    df_bull_fail = pd.DataFrame(bull_mss_failures)
    df_bear_fail = pd.DataFrame(bear_mss_failures)

    return {
        "symbol": symbol,
        "bull_mss_fail_count": len(df_bull_fail),
        "bull_fail_drop_4h_pct": round((df_bull_fail['drift_4h'] < 0).mean() * 100, 1) if not df_bull_fail.empty else 0,
        "bull_fail_drop_8h_pct": round((df_bull_fail['drift_8h'] < 0).mean() * 100, 1) if not df_bull_fail.empty else 0,
        "bull_fail_avg_drop_8h": round(float(df_bull_fail['drift_8h'].mean()), 2) if not df_bull_fail.empty else 0,
        "bear_mss_fail_count": len(df_bear_fail),
        "bear_fail_rise_4h_pct": round((df_bear_fail['drift_4h'] > 0).mean() * 100, 1) if not df_bear_fail.empty else 0,
        "bear_fail_rise_8h_pct": round((df_bear_fail['drift_8h'] > 0).mean() * 100, 1) if not df_bear_fail.empty else 0,
        "bear_fail_avg_rise_8h": round(float(df_bear_fail['drift_8h'].mean()), 2) if not df_bear_fail.empty else 0,
    }


def main():
    print("=" * 80)
    print("🔬 AUDIT: HTF STRUCTURAL FAILURE AS A REGIME FILTER (1H MSS INVALIDATION)")
    print("=" * 80)
    for sym in ["XAUUSD", "NQ", "GBPUSD"]:
        res = audit_htf_mss_failure(sym)
        print(f"\n--- {sym} ---")
        print(f"When a 1H BULLISH MSS FAILS (Breaks Invalidation Low):")
        print(f"  Sample Events: {res['bull_mss_fail_count']}")
        print(f"  Price Continues SINKING at 4 Hours: {res['bull_fail_drop_4h_pct']}% of the time")
        print(f"  Price Continues SINKING at 8 Hours: {res['bull_fail_drop_8h_pct']}% of the time")
        print(f"  Average 8H Drawdown Drift: {res['bull_fail_avg_drop_8h']:+.2f}%")
        print(f"When a 1H BEARISH MSS FAILS (Breaks Invalidation High):")
        print(f"  Sample Events: {res['bear_mss_fail_count']}")
        print(f"  Price Continues RISING at 4 Hours: {res['bear_fail_rise_4h_pct']}% of the time")
        print(f"  Price Continues RISING at 8 Hours: {res['bear_fail_rise_8h_pct']}% of the time")
        print(f"  Average 8H Upward Drift: {res['bear_fail_avg_rise_8h']:+.2f}%")

if __name__ == "__main__":
    main()
