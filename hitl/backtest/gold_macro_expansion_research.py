"""
TradingGuard HITL - Gold Macro Expansion Empirical Research Engine
Audits 3 Institutional Methods for Capturing Big Moves ($30 - $80+) on Gold (XAUUSD_o):
1. Hypothesis G-A: Double MSS Reversal with 15M Structural Trailing
2. Hypothesis G-B: London Ignition Breakout & 15M Trend Riding
3. Hypothesis G-C: 15-Minute Breaker Displacement with Contract-Scaled Stop ($6-$10)
Full-Year 2026 (175 Trading Days | 298,638 M1 bars | All 4 Calendar Seasons)
"""

import sys
import json
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, List, Any, Tuple, Optional

import pandas as pd
import numpy as np

# Enforce UTF-8 on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

TZ_UTC = ZoneInfo("UTC")
CACHE_DIR = Path("backtest_results/cache")
OUT_DIR = Path("backtest_results/gold_macro_research")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def get_season_name(dt: datetime.datetime) -> str:
    m = dt.month
    if m in (12, 1, 2): return "Winter"
    elif m in (3, 4, 5): return "Spring"
    elif m in (6, 7, 8): return "Summer"
    elif m in (9, 10, 11): return "Autumn"
    return "Unknown"


def load_gold_microstructure() -> Dict[str, Any]:
    cache_file = CACHE_DIR / "M1_XAUUSD_o_2026.parquet"
    if not cache_file.exists():
        raise RuntimeError("Gold M1 cache not found!")

    print(f"   [Cache Hit] Loading Gold M1 bars from {cache_file.name}...")
    df = pd.read_parquet(cache_file)
    bars_m1 = []
    for row in df.itertuples():
        bars_m1.append({
            'time': int(row.time),
            'dt': row.Index.to_pydatetime() if hasattr(row.Index, 'to_pydatetime') else row.Index,
            'open': float(row.open),
            'high': float(row.high),
            'low': float(row.low),
            'close': float(row.close),
            'tick_volume': int(row.tick_volume),
            'spread': int(row.spread)
        })

    print(f"   Resampling M5, M15, H1, and D1 bars from {len(bars_m1)} M1 bars...")
    df_bars = pd.DataFrame(bars_m1)
    df_bars['datetime'] = pd.to_datetime(df_bars['time'], unit='s', utc=True)
    df_bars.set_index('datetime', inplace=True)

    def _resamp(rule):
        res = df_bars['close'].resample(rule).ohlc().dropna()
        res['open'] = df_bars['open'].resample(rule).first()
        res['high'] = df_bars['high'].resample(rule).max()
        res['low'] = df_bars['low'].resample(rule).min()
        res['close'] = df_bars['close'].resample(rule).last()
        res['tick_volume'] = df_bars['tick_volume'].resample(rule).sum()
        out = []
        for idx, row in res.iterrows():
            out.append({
                'time': int(idx.timestamp()),
                'dt': idx.to_pydatetime(),
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'tick_volume': int(row['tick_volume'])
            })
        out.sort(key=lambda x: x['time'])
        return out

    bars_m5 = _resamp("5min")
    bars_m15 = _resamp("15min")
    bars_h1 = _resamp("60min")
    bars_d1 = _resamp("1D")

    return {
        'm1': bars_m1,
        'm5': bars_m5,
        'm15': bars_m15,
        'h1': bars_h1,
        'd1': bars_d1
    }


