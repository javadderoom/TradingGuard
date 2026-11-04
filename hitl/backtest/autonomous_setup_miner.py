"""
TradingGuard HITL - Autonomous Quantitative Setup Mining Engine
Evaluates new non-ICT microstructure hypotheses across Full-Year 2026 (175 Trading Days):
1. Hypothesis A (SETUP-ARCH-012 Candidate): Frankfurt Liquidity Run & London Reversal / Expansion (Cable & Gold)
2. Hypothesis B (SETUP-ARCH-013 Candidate): Pre-Session Volatility Squeeze Breakout (Gold & Cable)
3. Hypothesis C (SETUP-ARCH-014 Candidate): Dynamic ADR Exhaustion Equilibrium Snapback (Cable & Gold)

Tests across all 4 calendar seasons:
- Autumn 2026 (Sep 1 - Nov 4)
- Summer 2026 (Jul 1 - Aug 31)
- Winter 2026 (Jan 2 - Feb 27)
- Spring 2026 (Mar 1 - Apr 30)
"""

import sys
import json
import time
import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.session_clock import get_session_times_for_date

OUTPUT_DIR = BASE_DIR / "backtest_results" / "autonomous_setup_mining"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_UTC = datetime.timezone.utc


def load_symbol_year_data(symbol: str) -> Dict[str, Any]:
    print(f"\n📥 Ingesting Full-Year 2026 Microstructure for {symbol}...")
    if not mt5.initialize():
        raise RuntimeError("MT5 initialization failed")

    mt5.symbol_select(symbol, True)
    is_fx = "GBP" in symbol.upper() or "EUR" in symbol.upper()
    pip_size = 0.0001 if is_fx else 1.0

    t_start = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=TZ_UTC)
    t_end = datetime.datetime(2026, 11, 4, 23, 59, tzinfo=TZ_UTC)

    # 1. D1 bars
    t_d1_start = datetime.datetime(2025, 11, 1, 0, 0, tzinfo=TZ_UTC)
    r_d1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, t_d1_start, t_end)

    # 2. H1 bars
    t_h1_start = datetime.datetime(2025, 12, 1, 0, 0, tzinfo=TZ_UTC)
    r_h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, t_h1_start, t_end)

    # 3. M5 bars
    t_m5_start = datetime.datetime(2025, 12, 20, 0, 0, tzinfo=TZ_UTC)
    r_m5 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, t_m5_start, t_end)

    def _conv(records, default_spread):
        if records is None: return []
        out = []
        for r in records:
            s_val = int(r['spread']) if 'spread' in r.dtype.names else default_spread
            out.append({
                'time': int(r['time']),
                'dt': datetime.datetime.fromtimestamp(r['time'], tz=TZ_UTC),
                'open': float(r['open']),
                'high': float(r['high']),
                'low': float(r['low']),
                'close': float(r['close']),
                'tick_volume': int(r['tick_volume']),
                'spread': s_val
            })
        return out

    bars_d1 = _conv(r_d1, 6 if is_fx else 20)
    bars_h1 = _conv(r_h1, 6 if is_fx else 20)
    bars_m5 = _conv(r_m5, 6 if is_fx else 20)

    # 4. M1 bars directly from MT5
    r_m1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, t_start, t_end)
    bars_m1 = _conv(r_m1, 6 if is_fx else 20)

    # If M1 bars directly fetched are insufficient, resample from raw broker ticks
    if len(bars_m1) < 50000:
        print(f"   Fetching M1 bars from raw broker ticks across 2026...")
        cur_d = datetime.date(2026, 1, 2)
        end_d = datetime.date(2026, 11, 5)
        m1_list = []
        t0 = time.time()
        tick_cnt = 0
        while cur_d < end_d:
            if cur_d.weekday() < 5:
                dt_s = datetime.datetime(cur_d.year, cur_d.month, cur_d.day, 0, 0, tzinfo=TZ_UTC)
                dt_e = dt_s + datetime.timedelta(days=1)
                ticks = mt5.copy_ticks_range(symbol, dt_s, dt_e, mt5.COPY_TICKS_ALL)
                if ticks is not None and len(ticks) > 0:
                    tick_cnt += len(ticks)
                    df = pd.DataFrame(ticks)
                    df['datetime'] = pd.to_datetime(df['time'], unit='s', utc=True)
                    df.set_index('datetime', inplace=True)
                    ohlc = df['bid'].resample('1min').ohlc().dropna()
                    spread = ((df['ask'] - df['bid']) / (0.0001 if is_fx else 0.01)).resample('1min').mean().dropna()
                    vol = df['flags'].resample('1min').count()
                    for idx, row in ohlc.iterrows():
                        m1_list.append({
                            'time': int(idx.timestamp()),
                            'dt': idx.to_pydatetime(),
                            'open': float(row['open']),
                            'high': float(row['high']),
                            'low': float(row['low']),
                            'close': float(row['close']),
                            'tick_volume': int(vol.loc[idx]) if idx in vol.index else 100,
                            'spread': int(round(spread.loc[idx])) if idx in spread.index else (6 if is_fx else 15)
                        })
            cur_d += datetime.timedelta(days=1)
        m1_list.sort(key=lambda x: x['time'])
        bars_m1 = m1_list
        print(f"   Resampled {len(bars_m1)} M1 bars from {tick_cnt:,} broker ticks in {time.time()-t0:.2f}s.")
    else:
        print(f"   Directly loaded {len(bars_m1):,} M1 bars from MT5.")

    print(f"✅ Ingestion Complete: {len(bars_d1)} D1 | {len(bars_h1)} H1 | {len(bars_m5)} M5 | {len(bars_m1)} M1 bars.")
    return {
        'symbol': symbol,
        'is_fx': is_fx,
        'pip_size': pip_size,
        'd1': bars_d1,
        'h1': bars_h1,
        'm5': bars_m5,
        'm1': bars_m1
    }


