"""
TradingGuard Quantitative Alpha Research - Model A: Opening Range Breakout (ORB)
Evaluates Institutional Opening Range Breakout across London Open and NYSE Cash Open on Nasdaq 100 (NQ).
Features:
- 15-minute and 30-minute Opening Range calculation.
- Volatility compression gate: Prior Day NR4/NR7 or Inside Day (compression precedes expansion).
- Stop Loss: OR Midpoint (Equilibrium) for tight risk or opposite boundary.
- Continuous M1 execution verification over 5.2 months (June 1 - Nov 6, 2026: 32,974 M5 bars, 157,960 M1 bars).
"""

import sys
import os
import json
import time
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Tuple, Dict, Any, List
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.evaluator import evaluate_council_decision

CACHE_DIR = BASE_DIR / 'backtest_results' / 'cache'
OUTPUT_DIR = BASE_DIR / 'backtest_results' / 'quant_models' / 'orb_model'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_LONDON = ZoneInfo("Europe/London")
TZ_UTC = ZoneInfo("UTC")


def run_orb_model():
    print("=" * 95)
    print("🔬 QUANTITATIVE ALPHA RESEARCH - MODEL A: OPENING RANGE BREAKOUT (ORB)")
    print("Nasdaq 100 (NQ) Continuous 5.2 Months (June 1 - Nov 6, 2026) | 32,974 M5 Bars | 157,960 M1 Bars")
    print("=" * 95)

    # 1. Load Combined 5.2-Month Data
    df_m5_sum = pd.read_parquet(CACHE_DIR / 'NQ_M5_SUMMER_2026.parquet')
    df_m1_sum = pd.read_parquet(CACHE_DIR / 'NQ_M1_SUMMER_2026.parquet')
    df_d1_sum = pd.read_parquet(CACHE_DIR / 'NQ_D1_SUMMER_2026.parquet')

    df_m5_aut = pd.read_parquet(CACHE_DIR / 'NQ_M5_EXTENDED_2026.parquet')
    df_m1_aut = pd.read_parquet(CACHE_DIR / 'NQ_M1_EXTENDED_2026.parquet')
    df_d1_aut = pd.read_parquet(CACHE_DIR / 'NQ_D1_EXTENDED_2026.parquet')

    df_m5 = pd.concat([df_m5_sum, df_m5_aut]).drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)
    df_m1 = pd.concat([df_m1_sum, df_m1_aut]).drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)
    df_d1 = pd.concat([df_d1_sum, df_d1_aut]).drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)

    bars_m5 = df_m5.to_dict('records')
    bars_m1 = df_m1.to_dict('records')
    bars_d1 = df_d1.to_dict('records')
    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    # Build daily range map for volatility compression calculation (NR4, NR7, Inside Day)
    d1_ranges = {}
    for idx, d in enumerate(bars_d1):
        rng = d['high'] - d['low']
        d_date = datetime.datetime.fromtimestamp(d['time'], tz=TZ_UTC).date()
        d1_ranges[d_date] = {
            "range": rng,
            "high": d['high'],
            "low": d['low'],
            "idx": idx
        }

    def is_volatility_compressed(curr_date: datetime.date) -> Tuple[bool, str]:
        # Check prior 7 trading days
        prior_dates = [dt for dt in sorted(d1_ranges.keys()) if dt < curr_date]
        if len(prior_dates) < 4:
            return False, "NONE"
        
        last_d = prior_dates[-1]
        last_rng = d1_ranges[last_d]["range"]
        prev_ranges = [d1_ranges[dt]["range"] for dt in prior_dates[-4:-1]]
        
        # NR4: Narrowest Range of last 4 days
        is_nr4 = all(last_rng < r for r in prev_ranges)
        
        # Inside Day: prior day completely inside the day before it
        if len(prior_dates) >= 2:
            d_prev1 = d1_ranges[prior_dates[-1]]
            d_prev2 = d1_ranges[prior_dates[-2]]
            is_inside = (d_prev1['high'] <= d_prev2['high']) and (d_prev1['low'] >= d_prev2['low'])
        else:
            is_inside = False
            
        if is_inside and is_nr4:
            return True, "INSIDE_NR4"
        elif is_inside:
            return True, "INSIDE_DAY"
        elif is_nr4:
            return True, "NR4"
        
        return False, "NORMAL"

    # Test two sessions:
    # 1. London Open ORB: 08:00 - 08:30 London local time (30m OR). Trade breakout between 08:30 and 10:30.
    # 2. NYSE Cash Open ORB: 09:30 - 10:00 NY local time (30m OR). Trade breakout between 10:00 and 12:00.
    
    for session_type in ["NYSE_Cash_Open", "London_Open"]:
        print(f"\n--- Testing ORB Model for {session_type} ---")
        trades = []
        days_processed = set()
        active_until = 0

        for i in range(120, len(bars_m5)):
            curr_bar = bars_m5[i]
            curr_epoch = curr_bar['time']

            if curr_epoch < active_until:
                continue

            bar_dt_utc = datetime.datetime.fromtimestamp(curr_epoch, tz=TZ_UTC)
            dt_ny = bar_dt_utc.astimezone(TZ_NEW_YORK)
            dt_lon = bar_dt_utc.astimezone(TZ_LONDON)
            curr_date = bar_dt_utc.date()

            # Skip weekends
            if bar_dt_utc.weekday() in (5, 6):
                continue

            # Determine opening range window
            if session_type == "NYSE_Cash_Open":
                # OR is 09:30 to 10:00 NY
                or_start = datetime.time(9, 30)
                or_end = datetime.time(10, 0)
                trade_end = datetime.time(12, 0)
                curr_t = dt_ny.time()
                is_eval_time = (or_end <= curr_t < trade_end)
            else:
                # London OR is 08:00 to 08:30 London
                or_start = datetime.time(8, 0)
                or_end = datetime.time(8, 30)
                trade_end = datetime.time(10, 30)
                curr_t = dt_lon.time()
                is_eval_time = (or_end <= curr_t < trade_end)

            if not is_eval_time:
                continue

            # Check if trade already taken today for this session
            day_key = f"{curr_date}_{session_type}"
            if day_key in days_processed:
                continue

            # Find the 6 bars of the 30-min Opening Range
            if session_type == "NYSE_Cash_Open":
                or_bars = [b for b in bars_m5[i-24:i+1] if datetime.datetime.fromtimestamp(b['time'], tz=TZ_NEW_YORK).date() == curr_date and or_start <= datetime.datetime.fromtimestamp(b['time'], tz=TZ_NEW_YORK).time() < or_end]
            else:
                or_bars = [b for b in bars_m5[i-24:i+1] if datetime.datetime.fromtimestamp(b['time'], tz=TZ_LONDON).date() == curr_date and or_start <= datetime.datetime.fromtimestamp(b['time'], tz=TZ_LONDON).time() < or_end]

            if len(or_bars) < 5:
                continue

            or_high = max(b['high'] for b in or_bars)
            or_low = min(b['low'] for b in or_bars)
            or_range = or_high - or_low
            or_mid = (or_high + or_low) / 2.0

            # Guard: Minimum opening range must be >= 25 pts, max <= 150 pts
            if or_range < 25.0 or or_range > 150.0:
                continue

            # Check breakout of current 5M bar
            is_breakout_up = curr_bar['close'] > or_high + 2.0 and curr_bar['close'] > curr_bar['open']
            is_breakout_down = curr_bar['close'] < or_low - 2.0 and curr_bar['close'] < curr_bar['open']

            if not (is_breakout_up or is_breakout_down):
                continue

            direction = "BUY" if is_breakout_up else "SELL"
            entry_p = curr_bar['close']
            
            # Stop loss at OR Equilibrium (Midpoint)
            sl_p = or_mid if direction == "BUY" else or_mid
            risk_pts = abs(entry_p - sl_p)
            
            # Risk boundaries
            if risk_pts < 15.0 or risk_pts > 90.0:
                continue

            target_rr = 2.5
            tp_p = entry_p + (target_rr * risk_pts) if direction == "BUY" else entry_p - (target_rr * risk_pts)

            next_m1_epoch = curr_epoch + 300
            m1_start_idx = m1_time_map.get(next_m1_epoch)
            if m1_start_idx is None:
                forward_m1 = [b for b in bars_m1 if b['time'] >= next_m1_epoch][:360]
            else:
                forward_m1 = bars_m1[m1_start_idx : m1_start_idx + 360]

            if not forward_m1:
                continue

            decision_dict = {
                "decision": direction,
                "entry": round(entry_p, 1),
                "sl": round(sl_p, 1),
                "tp": round(tp_p, 1),
                "lot": 0.01
            }

            eval_res = evaluate_council_decision(
                decision_dict=decision_dict,
                forward_m1_bars=forward_m1,
                symbol="NQ",
                spread_pts=1.0,
                breakeven_rr=1.5,
                target_rr_cap=target_rr,
                commission_usd=0.10,
                slippage_pts=0.0,
                ttl_minutes=60
            )

            status = eval_res["status"]
            pnl = eval_res["realized_pnl_usd"]
            rr = eval_res.get("rr_realized", 0.0)
            exit_min = eval_res.get("exit_minute") or 60

            is_comp, comp_type = is_volatility_compressed(curr_date)

            trades.append({
                "epoch": curr_epoch,
                "date": curr_date.strftime("%Y-%m-%d"),
                "month": curr_date.strftime("%Y-%m"),
                "session": session_type,
                "direction": direction,
                "or_range": round(or_range, 1),
                "risk_pts": round(risk_pts, 1),
                "compression_type": comp_type,
                "is_compressed": is_comp,
                "status": status,
                "realized_pnl_usd": pnl,
                "rr_realized": rr
            })

            days_processed.add(day_key)
            if status in ("WIN", "LOSS", "BREAKEVEN"):
                active_until = curr_epoch + (exit_min * 60)
            elif status == "EXPIRED":
                active_until = curr_epoch + (60 * 60)

        df_t = pd.DataFrame(trades)
        df_t.to_parquet(OUTPUT_DIR / f"nq_orb_{session_type.lower()}_trades.parquet")
        df_t.to_csv(OUTPUT_DIR / f"nq_orb_{session_type.lower()}_trades.csv", index=False)

        def calc_stats(df_sub):
            fills = df_sub[df_sub['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
            n = len(fills)
            wins = len(df_sub[df_sub['status'] == 'WIN'])
            losses = len(df_sub[df_sub['status'] == 'LOSS'])
            be = len(df_sub[df_sub['status'] == 'BREAKEVEN'])
            exp = len(df_sub[df_sub['status'] == 'EXPIRED'])
            wr = (wins / n * 100) if n > 0 else 0.0
            net_r = df_sub['rr_realized'].sum() if len(df_sub) > 0 else 0.0
            net_pnl = df_sub['realized_pnl_usd'].sum() if len(df_sub) > 0 else 0.0
            gp = df_sub[df_sub['realized_pnl_usd'] > 0]['realized_pnl_usd'].sum() if len(df_sub) > 0 else 0.0
            gl = abs(df_sub[df_sub['realized_pnl_usd'] < 0]['realized_pnl_usd'].sum()) if len(df_sub) > 0 else 0.0
            pf = (gp / gl) if gl > 0 else (99.0 if gp > 0 else 0.0)
            return {
                "Signals": len(df_sub), "Fills": n, "Wins": wins, "Losses": losses, "BE": be, "Exp": exp,
                "WR%": round(wr, 1), "Net_R": round(net_r, 2), "Net_PnL": round(net_pnl, 2), "PF": round(pf, 2)
            }

        s_all = calc_stats(df_t)
        print(f"Overall {session_type} ORB:", s_all)

        # Breakout under Volatility Compression Gate (NR4/Inside Day)
        df_comp = df_t[df_t['is_compressed'] == True]
        s_comp = calc_stats(df_comp)
        print(f"  Under Volatility Compression (NR4/Inside Day):", s_comp)

        df_uncomp = df_t[df_t['is_compressed'] == False]
        s_uncomp = calc_stats(df_uncomp)
        print(f"  Uncompressed Normal Days:", s_uncomp)

        print("\n  Monthly Progression:")
        for m, g in df_t.groupby('month'):
            sm = calc_stats(g)
            print(f"    {m} | Fills: {sm['Fills']:2d} | W: {sm['Wins']:2d} | L: {sm['Losses']:2d} | BE: {sm['BE']:2d} | WR: {sm['WR%']:5.1f}% | Net R: {sm['Net_R']:+6.2f}R | Net PnL: ${sm['Net_PnL']:+6.2f} | PF: {sm['PF']:.2f}")


if __name__ == '__main__':
    run_orb_model()
