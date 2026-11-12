import sys
import datetime
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.fast_screener import get_session_times_for_date
from hitl.screener_gate import tehran_hour_from_bar_time

def test_today_setup_b():
    cache_file = Path('backtest_results/cache/M1_XAUUSD_o_2026.parquet')
    df = pd.read_parquet(cache_file)
    print(f"Total M1 bars: {len(df)}")

    # Get today's M1 bars
    df_today = df[df.index >= '2026-11-11 00:00:00'].copy()
    print(f"Today M1 bars: {len(df_today)}")

    # Resample M5
    res = df_today['close'].resample('5min').ohlc().dropna()
    res['open'] = df_today['open'].resample('5min').first()
    res['high'] = df_today['high'].resample('5min').max()
    res['low'] = df_today['low'].resample('5min').min()
    res['close'] = df_today['close'].resample('5min').last()
    bars_m5 = []
    for idx, row in res.iterrows():
        bars_m5.append({
            'time': int(idx.timestamp()),
            'dt': idx.to_pydatetime(),
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
        })

    print(f"Today M5 bars: {len(bars_m5)}")

    # Let's inspect when 5M MSS happened
    # Asian high: max of 00:00 to 07:00 UTC (or server 02:00 to 09:00)
    asian_bars = [b for b in bars_m5 if 0 <= b['dt'].hour < 7]
    a_high = max(b['high'] for b in asian_bars) if asian_bars else 4065.88
    print(f"Asian High: {a_high}")

    # Find sweep of Asian High
    sweep_bar = None
    for b in bars_m5:
        if b['high'] > a_high:
            sweep_bar = b
            print(f"Sweep Bar: {b['dt']} -> High: {b['high']}")
            break

    # Origin swing low before sweep:
    # 08:40 bar had low 4053.95
    origin_low = 4053.95
    print(f"Origin Swing Low: {origin_low}")

    # Find displacement close below origin_low
    disp_bar = None
    for b in bars_m5:
        if b['dt'] > sweep_bar['dt'] and b['close'] < origin_low:
            disp_bar = b
            print(f"Displacement Bar: {b['dt']} -> Close: {b['close']} < {origin_low}")
            break

    # Pre-break local high between sweep and displacement
    interim_bars = [b for b in bars_m5 if sweep_bar['dt'] < b['dt'] < disp_bar['dt']]
    local_high = max(b['high'] for b in interim_bars)
    print(f"Local Pre-Break High: {local_high}")

    entry = origin_low
    sl = round(local_high + 1.50, 2)
    risk = round(sl - entry, 2)
    tp_35 = round(entry - (3.5 * risk), 2)
    print(f"Setup B Order: SELL LIMIT @ {entry} | SL: {sl} (Risk: {risk} pts) | TP (3.5R): {tp_35}")

    # Check forward M1 fill after disp_bar
    disp_time = disp_bar['dt']
    forward_m1 = df_today[df_today.index > disp_time]
    fill_time = None
    for idx, row in forward_m1.iterrows():
        if row['high'] >= entry:
            fill_time = idx
            print(f"✅ Setup B FILLED at {fill_time} | Bar High: {row['high']} >= {entry}")
            break

    if fill_time:
        trade_bars = forward_m1[forward_m1.index >= fill_time]
        cur_sl = sl
        be_active = False
        status = "OPEN"
        for idx, row in trade_bars.iterrows():
            mfe = (entry - row['low']) / risk
            if mfe >= 1.8 and not be_active:
                be_active = True
                cur_sl = entry - 0.20
                print(f"   🛡️ Breakeven activated at {idx} (+{mfe:.2f}R)")
            if row['high'] >= cur_sl:
                status = "BE" if be_active else "LOSS"
                print(f"   Exited at SL/BE: {cur_sl} at {idx} (Status: {status})")
                break
            if row['low'] <= tp_35:
                status = "WIN"
                print(f"   🎉 WIN! Hit TP {tp_35} at {idx} (+3.50R)")
                break

test_today_setup_b()