def find_swings(bars: List[Dict[str, Any]], window: int = 2) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    highs, lows = [], []
    n = len(bars)
    for i in range(window, n - window):
        b = bars[i]
        if all(b['high'] >= bars[i - w]['high'] and b['high'] >= bars[i + w]['high'] for w in range(1, window + 1)):
            highs.append({'idx': i, 'time': b['time'], 'dt': b['dt'], 'price': b['high']})
        if all(b['low'] <= bars[i - w]['low'] and b['low'] <= bars[i + w]['low'] for w in range(1, window + 1)):
            lows.append({'idx': i, 'time': b['time'], 'dt': b['dt'], 'price': b['low']})
    return highs, lows


def get_atr(bars: List[Dict[str, Any]], period: int = 14) -> float:
    if len(bars) < period + 1: return 0.0010
    trs = []
    for i in range(1, len(bars)):
        tr = max(bars[i]['high'] - bars[i]['low'], abs(bars[i]['high'] - bars[i-1]['close']), abs(bars[i]['low'] - bars[i-1]['close']))
        trs.append(tr)
    return sum(trs[-period:]) / period if trs else 0.0010


def simulate_trade(
    entry_price: float,
    sl_price: float,
    direction: str,
    forward_m1: List[Dict[str, Any]],
    target_rr: float = 2.5,
    be_rr: Optional[float] = 1.5,
    ttl_minutes: int = 90,
    spread_val: float = 0.00006
) -> Dict[str, Any]:
    is_buy = (direction in ("LONG", "BUY"))
    risk_pts = abs(entry_price - sl_price)
    if risk_pts <= 0:
        return {'status': 'INVALID', 'net_r': 0.0, 'mae_r': 0.0, 'mfe_r': 0.0, 'held_minutes': 0}

    tp_price = entry_price + (risk_pts * target_rr) if is_buy else entry_price - (risk_pts * target_rr)
    is_filled = False
    fill_idx = None
    active_sl = sl_price
    is_be_activated = False
    max_fav_dist = 0.0
    max_adv_dist = 0.0

    for idx, bar in enumerate(forward_m1):
        if not is_filled:
            if idx >= ttl_minutes:
                return {'status': 'EXPIRED', 'net_r': 0.0, 'mae_r': 0.0, 'mfe_r': 0.0, 'held_minutes': idx}

            if is_buy and bar['low'] <= sl_price:
                return {'status': 'INVALIDATED_BEFORE_FILL', 'net_r': 0.0, 'mae_r': 0.0, 'mfe_r': 0.0, 'held_minutes': idx}
            elif (not is_buy) and bar['high'] >= sl_price:
                return {'status': 'INVALIDATED_BEFORE_FILL', 'net_r': 0.0, 'mae_r': 0.0, 'mfe_r': 0.0, 'held_minutes': idx}

            if is_buy and (bar['low'] + spread_val) <= entry_price:
                is_filled = True
                fill_idx = idx
            elif (not is_buy) and bar['high'] >= entry_price:
                is_filled = True
                fill_idx = idx
        else:
            cur_fav = (bar['high'] - entry_price) if is_buy else (entry_price - bar['low'])
            cur_adv = (entry_price - bar['low']) if is_buy else (bar['high'] - entry_price)
            if cur_fav > max_fav_dist: max_fav_dist = cur_fav
            if cur_adv > max_adv_dist: max_adv_dist = cur_adv

            cur_rr = max_fav_dist / risk_pts
            if be_rr is not None and cur_rr >= be_rr and not is_be_activated:
                is_be_activated = True
                active_sl = (entry_price + spread_val) if is_buy else (entry_price - spread_val)

            hit_sl = (bar['low'] <= active_sl) if is_buy else (bar['high'] >= active_sl)
            if hit_sl:
                held_mins = idx - fill_idx
                mae_r = round(max_adv_dist / risk_pts, 2)
                mfe_r = round(max_fav_dist / risk_pts, 2)
                if is_be_activated:
                    return {'status': 'BREAKEVEN', 'net_r': 0.0, 'mae_r': mae_r, 'mfe_r': mfe_r, 'held_minutes': held_mins}
                else:
                    return {'status': 'LOSS', 'net_r': -1.0, 'mae_r': mae_r, 'mfe_r': mfe_r, 'held_minutes': held_mins}

            hit_tp = (bar['high'] >= tp_price) if is_buy else (bar['low'] <= tp_price)
            if hit_tp:
                held_mins = idx - fill_idx
                mae_r = round(max_adv_dist / risk_pts, 2)
                mfe_r = round(max_fav_dist / risk_pts, 2)
                return {'status': 'WIN', 'net_r': target_rr, 'mae_r': mae_r, 'mfe_r': mfe_r, 'held_minutes': held_mins}

    held_mins = len(forward_m1) - fill_idx if is_filled else len(forward_m1)
    if is_filled:
        final_price = forward_m1[-1]['close']
        fav_dist = (final_price - entry_price) if is_buy else (entry_price - final_price)
        final_r = fav_dist / risk_pts
        return {'status': 'OPEN_EXPANSION' if final_r > 1.0 else 'OPEN_CLOSE', 'net_r': round(final_r, 2), 'mae_r': round(max_adv_dist / risk_pts, 2), 'mfe_r': round(max_fav_dist / risk_pts, 2), 'held_minutes': held_mins}

    return {'status': 'UNFILLED_END', 'net_r': 0.0, 'mae_r': 0.0, 'mfe_r': 0.0, 'held_minutes': len(forward_m1)}


