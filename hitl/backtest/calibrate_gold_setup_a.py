"""
TradingGuard HITL - Deep Calibration of SETUP-ARCH-001 on Gold (XAUUSD_o)
Analyzes:
1. Directional Asymmetry: SHORT (Bearish Judas fading Highs) vs LONG (Bullish Judas fading Lows)
2. Session Timing: London Open (11:30 - 13:30 Tehran) vs NY Open (16:30 - 18:30 Tehran)
3. Target & Breakeven Surface
4. Max Risk (Stop Loss) Ceiling
5. Seasonal Breakdown across Winter, Spring, Summer, Autumn
"""

import sys
import datetime
from pathlib import Path
from bisect import bisect_right
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hitl.backtest.fast_screener import screen_ict_session
from hitl.screener_gate import tehran_hour_from_bar_time

CACHE_FILE = PROJECT_ROOT / "backtest_results" / "cache" / "M1_XAUUSD_o_2026.parquet"

def run_deep_calibration():
    print("=" * 95)
    print("DEEP FACTOR CALIBRATION OF SETUP-ARCH-001 ON GOLD (XAUUSD_o)")
    print("=" * 95)

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

    signals = []
    for day_idx in range(5, len(trading_dates)):
        day_date = trading_dates[day_idx]
        if day_date.weekday() in (5, 6): continue

        day_m5_indices = [idx for idx, b in enumerate(bars_m5) if b['dt'].date() == day_date]
        if len(day_m5_indices) < 20: continue

        found_lo = False; found_ny = False

        for m5_idx in day_m5_indices:
            curr_b = bars_m5[m5_idx]
            bar_time = curr_b['time']
            th_hour = tehran_hour_from_bar_time(bar_time)

            is_lo = (11 <= th_hour <= 13)
            is_ny = (16 <= th_hour <= 18)
            if not (is_lo or is_ny): continue
            if is_lo and found_lo: continue
            if is_ny and found_ny: continue

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
                signals.append({
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
                })
                if is_lo: found_lo = True
                if is_ny: found_ny = True

    print(f"Collected {len(signals)} raw candidate signals.")

    def run_sim(sig_filter, target_r, be_r, max_risk=15.0):
        trades = []
        days_seen = set()
        for sig in signals:
            if not sig_filter(sig): continue
            d = sig["date"]
            if d in days_seen: continue

            risk = sig["risk"]
            if risk < 3.0 or risk > max_risk: continue

            entry = sig["entry"]
            sl = sig["sl"]
            direction = sig["direction"]
            tp = entry - (target_r * risk) if direction == "SHORT" else entry + (target_r * risk)

            t_epoch = sig["time"]
            m1_idx = m1_map.get(t_epoch)
            if m1_idx is None: continue

            fwd_window = bars_m1[m1_idx + 1 : m1_idx + 481]
            filled = False; fill_idx = 0
            for f_i, f_bar in enumerate(fwd_window):
                if direction == "SHORT" and f_bar['high'] >= entry:
                    filled = True; fill_idx = f_i; break
                elif direction == "LONG" and f_bar['low'] <= entry:
                    filled = True; fill_idx = f_i; break
                if direction == "SHORT" and f_bar['high'] >= sl: break
                elif direction == "LONG" and f_bar['low'] <= sl: break

            if not filled: continue
            days_seen.add(d)

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

            trades.append({"status": status, "net_r": net_r, "risk": risk, "season": sig["dt"].month})

        total = len(trades)
        wins = sum(1 for t in trades if t["status"] == "WIN")
        losses = sum(1 for t in trades if t["status"] == "LOSS")
        bes = sum(1 for t in trades if t["status"] == "BE")
        net_alpha = sum(t["net_r"] for t in trades)
        pf = round((wins * target_r) / (losses * 1.0), 2) if losses > 0 else 99.0
        wr = round(wins / total * 100, 1) if total > 0 else 0.0
        return total, wins, losses, bes, wr, net_alpha, pf

    print("\n--- 1. DIRECTIONAL ASYMMETRY (SHORT vs LONG) ---")
    for d_name, d_check in [("ALL", lambda s: True), ("SHORT ONLY (Bearish Judas High)", lambda s: s["direction"] == "SHORT"), ("LONG ONLY (Bullish Judas Low)", lambda s: s["direction"] == "LONG")]:
        tot, w, l, be, wr, net_r, pf = run_sim(d_check, 2.0, 1.2)
        print(f"{d_name:<35} | {tot:>2} Fills | {w}W-{l}L-{be}B | WR: {wr:>4.1f}% | Net: {net_r:>+5.2f}R | PF: {pf:.2f}")

    print("\n--- 2. SESSION TIMING (LONDON vs NEW YORK) on SHORT TRADES ---")
    for s_name, s_check in [("Both London & NY", lambda s: s["direction"] == "SHORT"), ("London Open Only", lambda s: s["direction"] == "SHORT" and s["session"] == "LONDON"), ("New York Open Only", lambda s: s["direction"] == "SHORT" and s["session"] == "NEW_YORK")]:
        tot, w, l, be, wr, net_r, pf = run_sim(s_check, 2.0, 1.2)
        print(f"{s_name:<35} | {tot:>2} Fills | {w}W-{l}L-{be}B | WR: {wr:>4.1f}% | Net: {net_r:>+5.2f}R | PF: {pf:.2f}")

    print("\n--- 3. TARGET & BREAKEVEN SURFACE (SHORT ONLY) ---")
    for tp, be in [(2.0, 1.2), (2.2, 1.2), (2.0, 1.2), (2.8, 1.2), (3.0, 1.2), (3.5, 1.8)]:
        tot, w, l, be_cnt, wr, net_r, pf = run_sim(lambda s: s["direction"] == "SHORT", tp, be)
        print(f"TP {tp:.1f}R / BE {be:.1f}R {'':<18} | {tot:>2} Fills | {w}W-{l}L-{be_cnt}B | WR: {wr:>4.1f}% | Net: {net_r:>+5.2f}R | PF: {pf:.2f}")

    print("\n--- 4. MAX RISK (STOP LOSS) CEILING (SHORT ONLY, TP 2.0R, BE 1.2R) ---")
    for max_sl in [8.0, 10.0, 12.0, 15.0]:
        tot, w, l, be, wr, net_r, pf = run_sim(lambda s: s["direction"] == "SHORT", 2.0, 1.2, max_risk=max_sl)
        print(f"Max SL ${max_sl:<4.1f} pts {'':<21} | {tot:>2} Fills | {w}W-{l}L-{be}B | WR: {wr:>4.1f}% | Net: {net_r:>+5.2f}R | PF: {pf:.2f}")

    print("\n--- 5. SEASONAL BREAKDOWN (SHORT ONLY, TP 2.0R, BE 1.2R) ---")
    trades_season = []
    days_seen_season = set()
    for sig in signals:
        if sig['direction'] != 'SHORT': continue
        d = sig['date']
        if d in days_seen_season: continue
        risk = sig['risk']
        if risk < 3.0 or risk > 15.0: continue
        entry = sig['entry']; sl = sig['sl']
        tp_price = entry - (2.0 * risk)
        t_epoch = sig['time']
        m1_idx = m1_map.get(t_epoch)
        if m1_idx is None: continue
        fwd_window = bars_m1[m1_idx + 1 : m1_idx + 481]
        filled = False; fill_idx = 0
        for f_i, f_bar in enumerate(fwd_window):
            if f_bar['high'] >= entry: filled = True; fill_idx = f_i; break
            if f_bar['high'] >= sl: break
        if not filled: continue
        days_seen_season.add(d)
        trade_bars = fwd_window[fill_idx:]
        cur_sl = sl; be_active = False; net_r = 0.0; status = 'EXPIRED'
        for tb in trade_bars:
            mfe = (entry - tb['low'] - spread) / risk
            if not be_active and mfe >= 1.2:
                be_active = True
                cur_sl = entry - spread
            hit_sl = (tb['high'] >= cur_sl)
            hit_tp = (tb['low'] <= tp_price)
            if hit_tp: status = 'WIN'; net_r = 2.0; break
            elif hit_sl: status = 'BE' if be_active else 'LOSS'; net_r = 0.0 if be_active else -1.0; break
        m = sig['dt'].month
        s = 'Winter' if m in (12, 1, 2) else ('Spring' if m in (3, 4, 5) else ('Summer' if m in (6, 7, 8) else 'Autumn'))
        trades_season.append({'status': status, 'net_r': net_r, 'season': s})

    for s in ['Winter', 'Spring', 'Summer', 'Autumn']:
        st = [t for t in trades_season if t['season'] == s]
        w = sum(1 for t in st if t['status'] == 'WIN')
        l = sum(1 for t in st if t['status'] == 'LOSS')
        b = sum(1 for t in st if t['status'] == 'BE')
        net = sum(t['net_r'] for t in st)
        pf = round((w * 2.0) / l, 2) if l > 0 else 99.0
        print(f"{s:<8}: {len(st):>2} Fills | {w}W-{l}L-{b}B | Net: {net:>+5.2f}R | PF: {pf:.2f}")

if __name__ == "__main__":
    run_deep_calibration()
