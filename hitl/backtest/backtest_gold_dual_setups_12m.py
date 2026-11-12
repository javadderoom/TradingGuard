"""
TradingGuard HITL - Full-Year 2026 Comparative Backtest Audit: Gold (XAUUSD_o)
Evaluates two distinct execution architectures across 12 months (305,293 M1 bars / 700 sessions):

1. Setup A (SETUP-ARCH-001):
   - Judas Swing Liquidity Sweep & Breaker Block Retest.
   - Entry: Passive limit at 5M Breaker Block (top range).
   - Stop Loss: Anchored above Sweep High (+1.50 buffer).
   - Target: 3.5R | BE: +1.8R ratchet.

2. Setup B (User's Setup / SETUP-ARCH-015):
   - 5M Origin Swing MSS Retest (Support-to-Resistance Flip).
   - Entry: Retest of the broken Originating Swing Low (macro 5M MSS level).
   - Stop Loss: Pre-breakdown local swing high (+1.50 buffer).
   - Target: 3.5R (and 2.5R) | BE: +1.8R ratchet.
"""

import sys
import json
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, List, Any, Tuple, Optional
import pandas as pd
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hitl.backtest.fast_screener import screen_ict_session, get_session_times_for_date
from hitl.screener_gate import tehran_hour_from_bar_time

CACHE_FILE = PROJECT_ROOT / "backtest_results" / "cache" / "M1_XAUUSD_o_2026.parquet"
OUT_DIR = PROJECT_ROOT / "backtest_results" / "master_portfolio_audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def get_season(dt: datetime.datetime) -> str:
    m = dt.month
    if m in (12, 1, 2): return "Winter"
    elif m in (3, 4, 5): return "Spring"
    elif m in (6, 7, 8): return "Summer"
    elif m in (9, 10, 11): return "Autumn"
    return "Unknown"