def get_season_name(dt: datetime.datetime) -> str:
    m = dt.month
    if m in (1, 2): return "Winter"
    elif m in (3, 4): return "Spring"
    elif m in (7, 8): return "Summer"
    elif m in (9, 10, 11): return "Autumn"
    return "Other"


def mine_hypothesis_a_frankfurt_trap(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Hypothesis A: Frankfurt Liquidity Run & London Reversal / Expansion.
    Evaluates: In the 1 hour between Frankfurt Open (06:00/07:00 UTC) and London Open (07:00/08:00 UTC):
    Does Frankfurt sweep Asian session High/Low?
    If London Open candle immediately displaces in reverse with MSS, enter on retracement to Frankfurt swing.
    """
    symbol = data['symbol']
    is_fx = data['is_fx']
    bars_d1 = data['d1']
    bars_m5 = data['m5']
    bars_m1 = data['m1']
    m1_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    spread = 0.00006 if is_fx else 0.20
    min_sl = 0.0008 if is_fx else 3.50
    max_sl = 0.0022 if is_fx else 9.00
    target_rr = 2.5 if is_fx else 3.5
    be_rr = 1.5 if is_fx else 1.8

    candidates = []

    for d_bar in bars_d1:
        day_date = d_bar['dt'].date()
        if day_date.weekday() in (5, 6): continue

        sess_times = get_session_times_for_date(day_date)
        lon_open = sess_times['london']['utc_time']
        fra_open = lon_open - datetime.timedelta(hours=1)

        asian_bars = [b for b in bars_m5 if b['dt'].date() == day_date and b['dt'] < fra_open]
        fra_bars = [b for b in bars_m5 if b['dt'].date() == day_date and fra_open <= b['dt'] < lon_open]

        if len(asian_bars) < 10 or len(fra_bars) < 8:
            continue

        asian_high = max(b['high'] for b in asian_bars)
        asian_low = min(b['low'] for b in asian_bars)
        fra_high = max(b['high'] for b in fra_bars)
        fra_low = min(b['low'] for b in fra_bars)

        fra_swept_high = fra_high > asian_high
        fra_swept_low = fra_low < asian_low

        lon_ts = int(lon_open.timestamp())
        m1_idx = m1_map.get(lon_ts)
        if m1_idx is None:
            cands = [idx for idx, b in enumerate(bars_m1) if b['time'] >= lon_ts]
            if not cands: continue
            m1_idx = cands[0]

        forward_m1 = bars_m1[m1_idx:m1_idx + 600]
        if len(forward_m1) < 120: continue

        # Scenario 1: Frankfurt swept Asian High -> London opens and pushes down (Bearish Reversal Trap)
        if fra_swept_high and not fra_swept_low:
            # Entry at Frankfurt High minus buffer or break below Frankfurt low
            first_15m = forward_m1[:15]
            if first_15m and min(b['low'] for b in first_15m) < fra_low:
                # London confirmed displacement below Frankfurt Low
                entry = fra_low
                sl = fra_high + (0.0002 if is_fx else 1.50)
                dist = abs(entry - sl)
                if min_sl <= dist <= max_sl:
                    sim = simulate_trade(entry, sl, "SHORT", forward_m1[15:], target_rr=target_rr, be_rr=be_rr, spread_val=spread)
                    candidates.append({
                        'date': str(day_date),
                        'season': get_season_name(lon_open),
                        'hypothesis': 'HYP-A_FRANKFURT_TRAP',
                        'symbol': symbol,
                        'direction': 'SHORT',
                        'entry': entry,
                        'sl': sl,
                        'risk_pts': round(dist, 5 if is_fx else 2),
                        'status': sim['status'],
                        'net_r': sim['net_r'],
                        'mfe_r': sim['mfe_r'],
                        'mae_r': sim['mae_r'],
                        'held_minutes': sim['held_minutes']
                    })

        # Scenario 2: Frankfurt swept Asian Low -> London opens and pushes up (Bullish Reversal Trap)
        if fra_swept_low and not fra_swept_high:
            first_15m = forward_m1[:15]
            if first_15m and max(b['high'] for b in first_15m) > fra_high:
                entry = fra_high
                sl = fra_low - (0.0002 if is_fx else 1.50)
                dist = abs(entry - sl)
                if min_sl <= dist <= max_sl:
                    sim = simulate_trade(entry, sl, "LONG", forward_m1[15:], target_rr=target_rr, be_rr=be_rr, spread_val=spread)
                    candidates.append({
                        'date': str(day_date),
                        'season': get_season_name(lon_open),
                        'hypothesis': 'HYP-A_FRANKFURT_TRAP',
                        'symbol': symbol,
                        'direction': 'LONG',
                        'entry': entry,
                        'sl': sl,
                        'risk_pts': round(dist, 5 if is_fx else 2),
                        'status': sim['status'],
                        'net_r': sim['net_r'],
                        'mfe_r': sim['mfe_r'],
                        'mae_r': sim['mae_r'],
                        'held_minutes': sim['held_minutes']
                    })

    return candidates


def mine_hypothesis_b_pre_session_compression(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Hypothesis B: Pre-Session Volatility Compression Breakout.
    In the 45 minutes preceding London Open or NY Open:
    Is the 45M range compressed (< 0.5x 20-day 5M ATR * 9)?
    When the session opens with institutional volume surge, enter on retest of the compression boundary.
    """
    symbol = data['symbol']
    is_fx = data['is_fx']
    bars_d1 = data['d1']
    bars_m5 = data['m5']
    bars_m1 = data['m1']
    m1_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    spread = 0.00006 if is_fx else 0.20
    min_sl = 0.0008 if is_fx else 3.50
    max_sl = 0.0022 if is_fx else 9.00
    target_rr = 2.5 if is_fx else 3.5
    be_rr = 1.5 if is_fx else 1.8

    candidates = []

    for d_bar in bars_d1:
        day_date = d_bar['dt'].date()
        if day_date.weekday() in (5, 6): continue

        sess_times = get_session_times_for_date(day_date)
        milestones = [
            (sess_times['london']['utc_time'], "London_Open"),
            (sess_times['new_york']['utc_time'], "NY_Open")
        ]

        for s_dt, s_label in milestones:
            # If Cable, bypass NY Open
            if is_fx and s_label == "NY_Open":
                continue

            pre_s = s_dt - datetime.timedelta(minutes=45)
            comp_bars = [b for b in bars_m5 if pre_s <= b['dt'] < s_dt]
            if len(comp_bars) < 7: continue

            c_high = max(b['high'] for b in comp_bars)
            c_low = min(b['low'] for b in comp_bars)
            c_range = c_high - c_low

            # Check if compressed
            hist_m5 = [b for b in bars_m5 if b['dt'] < pre_s][-30:]
            if len(hist_m5) < 20: continue
            atr_5m = get_atr(hist_m5, 14)

            # Volatility Squeeze condition: 45M range is less than 2.5x 5M ATR
            if c_range > (2.5 * atr_5m):
                continue

            s_ts = int(s_dt.timestamp())
            m1_idx = m1_map.get(s_ts)
            if m1_idx is None:
                cands = [idx for idx, b in enumerate(bars_m1) if b['time'] >= s_ts]
                if not cands: continue
                m1_idx = cands[0]

            forward_m1 = bars_m1[m1_idx:m1_idx + 600]
            if len(forward_m1) < 120: continue

            first_20m = forward_m1[:20]
            max_p = max(b['high'] for b in first_20m)
            min_p = min(b['low'] for b in first_20m)

            # Bullish expansion breakout
            if max_p > c_high + (0.0003 if is_fx else 1.50):
                entry = c_high
                sl = c_low - (0.0002 if is_fx else 1.00)
                dist = abs(entry - sl)
                if min_sl <= dist <= max_sl:
                    sim = simulate_trade(entry, sl, "LONG", forward_m1[20:], target_rr=target_rr, be_rr=be_rr, spread_val=spread)
                    candidates.append({
                        'date': str(day_date),
                        'season': get_season_name(s_dt),
                        'hypothesis': 'HYP-B_VOLATILITY_COMPRESSION',
                        'symbol': symbol,
                        'session': s_label,
                        'direction': 'LONG',
                        'entry': entry,
                        'sl': sl,
                        'risk_pts': round(dist, 5 if is_fx else 2),
                        'status': sim['status'],
                        'net_r': sim['net_r'],
                        'mfe_r': sim['mfe_r'],
                        'mae_r': sim['mae_r'],
                        'held_minutes': sim['held_minutes']
                    })

            # Bearish expansion breakdown
            elif min_p < c_low - (0.0003 if is_fx else 1.50):
                entry = c_low
                sl = c_high + (0.0002 if is_fx else 1.00)
                dist = abs(entry - sl)
                if min_sl <= dist <= max_sl:
                    sim = simulate_trade(entry, sl, "SHORT", forward_m1[20:], target_rr=target_rr, be_rr=be_rr, spread_val=spread)
                    candidates.append({
                        'date': str(day_date),
                        'season': get_season_name(s_dt),
                        'hypothesis': 'HYP-B_VOLATILITY_COMPRESSION',
                        'symbol': symbol,
                        'session': s_label,
                        'direction': 'SHORT',
                        'entry': entry,
                        'sl': sl,
                        'risk_pts': round(dist, 5 if is_fx else 2),
                        'status': sim['status'],
                        'net_r': sim['net_r'],
                        'mfe_r': sim['mfe_r'],
                        'mae_r': sim['mae_r'],
                        'held_minutes': sim['held_minutes']
                    })

    return candidates


def mine_hypothesis_c_adr_exhaustion_snapback(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Hypothesis C: Macro ADR Exhaustion Mean-Reversion Snapback.
    When intraday expansion reaches >= 85% of 20-day ADR before 15:00 UTC,
    does price form a high-probability reversal back to session equilibrium?
    """
    symbol = data['symbol']
    is_fx = data['is_fx']
    bars_d1 = data['d1']
    bars_m5 = data['m5']
    bars_m1 = data['m1']
    m1_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    spread = 0.00006 if is_fx else 0.20
    min_sl = 0.0008 if is_fx else 3.50
    max_sl = 0.0022 if is_fx else 9.00
    target_rr = 2.0 if is_fx else 2.5  # Mean reversion typically has tighter targets
    be_rr = 1.2 if is_fx else 1.5

    candidates = []

    for i in range(20, len(bars_d1)):
        d_bar = bars_d1[i]
        day_date = d_bar['dt'].date()
        if day_date.weekday() in (5, 6): continue

        prior_20 = bars_d1[i-20:i]
        adr_20 = sum(b['high'] - b['low'] for b in prior_20) / 20.0
        if adr_20 <= 0: continue

        day_m5 = [b for b in bars_m5 if b['dt'].date() == day_date and b['dt'].hour < 16]
        if len(day_m5) < 30: continue

        for idx_m5 in range(25, len(day_m5) - 6):
            cur_b = day_m5[idx_m5]
            window_so_far = day_m5[:idx_m5+1]
            high_so_far = max(b['high'] for b in window_so_far)
            low_so_far = min(b['low'] for b in window_so_far)
            range_so_far = high_so_far - low_so_far

            # ADR exhaustion >= 85%
            if range_so_far >= (0.85 * adr_20):
                # Check if current bar is at extreme and rejecting
                is_at_high = (cur_b['high'] >= high_so_far - (0.0002 if is_fx else 1.00)) and (cur_b['close'] < cur_b['open'])
                is_at_low = (cur_b['low'] <= low_so_far + (0.0002 if is_fx else 1.00)) and (cur_b['close'] > cur_b['open'])

                m1_ts = cur_b['time']
                m1_idx = m1_map.get(m1_ts)
                if m1_idx is None: continue

                forward_m1 = bars_m1[m1_idx:m1_idx + 480]
                if len(forward_m1) < 120: continue

                if is_at_high:
                    entry = cur_b['close']
                    sl = high_so_far + (0.0002 if is_fx else 1.50)
                    dist = abs(entry - sl)
                    if min_sl <= dist <= max_sl:
                        sim = simulate_trade(entry, sl, "SHORT", forward_m1, target_rr=target_rr, be_rr=be_rr, spread_val=spread)
                        candidates.append({
                            'date': str(day_date),
                            'season': get_season_name(cur_b['dt']),
                            'hypothesis': 'HYP-C_ADR_EXHAUSTION',
                            'symbol': symbol,
                            'direction': 'SHORT',
                            'entry': entry,
                            'sl': sl,
                            'risk_pts': round(dist, 5 if is_fx else 2),
                            'status': sim['status'],
                            'net_r': sim['net_r'],
                            'mfe_r': sim['mfe_r'],
                            'mae_r': sim['mae_r'],
                            'held_minutes': sim['held_minutes']
                        })
                        break  # 1 trigger per day max

                elif is_at_low:
                    entry = cur_b['close']
                    sl = low_so_far - (0.0002 if is_fx else 1.50)
                    dist = abs(entry - sl)
                    if min_sl <= dist <= max_sl:
                        sim = simulate_trade(entry, sl, "LONG", forward_m1, target_rr=target_rr, be_rr=be_rr, spread_val=spread)
                        candidates.append({
                            'date': str(day_date),
                            'season': get_season_name(cur_b['dt']),
                            'hypothesis': 'HYP-C_ADR_EXHAUSTION',
                            'symbol': symbol,
                            'direction': 'LONG',
                            'entry': entry,
                            'sl': sl,
                            'risk_pts': round(dist, 5 if is_fx else 2),
                            'status': sim['status'],
                            'net_r': sim['net_r'],
                            'mfe_r': sim['mfe_r'],
                            'mae_r': sim['mae_r'],
                            'held_minutes': sim['held_minutes']
                        })
                        break

    return candidates


def run_mining_pipeline():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 90)
    print("🚀 TRADINGGUARD - AUTONOMOUS QUANTITATIVE SETUP MINING & DISCOVERY ENGINE")
    print("Scope: Full-Year 2026 (175 Trading Days | 700 Sessions | Gold & GBPUSD)")
    print("=" * 90)

    symbols = ["GBPUSD_o", "XAUUSD_o"]
    all_mined_trades = []

    for sym in symbols:
        data = load_symbol_year_data(sym)

        print(f"\n🔍 Mining Hypothesis A (Frankfurt Liquidity Trap) on {sym}...")
        t_a = mine_hypothesis_a_frankfurt_trap(data)
        print(f"   => Found {len(t_a)} trade opportunities.")
        all_mined_trades.extend(t_a)

        print(f"\n🔍 Mining Hypothesis B (Pre-Session Volatility Squeeze) on {sym}...")
        t_b = mine_hypothesis_b_pre_session_compression(data)
        print(f"   => Found {len(t_b)} trade opportunities.")
        all_mined_trades.extend(t_b)

        print(f"\n🔍 Mining Hypothesis C (ADR Exhaustion Snapback) on {sym}...")
        t_c = mine_hypothesis_c_adr_exhaustion_snapback(data)
        print(f"   => Found {len(t_c)} trade opportunities.")
        all_mined_trades.extend(t_c)

    print(f"\n✅ Total Candidate Setups Evaluated Across Both Assets: {len(all_mined_trades)}")
    df_all = pd.DataFrame(all_mined_trades)
    df_all.to_csv(OUTPUT_DIR / "mined_candidate_trades_all.csv", index=False)

    def stats(sub):
        n = len(sub)
        if n == 0: return {'fills': 0, 'wins': 0, 'losses': 0, 'be': 0, 'wr': 0.0, 'net_r': 0.0, 'pf': 0.0}
        w = len(sub[sub['status'] == 'WIN'])
        l = len(sub[sub['status'] == 'LOSS'])
        b = len(sub[sub['status'] == 'BREAKEVEN'])
        net_r = sub['net_r'].sum()
        gw = sub[sub['net_r'] > 0]['net_r'].sum()
        gl = abs(sub[sub['net_r'] < 0]['net_r'].sum())
        pf = round(gw / max(0.001, gl), 2)
        wr = round((w / n) * 100.0, 1)
        return {'fills': n, 'wins': w, 'losses': l, 'be': b, 'wr': wr, 'net_r': round(net_r, 2), 'pf': pf}

    df_fills = df_all[df_all['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]

    print("\n" + "=" * 90)
    print("📊 MULTI-SEASONAL DISCOVERY SCORECARD BY CANDIDATE HYPOTHESIS")
    print("=" * 90)

    scorecard = {}
    for hyp in sorted(df_fills['hypothesis'].unique()):
        print(f"\n🔬 EVALUATING {hyp}:")
        hyp_sub = df_fills[df_fills['hypothesis'] == hyp]

        for sym in symbols:
            s_sub = hyp_sub[hyp_sub['symbol'] == sym]
            st = stats(s_sub)
            print(f"  * Symbol: {sym:<9} | {st['fills']:>2} Fills | {st['wins']:>2}W - {st['losses']:>2}L - {st['be']:>2}BE | WR: {st['wr']:>5.1f}% | Net: {st['net_r']:>+6.1f}R | PF: {st['pf']:>4.2f}")

            # Seasonal Breakdown for this symbol
            season_res = {}
            for s_name in ['Winter', 'Spring', 'Summer', 'Autumn']:
                seas_sub = s_sub[s_sub['season'] == s_name]
                st_s = stats(seas_sub)
                season_res[s_name] = st_s
                print(f"      - {s_name:<7}: {st_s['fills']:>2} Fills | {st_s['wins']:>2}W - {st_s['losses']:>2}L - {st_s['be']:>2}BE | WR: {st_s['wr']:>5.1f}% | Net: {st_s['net_r']:>+5.1f}R | PF: {st_s['pf']:>4.2f}")

            scorecard[f"{hyp}_{sym}"] = {
                'total': st,
                'seasons': season_res
            }

    with open(OUTPUT_DIR / "mining_scorecard.json", "w", encoding="utf-8") as f:
        json.dump(scorecard, f, indent=2)

    print(f"\n🎉 Quantitative Mining Scorecard Saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    run_mining_pipeline()
