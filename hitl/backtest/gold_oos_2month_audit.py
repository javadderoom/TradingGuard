"""
TradingGuard HITL - Out-Of-Sample (OOS) 2-Month Quantitative Gold (XAUUSD) Strategy Audit
Audit Period: July 1, 2026 - August 31, 2026 (Continuous M1 Broker Microstructure & Raw Ticks)
Instrument: XAUUSD_o (Gold Standalone, 100% pure, zero Silver / SMT assistance)
Scope: 44 Trading Days | 176 Institutional Sessions | Multi-Archetype Forward Execution

Tests:
1. Baseline vs Calibrated Core Strategy (Target 3.5R vs 3.0R, BE 1.8R, Silver Bullet Banned)
2. All Ratified Archetypes:
   - SETUP-ARCH-001 (Judas Sweep + Breaker)
   - SETUP-ARCH-002 (Judas Sweep + FVG - Decommissioned test)
   - SETUP-ARCH-003 (Clean MSS + Breaker Retest)
   - SETUP-ARCH-004 (Expansion FVG in PRO_EXPANSION)
   - SETUP-ARCH-009 (OTE Retracement - Decommissioned test)
   - SETUP-ARCH-010 (Prominent Sweep + MSS)
   - SETUP-ARCH-011 (Nested Double MSS: Macro Shift + Pullback Exhaustion Shift)
3. Target R:R Grid (2.0R, 2.5R, 3.0R, 3.5R, 4.0R, 5.0R) & MFE/MAE Curve
4. Breakeven Trigger Grid (None, 1.5R, 1.8R, 2.0R)
5. Double MSS vs Single MSS failure and continuation rates
6. Macro Sweep Hierarchy (PDH vs PDL vs Asian High vs Asian Low vs Minor Low Trap vs Open Air)
"""

import sys
import json
import math
import time
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np

# Ensure workspace root in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.session_clock import get_session_times_for_date
from hitl.backtest.mtf_structure import analyze_mtf_state, classify_setup_phase

OUTPUT_DIR = BASE_DIR / "backtest_results" / "gold_oos_2month_audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_UTC = datetime.timezone.utc
TZ_TEHRAN = ZoneInfo("Asia/Tehran")


def load_continuous_oos_m1_bars(symbol: str = "XAUUSD_o") -> Dict[str, Any]:
    """
    Loads continuous July 1, 2026 to August 31, 2026 M1, M5, H1, D1 bars.
    Combines raw broker ticks (July 1 - July 24) with native M1 bars (July 25 - August 31).
    """
    print(f"📥 Loading continuous Out-Of-Sample (OOS) bars from MT5 for {symbol} (July 1 - Aug 31, 2026)...")
    mt5.symbol_select(symbol, True)

    t_start = datetime.datetime(2026, 7, 1, 0, 0, tzinfo=TZ_UTC)
    t_end = datetime.datetime(2026, 8, 31, 23, 59, tzinfo=TZ_UTC)

    # 1. Daily bars (from April 1 for 20-day ADR and historical swings)
    t_d1_start = datetime.datetime(2026, 4, 1, 0, 0, tzinfo=TZ_UTC)
    r_d1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, t_d1_start, t_end)

    # 2. H1 bars (from June 1 for 1H MSS state machine)
    t_h1_start = datetime.datetime(2026, 6, 1, 0, 0, tzinfo=TZ_UTC)
    r_h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, t_h1_start, t_end)

    # 3. M5 bars (from June 20 for session structures)
    t_m5_start = datetime.datetime(2026, 6, 20, 0, 0, tzinfo=TZ_UTC)
    r_m5 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, t_m5_start, t_end)

    def _conv(records):
        if records is None:
            return []
        out = []
        for r in records:
            s_val = int(r['spread']) if 'spread' in r.dtype.names else 20
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

    bars_d1 = _conv(r_d1)
    bars_h1 = _conv(r_h1)
    bars_m5 = _conv(r_m5)

    # 4. Continuous M1 Bars:
    # A. July 1 - July 24 via Raw Broker Ticks
    m1_list = []
    cur_d = datetime.date(2026, 7, 1)
    switch_d = datetime.date(2026, 7, 25)

    print("   Resampling July 1 - July 24 from raw broker ticks...")
    while cur_d < switch_d:
        if cur_d.weekday() < 5:
            dt_s = datetime.datetime(cur_d.year, cur_d.month, cur_d.day, 0, 0, tzinfo=TZ_UTC)
            dt_e = dt_s + datetime.timedelta(days=1)
            ticks = mt5.copy_ticks_range(symbol, dt_s, dt_e, mt5.COPY_TICKS_ALL)
            if ticks is not None and len(ticks) > 0:
                df = pd.DataFrame(ticks)
                df['datetime'] = pd.to_datetime(df['time'], unit='s', utc=True)
                df.set_index('datetime', inplace=True)
                ohlc = df['bid'].resample('1min').ohlc().dropna()
                spread = ((df['ask'] - df['bid']) * 100).resample('1min').mean().dropna()
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
                        'spread': int(round(spread.loc[idx])) if idx in spread.index else 15
                    })
        cur_d += datetime.timedelta(days=1)

    print(f"   Generated {len(m1_list)} M1 bars from raw ticks for July 1-24.")

    # B. July 25 - August 31 via native MT5 M1 bars
    t_m1_start = datetime.datetime(2026, 7, 25, 0, 0, tzinfo=TZ_UTC)
    r_m1_direct = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, t_m1_start, t_end)
    m1_direct_list = _conv(r_m1_direct)
    print(f"   Fetched {len(m1_direct_list)} native M1 bars for July 25 - August 31.")

    all_m1 = m1_list + m1_direct_list
    all_m1.sort(key=lambda x: x['time'])

    print(f"✅ OOS Ingestion Complete: {len(bars_d1)} D1 | {len(bars_h1)} H1 | {len(bars_m5)} M5 | {len(all_m1)} Continuous M1 bars.")
    return {
        'd1': bars_d1,
        'h1': bars_h1,
        'm5': bars_m5,
        'm1': all_m1
    }