def run_dual_backtest():
    print("=" * 95)
    print("🏛️ TRADINGGUARD - FULL-YEAR 2026 GOLD COMPARATIVE AUDIT: SETUP A vs SETUP B")
    print("=" * 95)

    if not CACHE_FILE.exists():
        print(f"❌ Cache file not found: {CACHE_FILE}")
        return

    print(f"📂 Loading Gold M1 microstructure data from: {CACHE_FILE}...")
    df_m1 = pd.read_parquet(CACHE_FILE)
    print(f"✅ Loaded {len(df_m1):,} M1 bars spanning from {df_m1.index[0]} to {df_m1.index[-1]}")

    # Build M1 list and index map
    bars_m1 = []
    for row in df_m1.itertuples():
        bars_m1.append({
            'time': int(row.time),
            'dt': row.Index.to_pydatetime() if hasattr(row.Index, 'to_pydatetime') else row.Index,
            'open': float(row.open),
            'high': float(row.high),
            'low': float(row.low),
            'close': float(row.close),
            'tick_volume': int(row.tick_volume) if hasattr(row, 'tick_volume') else 0
        })

    m1_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    # Resample to M5, H1, D1
    print("🔄 Resampling M5, H1, D1 bars...")
    df_bars = pd.DataFrame(bars_m1)
    df_bars['datetime'] = pd.to_datetime(df_bars['time'], unit='s', utc=True)
    df_bars.set_index('datetime', inplace=True)

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
    print(f"✅ Created {len(bars_m5):,} M5 bars | {len(bars_h1):,} H1 bars | {len(bars_d1):,} D1 bars")

    # Group by trading dates
    trading_dates = sorted(list(set(b['dt'].date() for b in bars_m5)))
    print(f"📅 Total unique trading days: {len(trading_dates)}")

    from bisect import bisect_right
    h1_times = [b['time'] for b in bars_h1]
    d1_times = [b['time'] for b in bars_d1]

    trades_setup_a = []
    trades_setup_b = []

    spread = 0.20 # Standard institutional Gold spread ($0.20)

    # Screening sessions: London Open (session_hour 11, 12, 13) and NY Open (16, 17, 18)
    for day_idx in range(5, len(trading_dates)):
        day_date = trading_dates[day_idx]
        if day_date.weekday() in (5, 6): # Skip weekends
            continue

        day_m5_indices = [idx for idx, b in enumerate(bars_m5) if b['dt'].date() == day_date]
        if len(day_m5_indices) < 20:
            continue

        taken_a_today = False
        taken_b_today = False

        for m5_idx in day_m5_indices:
            curr_b = bars_m5[m5_idx]
            bar_time = curr_b['time']
            th_hour = tehran_hour_from_bar_time(bar_time)

            # Institutional filter: London Open (11:30 - 13:30 Tehran) & NY Open (16:30 - 18:30 Tehran)
            if not (11 <= th_hour <= 13 or 16 <= th_hour <= 18):
                continue

            hist_m5 = bars_m5[max(0, m5_idx - 120) : m5_idx + 1]
            h1_idx = bisect_right(h1_times, bar_time)
            hist_h1 = bars_h1[max(0, h1_idx - 60) : h1_idx]
            d1_idx = bisect_right(d1_times, bar_time)
            hist_d1 = bars_d1[max(0, d1_idx - 15) : d1_idx]

            # ------------------------------------------------------------------
            # 1. EVALUATE SETUP A: SETUP-ARCH-001 (Judas Sweep + Breaker Block)
            # ------------------------------------------------------------------
            if not taken_a_today:
                res_a = screen_ict_session(
                    bars_5m=hist_m5,
                    bars_1h=hist_h1,
                    symbol="XAUUSD_o",
                    session_hour=th_hour,
                    bars_1m=None,
                    bars_1d=hist_d1,
                    closed_bars_only=True
                )

                if res_a.get("has_setup") and res_a.get("archetype_id") == "SETUP-ARCH-001":
                    entry_a = res_a.get("entry_ref")
                    sl_a = res_a.get("sl_ref")
                    direction_a = "SHORT" if "BEARISH" in res_a.get("setup_type", "") else "LONG"
                    risk_a = abs(entry_a - sl_a)

                    if 3.0 <= risk_a <= 15.0:
                        target_rr = 3.5
                        tp_a = entry_a - (target_rr * risk_a) if direction_a == "SHORT" else entry_a + (target_rr * risk_a)

                        # Simulate forward M1 execution
                        t_epoch = curr_b['time']
                        m1_idx = m1_map.get(t_epoch)
                        if m1_idx is not None:
                            fwd_window = bars_m1[m1_idx + 1 : m1_idx + 481] # 8 hours TTL
                            
                            # Check fill
                            filled = False
                            fill_idx = 0
                            for f_i, f_bar in enumerate(fwd_window):
                                if direction_a == "SHORT" and f_bar['high'] >= entry_a:
                                    filled = True; fill_idx = f_i; break
                                elif direction_a == "LONG" and f_bar['low'] <= entry_a:
                                    filled = True; fill_idx = f_i; break
                                # Check if SL breached before fill
                                if direction_a == "SHORT" and f_bar['high'] >= sl_a: break
                                elif direction_a == "LONG" and f_bar['low'] <= sl_a: break

                            if filled:
                                taken_a_today = True
                                trade_bars = fwd_window[fill_idx:]
                                cur_sl = sl_a
                                be_active = False
                                status_a = "EXPIRED"
                                net_r_a = 0.0
                                max_mfe = 0.0
                                max_mae = 0.0

                                for t_i, tb in enumerate(trade_bars):
                                    if direction_a == "SHORT":
                                        mfe = (entry_a - tb['low'] - spread) / risk_a
                                        mae = (tb['high'] - entry_a + spread) / risk_a
                                    else:
                                        mfe = (tb['high'] - entry_a - spread) / risk_a
                                        mae = (entry_a - tb['low'] + spread) / risk_a

                                    if mfe > max_mfe: max_mfe = mfe
                                    if mae > max_mae: max_mae = mae

                                    # Breakeven ratchet (+1.8R)
                                    if not be_active and max_mfe >= 1.8:
                                        be_active = True
                                        cur_sl = entry_a - spread if direction_a == "SHORT" else entry_a + spread

                                    # Hit SL / BE
                                    hit_sl = (tb['high'] >= cur_sl) if direction_a == "SHORT" else (tb['low'] <= cur_sl)
                                    hit_tp = (tb['low'] <= tp_a) if direction_a == "SHORT" else (tb['high'] >= tp_a)

                                    if hit_tp:
                                        status_a = "WIN"; net_r_a = target_rr; break
                                    elif hit_sl:
                                        status_a = "BREAKEVEN" if be_active else "LOSS"
                                        net_r_a = 0.0 if be_active else -1.0; break

                                trades_setup_a.append({
                                    'date': str(day_date),
                                    'season': get_season(curr_b['dt']),
                                    'time': curr_b['dt'].strftime('%H:%M'),
                                    'direction': direction_a,
                                    'entry': entry_a,
                                    'sl': sl_a,
                                    'risk': risk_a,
                                    'target_rr': target_rr,
                                    'status': status_a,
                                    'net_r': net_r_a,
                                    'mfe_r': max_mfe,
                                    'mae_r': max_mae
                                })

            # ------------------------------------------------------------------
            # 2. EVALUATE SETUP B: 5M Origin Swing MSS Retest (User's Setup)
            # ------------------------------------------------------------------
            if not taken_b_today:
                # Detect if there was a prominent sweep in recent 36 bars
                lookback = hist_m5[-36:]
                if len(lookback) >= 15:
                    # Find session high/low of prior session window
                    sess_window = hist_m5[-84:-10] if len(hist_m5) >= 84 else hist_m5[:-10]
                    if sess_window:
                        range_h = max(b['high'] for b in sess_window)
                        range_l = min(b['low'] for b in sess_window)

                        # Locate swing peaks in recent 36 bars
                        recent_highs = []
                        recent_lows = []
                        for i in range(2, len(lookback) - 1):
                            if lookback[i]['high'] >= lookback[i-1]['high'] and lookback[i]['high'] >= lookback[i+1]['high']:
                                recent_highs.append((i, lookback[i]['high']))
                            if lookback[i]['low'] <= lookback[i-1]['low'] and lookback[i]['low'] <= lookback[i+1]['low']:
                                recent_lows.append((i, lookback[i]['low']))

                        # BEARISH SETUP B: Swept Range High, then closed below Origin Swing Low
                        if recent_highs:
                            max_h_item = max(recent_highs, key=lambda x: x[1])
                            h_idx, h_val = max_h_item
                            if h_val > range_h: # Pierced/swept range high
                                # Origin swing low before the sweep peak
                                prior_lows = [b['low'] for b in lookback[max(0, h_idx - 12):h_idx]]
                                if prior_lows:
                                    origin_low = min(prior_lows)
                                    curr_close = curr_b['close']
                                    curr_open = curr_b['open']

                                    # Has current bar just displaced below origin_low?
                                    prev_close = hist_m5[-2]['close']
                                    if prev_close >= origin_low and curr_close < origin_low and curr_close < curr_open:
                                        # Displacement confirmed on this bar!
                                        entry_b = origin_low
                                        # Local pre-break swing high between sweep and current bar
                                        interim_bars = lookback[h_idx:]
                                        local_roof = max(b['high'] for b in interim_bars[:-1]) if len(interim_bars) > 1 else h_val
                                        sl_b = round(local_roof + 1.50, 2)
                                        risk_b = round(sl_b - entry_b, 2)

                                        if 3.0 <= risk_b <= 15.0:
                                            target_rr_b = 3.5
                                            tp_b = round(entry_b - (target_rr_b * risk_b), 2)

                                            # Simulate forward M1 execution for Setup B
                                            t_epoch = curr_b['time']
                                            m1_idx = m1_map.get(t_epoch)
                                            if m1_idx is not None:
                                                fwd_window = bars_m1[m1_idx + 1 : m1_idx + 481]
                                                filled_b = False
                                                fill_idx_b = 0
                                                for f_i, f_bar in enumerate(fwd_window):
                                                    if f_bar['high'] >= entry_b: # Retested broken level
                                                        filled_b = True; fill_idx_b = f_i; break
                                                    if f_bar['high'] >= sl_b: break # Breached SL before fill

                                                if filled_b:
                                                    taken_b_today = True
                                                    trade_bars = fwd_window[fill_idx_b:]
                                                    cur_sl = sl_b
                                                    be_active = False
                                                    status_b = "EXPIRED"
                                                    net_r_b = 0.0
                                                    max_mfe = 0.0
                                                    max_mae = 0.0

                                                    for tb in trade_bars:
                                                        mfe = (entry_b - tb['low'] - spread) / risk_b
                                                        mae = (tb['high'] - entry_b + spread) / risk_b
                                                        if mfe > max_mfe: max_mfe = mfe
                                                        if mae > max_mae: max_mae = mae

                                                        if not be_active and max_mfe >= 1.8:
                                                            be_active = True
                                                            cur_sl = entry_b - spread

                                                        hit_sl = (tb['high'] >= cur_sl)
                                                        hit_tp = (tb['low'] <= tp_b)

                                                        if hit_tp:
                                                            status_b = "WIN"; net_r_b = target_rr_b; break
                                                        elif hit_sl:
                                                            status_b = "BREAKEVEN" if be_active else "LOSS"
                                                            net_r_b = 0.0 if be_active else -1.0; break

                                                    trades_setup_b.append({
                                                        'date': str(day_date),
                                                        'season': get_season(curr_b['dt']),
                                                        'time': curr_b['dt'].strftime('%H:%M'),
                                                        'direction': 'SHORT',
                                                        'entry': entry_b,
                                                        'sl': sl_b,
                                                        'risk': risk_b,
                                                        'target_rr': target_rr_b,
                                                        'status': status_b,
                                                        'net_r': net_r_b,
                                                        'mfe_r': max_mfe,
                                                        'mae_r': max_mae
                                                    })

                        # BULLISH SETUP B: Swept Range Low, then closed above Origin Swing High
                        if not taken_b_today and recent_lows:
                            min_l_item = min(recent_lows, key=lambda x: x[1])
                            l_idx, l_val = min_l_item
                            if l_val < range_l:
                                prior_highs = [b['high'] for b in lookback[max(0, l_idx - 12):l_idx]]
                                if prior_highs:
                                    origin_high = max(prior_highs)
                                    curr_close = curr_b['close']
                                    curr_open = curr_b['open']

                                    prev_close = hist_m5[-2]['close']
                                    if prev_close <= origin_high and curr_close > origin_high and curr_close > curr_open:
                                        entry_b = origin_high
                                        interim_bars = lookback[l_idx:]
                                        local_floor = min(b['low'] for b in interim_bars[:-1]) if len(interim_bars) > 1 else l_val
                                        sl_b = round(local_floor - 1.50, 2)
                                        risk_b = round(entry_b - sl_b, 2)

                                        if 3.0 <= risk_b <= 15.0:
                                            target_rr_b = 3.5
                                            tp_b = round(entry_b + (target_rr_b * risk_b), 2)

                                            t_epoch = curr_b['time']
                                            m1_idx = m1_map.get(t_epoch)
                                            if m1_idx is not None:
                                                fwd_window = bars_m1[m1_idx + 1 : m1_idx + 481]
                                                filled_b = False
                                                fill_idx_b = 0
                                                for f_i, f_bar in enumerate(fwd_window):
                                                    if f_bar['low'] <= entry_b:
                                                        filled_b = True; fill_idx_b = f_i; break
                                                    if f_bar['low'] <= sl_b: break

                                                if filled_b:
                                                    taken_b_today = True
                                                    trade_bars = fwd_window[fill_idx_b:]
                                                    cur_sl = sl_b
                                                    be_active = False
                                                    status_b = "EXPIRED"
                                                    net_r_b = 0.0
                                                    max_mfe = 0.0
                                                    max_mae = 0.0

                                                    for tb in trade_bars:
                                                        mfe = (tb['high'] - entry_b - spread) / risk_b
                                                        mae = (entry_b - tb['low'] + spread) / risk_b
                                                        if mfe > max_mfe: max_mfe = mfe
                                                        if mae > max_mae: max_mae = mae

                                                        if not be_active and max_mfe >= 1.8:
                                                            be_active = True
                                                            cur_sl = entry_b + spread

                                                        hit_sl = (tb['low'] <= cur_sl)
                                                        hit_tp = (tb['high'] >= tp_b)

                                                        if hit_tp:
                                                            status_b = "WIN"; net_r_b = target_rr_b; break
                                                        elif hit_sl:
                                                            status_b = "BREAKEVEN" if be_active else "LOSS"
                                                            net_r_b = 0.0 if be_active else -1.0; break

                                                    trades_setup_b.append({
                                                        'date': str(day_date),
                                                        'season': get_season(curr_b['dt']),
                                                        'time': curr_b['dt'].strftime('%H:%M'),
                                                        'direction': 'LONG',
                                                        'entry': entry_b,
                                                        'sl': sl_b,
                                                        'risk': risk_b,
                                                        'target_rr': target_rr_b,
                                                        'status': status_b,
                                                        'net_r': net_r_b,
                                                        'mfe_r': max_mfe,
                                                        'mae_r': max_mae
                                                    })

    # Summary Statistics Function
    def summarize(trades: List[Dict[str, Any]], name: str):
        total = len(trades)
        if total == 0:
            print(f"\n❌ {name}: No trades filled across 12 months.")
            return {}

        wins = [t for t in trades if t['status'] == 'WIN']
        losses = [t for t in trades if t['status'] == 'LOSS']
        bes = [t for t in trades if t['status'] == 'BREAKEVEN']
        exp = [t for t in trades if t['status'] == 'EXPIRED']

        n_win = len(wins)
        n_loss = len(losses)
        n_be = len(bes)
        n_exp = len(exp)

        wr = (n_win / total) * 100.0 if total > 0 else 0.0
        gross_profit = sum(t['net_r'] for t in wins)
        gross_loss = abs(sum(t['net_r'] for t in losses))
        net_r = gross_profit - gross_loss
        pf = (gross_profit / gross_loss) if gross_loss > 0 else 99.0

        # Drawdown calculation
        eq = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in trades:
            eq += t['net_r']
            if eq > peak: peak = eq
            dd = peak - eq
            if dd > max_dd: max_dd = dd

        # Seasons
        seasons = {}
        for s in ["Winter", "Spring", "Summer", "Autumn"]:
            s_trades = [t for t in trades if t['season'] == s]
            s_tot = len(s_trades)
            s_win = len([t for t in s_trades if t['status'] == 'WIN'])
            s_loss = len([t for t in s_trades if t['status'] == 'LOSS'])
            s_net = sum(t['net_r'] for t in s_trades)
            s_pf = (sum(t['net_r'] for t in s_trades if t['net_r'] > 0) / abs(sum(t['net_r'] for t in s_trades if t['net_r'] < 0))) if s_loss > 0 else (99.0 if s_win > 0 else 0.0)
            seasons[s] = {'total': s_tot, 'win': s_win, 'loss': s_loss, 'net_r': round(s_net, 2), 'pf': round(s_pf, 2)}

        print(f"\n{'='*75}")
        print(f"📊 {name.upper()} - 12-MONTH AUDIT RESULTS (GOLD)")
        print(f"{'='*75}")
        print(f"Total Production Fills: {total}")
        print(f"Win / Loss / BE:        {n_win} Wins ({wr:.1f}%) | {n_loss} Losses | {n_be} Breakevens | {n_exp} Expired")
        print(f"Net Realized Alpha:     +{net_r:.2f} R")
        print(f"Profit Factor:          {pf:.2f}")
        print(f"Max Drawdown:           {max_dd:.2f} R")
        print(f"\nSeasonal Performance:")
        for s, s_data in seasons.items():
            print(f"  * {s:<6}: {s_data['total']:>2} Fills | Net: {s_data['net_r']:>+6.2f}R | PF: {s_data['pf']:>5.2f} | ({s_data['win']}W - {s_data['loss']}L)")

        return {
            'name': name,
            'total': total,
            'wins': n_win,
            'losses': n_loss,
            'bes': n_be,
            'wr': round(wr, 1),
            'net_r': round(net_r, 2),
            'pf': round(pf, 2),
            'max_dd': round(max_dd, 2),
            'seasons': seasons,
            'trades': trades
        }

    sum_a = summarize(trades_setup_a, "Setup A (SETUP-ARCH-001: 5M Breaker Block)")
    sum_b = summarize(trades_setup_b, "Setup B (User's Setup: 5M Origin MSS S/R Flip)")

    # Save summary
    res_payload = {
        'timestamp': datetime.datetime.now().isoformat(),
        'symbol': 'XAUUSD_o',
        'bars_m1_count': len(bars_m1),
        'setup_a': sum_a,
        'setup_b': sum_b
    }
    with open(OUT_DIR / "gold_dual_setups_12m_audit.json", "w", encoding="utf-8") as f:
        json.dump(res_payload, f, indent=2, default=str)

    # Save CSV of all trades
    all_rows = []
    for t in trades_setup_a:
        row = dict(t); row['setup'] = 'SETUP_A_BREAKER'; all_rows.append(row)
    for t in trades_setup_b:
        row = dict(t); row['setup'] = 'SETUP_B_ORIGIN_MSS'; all_rows.append(row)

    if all_rows:
        df_out = pd.DataFrame(all_rows)
        csv_path = OUT_DIR / "gold_dual_setups_12m_trades.csv"
        df_out.to_csv(csv_path, index=False)
        print(f"\n💾 Saved all trade logs to: {csv_path}")

    return sum_a, sum_b

if __name__ == "__main__":
    run_dual_backtest()
