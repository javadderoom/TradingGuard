"""
TradingGuard HITL - Autumn 2-Month Quantitative British Pound (GBPUSD) Strategy Audit
Audit Period: September 1, 2026 - November 4, 2026 (Autumn Season & DST Transition)
Instrument: GBPUSD_o (British Pound Standalone, 100% pure execution, zero EUR crutches)
Scope: 47 Trading Days | 188 Institutional Sessions | Resampled M1 Microstructure

Evaluates:
1. Baseline vs Calibrated Strategies on Cable
2. All Archetypes (ARCH-001, ARCH-002, ARCH-003, ARCH-004, ARCH-009, ARCH-010, ARCH-011)
3. Target R:R Sensitivity Grid (1.5R, 2.0R, 2.5R, 3.0R, 3.5R, 4.0R)
4. Breakeven Sensitivity Grid (No BE, 1.0R, 1.5R, 1.8R, 2.0R)
5. Session Breakdown (London Open, London Continuation, NY Open, NY Silver Bullet)
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
from hitl.backtest.mtf_structure import analyze_mtf_state, classify_setup_phase

OUTPUT_DIR = BASE_DIR / "backtest_results" / "gbpusd_autumn_2month_audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_UTC = datetime.timezone.utc
PIP_SIZE = 0.0001
SPREAD_PIPS = 0.00006  # 0.6 pips realistic spread + slippage


def load_gbpusd_autumn_bars_and_resample_m1(symbol: str = "GBPUSD_o") -> Dict[str, Any]:
    print(f"📥 Loading Autumn 2026 dataset from MT5 for {symbol}...")
    mt5.symbol_select(symbol, True)

    t_start = datetime.datetime(2026, 9, 1, 0, 0, tzinfo=TZ_UTC)
    t_end = datetime.datetime(2026, 11, 4, 23, 59, tzinfo=TZ_UTC)

    # 1. Daily bars (from July 2026 for 20-day ADR)
    t_d1_start = datetime.datetime(2026, 7, 1, 0, 0, tzinfo=TZ_UTC)
    r_d1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, t_d1_start, t_end)

    # 2. H1 bars (from Aug 2026 for 1H MSS state machine)
    t_h1_start = datetime.datetime(2026, 8, 1, 0, 0, tzinfo=TZ_UTC)
    r_h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, t_h1_start, t_end)

    # 3. M5 bars
    r_m5 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, datetime.datetime(2026, 8, 20, tzinfo=TZ_UTC), t_end)

    def _conv(records):
        if records is None: return []
        out = []
        for r in records:
            s_val = int(r['spread']) if 'spread' in r.dtype.names else 6
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

    # 4. Resample M1 from raw ticks
    print("   Resampling 47 trading days from raw broker ticks...")
    m1_list = []
    cur_d = datetime.date(2026, 9, 1)
    end_d = datetime.date(2026, 11, 5)

    t0 = time.time()
    tick_count = 0
    while cur_d < end_d:
        if cur_d.weekday() < 5:
            dt_s = datetime.datetime(cur_d.year, cur_d.month, cur_d.day, 0, 0, tzinfo=TZ_UTC)
            dt_e = dt_s + datetime.timedelta(days=1)
            ticks = mt5.copy_ticks_range(symbol, dt_s, dt_e, mt5.COPY_TICKS_ALL)
            if ticks is not None and len(ticks) > 0:
                tick_count += len(ticks)
                df = pd.DataFrame(ticks)
                df['datetime'] = pd.to_datetime(df['time'], unit='s', utc=True)
                df.set_index('datetime', inplace=True)
                ohlc = df['bid'].resample('1min').ohlc().dropna()
                spread = ((df['ask'] - df['bid']) / PIP_SIZE).resample('1min').mean().dropna()
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
                        'spread': int(round(spread.loc[idx])) if idx in spread.index else 6
                    })
        cur_d += datetime.timedelta(days=1)

    m1_list.sort(key=lambda x: x['time'])
    print(f"   Generated {len(m1_list)} continuous M1 bars from {tick_count:,} ticks in {time.time()-t0:.2f}s.")
    print(f"✅ Ingestion Complete: {len(bars_d1)} D1 | {len(bars_h1)} H1 | {len(bars_m5)} M5 | {len(m1_list)} M1 bars.")

    return {
        'd1': bars_d1,
        'h1': bars_h1,
        'm5': bars_m5,
        'm1': m1_list
    }


def find_swing_points(bars: List[Dict[str, Any]], window: int = 2) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
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


def simulate_trade_execution(
    entry_price: float,
    sl_price: float,
    direction: str,
    forward_m1: List[Dict[str, Any]],
    target_rr: float = 3.0,
    be_rr: Optional[float] = 1.5,
    ttl_minutes: int = 90,
    watchdog_enabled: bool = True,
    spread_pips: float = SPREAD_PIPS
) -> Dict[str, Any]:
    is_buy = (direction in ("LONG", "BUY"))
    risk_pts = abs(entry_price - sl_price)
    if risk_pts <= 0:
        return {'status': 'INVALID', 'net_r': 0.0, 'realized_usd': 0.0, 'mae_r': 0.0, 'mfe_r': 0.0}

    tp_price = entry_price + (risk_pts * target_rr) if is_buy else entry_price - (risk_pts * target_rr)
    is_filled = False
    fill_idx = None
    active_sl = sl_price
    is_be_activated = False
    max_fav_dist = 0.0
    max_adv_dist = 0.0
    risk_usd = (risk_pts / PIP_SIZE) * 10.0  # $10/pip on standard lot

    recent_m1 = []
    for idx, bar in enumerate(forward_m1):
        recent_m1.append(bar)
        if not is_filled:
            if idx >= ttl_minutes:
                return {'status': 'EXPIRED', 'fill_idx': None, 'exit_idx': idx, 'net_r': 0.0, 'realized_usd': 0.0, 'mae_r': 0.0, 'mfe_r': 0.0, 'held_minutes': idx}

            if watchdog_enabled and len(recent_m1) >= 15:
                body = abs(bar['close'] - bar['open'])
                is_adverse = (bar['close'] < bar['open']) if is_buy else (bar['close'] > bar['open'])
                atr_local = get_atr(recent_m1[-15:], 14)
                if is_adverse and body >= (3.5 * atr_local) and abs(bar['close'] - entry_price) <= (3.0 * atr_local):
                    return {'status': 'CANCELLED_WATCHDOG', 'fill_idx': None, 'exit_idx': idx, 'net_r': 0.0, 'realized_usd': 0.0, 'mae_r': 0.0, 'mfe_r': 0.0, 'held_minutes': idx}

            if is_buy and bar['low'] <= sl_price:
                return {'status': 'INVALIDATED_BEFORE_FILL', 'fill_idx': None, 'exit_idx': idx, 'net_r': 0.0, 'realized_usd': 0.0, 'mae_r': 0.0, 'mfe_r': 0.0, 'held_minutes': idx}
            elif (not is_buy) and bar['high'] >= sl_price:
                return {'status': 'INVALIDATED_BEFORE_FILL', 'fill_idx': None, 'exit_idx': idx, 'net_r': 0.0, 'realized_usd': 0.0, 'mae_r': 0.0, 'mfe_r': 0.0, 'held_minutes': idx}

            if is_buy and (bar['low'] + spread_pips) <= entry_price:
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
                active_sl = (entry_price + spread_pips) if is_buy else (entry_price - spread_pips)

            hit_sl = (bar['low'] <= active_sl) if is_buy else (bar['high'] >= active_sl)
            if hit_sl:
                held_mins = idx - fill_idx
                mae_r = round(max_adv_dist / risk_pts, 2)
                mfe_r = round(max_fav_dist / risk_pts, 2)
                if is_be_activated:
                    return {'status': 'BREAKEVEN', 'fill_idx': fill_idx, 'exit_idx': idx, 'net_r': 0.0, 'realized_usd': 0.0, 'mae_r': mae_r, 'mfe_r': mfe_r, 'held_minutes': held_mins}
                else:
                    return {'status': 'LOSS', 'fill_idx': fill_idx, 'exit_idx': idx, 'net_r': -1.0, 'realized_usd': round(-risk_usd, 2), 'mae_r': mae_r, 'mfe_r': mfe_r, 'held_minutes': held_mins}

            hit_tp = (bar['high'] >= tp_price) if is_buy else (bar['low'] <= tp_price)
            if hit_tp:
                held_mins = idx - fill_idx
                mae_r = round(max_adv_dist / risk_pts, 2)
                mfe_r = round(max_fav_dist / risk_pts, 2)
                return {'status': 'WIN', 'fill_idx': fill_idx, 'exit_idx': idx, 'net_r': target_rr, 'realized_usd': round(target_rr * risk_usd, 2), 'mae_r': mae_r, 'mfe_r': mfe_r, 'held_minutes': held_mins}

    held_mins = len(forward_m1) - fill_idx if is_filled else len(forward_m1)
    if is_filled:
        final_price = forward_m1[-1]['close']
        fav_dist = (final_price - entry_price) if is_buy else (entry_price - final_price)
        final_r = fav_dist / risk_pts
        return {'status': 'OPEN_EXPANSION' if final_r > 1.0 else 'OPEN_CLOSE', 'fill_idx': fill_idx, 'exit_idx': len(forward_m1) - 1, 'net_r': round(final_r, 2), 'realized_usd': round(final_r * risk_usd, 2), 'mae_r': round(max_adv_dist / risk_pts, 2), 'mfe_r': round(max_fav_dist / risk_pts, 2), 'held_minutes': held_mins}

    return {'status': 'UNFILLED_END', 'fill_idx': None, 'exit_idx': len(forward_m1), 'net_r': 0.0, 'realized_usd': 0.0, 'mae_r': 0.0, 'mfe_r': 0.0, 'held_minutes': len(forward_m1)}


def run_gbpusd_autumn_audit():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    t_start_wall = time.time()
    print("=" * 85)
    print("🇬🇧 TRADINGGUARD - AUTUMN 2-MONTH QUANTITATIVE BRITISH POUND AUDIT (SEP - NOV 2026)")
    print("Instrument: GBPUSD_o (Cable Standalone) | 47 Trading Days | 188 Institutional Sessions")
    print("Microstructure: Resampled M1 Bars with Spread 0.6 Pips")
    print("=" * 85)

    if not mt5.initialize():
        print("❌ Error: MT5 initialization failed.")
        return

    data = load_gbpusd_autumn_bars_and_resample_m1("GBPUSD_o")
    bars_d1 = data['d1']
    bars_h1 = data['h1']
    bars_m5 = data['m5']
    bars_m1 = data['m1']

    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    scope_start = datetime.datetime(2026, 9, 1, 0, 0, tzinfo=TZ_UTC)
    scope_end = datetime.datetime(2026, 11, 4, 23, 59, tzinfo=TZ_UTC)

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

    print(f"\n📊 Total Autumn Trading Days: {len([b for b in bars_d1 if scope_start <= b['dt'] <= scope_end])}")
    print(f"🎯 Total Autumn Institutional Sessions: {len(session_milestones)}")

    all_trades = []

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
            if not cands: continue
            m1_idx = cands[0]

        forward_m1 = bars_m1[m1_idx:m1_idx + 720]
        if len(forward_m1) < 120:
            continue

        current_price = hist_m5[-1]['close']
        mtf_state = analyze_mtf_state(bars_1d=hist_d1, bars_1h=hist_h1, bars_5m=hist_m5, symbol="GBPUSD")
        h1_state = mtf_state.get('h1_state', 'NEUTRAL')
        is_inside_day = mtf_state.get('is_inside_day', False)
        in_mid_equilibrium = mtf_state.get('in_mid_equilibrium', False)

        # Dynamic Asian Range (ends at London Open)
        lon_open_utc = sess_times['london']['utc_time']
        day_date = ms_dt.date()
        asian_bars = [b for b in hist_m5 if b['dt'].date() == day_date and b['dt'] < lon_open_utc]
        asian_high = max(b['high'] for b in asian_bars) if asian_bars else hist_m5[-20]['high']
        asian_low = min(b['low'] for b in asian_bars) if asian_bars else hist_m5[-20]['low']

        pdh = hist_d1[-1]['high'] if hist_d1 else asian_high
        pdl = hist_d1[-1]['low'] if hist_d1 else asian_low

        recent_m5 = hist_m5[-24:]
        detected_setups = []

        swept_pdh = any(b['high'] >= pdh for b in recent_m5[-8:])
        swept_pdl = any(b['low'] <= pdl for b in recent_m5[-8:])
        swept_asian_h = any(b['high'] >= asian_high for b in recent_m5[-8:])
        swept_asian_l = any(b['low'] <= asian_low for b in recent_m5[-8:])

        # 1. SETUP-ARCH-001 (Judas Sweep Breaker)
        sh_m5, sl_m5 = find_swing_points(recent_m5, window=2)
        if (swept_asian_l or swept_pdl) and current_price > (asian_low + 0.0005) and sh_m5:
            last_sh = sh_m5[-1]['price']
            if current_price > last_sh:
                sl_calc = min(asian_low - 0.0002, last_sh - 0.0012)
                if abs(last_sh - sl_calc) >= 0.0008:
                    detected_setups.append({
                        'archetype': 'JUDAS_SWEEP_BREAKER',
                        'archetype_id': 'SETUP-ARCH-001',
                        'direction': 'LONG',
                        'entry': last_sh,
                        'sl': sl_calc,
                        'sweep_type': 'PDL' if swept_pdl else 'Asian_Low'
                    })
        elif (swept_asian_h or swept_pdh) and current_price < (asian_high - 0.0005) and sl_m5:
            last_sl = sl_m5[-1]['price']
            if current_price < last_sl:
                sl_calc = max(asian_high + 0.0002, last_sl + 0.0012)
                if abs(sl_calc - last_sl) >= 0.0008:
                    detected_setups.append({
                        'archetype': 'JUDAS_SWEEP_BREAKER',
                        'archetype_id': 'SETUP-ARCH-001',
                        'direction': 'SHORT',
                        'entry': last_sl,
                        'sl': sl_calc,
                        'sweep_type': 'PDH' if swept_pdh else 'Asian_High'
                    })

        # 2. SETUP-ARCH-002 (Judas Sweep FVG)
        for i in range(len(recent_m5) - 3, max(0, len(recent_m5) - 12), -1):
            b1, b2, b3 = recent_m5[i-2], recent_m5[i-1], recent_m5[i]
            if (swept_asian_l or swept_pdl) and b3['low'] > b1['high'] + 0.0004:
                detected_setups.append({
                    'archetype': 'JUDAS_SWEEP_FVG',
                    'archetype_id': 'SETUP-ARCH-002',
                    'direction': 'LONG',
                    'entry': b3['low'],
                    'sl': min(b1['low'] - 0.0002, b3['low'] - 0.0014),
                    'sweep_type': 'PDL' if swept_pdl else 'Asian_Low'
                })
                break
            elif (swept_asian_h or swept_pdh) and b3['high'] < b1['low'] - 0.0004:
                detected_setups.append({
                    'archetype': 'JUDAS_SWEEP_FVG',
                    'archetype_id': 'SETUP-ARCH-002',
                    'direction': 'SHORT',
                    'entry': b3['high'],
                    'sl': max(b1['high'] + 0.0002, b3['high'] + 0.0014),
                    'sweep_type': 'PDH' if swept_pdh else 'Asian_High'
                })
                break

        # 3. SETUP-ARCH-003 (Clean MSS Breaker Retest)
        if not in_mid_equilibrium:
            if sh_m5 and len(sh_m5) >= 2:
                recent_sh = sh_m5[-1]['price']
                if current_price > recent_sh and abs(current_price - recent_sh) <= 0.0004:
                    detected_setups.append({
                        'archetype': 'MSS_BREAKER_RETEST',
                        'archetype_id': 'SETUP-ARCH-003',
                        'direction': 'LONG',
                        'entry': recent_sh,
                        'sl': recent_sh - 0.0014,
                        'sweep_type': 'Structural_Breakout'
                    })
            if sl_m5 and len(sl_m5) >= 2:
                recent_sl = sl_m5[-1]['price']
                if current_price < recent_sl and abs(current_price - recent_sl) <= 0.0004:
                    detected_setups.append({
                        'archetype': 'MSS_BREAKER_RETEST',
                        'archetype_id': 'SETUP-ARCH-003',
                        'direction': 'SHORT',
                        'entry': recent_sl,
                        'sl': recent_sl + 0.0014,
                        'sweep_type': 'Structural_Breakdown'
                    })

        # 4. SETUP-ARCH-004 (Expansion FVG)
        if not is_inside_day:
            if current_price > asian_high + 0.0008:
                detected_setups.append({
                    'archetype': 'SESSION_EXPANSION_FVG',
                    'archetype_id': 'SETUP-ARCH-004',
                    'direction': 'LONG',
                    'entry': current_price - 0.0004,
                    'sl': current_price - 0.0016,
                    'sweep_type': 'Expansion_High'
                })
            elif current_price < asian_low - 0.0008:
                detected_setups.append({
                    'archetype': 'SESSION_EXPANSION_FVG',
                    'archetype_id': 'SETUP-ARCH-004',
                    'direction': 'SHORT',
                    'entry': current_price + 0.0004,
                    'sl': current_price + 0.0016,
                    'sweep_type': 'Expansion_Low'
                })

        # 5. SETUP-ARCH-009 (Pro-Trend OTE Retracement)
        session_rng = max(b['high'] for b in recent_m5) - min(b['low'] for b in recent_m5)
        if session_rng >= 0.0025 and not in_mid_equilibrium:
            r_high = max(b['high'] for b in recent_m5)
            r_low = min(b['low'] for b in recent_m5)
            if h1_state == "BULLISH_MSS":
                detected_setups.append({
                    'archetype': 'PRO_TREND_RETEST_OTE',
                    'archetype_id': 'SETUP-ARCH-009',
                    'direction': 'LONG',
                    'entry': r_high - 0.705 * session_rng,
                    'sl': r_low - 0.0002,
                    'sweep_type': 'OTE_Discount'
                })
            elif h1_state == "BEARISH_MSS":
                detected_setups.append({
                    'archetype': 'PRO_TREND_RETEST_OTE',
                    'archetype_id': 'SETUP-ARCH-009',
                    'direction': 'SHORT',
                    'entry': r_low + 0.705 * session_rng,
                    'sl': r_high + 0.0002,
                    'sweep_type': 'OTE_Premium'
                })

        # 6. SETUP-ARCH-010 (Prominent Sweep + MSS)
        if swept_pdh and sl_m5:
            last_sl = sl_m5[-1]['price']
            if current_price < last_sl:
                sl_calc = pdh + 0.0002
                if 0.0008 <= abs(last_sl - sl_calc) <= 0.0025:
                    detected_setups.append({
                        'archetype': 'PROMINENT_SWEEP_MSS',
                        'archetype_id': 'SETUP-ARCH-010',
                        'direction': 'SHORT',
                        'entry': last_sl,
                        'sl': sl_calc,
                        'sweep_type': 'PDH_Sweep'
                    })
        elif swept_pdl and sh_m5:
            last_sh = sh_m5[-1]['price']
            if current_price > last_sh:
                sl_calc = pdl - 0.0002
                if 0.0008 <= abs(last_sh - sl_calc) <= 0.0025:
                    detected_setups.append({
                        'archetype': 'PROMINENT_SWEEP_MSS',
                        'archetype_id': 'SETUP-ARCH-010',
                        'direction': 'LONG',
                        'entry': last_sh,
                        'sl': sl_calc,
                        'sweep_type': 'PDL_Sweep'
                    })

        # 7. SETUP-ARCH-011 (Nested Double MSS)
        if len(sh_m5) >= 3 and len(sl_m5) >= 3:
            h3 = sh_m5[-1]
            if current_price > h3['price']:
                h2, h1 = sh_m5[-2], sh_m5[-3]
                l3, l2 = sl_m5[-1], sl_m5[-2]
                if (h2['price'] > h1['price'] + 0.0002) and (h3['price'] < h2['price'] - 0.0002) and (l3['price'] > l2['price']):
                    sl_calc = l3['price'] - 0.0002
                    if 0.0008 <= abs(h3['price'] - sl_calc) <= 0.0025:
                        detected_setups.append({
                            'archetype': 'NESTED_DOUBLE_MSS',
                            'archetype_id': 'SETUP-ARCH-011',
                            'direction': 'LONG',
                            'entry': h3['price'],
                            'sl': sl_calc,
                            'sweep_type': 'PDL' if swept_pdl else ('Asian_Low' if swept_asian_l else 'Swing_Low')
                        })
            l3_item = sl_m5[-1]
            if current_price < l3_item['price']:
                l2, l1 = sl_m5[-2], sl_m5[-3]
                h3_val, h2 = sh_m5[-1], sh_m5[-2]
                if (l2['price'] < l1['price'] - 0.0002) and (l3_item['price'] > l2['price'] + 0.0002) and (h3_val['price'] < h2['price']):
                    sl_calc = h3_val['price'] + 0.0002
                    if 0.0008 <= abs(l3_item['price'] - sl_calc) <= 0.0025:
                        detected_setups.append({
                            'archetype': 'NESTED_DOUBLE_MSS',
                            'archetype_id': 'SETUP-ARCH-011',
                            'direction': 'SHORT',
                            'entry': l3_item['price'],
                            'sl': sl_calc,
                            'sweep_type': 'PDH' if swept_pdh else ('Asian_High' if swept_asian_h else 'Swing_High')
                        })

        for s in detected_setups:
            risk_dist = abs(s['entry'] - s['sl'])
            if risk_dist < 0.0008:
                s['sl'] = s['entry'] - 0.0008 if s['direction'] == 'LONG' else s['entry'] + 0.0008
            elif risk_dist > 0.0025:
                s['sl'] = s['entry'] - 0.0025 if s['direction'] == 'LONG' else s['entry'] + 0.0025

            risk_dist = abs(s['entry'] - s['sl'])
            risk_pips = round(risk_dist / PIP_SIZE, 1)

            # Replay with baseline target 2.5R, BE 1.5R (Forex standard)
            sim_baseline = simulate_trade_execution(
                entry_price=s['entry'],
                sl_price=s['sl'],
                direction=s['direction'],
                forward_m1=forward_m1,
                target_rr=2.5,
                be_rr=1.5,
                spread_pips=SPREAD_PIPS
            )

            # R:R Sensitivity Simulations
            sim_15 = simulate_trade_execution(s['entry'], s['sl'], s['direction'], forward_m1, target_rr=1.5, be_rr=1.2, spread_pips=SPREAD_PIPS)
            sim_20 = simulate_trade_execution(s['entry'], s['sl'], s['direction'], forward_m1, target_rr=2.0, be_rr=1.5, spread_pips=SPREAD_PIPS)
            sim_25 = simulate_trade_execution(s['entry'], s['sl'], s['direction'], forward_m1, target_rr=2.5, be_rr=1.5, spread_pips=SPREAD_PIPS)
            sim_30 = simulate_trade_execution(s['entry'], s['sl'], s['direction'], forward_m1, target_rr=3.0, be_rr=1.5, spread_pips=SPREAD_PIPS)
            sim_35 = simulate_trade_execution(s['entry'], s['sl'], s['direction'], forward_m1, target_rr=3.5, be_rr=1.8, spread_pips=SPREAD_PIPS)
            sim_40 = simulate_trade_execution(s['entry'], s['sl'], s['direction'], forward_m1, target_rr=4.0, be_rr=1.8, spread_pips=SPREAD_PIPS)

            # Breakeven Sensitivity Simulations (at 2.5R target)
            sim_no_be = simulate_trade_execution(s['entry'], s['sl'], s['direction'], forward_m1, target_rr=2.5, be_rr=None, spread_pips=SPREAD_PIPS)
            sim_be_10 = simulate_trade_execution(s['entry'], s['sl'], s['direction'], forward_m1, target_rr=2.5, be_rr=1.0, spread_pips=SPREAD_PIPS)
            sim_be_15 = simulate_trade_execution(s['entry'], s['sl'], s['direction'], forward_m1, target_rr=2.5, be_rr=1.5, spread_pips=SPREAD_PIPS)
            sim_be_20 = simulate_trade_execution(s['entry'], s['sl'], s['direction'], forward_m1, target_rr=2.5, be_rr=2.0, spread_pips=SPREAD_PIPS)

            all_trades.append({
                'date': ms_dt.strftime("%Y-%m-%d"),
                'time_utc': ms_dt.strftime("%Y-%m-%d %H:%M"),
                'session': sess_label,
                'archetype': s['archetype'],
                'archetype_id': s['archetype_id'],
                'direction': s['direction'],
                'phase': classify_setup_phase(mtf_state, s['direction'], "GBPUSD")['phase'],
                'entry': round(s['entry'], 5),
                'sl': round(s['sl'], 5),
                'risk_pips': risk_pips,
                'sweep_type': s['sweep_type'],
                'has_sweep': (s['sweep_type'] != 'None'),
                'status': sim_baseline['status'],
                'net_r': sim_baseline['net_r'],
                'realized_usd': sim_baseline['realized_usd'],
                'mae_r': sim_baseline['mae_r'],
                'mfe_r': sim_baseline['mfe_r'],
                'held_minutes': sim_baseline['held_minutes'],
                'sim_15': sim_15,
                'sim_20': sim_20,
                'sim_25': sim_25,
                'sim_30': sim_30,
                'sim_35': sim_35,
                'sim_40': sim_40,
                'sim_no_be': sim_no_be,
                'sim_be_10': sim_be_10,
                'sim_be_15': sim_be_15,
                'sim_be_20': sim_be_20
            })

    print(f"\n✅ Total Candidate Setups Evaluated: {len(all_trades)}")

    df_trades = pd.DataFrame(all_trades)
    df_trades.to_csv(OUTPUT_DIR / "gbpusd_autumn_all_trades_ledger.csv", index=False)

    def stats(df_sub):
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

    df_fills = df_trades[df_trades['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
    st_base = stats(df_fills)

    print("\n" + "=" * 90)
    print("🇬🇧 GBPUSD AUTUMN 2026 AUDIT PERFORMANCE COMPARISON (SEP 1 - NOV 4, 2026)")
    print("=" * 90)
    print(f"Baseline Suite (All Sessions & Setups): {st_base['fills']} Fills | {st_base['wins']}W - {st_base['losses']}L - {st_base['be']}BE | WR: {st_base['wr']}% | Net: {st_base['net_r']:+0.1f}R | PF: {st_base['pf']}")

    # Session Breakdown
    print("\n📍 Performance by Institutional Session Window:")
    sess_summary = {}
    for sess in sorted(df_trades['session'].unique()):
        sub = df_fills[df_fills['session'] == sess]
        st = stats(sub)
        sess_summary[sess] = st
        print(f"  * {sess:<22}: {st['fills']:>2} Fills | {st['wins']:>2}W - {st['losses']:>2}L - {st['be']:>2}BE | WR: {st['wr']:>5.1f}% | Net: {st['net_r']:>+6.1f}R | PF: {st['pf']:>4.2f}")

    # Archetype Breakdown
    print("\n📍 Performance by Setup Archetype:")
    arch_summary = {}
    for arch_id in sorted(df_trades['archetype_id'].unique()):
        sub = df_fills[df_fills['archetype_id'] == arch_id]
        arch_name = df_trades[df_trades['archetype_id'] == arch_id]['archetype'].iloc[0]
        st = stats(sub)
        arch_summary[arch_id] = {**st, 'name': arch_name}
        print(f"  * [{arch_id}] {arch_name:<24}: {st['fills']:>2} Fills | {st['wins']:>2}W - {st['losses']:>2}L - {st['be']:>2}BE | WR: {st['wr']:>5.1f}% | Net: {st['net_r']:>+6.1f}R | PF: {st['pf']:>4.2f}")

    # Target R:R Sensitivity Grid
    print("\n📍 Target R:R Sensitivity Across All Fills:")
    grid_res = {}
    for t_label, t_key, t_val in [
        ('Target 1.5R', 'sim_15', 1.5),
        ('Target 2.0R', 'sim_20', 2.0),
        ('Target 2.5R', 'sim_25', 2.5),
        ('Target 3.0R', 'sim_30', 3.0),
        ('Target 3.5R', 'sim_35', 3.5),
        ('Target 4.0R', 'sim_40', 4.0)
    ]:
        sub_statuses = [t[t_key]['status'] for t in all_trades if t[t_key]['status'] in ['WIN', 'LOSS', 'BREAKEVEN']]
        sub_nets = [t[t_key]['net_r'] for t in all_trades if t[t_key]['status'] in ['WIN', 'LOSS', 'BREAKEVEN']]
        w = sub_statuses.count('WIN')
        l = sub_statuses.count('LOSS')
        b = sub_statuses.count('BREAKEVEN')
        tot = len(sub_statuses)
        net_r = round(sum(sub_nets), 2)
        gw = sum(r for r in sub_nets if r > 0)
        gl = abs(sum(r for r in sub_nets if r < 0))
        pf = round(gw / max(0.001, gl), 2)
        wr = round((w / max(1, tot)) * 100.0, 1)
        grid_res[t_label] = {'fills': tot, 'wins': w, 'losses': l, 'be': b, 'wr': wr, 'net_r': net_r, 'pf': pf}
        print(f"  * {t_label:<11}: WR: {wr:>5.1f}% | Net: {net_r:>+6.1f}R | PF: {pf:>4.2f} | Wins: {w:>2}/{tot}")

    # Breakeven Ratchet Sensitivity Grid
    print("\n📍 Breakeven Ratchet Sensitivity (at 2.5R Target):")
    be_res = {}
    for be_label, be_key in [
        ('No Breakeven', 'sim_no_be'),
        ('BE at 1.0R', 'sim_be_10'),
        ('BE at 1.5R', 'sim_be_15'),
        ('BE at 2.0R', 'sim_be_20')
    ]:
        sub_statuses = [t[be_key]['status'] for t in all_trades if t[be_key]['status'] in ['WIN', 'LOSS', 'BREAKEVEN']]
        sub_nets = [t[be_key]['net_r'] for t in all_trades if t[be_key]['status'] in ['WIN', 'LOSS', 'BREAKEVEN']]
        w = sub_statuses.count('WIN')
        l = sub_statuses.count('LOSS')
        b = sub_statuses.count('BREAKEVEN')
        tot = len(sub_statuses)
        net_r = round(sum(sub_nets), 2)
        gw = sum(r for r in sub_nets if r > 0)
        gl = abs(sum(r for r in sub_nets if r < 0))
        pf = round(gw / max(0.001, gl), 2)
        wr = round((w / max(1, tot)) * 100.0, 1)
        be_res[be_label] = {'fills': tot, 'wins': w, 'losses': l, 'be': b, 'wr': wr, 'net_r': net_r, 'pf': pf}
        print(f"  * {be_label:<14}: WR: {wr:>5.1f}% | Net: {net_r:>+6.1f}R | PF: {pf:>4.2f} | Scratches: {b:>2}/{tot}")

    summary_out = {
        'audit_period': '2026-09-01 to 2026-11-04',
        'season': 'Autumn (DST Transition)',
        'symbol': 'GBPUSD_o',
        'baseline': st_base,
        'sessions': sess_summary,
        'archetypes': arch_summary,
        'target_grid': grid_res,
        'breakeven_grid': be_res,
        'execution_wall_time_s': round(time.time() - t_start_wall, 2)
    }

    with open(OUTPUT_DIR / "gbpusd_autumn_summary_metrics.json", "w", encoding="utf-8") as f:
        json.dump(summary_out, f, indent=2)

    print(f"\n🎉 GBPUSD Autumn 2026 Audit Completed in {summary_out['execution_wall_time_s']}s!")
    print(f"📁 Reports saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    run_gbpusd_autumn_audit()