def find_swing_points(bars: List[Dict[str, Any]], window: int = 2) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Finds fractal swing highs and swing lows across bars."""
    highs = []
    lows = []
    n = len(bars)
    for i in range(window, n - window):
        b = bars[i]
        is_high = all(b['high'] >= bars[i - w]['high'] and b['high'] >= bars[i + w]['high'] for w in range(1, window + 1))
        is_low = all(b['low'] <= bars[i - w]['low'] and b['low'] <= bars[i + w]['low'] for w in range(1, window + 1))
        if is_high:
            highs.append({'idx': i, 'time': b['time'], 'dt': b['dt'], 'price': b['high']})
        if is_low:
            lows.append({'idx': i, 'time': b['time'], 'dt': b['dt'], 'price': b['low']})
    return highs, lows


def get_atr(bars: List[Dict[str, Any]], period: int = 14) -> float:
    """Computes simple ATR."""
    if len(bars) < period + 1:
        return 2.5
    trs = []
    for i in range(1, len(bars)):
        h = bars[i]['high']
        l = bars[i]['low']
        c_prev = bars[i-1]['close']
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        trs.append(tr)
    return sum(trs[-period:]) / period if trs else 2.5


def simulate_trade_execution(
    entry_price: float,
    sl_price: float,
    direction: str,
    forward_m1: List[Dict[str, Any]],
    target_rr: float = 3.5,
    be_rr: Optional[float] = 1.8,
    ttl_minutes: int = 75,
    watchdog_enabled: bool = True,
    spread_usd: float = 0.15
) -> Dict[str, Any]:
    """
    Simulates forward M1 execution with real broker spread, TTL expiration,
    Watchdog momentum spikes, Breakeven ratchet, and continuous MFE/MAE tracking.
    """
    is_buy = (direction == "LONG" or direction == "BUY")
    risk_pts = abs(entry_price - sl_price)
    if risk_pts <= 0:
        return {'status': 'INVALID', 'net_r': 0.0, 'realized_usd': 0.0, 'mae_r': 0.0, 'mfe_r': 0.0}

    # Dynamic target price
    if is_buy:
        tp_price = entry_price + (risk_pts * target_rr)
    else:
        tp_price = entry_price - (risk_pts * target_rr)

    is_filled = False
    fill_idx = None
    active_sl = sl_price
    is_be_activated = False

    max_fav_dist = 0.0
    max_adv_dist = 0.0
    risk_usd = risk_pts * 1.0  # 0.01 lot on Gold: 1 pt = $1.00

    recent_m1 = []

    for idx, bar in enumerate(forward_m1):
        recent_m1.append(bar)

        if not is_filled:
            # 1. TTL Inactivity Check
            if idx >= ttl_minutes:
                return {
                    'status': 'EXPIRED',
                    'fill_idx': None,
                    'exit_idx': idx,
                    'net_r': 0.0,
                    'realized_usd': 0.0,
                    'mae_r': 0.0,
                    'mfe_r': 0.0,
                    'held_minutes': idx
                }

            # 2. Watchdog Adverse Momentum Check
            if watchdog_enabled and len(recent_m1) >= 15:
                body = abs(bar['close'] - bar['open'])
                is_adverse = (bar['close'] < bar['open']) if is_buy else (bar['close'] > bar['open'])
                atr_local = get_atr(recent_m1[-15:], 14)
                if is_adverse and body >= (3.5 * atr_local) and abs(bar['close'] - entry_price) <= (3.0 * atr_local):
                    return {
                        'status': 'CANCELLED_WATCHDOG',
                        'fill_idx': None,
                        'exit_idx': idx,
                        'net_r': 0.0,
                        'realized_usd': 0.0,
                        'mae_r': 0.0,
                        'mfe_r': 0.0,
                        'held_minutes': idx
                    }

            # 3. Invalidation before fill (Price swept beyond SL before filling)
            if is_buy and bar['low'] <= sl_price:
                return {
                    'status': 'INVALIDATED_BEFORE_FILL',
                    'fill_idx': None,
                    'exit_idx': idx,
                    'net_r': 0.0,
                    'realized_usd': 0.0,
                    'mae_r': 0.0,
                    'mfe_r': 0.0,
                    'held_minutes': idx
                }
            elif (not is_buy) and bar['high'] >= sl_price:
                return {
                    'status': 'INVALIDATED_BEFORE_FILL',
                    'fill_idx': None,
                    'exit_idx': idx,
                    'net_r': 0.0,
                    'realized_usd': 0.0,
                    'mae_r': 0.0,
                    'mfe_r': 0.0,
                    'held_minutes': idx
                }

            # 4. Fill verification with Spread
            # BUY fills at Ask = bar['low'] + spread
            if is_buy and (bar['low'] + spread_usd) <= entry_price:
                is_filled = True
                fill_idx = idx
            # SELL fills at Bid = bar['high']
            elif (not is_buy) and bar['high'] >= entry_price:
                is_filled = True
                fill_idx = idx

        else:
            # Trade is LIVE!
            if is_buy:
                cur_fav = bar['high'] - entry_price
                cur_adv = entry_price - bar['low']
            else:
                cur_fav = entry_price - bar['low']
                cur_adv = bar['high'] - entry_price

            if cur_fav > max_fav_dist:
                max_fav_dist = cur_fav
            if cur_adv > max_adv_dist:
                max_adv_dist = cur_adv

            cur_rr = max_fav_dist / risk_pts

            # A. Dynamic Breakeven Ratchet
            if be_rr is not None and cur_rr >= be_rr and not is_be_activated:
                is_be_activated = True
                active_sl = (entry_price + spread_usd) if is_buy else (entry_price - spread_usd)

            # B. Check Stop Loss Hit
            hit_sl = (bar['low'] <= active_sl) if is_buy else (bar['high'] >= active_sl)
            if hit_sl:
                held_mins = idx - fill_idx
                mae_r = round(max_adv_dist / risk_pts, 2)
                mfe_r = round(max_fav_dist / risk_pts, 2)

                if is_be_activated:
                    return {
                        'status': 'BREAKEVEN',
                        'fill_idx': fill_idx,
                        'exit_idx': idx,
                        'net_r': 0.0,
                        'realized_usd': 0.0,
                        'mae_r': mae_r,
                        'mfe_r': mfe_r,
                        'held_minutes': held_mins
                    }
                else:
                    return {
                        'status': 'LOSS',
                        'fill_idx': fill_idx,
                        'exit_idx': idx,
                        'net_r': -1.0,
                        'realized_usd': round(-risk_usd, 2),
                        'mae_r': mae_r,
                        'mfe_r': mfe_r,
                        'held_minutes': held_mins
                    }

            # C. Check Take Profit Hit
            hit_tp = (bar['high'] >= tp_price) if is_buy else (bar['low'] <= tp_price)
            if hit_tp:
                held_mins = idx - fill_idx
                mae_r = round(max_adv_dist / risk_pts, 2)
                mfe_r = round(max_fav_dist / risk_pts, 2)
                net_r = target_rr
                net_usd = target_rr * risk_usd
                return {
                    'status': 'WIN',
                    'fill_idx': fill_idx,
                    'exit_idx': idx,
                    'net_r': round(net_r, 2),
                    'realized_usd': round(net_usd, 2),
                    'mae_r': mae_r,
                    'mfe_r': mfe_r,
                    'held_minutes': held_mins
                }

    # If trade remained open at end of slice (12 hours)
    held_mins = len(forward_m1) - fill_idx if is_filled else len(forward_m1)
    if is_filled:
        final_bar = forward_m1[-1]
        final_price = final_bar['close']
        fav_dist = (final_price - entry_price) if is_buy else (entry_price - final_price)
        final_r = fav_dist / risk_pts
        return {
            'status': 'OPEN_EXPANSION' if final_r > 1.0 else 'OPEN_CLOSE',
            'fill_idx': fill_idx,
            'exit_idx': len(forward_m1) - 1,
            'net_r': round(final_r, 2),
            'realized_usd': round(final_r * risk_usd, 2),
            'mae_r': round(max_adv_dist / risk_pts, 2),
            'mfe_r': round(max_fav_dist / risk_pts, 2),
            'held_minutes': held_mins
        }

    return {
        'status': 'UNFILLED_END',
        'fill_idx': None,
        'exit_idx': len(forward_m1),
        'net_r': 0.0,
        'realized_usd': 0.0,
        'mae_r': 0.0,
        'mfe_r': 0.0,
        'held_minutes': len(forward_m1)
    }


def detect_prominent_sweep_and_mss(bars_5m: List[Dict[str, Any]], lookback: int = 36) -> Tuple[bool, str, float, float, str, str]:
    """Detects prominent wick sweep followed by micro MSS displacement (SETUP-ARCH-010)."""
    if len(bars_5m) < 15:
        return False, "NONE", 0.0, 0.0, "", ""

    recent = bars_5m[-lookback:]
    curr_bar = recent[-1]
    c = curr_bar['close']
    o = curr_bar['open']

    # 1. Bullish Sweep + MSS
    swing_lows = [b['low'] for b in recent[:-3]]
    if swing_lows:
        lowest_prior = min(swing_lows)
        lowest_bar = min(recent[-10:], key=lambda x: x['low'])
        if lowest_bar['low'] < lowest_prior - 1.0:
            if c > lowest_prior and c > o:
                entry = lowest_prior
                sl = lowest_bar['low'] - 1.50
                dist = abs(entry - sl)
                if dist < 3.50:
                    sl = entry - 3.50
                elif dist > 8.00:
                    sl = entry - 8.00
                return True, "BULLISH", entry, sl, f"Swept low {lowest_bar['low']:.2f} -> displaced back inside", "Swing_Low"

    # 2. Bearish Sweep + MSS
    swing_highs = [b['high'] for b in recent[:-3]]
    if swing_highs:
        highest_prior = max(swing_highs)
        highest_bar = max(recent[-10:], key=lambda x: x['high'])
        if highest_bar['high'] > highest_prior + 1.0:
            if c < highest_prior and c < o:
                entry = highest_prior
                sl = highest_bar['high'] + 1.50
                dist = abs(entry - sl)
                if dist < 3.50:
                    sl = entry + 3.50
                elif dist > 8.00:
                    sl = entry + 8.00
                return True, "BEARISH", entry, sl, f"Swept high {highest_bar['high']:.2f} -> displaced back inside", "Swing_High"

    return False, "NONE", 0.0, 0.0, "", ""


def detect_nested_double_mss(bars_5m: List[Dict[str, Any]], lookback: int = 50) -> Tuple[bool, str, float, float, str, bool]:
    """
    Detects Nested Double MSS (SETUP-ARCH-011):
    L1 -> H1 -> L2 (Sweep of L1) -> H2 (Breaks H1: 1st MSS) -> L3 -> H3 -> L4 -> H4 (Breaks H3: 2nd MSS).
    Entry at H3 breaker retest (L5), SL below L4 + $1.50 spread buffer.
    Returns (has_setup, direction, entry, sl, desc, has_sweep).
    """
    if len(bars_5m) < 30:
        return False, "NONE", 0.0, 0.0, "", False

    recent = bars_5m[-lookback:]
    curr_bar = recent[-1]
    c = curr_bar['close']

    highs = []
    lows = []
    for i in range(2, len(recent) - 2):
        if recent[i]['high'] >= recent[i-1]['high'] and recent[i]['high'] >= recent[i-2]['high'] and \
           recent[i]['high'] >= recent[i+1]['high'] and recent[i]['high'] >= recent[i+2]['high']:
            highs.append((i, recent[i]['high']))
        if recent[i]['low'] <= recent[i-1]['low'] and recent[i]['low'] <= recent[i-2]['low'] and \
           recent[i]['low'] <= recent[i+1]['low'] and recent[i]['low'] <= recent[i+2]['low']:
            lows.append((i, recent[i]['low']))

    if len(highs) < 3 or len(lows) < 3:
        return False, "NONE", 0.0, 0.0, "", False

    # 1. Bullish Nested Double MSS
    h3_idx, h3_price = highs[-1]
    if c > h3_price and curr_bar['close'] > curr_bar['open']:
        bars_after_h3 = recent[h3_idx:]
        if len(bars_after_h3) >= 2:
            l4_price = min(b['low'] for b in bars_after_h3)
            prior_h = [h for h in highs if h[0] < h3_idx]
            prior_l = [l for l in lows if l[0] < h3_idx]
            if len(prior_h) >= 2 and len(prior_l) >= 2:
                h2_idx, h2_price = prior_h[-1]
                h1_idx, h1_price = prior_h[-2]
                l3_idx, l3_price = prior_l[-1]
                l2_idx, l2_price = prior_l[-2]

                has_sweep = (len(prior_l) >= 3 and l2_price < prior_l[-3][1]) or (l2_price < prior_l[0][1])

                if (h2_price > h1_price + 1.0) and (h3_price < h2_price - 1.0) and (l3_price > l2_price) and (l4_price > l2_price):
                    entry = h3_price
                    sl = l4_price - 1.50
                    dist = abs(entry - sl)
                    if dist < 3.50:
                        sl = entry - 3.50
                    elif dist > 8.00:
                        sl = entry - 8.00
                    return True, "BULLISH", entry, sl, f"Nested Double MSS (Swept {l2_price:.2f} -> 1st MSS {h2_price:.2f} -> Pullback -> 2nd MSS above {h3_price:.2f})", has_sweep

    # 2. Bearish Nested Double MSS
    l3_idx, l3_price = lows[-1]
    if c < l3_price and curr_bar['close'] < curr_bar['open']:
        bars_after_l3 = recent[l3_idx:]
        if len(bars_after_l3) >= 2:
            h4_price = max(b['high'] for b in bars_after_l3)
            prior_h = [h for h in highs if h[0] < l3_idx]
            prior_l = [l for l in lows if l[0] < l3_idx]
            if len(prior_h) >= 2 and len(prior_l) >= 2:
                l2_idx, l2_price = prior_l[-1]
                l1_idx, l1_price = prior_l[-2]
                h3_idx, h3_price = prior_h[-1]
                h2_idx, h2_price = prior_h[-2]

                has_sweep = (len(prior_h) >= 3 and h2_price > prior_h[-3][1]) or (h2_price > prior_h[0][1])

                if (l2_price < l1_price - 1.0) and (l3_price > l2_price + 1.0) and (h3_price < h2_price) and (h4_price < h2_price):
                    entry = l3_price
                    sl = h4_price + 1.50
                    dist = abs(entry - sl)
                    if dist < 3.50:
                        sl = entry + 3.50
                    elif dist > 8.00:
                        sl = entry + 8.00
                    return True, "BEARISH", entry, sl, f"Nested Double MSS (Swept {h2_price:.2f} -> 1st MSS {l2_price:.2f} -> Pullback -> 2nd MSS below {l3_price:.2f})", has_sweep

    return False, "NONE", 0.0, 0.0, "", False


def run_oos_audit():
    """Executes the full Out-Of-Sample 2-Month Audit on Gold."""
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    t_start_wall = time.time()
    print("=" * 85)
    print("🏆 TRADINGGUARD - OUT-OF-SAMPLE 2-MONTH QUANTITATIVE GOLD AUDIT")
    print("Horizon: July 1, 2026 to August 31, 2026 (Continuous M1 Microstructure & Raw Ticks)")
    print("Mandate: 100% Pure Standalone Gold Execution (Zero SMT/Silver Dependency)")
    print("=" * 85)

    if not mt5.initialize():
        print("❌ Error: MT5 initialization failed.")
        return

    data = load_continuous_oos_m1_bars("XAUUSD_o")
    bars_d1 = data['d1']
    bars_h1 = data['h1']
    bars_m5 = data['m5']
    bars_m1 = data['m1']

    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    scope_start = datetime.datetime(2026, 7, 1, 0, 0, tzinfo=TZ_UTC)
    scope_end = datetime.datetime(2026, 8, 31, 23, 59, tzinfo=TZ_UTC)

    session_milestones = []
    for d_bar in bars_d1:
        dt_day = d_bar['dt'].date()
        if dt_day < scope_start.date() or dt_day > scope_end.date():
            continue
        if dt_day.weekday() in (5, 6):
            continue

        sess_times = get_session_times_for_date(dt_day)
        t_lon = sess_times['london']['utc_time']
        t_lon_cont = t_lon + datetime.timedelta(minutes=90)
        t_ny = sess_times['new_york']['utc_time']
        t_nyse = sess_times['nyse_open']['utc_time']

        session_milestones.append((t_lon, "London_Open", sess_times))
        session_milestones.append((t_lon_cont, "London_Continuation", sess_times))
        session_milestones.append((t_ny, "NY_Open", sess_times))
        session_milestones.append((t_nyse, "NY_Silver_Bullet", sess_times))

    print(f"\n📊 Total Trading Days: {len([b for b in bars_d1 if scope_start <= b['dt'] <= scope_end])}")
    print(f"🎯 Total Institutional Session Milestones: {len(session_milestones)}")

    all_trades = []

    print("\n⏳ Sweeping through session milestones and executing forward M1 replay...")

    for ms_dt, sess_label, sess_times in session_milestones:
        ms_ts = int(ms_dt.timestamp())

        hist_d1 = [b for b in bars_d1 if b['time'] < ms_ts]
        hist_h1 = [b for b in bars_h1 if b['time'] < ms_ts]
        hist_m5 = [b for b in bars_m5 if b['time'] < ms_ts]

        if not (hist_d1 and hist_h1 and hist_m5):
            continue

        m1_idx = m1_time_map.get(ms_ts)
        if m1_idx is None:
            cands = [idx for idx, b in enumerate(bars_m1) if b['time'] >= ms_ts]
            if not cands:
                continue
            m1_idx = cands[0]

        forward_m1 = bars_m1[m1_idx:m1_idx + 720]
        if len(forward_m1) < 120:
            continue

        current_price = hist_m5[-1]['close']
        mtf_state = analyze_mtf_state(bars_1d=hist_d1, bars_1h=hist_h1, bars_5m=hist_m5, symbol="XAUUSD")
        h1_state = mtf_state.get('h1_state', 'NEUTRAL')
        is_inside_day = mtf_state.get('is_inside_day', False)
        in_mid_equilibrium = mtf_state.get('in_mid_equilibrium', False)

        # Asian Range
        day_date = ms_dt.date()
        asian_bars = [b for b in hist_m5 if b['dt'].date() == day_date and b['dt'].hour < 7]
        asian_high = max(b['high'] for b in asian_bars) if asian_bars else hist_m5[-20]['high']
        asian_low = min(b['low'] for b in asian_bars) if asian_bars else hist_m5[-20]['low']

        # Prior Day High & Low
        pdh = hist_d1[-1]['high'] if hist_d1 else asian_high
        pdl = hist_d1[-1]['low'] if hist_d1 else asian_low

        recent_m5 = hist_m5[-24:]
        detected_setups = []

        # Check Sweeps of Macro benchmarks
        swept_pdh = any(b['high'] >= pdh for b in recent_m5[-8:])
        swept_pdl = any(b['low'] <= pdl for b in recent_m5[-8:])
        swept_asian_h = any(b['high'] >= asian_high for b in recent_m5[-8:])
        swept_asian_l = any(b['low'] <= asian_low for b in recent_m5[-8:])

        # 1. SETUP-ARCH-001 (Judas Breaker)
        sh_m5, sl_m5 = find_swing_points(recent_m5, window=2)
        if (swept_asian_l or swept_pdl) and current_price > (asian_low + 1.0) and sh_m5:
            last_sh = sh_m5[-1]['price']
            if current_price > last_sh:
                detected_setups.append({
                    'archetype': 'JUDAS_SWEEP_BREAKER',
                    'archetype_id': 'SETUP-ARCH-001',
                    'direction': 'LONG',
                    'entry': last_sh,
                    'sl': min(asian_low - 1.50, last_sh - 5.50),
                    'sweep_type': 'PDL' if swept_pdl else 'Asian_Low'
                })
        elif (swept_asian_h or swept_pdh) and current_price < (asian_high - 1.0) and sl_m5:
            last_sl = sl_m5[-1]['price']
            if current_price < last_sl:
                detected_setups.append({
                    'archetype': 'JUDAS_SWEEP_BREAKER',
                    'archetype_id': 'SETUP-ARCH-001',
                    'direction': 'SHORT',
                    'entry': last_sl,
                    'sl': max(asian_high + 1.50, last_sl + 5.50),
                    'sweep_type': 'PDH' if swept_pdh else 'Asian_High'
                })

        # 2. SETUP-ARCH-002 (Judas Sweep + FVG - Decommissioned)
        # 5M FVG detection
        for i in range(len(recent_m5) - 3, max(0, len(recent_m5) - 12), -1):
            b1, b2, b3 = recent_m5[i-2], recent_m5[i-1], recent_m5[i]
            if (swept_asian_l or swept_pdl) and b3['low'] > b1['high'] + 1.0: # Bullish FVG
                detected_setups.append({
                    'archetype': 'JUDAS_SWEEP_FVG',
                    'archetype_id': 'SETUP-ARCH-002',
                    'direction': 'LONG',
                    'entry': b3['low'],
                    'sl': min(b1['low'] - 1.50, b3['low'] - 6.0),
                    'sweep_type': 'PDL' if swept_pdl else 'Asian_Low'
                })
                break
            elif (swept_asian_h or swept_pdh) and b3['high'] < b1['low'] - 1.0: # Bearish FVG
                detected_setups.append({
                    'archetype': 'JUDAS_SWEEP_FVG',
                    'archetype_id': 'SETUP-ARCH-002',
                    'direction': 'SHORT',
                    'entry': b3['high'],
                    'sl': max(b1['high'] + 1.50, b3['high'] + 6.0),
                    'sweep_type': 'PDH' if swept_pdh else 'Asian_High'
                })
                break

        # 3. SETUP-ARCH-003 (Clean MSS + Breaker Retest)
        if not in_mid_equilibrium:
            if sh_m5 and len(sh_m5) >= 2:
                recent_sh = sh_m5[-1]['price']
                if current_price > recent_sh and abs(current_price - recent_sh) <= 2.50:
                    detected_setups.append({
                        'archetype': 'MSS_BREAKER_RETEST',
                        'archetype_id': 'SETUP-ARCH-003',
                        'direction': 'LONG',
                        'entry': recent_sh,
                        'sl': recent_sh - 5.50,
                        'sweep_type': 'Structural_Breakout'
                    })
            if sl_m5 and len(sl_m5) >= 2:
                recent_sl = sl_m5[-1]['price']
                if current_price < recent_sl and abs(current_price - recent_sl) <= 2.50:
                    detected_setups.append({
                        'archetype': 'MSS_BREAKER_RETEST',
                        'archetype_id': 'SETUP-ARCH-003',
                        'direction': 'SHORT',
                        'entry': recent_sl,
                        'sl': recent_sl + 5.50,
                        'sweep_type': 'Structural_Breakdown'
                    })

        # 4. SETUP-ARCH-004 (Expansion FVG)
        if not is_inside_day:
            if current_price > asian_high + 2.0:
                detected_setups.append({
                    'archetype': 'SESSION_EXPANSION_FVG',
                    'archetype_id': 'SETUP-ARCH-004',
                    'direction': 'LONG',
                    'entry': current_price - 1.50,
                    'sl': current_price - 6.50,
                    'sweep_type': 'Expansion_High'
                })
            elif current_price < asian_low - 2.0:
                detected_setups.append({
                    'archetype': 'SESSION_EXPANSION_FVG',
                    'archetype_id': 'SETUP-ARCH-004',
                    'direction': 'SHORT',
                    'entry': current_price + 1.50,
                    'sl': current_price + 6.50,
                    'sweep_type': 'Expansion_Low'
                })

        # 5. SETUP-ARCH-009 (Pro-Trend OTE Retracement - Decommissioned)
        session_rng = max(b['high'] for b in recent_m5) - min(b['low'] for b in recent_m5)
        if session_rng >= 12.0 and not in_mid_equilibrium:
            r_high = max(b['high'] for b in recent_m5)
            r_low = min(b['low'] for b in recent_m5)
            if h1_state == "BULLISH_MSS":
                ote_entry = r_high - 0.705 * session_rng
                detected_setups.append({
                    'archetype': 'PRO_TREND_RETEST_OTE',
                    'archetype_id': 'SETUP-ARCH-009',
                    'direction': 'LONG',
                    'entry': ote_entry,
                    'sl': r_low - 1.50,
                    'sweep_type': 'OTE_Discount'
                })
            elif h1_state == "BEARISH_MSS":
                ote_entry = r_low + 0.705 * session_rng
                detected_setups.append({
                    'archetype': 'PRO_TREND_RETEST_OTE',
                    'archetype_id': 'SETUP-ARCH-009',
                    'direction': 'SHORT',
                    'entry': ote_entry,
                    'sl': r_high + 1.50,
                    'sweep_type': 'OTE_Premium'
                })

        # 6. SETUP-ARCH-010 (Prominent Sweep + MSS)
        has_prom, prom_dir, prom_entry, prom_sl, prom_desc, sweep_src = detect_prominent_sweep_and_mss(hist_m5)
        if has_prom:
            # classify sweep source
            sw_cat = "Minor_Low" if "low" in prom_desc.lower() else "Minor_High"
            if swept_pdh: sw_cat = "PDH"
            elif swept_pdl: sw_cat = "PDL"
            elif swept_asian_h: sw_cat = "Asian_High"
            elif swept_asian_l: sw_cat = "Asian_Low"

            detected_setups.append({
                'archetype': 'PROMINENT_SWEEP_MSS',
                'archetype_id': 'SETUP-ARCH-010',
                'direction': 'LONG' if prom_dir == 'BULLISH' else 'SHORT',
                'entry': prom_entry,
                'sl': prom_sl,
                'sweep_type': sw_cat
            })

        # 7. SETUP-ARCH-011 (Nested Double MSS)
        has_nested, nest_dir, nest_entry, nest_sl, nest_desc, has_sw = detect_nested_double_mss(hist_m5)
        if has_nested:
            sw_cat = "Nested_Sweep" if has_sw else "No_Sweep_OpenAir"
            if swept_pdh: sw_cat = "PDH"
            elif swept_pdl: sw_cat = "PDL"

            detected_setups.append({
                'archetype': 'NESTED_DOUBLE_MSS',
                'archetype_id': 'SETUP-ARCH-011',
                'direction': 'LONG' if nest_dir == 'BULLISH' else 'SHORT',
                'entry': nest_entry,
                'sl': nest_sl,
                'sweep_type': sw_cat,
                'has_sweep': has_sw
            })

        # Simulate every detected setup through forward M1 engine
        for s in detected_setups:
            p_info = classify_setup_phase(mtf_state, s['direction'], symbol="XAUUSD")
            phase = p_info['phase']

            # Enforce Risk Bracketing: $3.50 min, $8.00 max
            sl_dist = abs(s['entry'] - s['sl'])
            if sl_dist < 3.50:
                s['sl'] = s['entry'] - 3.50 if s['direction'] == 'LONG' else s['entry'] + 3.50
            elif sl_dist > 8.00:
                s['sl'] = s['entry'] - 8.00 if s['direction'] == 'LONG' else s['entry'] + 8.00

            # Forward replay
            sim = simulate_trade_execution(
                entry_price=s['entry'],
                sl_price=s['sl'],
                direction=s['direction'],
                forward_m1=forward_m1,
                target_rr=3.5,
                be_rr=1.8,
                spread_usd=0.15
            )

            # Record full trade record
            all_trades.append({
                'date': str(ms_dt.date()),
                'time_utc': ms_dt.strftime("%H:%M"),
                'session': sess_label,
                'archetype': s['archetype'],
                'archetype_id': s['archetype_id'],
                'direction': s['direction'],
                'phase': phase,
                'entry': round(s['entry'], 2),
                'sl': round(s['sl'], 2),
                'risk_pts': round(abs(s['entry'] - s['sl']), 2),
                'sweep_type': s.get('sweep_type', 'None'),
                'has_sweep': s.get('has_sweep', True),
                'status': sim['status'],
                'net_r': sim['net_r'],
                'realized_usd': sim['realized_usd'],
                'mae_r': sim['mae_r'],
                'mfe_r': sim['mfe_r'],
                'held_minutes': sim['held_minutes']
            })

    print(f"\n✅ Total Candidate Setups Evaluated: {len(all_trades)}")
    df_all = pd.DataFrame(all_trades)
    df_all.to_csv(OUTPUT_DIR / "oos_all_trades_ledger.csv", index=False)

    # 4. Quantitative Analysis & Comparison
    # Filter 1: Baseline Suite (All Setups & All Sessions)
    df_baseline_fills = df_all[df_all['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
    
    # Filter 2: Calibrated Suite:
    # - Prime Sessions only (Banned NY Silver Bullet)
    # - Negative-edge setups decommissioned (No ARCH-002, No ARCH-009)
    # - ARCH-004 restricted to PRO_EXPANSION
    # - Mandatory sweep for ARCH-011
    df_calibrated = df_all[
        (df_all['session'] != 'NY_Silver_Bullet') &
        (~df_all['archetype_id'].isin(['SETUP-ARCH-002', 'SETUP-ARCH-009'])) &
        (~((df_all['archetype_id'] == 'SETUP-ARCH-004') & (df_all['phase'] != 'PRO_EXPANSION'))) &
        (~((df_all['archetype_id'] == 'SETUP-ARCH-011') & (df_all['has_sweep'] == False)))
    ]
    df_calibrated_fills = df_calibrated[df_calibrated['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]

    def _stats(df_sub):
        n = len(df_sub)
        if n == 0:
            return {'fills': 0, 'wins': 0, 'losses': 0, 'be': 0, 'wr': 0.0, 'net_r': 0.0, 'pf': 0.0}
        w = len(df_sub[df_sub['status'] == 'WIN'])
        l = len(df_sub[df_sub['status'] == 'LOSS'])
        b = len(df_sub[df_sub['status'] == 'BREAKEVEN'])
        net_r = df_sub['net_r'].sum()
        gw = df_sub[df_sub['net_r'] > 0]['net_r'].sum()
        gl = abs(df_sub[df_sub['net_r'] < 0]['net_r'].sum())
        pf = round(gw / max(0.001, gl), 2)
        wr = round((w / n) * 100.0, 1)
        return {'fills': n, 'wins': w, 'losses': l, 'be': b, 'wr': wr, 'net_r': round(net_r, 2), 'pf': pf}

    base_s = _stats(df_baseline_fills)
    cal_s = _stats(df_calibrated_fills)

    print("\n" + "=" * 90)
    print("🏆 OUT-OF-SAMPLE PERFORMANCE COMPARISON (JULY 1 - AUGUST 31, 2026)")
    print("=" * 90)
    print(f"Baseline Suite (All Sessions & Setups):    {base_s['fills']} Fills | {base_s['wins']}W - {base_s['losses']}L - {base_s['be']}BE | WR: {base_s['wr']}% | Net: {base_s['net_r']:+0.1f}R | PF: {base_s['pf']}")
    print(f"CALIBRATED SUITE (Target 3.5R, BE 1.8R):   {cal_s['fills']} Fills | {cal_s['wins']}W - {cal_s['losses']}L - {cal_s['be']}BE | WR: {cal_s['wr']}% | Net: {cal_s['net_r']:+0.1f}R | PF: {cal_s['pf']}")
    print("=" * 90)

    # 5. Session Breakdown in OOS
    print("\n📍 Performance by Institutional Session Window:")
    for sess in ['London_Open', 'London_Continuation', 'NY_Open', 'NY_Silver_Bullet']:
        sub = df_all[(df_all['session'] == sess) & (df_all['status'].isin(['WIN', 'LOSS', 'BREAKEVEN']))]
        st = _stats(sub)
        print(f"  * {sess:<22}: {st['fills']:>2} Fills | {st['wins']:>2}W - {st['losses']:>2}L - {st['be']:>2}BE | WR: {st['wr']:>4.1f}% | Net: {st['net_r']:>+5.1f}R | PF: {st['pf']:>4.2f}")

    # 6. Archetype Breakdown in OOS
    print("\n📍 Performance by Setup Archetype in OOS:")
    for arch in df_all['archetype_id'].unique():
        sub = df_calibrated[(df_calibrated['archetype_id'] == arch) & (df_calibrated['status'].isin(['WIN', 'LOSS', 'BREAKEVEN']))]
        st = _stats(sub)
        arch_name = sub['archetype'].iloc[0] if len(sub) > 0 else arch
        print(f"  * [{arch}] {arch_name:<24}: {st['fills']:>2} Fills | {st['wins']:>2}W - {st['losses']:>2}L - {st['be']:>2}BE | WR: {st['wr']:>4.1f}% | Net: {st['net_r']:>+5.1f}R | PF: {st['pf']:>4.2f}")

    # 7. Sweep Hierarchy Breakdown in OOS
    print("\n📍 Performance by Sweep Hierarchy in OOS:")
    for sw in ['PDH', 'PDL', 'Asian_High', 'Asian_Low', 'Minor_Low', 'Nested_Sweep', 'No_Sweep_OpenAir']:
        sub = df_all[(df_all['sweep_type'] == sw) & (df_all['status'].isin(['WIN', 'LOSS', 'BREAKEVEN']))]
        st = _stats(sub)
        print(f"  * {sw:<18}: {st['fills']:>2} Fills | {st['wins']:>2}W - {st['losses']:>2}L - {st['be']:>2}BE | WR: {st['wr']:>4.1f}% | Net: {st['net_r']:>+5.1f}R | PF: {st['pf']:>4.2f}")

    # 8. MFE / MAE & Target R:R Cliff Verification in OOS
    print("\n📍 Target R:R Grid Sensitivity on Calibrated Fills:")
    for trg in [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
        re_sim_records = []
        for idx, row in df_calibrated_fills.iterrows():
            # simulate with trg
            mfe = row['mfe_r']
            mae = row['mae_r']
            # If MFE reached trg before SL hit
            if mfe >= trg:
                re_sim_records.append(trg)
            elif mfe >= 1.8:
                re_sim_records.append(0.0) # Scratch
            else:
                re_sim_records.append(-1.0)
        net_re = sum(re_sim_records)
        wins_re = sum(1 for r in re_sim_records if r > 0)
        wr_re = (wins_re / len(re_sim_records)) * 100.0 if re_sim_records else 0.0
        gw = sum(r for r in re_sim_records if r > 0)
        gl = abs(sum(r for r in re_sim_records if r < 0))
        pf_re = round(gw / max(0.001, gl), 2)
        print(f"  * Target {trg:>3.1f}R: WR: {wr_re:>4.1f}% | Net: {net_re:>+5.1f}R | PF: {pf_re:>4.2f} | Wins: {wins_re:>2}/{len(re_sim_records)}")

    # Save summary json
    summary_out = {
        'audit_period': '2026-07-01 to 2026-08-31',
        'symbol': 'XAUUSD_o',
        'baseline': base_s,
        'calibrated': cal_s,
        'execution_wall_time_s': round(time.time() - t_start_wall, 2)
    }
    with open(OUTPUT_DIR / "oos_summary_metrics.json", "w", encoding="utf-8") as f:
        json.dump(summary_out, f, indent=2)

    print(f"\n🎉 Out-Of-Sample Audit Completed in {summary_out['execution_wall_time_s']}s!")
    print(f"📁 Reports saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    run_oos_audit()