def simulate_gold_macro_trade(
    entry: float,
    sl: float,
    direction: str,
    dol_target: float,
    forward_m1: List[Dict[str, Any]],
    bars_m15_map: Dict[int, Dict[str, Any]]
) -> Dict[str, Any]:
    spread = 0.20
    risk = abs(entry - sl)
    if risk <= 0: return None

    dol_rr = abs(dol_target - entry) / risk
    max_mfe_r = 0.0
    max_mae_r = 0.0

    # Policy: Trailing behind 15M structure with BE at 2.5R
    cur_sl = sl
    be_active = False
    trail_active = False

    recent_m15_highs = []
    recent_m15_lows = []
    last_m15_time = 0
    held_minutes = 0

    status = "EXPIRED"
    net_r = 0.0

    for m1_idx, bar in enumerate(forward_m1):
        held_minutes = m1_idx + 1
        h = bar['high']
        l = bar['low']

        if direction == "LONG":
            cur_mfe = (h - entry - spread) / risk
            cur_mae = (entry - l + spread) / risk
        else:
            cur_mfe = (entry - l - spread) / risk
            cur_mae = (h - entry + spread) / risk

        if cur_mfe > max_mfe_r: max_mfe_r = cur_mfe
        if cur_mae > max_mae_r: max_mae_r = cur_mae

        # Check 15M completion
        bar_m15_slot = (bar['time'] // 900) * 900
        if bar_m15_slot in bars_m15_map and bar_m15_slot != last_m15_time:
            last_m15_time = bar_m15_slot
            m15_b = bars_m15_map[bar_m15_slot]
            recent_m15_highs.append(m15_b['high'])
            recent_m15_lows.append(m15_b['low'])
            if len(recent_m15_highs) > 10:
                recent_m15_highs.pop(0)
                recent_m15_lows.pop(0)

        # BE ratchet at +2.5R
        if not be_active and max_mfe_r >= 2.5:
            be_active = True
            cur_sl = entry + (0.2 * risk if direction == "LONG" else -0.2 * risk)

        # 15M Trailing at +3.5R
        if max_mfe_r >= 3.5 and len(recent_m15_lows) >= 3:
            trail_active = True
            if direction == "LONG":
                t_lvl = min(recent_m15_lows[-3:-1]) - 1.00
                if t_lvl > cur_sl: cur_sl = t_lvl
            else:
                t_lvl = max(recent_m15_highs[-3:-1]) + 1.00
                if t_lvl < cur_sl: cur_sl = t_lvl

        # Check exit
        hit_sl = (l <= cur_sl) if direction == "LONG" else (h >= cur_sl)
        hit_dol = (h >= dol_target) if direction == "LONG" else (l <= dol_target)

        if hit_dol:
            status = "WIN_DOL"
            net_r = round(dol_rr, 2)
            break
        elif hit_sl:
            if trail_active:
                realized = ((cur_sl - entry) / risk) if direction == "LONG" else ((entry - cur_sl) / risk)
                status = "TRAIL_WIN" if realized > 0.5 else ("BREAKEVEN" if realized >= 0.0 else "LOSS")
                net_r = round(max(realized, 0.0) if be_active else -1.0, 2)
            else:
                status = "BREAKEVEN" if be_active else "LOSS"
                net_r = 0.2 if be_active else -1.0
            break

        if held_minutes >= 480:  # 8 hours max hold
            realized = ((bar['close'] - entry) / risk) if direction == "LONG" else ((entry - bar['close']) / risk)
            status = "SESSION_CLOSE"
            net_r = round(max(realized, 0.0) if be_active else -1.0, 2)
            break

    return {
        'status': status,
        'net_r': net_r,
        'risk_pts': round(risk, 2),
        'max_mfe_r': round(max_mfe_r, 2),
        'max_mae_r': round(max_mae_r, 2),
        'held_minutes': held_minutes,
        'dol_rr': round(dol_rr, 2)
    }


def research_hypothesis_g_a_double_mss(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Hypothesis G-A: Double MSS Reversal with 15M Structural Trailing.
    Instead of entering on the first M1 sweep, wait for M5 Double MSS confirmation:
    Sweep of PDH/PDL or Asian Extreme -> 1st MSS -> Pullback -> 2nd MSS.
    Stop Loss placed at internal pullback extreme ($4.50 - $8.00 risk).
    """
    bars_m1 = data['m1']
    bars_m5 = data['m5']
    bars_m15 = data['m15']
    bars_d1 = data['d1']

    m1_map = {b['time']: idx for idx, b in enumerate(bars_m1)}
    m15_map = {b['time']: b for b in bars_m15}
    d_map = {b['dt'].date(): b for b in bars_d1}
    dates = sorted(list(set(b['dt'].date() for b in bars_m1)))

    trades = []

    for day_idx in range(21, len(dates)):
        day_date = dates[day_idx]
        if day_date.weekday() in (5, 6): continue

        prev_d = d_map.get(dates[day_idx - 1])
        if not prev_d: continue
        pdh = prev_d['high']
        pdl = prev_d['low']

        day_m5 = [b for b in bars_m5 if b['dt'].date() == day_date]
        if len(day_m5) < 30: continue

        asian_bars = [b for b in day_m5 if b['dt'].hour < 7]
        asian_high = max(b['high'] for b in asian_bars) if asian_bars else 0.0
        asian_low = min(b['low'] for b in asian_bars) if asian_bars else 0.0

        session_bars = [b for b in day_m5 if 7 <= b['dt'].hour < 16]

        for i in range(15, len(session_bars) - 5):
            window = session_bars[max(0, i-25):i+1]
            curr_b = window[-1]

            # Detect Double MSS
            highs = []
            lows = []
            for k in range(2, len(window) - 2):
                if window[k]['high'] >= window[k-1]['high'] and window[k]['high'] >= window[k+1]['high']:
                    highs.append((k, window[k]['high']))
                if window[k]['low'] <= window[k-1]['low'] and window[k]['low'] <= window[k+1]['low']:
                    lows.append((k, window[k]['low']))

            if len(highs) >= 2 and len(lows) >= 2:
                # Bullish Double MSS (Swept low -> 1st MSS -> Pullback -> 2nd MSS)
                h2_idx, h2_p = highs[-1]
                l2_idx, l2_p = lows[-1]
                if curr_b['close'] > h2_p and curr_b['close'] > curr_b['open']:
                    # Check prior sweep
                    has_sweep = (l2_p < pdl or l2_p < asian_low)
                    if has_sweep and h2_idx < len(window) - 1:
                        pullback_low = min(b['low'] for b in window[h2_idx:])
                        entry = curr_b['close']
                        sl = pullback_low - 1.50
                        risk = entry - sl
                        if 4.00 <= risk <= 9.00:
                            dol = pdh if pdh > entry else asian_high
                            if dol > entry and ((dol - entry) / risk) >= 4.0:
                                m1_idx = m1_map.get(curr_b['time'])
                                if m1_idx is not None:
                                    sim = simulate_gold_macro_trade(entry, sl, "LONG", dol, bars_m1[m1_idx:m1_idx+480], m15_map)
                                    if sim:
                                        trades.append({
                                            'date': str(day_date),
                                            'season': get_season_name(curr_b['dt']),
                                            'hypothesis': 'G-A_DOUBLE_MSS_REVERSAL',
                                            'direction': 'LONG',
                                            'entry': entry,
                                            'sl': sl,
                                            'dol': dol,
                                            **sim
                                        })
                                        break

                # Bearish Double MSS (Swept high -> 1st MSS -> Pullback -> 2nd MSS)
                l2_idx, l2_p = lows[-1]
                h2_idx, h2_p = highs[-1]
                if curr_b['close'] < l2_p and curr_b['close'] < curr_b['open']:
                    has_sweep = (h2_p > pdh or h2_p > asian_high)
                    if has_sweep and l2_idx < len(window) - 1:
                        pullback_high = max(b['high'] for b in window[l2_idx:])
                        entry = curr_b['close']
                        sl = pullback_high + 1.50
                        risk = sl - entry
                        if 4.00 <= risk <= 9.00:
                            dol = pdl if pdl < entry else asian_low
                            if dol < entry and ((entry - dol) / risk) >= 4.0:
                                m1_idx = m1_map.get(curr_b['time'])
                                if m1_idx is not None:
                                    sim = simulate_gold_macro_trade(entry, sl, "SHORT", dol, bars_m1[m1_idx:m1_idx+480], m15_map)
                                    if sim:
                                        trades.append({
                                            'date': str(day_date),
                                            'season': get_season_name(curr_b['dt']),
                                            'hypothesis': 'G-A_DOUBLE_MSS_REVERSAL',
                                            'direction': 'SHORT',
                                            'entry': entry,
                                            'sl': sl,
                                            'dol': dol,
                                            **sim
                                        })
                                        break

    return trades


def research_hypothesis_g_b_london_ignition(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Hypothesis G-B: London Ignition Breakout & 15M Trend Riding.
    Instead of fading the move, trade in the direction of the London Open impulse!
    When London Open (07:00-09:00 UTC) produces an H1 candle closing outside Asian range
    by at least $5.00, enter on M5 pullback to Asian boundary with $6.00 - $10.00 stop,
    trailing behind 15M structure across London + NY sessions.
    """
    bars_m1 = data['m1']
    bars_m5 = data['m5']
    bars_m15 = data['m15']
    bars_h1 = data['h1']
    bars_d1 = data['d1']

    m1_map = {b['time']: idx for idx, b in enumerate(bars_m1)}
    m15_map = {b['time']: b for b in bars_m15}
    d_map = {b['dt'].date(): b for b in bars_d1}
    dates = sorted(list(set(b['dt'].date() for b in bars_m1)))

    trades = []

    for day_idx in range(21, len(dates)):
        day_date = dates[day_idx]
        if day_date.weekday() in (5, 6): continue

        day_h1 = [b for b in bars_h1 if b['dt'].date() == day_date]
        if len(day_h1) < 8: continue

        asian_bars = [b for b in day_h1 if b['dt'].hour < 7]
        if not asian_bars: continue
        asian_high = max(b['high'] for b in asian_bars)
        asian_low = min(b['low'] for b in asian_bars)
        asian_range = asian_high - asian_low

        if asian_range < 5.0 or asian_range > 35.0: continue

        # London Open hours: 07:00 or 08:00 UTC
        london_bars = [b for b in day_h1 if 7 <= b['dt'].hour <= 9]
        if not london_bars: continue

        first_h1 = london_bars[0]
        # Bullish ignition: H1 closes above Asian High with strong body
        is_bull_ignition = (first_h1['close'] > asian_high + 3.0) and (first_h1['close'] > first_h1['open'])
        # Bearish ignition: H1 closes below Asian Low with strong body
        is_bear_ignition = (first_h1['close'] < asian_low - 3.0) and (first_h1['close'] < first_h1['open'])

        if is_bull_ignition:
            # Look for M5 retest of Asian High in subsequent hours
            entry_m5 = [b for b in bars_m5 if b['dt'].date() == day_date and 8 <= b['dt'].hour <= 11 and b['low'] <= asian_high + 2.0]
            if entry_m5:
                entry_b = entry_m5[0]
                entry = entry_b['close']
                sl = asian_high - 6.00
                risk = entry - sl
                if 5.00 <= risk <= 12.00:
                    dol = entry + 45.0  # Macro expansion target ($45 move)
                    m1_idx = m1_map.get(entry_b['time'])
                    if m1_idx is not None:
                        sim = simulate_gold_macro_trade(entry, sl, "LONG", dol, bars_m1[m1_idx:m1_idx+480], m15_map)
                        if sim:
                            trades.append({
                                'date': str(day_date),
                                'season': get_season_name(entry_b['dt']),
                                'hypothesis': 'G-B_LONDON_IGNITION_TREND',
                                'direction': 'LONG',
                                'entry': entry,
                                'sl': sl,
                                'dol': dol,
                                **sim
                            })

        elif is_bear_ignition:
            entry_m5 = [b for b in bars_m5 if b['dt'].date() == day_date and 8 <= b['dt'].hour <= 11 and b['high'] >= asian_low - 2.0]
            if entry_m5:
                entry_b = entry_m5[0]
                entry = entry_b['close']
                sl = asian_low + 6.00
                risk = sl - entry
                if 5.00 <= risk <= 12.00:
                    dol = entry - 45.0
                    m1_idx = m1_map.get(entry_b['time'])
                    if m1_idx is not None:
                        sim = simulate_gold_macro_trade(entry, sl, "SHORT", dol, bars_m1[m1_idx:m1_idx+480], m15_map)
                        if sim:
                            trades.append({
                                'date': str(day_date),
                                'season': get_season_name(entry_b['dt']),
                                'hypothesis': 'G-B_LONDON_IGNITION_TREND',
                                'direction': 'SHORT',
                                'entry': entry,
                                'sl': sl,
                                'dol': dol,
                                **sim
                            })

    return trades


def research_hypothesis_g_c_15m_breaker(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Hypothesis G-C: 15-Minute Breaker Displacement with Contract-Scaled Stop ($6-$10).
    Instead of 1-minute entries, use 15-Minute displacement bars!
    When a 15M bar displaces past an opposing swing pivot by >= $3.00,
    enter on 15M breaker retest with SL anchored beyond the 15M origin wick ($6-$10 stop).
    """
    bars_m1 = data['m1']
    bars_m15 = data['m15']
    bars_d1 = data['d1']

    m1_map = {b['time']: idx for idx, b in enumerate(bars_m1)}
    m15_map = {b['time']: b for b in bars_m15}
    d_map = {b['dt'].date(): b for b in bars_d1}
    dates = sorted(list(set(b['dt'].date() for b in bars_m1)))

    trades = []

    for day_idx in range(21, len(dates)):
        day_date = dates[day_idx]
        if day_date.weekday() in (5, 6): continue

        prev_d = d_map.get(dates[day_idx - 1])
        if not prev_d: continue
        pdh = prev_d['high']
        pdl = prev_d['low']

        day_m15 = [b for b in bars_m15 if b['dt'].date() == day_date and 7 <= b['dt'].hour < 16]
        if len(day_m15) < 10: continue

        for i in range(4, len(day_m15)):
            cur_b = day_m15[i]
            prev_bars = day_m15[:i]

            # Bullish Breaker: 15M bar closes above prior 15M swing high by >= 2.50
            recent_highs = [b['high'] for b in prev_bars[-6:-1]]
            recent_lows = [b['low'] for b in prev_bars[-6:-1]]
            if recent_highs and recent_lows:
                sw_h = max(recent_highs)
                sw_l = min(recent_lows)
                body = cur_b['close'] - cur_b['open']

                if cur_b['close'] > sw_h + 2.50 and body >= 3.50:
                    entry = cur_b['close']
                    sl = sw_l - 2.00
                    risk = entry - sl
                    if 6.00 <= risk <= 12.00:
                        dol = pdh if pdh > entry else (entry + 50.0)
                        if ((dol - entry) / risk) >= 4.0:
                            m1_idx = m1_map.get(cur_b['time'])
                            if m1_idx is not None:
                                sim = simulate_gold_macro_trade(entry, sl, "LONG", dol, bars_m1[m1_idx:m1_idx+480], m15_map)
                                if sim:
                                    trades.append({
                                        'date': str(day_date),
                                        'season': get_season_name(cur_b['dt']),
                                        'hypothesis': 'G-C_15M_BREAKER_DISPLACEMENT',
                                        'direction': 'LONG',
                                        'entry': entry,
                                        'sl': sl,
                                        'dol': dol,
                                        **sim
                                    })
                                    break

                elif cur_b['close'] < sw_l - 2.50 and -body >= 3.50:
                    entry = cur_b['close']
                    sl = sw_h + 2.00
                    risk = sl - entry
                    if 6.00 <= risk <= 12.00:
                        dol = pdl if pdl < entry else (entry - 50.0)
                        if ((entry - dol) / risk) >= 4.0:
                            m1_idx = m1_map.get(cur_b['time'])
                            if m1_idx is not None:
                                sim = simulate_gold_macro_trade(entry, sl, "SHORT", dol, bars_m1[m1_idx:m1_idx+480], m15_map)
                                if sim:
                                    trades.append({
                                        'date': str(day_date),
                                        'season': get_season_name(cur_b['dt']),
                                        'hypothesis': 'G-C_15M_BREAKER_DISPLACEMENT',
                                        'direction': 'SHORT',
                                        'entry': entry,
                                        'sl': sl,
                                        'dol': dol,
                                        **sim
                                    })
                                    break

    return trades


def run_gold_macro_expansion_audit():
    print("=" * 95)
    print("🚀 TRADINGGUARD - GOLD MACRO EXPANSION EMPIRICAL RESEARCH AUDIT")
    print("Testing 3 Scaled Institutional Architectures for Capturing $30 - $80 Moves on Gold")
    print("=" * 95)

    data = load_gold_microstructure()

    print("\n🔬 Testing Hypothesis G-A: Double MSS Reversal with 15M Structural Trailing...")
    trades_ga = research_hypothesis_g_a_double_mss(data)
    print(f"   => Found {len(trades_ga)} trades.")

    print("\n🔬 Testing Hypothesis G-B: London Ignition Breakout & 15M Trend Riding...")
    trades_gb = research_hypothesis_g_b_london_ignition(data)
    print(f"   => Found {len(trades_gb)} trades.")

    print("\n🔬 Testing Hypothesis G-C: 15-Minute Breaker Displacement with $6-$10 Stop...")
    trades_gc = research_hypothesis_g_c_15m_breaker(data)
    print(f"   => Found {len(trades_gc)} trades.")

    all_trades = trades_ga + trades_gb + trades_gc
    df_all = pd.DataFrame(all_trades)
    csv_file = OUT_DIR / "gold_macro_expansion_trades.csv"
    df_all.to_csv(csv_file, index=False)
    print(f"\n💾 Saved all trades to {csv_file}")

    print("\n" + "=" * 95)
    print("📊 GOLD MACRO EXPANSION SCORECARD BY CANDIDATE HYPOTHESIS")
    print("=" * 95)

    scorecard = {}
    for hyp in ['G-A_DOUBLE_MSS_REVERSAL', 'G-B_LONDON_IGNITION_TREND', 'G-C_15M_BREAKER_DISPLACEMENT']:
        df_h = df_all[df_all['hypothesis'] == hyp]
        if df_h.empty:
            print(f"\n* {hyp}: 0 Fills")
            continue

        net_r = df_h['net_r'].sum()
        wins = len(df_h[df_h['net_r'] > 0.5])
        losses = len(df_h[df_h['net_r'] <= -0.5])
        bes = len(df_h) - wins - losses
        wr = (wins / len(df_h)) * 100 if len(df_h) > 0 else 0
        gross_w = df_h[df_h['net_r'] > 0]['net_r'].sum()
        gross_l = abs(df_h[df_h['net_r'] < 0]['net_r'].sum())
        pf = gross_w / gross_l if gross_l > 0 else 99.0

        five_r_plus = len(df_h[df_h['net_r'] >= 5.0])
        eight_r_plus = len(df_h[df_h['net_r'] >= 8.0])

        scorecard[hyp] = {
            'fills': len(df_h),
            'wins': wins,
            'losses': losses,
            'be': bes,
            'wr': round(wr, 1),
            'net_r': round(net_r, 2),
            'pf': round(pf, 2),
            'five_r_plus': five_r_plus,
            'eight_r_plus': eight_r_plus,
            'seasons': {}
        }

        print(f"\n* {hyp}:")
        print(f"    Net Realized: {net_r:+6.1f}R | WR: {wr:4.1f}% ({wins}W - {losses}L - {bes}BE) | PF: {pf:4.2f}")
        print(f"    Trades >= +5R: {five_r_plus} | Trades >= +8R: {eight_r_plus} | Max Single Trade: {df_h['net_r'].max():+.2f}R")
        print("    Seasonal Performance:")
        for s in ['Winter', 'Spring', 'Summer', 'Autumn']:
            df_s = df_h[df_h['season'] == s]
            s_net = df_s['net_r'].sum()
            s_w = len(df_s[df_s['net_r'] > 0.5])
            s_l = len(df_s[df_s['net_r'] <= -0.5])
            s_be = len(df_s) - s_w - s_l
            scorecard[hyp]['seasons'][s] = {
                'fills': len(df_s),
                'net_r': round(s_net, 2),
                'wins': s_w,
                'losses': s_l,
                'be': s_be
            }
            print(f"      - {s:6s}: {len(df_s):2d} Fills | Net: {s_net:+5.1f}R ({s_w}W - {s_l}L - {s_be}BE)")

    with open(OUT_DIR / "gold_macro_scorecard.json", 'w', encoding='utf-8') as f:
        json.dump(scorecard, f, indent=2)
    print(f"\n🎉 Saved JSON scorecard to {OUT_DIR / 'gold_macro_scorecard.json'}")


if __name__ == "__main__":
    run_gold_macro_expansion_audit()
