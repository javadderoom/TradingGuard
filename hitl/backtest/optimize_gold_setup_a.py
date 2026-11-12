"""
TradingGuard HITL - Quantitative Optimization & Calibration of SETUP-ARCH-001 on Gold (XAUUSD_o)
Tests institutional hypotheses across the 305,293 M1 broker bars of 2026:
1. Baseline (Unfiltered 3.5R, BE 1.8R, All Phases, Both Sessions)
2. HTF Orderflow Alignment: Gated to PRO_EXPANSION only vs Vetoing HTF_RETRACEMENT
3. Target Calibration: 2.0R, 2.5R, 3.0R, 3.5R with matched BE thresholds
4. Session Calibration: London Open only vs NY Open only vs Both
5. Stop Loss Tightening: Max Risk $8.0, $10.0, $12.0, $15.0 pts
"""

import sys
import json
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from bisect import bisect_right
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hitl.backtest.fast_screener import screen_ict_session
from hitl.screener_gate import tehran_hour_from_bar_time

CACHE_FILE = PROJECT_ROOT / "backtest_results" / "cache" / "M1_XAUUSD_o_2026.parquet"

def run_optimization():
    print("=" * 80)
    print("OPTIMIZING SETUP-ARCH-001 ON GOLD (XAUUSD_o) ACROSS 12 MONTHS (2026)")
    print("=" * 80)

    df_raw = pd.read_parquet(CACHE_FILE)
    df_raw['dt'] = pd.to_datetime(df_raw['time'], unit='s', utc=True)
    df_bars = df_raw.set_index('dt').sort_index()

    bars_m1 = [
        {
            'time': int(idx.timestamp()),
            'dt': idx.to_pydatetime(),
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
        }
        for idx, row in df_bars.iterrows()
    ]
    m1_map = {b['time']: i for i, b in enumerate(bars_m1)}

    def _resample(rule: str):
        r = df_bars['close'].resample(rule).ohlc().dropna()
        r['open'] = df_bars['open'].resample(rule).first()
        r['high'] = df_bars['high'].resample(rule).max()
        r['low'] = df_bars['low'].resample(rule).min()
        r['close'] = df_bars['close'].resample(rule).last()
        out = []
        for idx, row in r.iterrows():
            out.append({
                'time': int(idx.timestamp()),
                'dt': idx.to_pydatetime(),
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
            })
        out.sort(key=lambda x: x['time'])
        return out

    bars_m5 = _resample("5min")
    bars_h1 = _resample("60min")
    bars_d1 = _resample("1D")

    trading_dates = sorted(list(set(b['dt'].date() for b in bars_m5)))
    h1_times = [b['time'] for b in bars_h1]
    d1_times = [b['time'] for b in bars_d1]

    spread = 0.20

    # Collect all raw candidate signals first to avoid re-screening multiple times
    print("🔍 Screening all raw SETUP-ARCH-001 candidates across 2026...")
    candidate_signals = []

    for day_idx in range(5, len(trading_dates)):
        day_date = trading_dates[day_idx]
        if day_date.weekday() in (5, 6):
            continue

        day_m5_indices = [idx for idx, b in enumerate(bars_m5) if b['dt'].date() == day_date]
        if len(day_m5_indices) < 20:
            continue

        found_today_lo = False
        found_today_ny = False

        for m5_idx in day_m5_indices:
            curr_b = bars_m5[m5_idx]
            bar_time = curr_b['time']
            th_hour = tehran_hour_from_bar_time(bar_time)

            is_lo = (11 <= th_hour <= 13)
            is_ny = (16 <= th_hour <= 18)

            if not (is_lo or is_ny):
                continue
            if is_lo and found_today_lo:
                continue
            if is_ny and found_today_ny:
                continue

            hist_m5 = bars_m5[max(0, m5_idx - 120) : m5_idx + 1]
            h1_idx = bisect_right(h1_times, bar_time)
            hist_h1 = bars_h1[max(0, h1_idx - 60) : h1_idx]
            d1_idx = bisect_right(d1_times, bar_time)
            hist_d1 = bars_d1[max(0, d1_idx - 15) : d1_idx]

            res = screen_ict_session(
                bars_5m=hist_m5,
                bars_1h=hist_h1,
                symbol="XAUUSD_o",
                session_hour=th_hour,
                bars_1m=None,
                bars_1d=hist_d1,
                closed_bars_only=True
            )

            if res.get("has_setup") and res.get("archetype_id") == "SETUP-ARCH-001":
                direction = "SHORT" if "BEARISH" in res.get("setup_type", "") else "LONG"
                candidate_signals.append({
                    "date": str(day_date),
                    "time": bar_time,
                    "dt": curr_b['dt'],
                    "session": "LONDON" if is_lo else "NEW_YORK",
                    "direction": direction,
                    "entry": res.get("entry_ref"),
                    "sl": res.get("sl_ref"),
                    "risk": abs(res.get("entry_ref") - res.get("sl_ref")),
                    "phase": res.get("phase"),
                    "h1_state": res.get("mtf_info", {}).get("h1_state"),
                    "is_inside_day": res.get("mtf_info", {}).get("is_inside_day"),
                    "in_mid_equilibrium": res.get("mtf_info", {}).get("in_mid_equilibrium")
                })
                if is_lo: found_today_lo = True
                if is_ny: found_today_ny = True

    print(f"✅ Found {len(candidate_signals)} candidate signals across 2026.")

    # Helper simulator
    def simulate_trades(signals, target_r, be_r, max_risk_pts=15.0, min_risk_pts=3.0, allowed_sessions=("LONDON", "NEW_YORK"), allowed_phases=None):
        trades = []
        # One trade per day maximum
        trades_per_day = set()

        for sig in signals:
            day_str = sig["date"]
            if day_str in trades_per_day:
                continue

            if sig["session"] not in allowed_sessions:
                continue

            if allowed_phases is not None and sig["phase"] not in allowed_phases:
                continue

            risk = sig["risk"]
            if risk < min_risk_pts or risk > max_risk_pts:
                continue

            entry = sig["entry"]
            sl = sig["sl"]
            direction = sig["direction"]
            tp = entry - (target_r * risk) if direction == "SHORT" else entry + (target_r * risk)

            t_epoch = sig["time"]
            m1_idx = m1_map.get(t_epoch)
            if m1_idx is None:
                continue

            fwd_window = bars_m1[m1_idx + 1 : m1_idx + 481] # 8 hours TTL
            filled = False
            fill_idx = 0
            for f_i, f_bar in enumerate(fwd_window):
                if direction == "SHORT" and f_bar['high'] >= entry:
                    filled = True; fill_idx = f_i; break
                elif direction == "LONG" and f_bar['low'] <= entry:
                    filled = True; fill_idx = f_i; break
                if direction == "SHORT" and f_bar['high'] >= sl: break
                elif direction == "LONG" and f_bar['low'] <= sl: break

            if not filled:
                continue

            trades_per_day.add(day_str)
            trade_bars = fwd_window[fill_idx:]
            cur_sl = sl
            be_active = False
            net_r = 0.0
            status = "EXPIRED"

            for tb in trade_bars:
                if direction == "SHORT":
                    mfe = (entry - tb['low'] - spread) / risk
                else:
                    mfe = (tb['high'] - entry - spread) / risk

                if not be_active and mfe >= be_r:
                    be_active = True
                    cur_sl = entry - spread if direction == "SHORT" else entry + spread

                hit_sl = (tb['high'] >= cur_sl) if direction == "SHORT" else (tb['low'] <= cur_sl)
                hit_tp = (tb['low'] <= tp) if direction == "SHORT" else (tb['high'] >= tp)

                if hit_tp:
                    status = "WIN"; net_r = target_r; break
                elif hit_sl:
                    status = "BE" if be_active else "LOSS"
                    net_r = 0.0 if be_active else -1.0
                    break

            trades.append({
                "status": status,
                "net_r": net_r,
                "risk": risk,
                "phase": sig["phase"],
                "session": sig["session"]
            })

        wins = sum(1 for t in trades if t["status"] == "WIN")
        losses = sum(1 for t in trades if t["status"] == "LOSS")
        bes = sum(1 for t in trades if t["status"] == "BE")
        exps = sum(1 for t in trades if t["status"] == "EXPIRED")
        total = len(trades)
        net_alpha = sum(t["net_r"] for t in trades)
        gross_win = wins * target_r
        gross_loss = losses * 1.0
        pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 99.0
        wr = round(wins / total * 100, 1) if total > 0 else 0.0

        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "bes": bes,
            "exps": exps,
            "wr": wr,
            "net_r": round(net_alpha, 2),
            "pf": pf
        }

    # Experiments
    configs = [
        ("Baseline (All Phases, Both Sessions, TP 3.5R, BE 1.8R, Max SL 15)", 3.5, 1.8, 15.0, ("LONDON", "NEW_YORK"), None),
        ("Exp 1: London Open Only (TP 3.5R, BE 1.8R, Max SL 15)", 3.5, 1.8, 15.0, ("LONDON",), None),
        ("Exp 2: NY Open Only (TP 3.5R, BE 1.8R, Max SL 15)", 3.5, 1.8, 15.0, ("NEW_YORK",), None),
        ("Exp 3: Gated to PRO_EXPANSION Only (Both Sessions, TP 3.5R, BE 1.8R)", 3.5, 1.8, 15.0, ("LONDON", "NEW_YORK"), ("PRO_EXPANSION",)),
        ("Exp 4: Exclude HTF_RETRACEMENT (Allow PRO_EXPANSION + BALANCED_RANGE)", 3.5, 1.8, 15.0, ("LONDON", "NEW_YORK"), ("PRO_EXPANSION", "BALANCED_RANGE")),
        ("Exp 5: Target 2.5R (BE 1.5R, Both Sessions, All Phases)", 2.5, 1.5, 15.0, ("LONDON", "NEW_YORK"), None),
        ("Exp 6: Target 2.5R + Gated PRO_EXPANSION (BE 1.5R)", 2.5, 1.5, 15.0, ("LONDON", "NEW_YORK"), ("PRO_EXPANSION",)),
        ("Exp 7: Target 2.5R + Exclude HTF_RETRACEMENT (BE 1.5R)", 2.5, 1.5, 15.0, ("LONDON", "NEW_YORK"), ("PRO_EXPANSION", "BALANCED_RANGE")),
        ("Exp 8: Target 3.0R + Exclude HTF_RETRACEMENT (BE 1.5R)", 3.0, 1.5, 15.0, ("LONDON", "NEW_YORK"), ("PRO_EXPANSION", "BALANCED_RANGE")),
        ("Exp 9: Max SL 10.0 pts (TP 3.5R, BE 1.8R, Exclude HTF_RETRACEMENT)", 3.5, 1.8, 10.0, ("LONDON", "NEW_YORK"), ("PRO_EXPANSION", "BALANCED_RANGE")),
        ("Exp 10: London Only + Exclude HTF_RETRACEMENT (TP 3.5R, BE 1.8R)", 3.5, 1.8, 15.0, ("LONDON",), ("PRO_EXPANSION", "BALANCED_RANGE")),
        ("Exp 11: London Only + Target 2.5R + BE 1.5R", 2.5, 1.5, 15.0, ("LONDON",), None),
    ]

    print("\n" + "=" * 95)
    print(f"{'Configuration':<65} | {'Fills':<5} | {'W-L-BE':<10} | {'WR%':<6} | {'Net R':<8} | {'PF':<5}")
    print("-" * 95)

    for name, tp_r, be_r, max_sl, sess, phases in configs:
        res = simulate_trades(candidate_signals, tp_r, be_r, max_risk_pts=max_sl, allowed_sessions=sess, allowed_phases=phases)
        w_l_be = f"{res['wins']}W-{res['losses']}L-{res['bes']}B"
        print(f"{name:<65} | {res['total']:<5} | {w_l_be:<10} | {res['wr']:<5.1f}% | {res['net_r']:<+7.2f}R | {res['pf']:<5.2f}")

    print("=" * 95)

if __name__ == "__main__":
    run_optimization()
