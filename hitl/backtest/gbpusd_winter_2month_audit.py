"""
TradingGuard HITL - Winter 2-Month Quantitative British Pound (GBPUSD) Audit
Audit Period: January 2, 2026 - February 27, 2026 (Winter Season, Fixed No-DST)
Instrument: GBPUSD_o (British Pound Standalone, 100% pure execution)
Scope: 41 Trading Days | 164 Institutional Sessions | Resampled M1 Microstructure

Evaluates:
1. Baseline vs Calibrated Strategies on Cable Winter
2. Verification of Target 2.5R, BE 1.5R, Silver Bullet Banned, and London Open Superiority
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
from hitl.backtest.gbpusd_autumn_2month_audit import find_swing_points, get_atr, simulate_trade_execution, PIP_SIZE, SPREAD_PIPS

OUTPUT_DIR = BASE_DIR / "backtest_results" / "gbpusd_winter_2month_audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_UTC = datetime.timezone.utc


def load_gbpusd_winter_bars_and_resample_m1(symbol: str = "GBPUSD_o") -> Dict[str, Any]:
    print(f"📥 Loading Winter 2026 dataset from MT5 for {symbol}...")
    mt5.symbol_select(symbol, True)

    t_start = datetime.datetime(2026, 1, 2, 0, 0, tzinfo=TZ_UTC)
    t_end = datetime.datetime(2026, 2, 28, 23, 59, tzinfo=TZ_UTC)

    # 1. Daily bars (from Nov 2025 for 20-day ADR)
    t_d1_start = datetime.datetime(2025, 11, 1, 0, 0, tzinfo=TZ_UTC)
    r_d1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, t_d1_start, t_end)

    # 2. H1 bars (from Dec 2025 for 1H MSS state machine)
    t_h1_start = datetime.datetime(2025, 12, 1, 0, 0, tzinfo=TZ_UTC)
    r_h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, t_h1_start, t_end)

    # 3. M5 bars
    r_m5 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, datetime.datetime(2025, 12, 20, tzinfo=TZ_UTC), t_end)

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

    print("   Resampling 41 trading days from raw broker ticks...")
    m1_list = []
    cur_d = datetime.date(2026, 1, 2)
    end_d = datetime.date(2026, 3, 1)

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


def run_gbpusd_winter_audit():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    t_start_wall = time.time()
    print("=" * 85)
    print("❄️ TRADINGGUARD - WINTER 2-MONTH QUANTITATIVE BRITISH POUND AUDIT (JAN - FEB 2026)")
    print("Instrument: GBPUSD_o (Cable Standalone) | 41 Trading Days | 164 Institutional Sessions")
    print("Microstructure: Resampled M1 Bars with Spread 0.6 Pips")
    print("=" * 85)

    if not mt5.initialize():
        print("❌ Error: MT5 initialization failed.")
        return

    data = load_gbpusd_winter_bars_and_resample_m1("GBPUSD_o")
    bars_d1 = data['d1']
    bars_h1 = data['h1']
    bars_m5 = data['m5']
    bars_m1 = data['m1']

    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    scope_start = datetime.datetime(2026, 1, 2, 0, 0, tzinfo=TZ_UTC)
    scope_end = datetime.datetime(2026, 2, 28, 23, 59, tzinfo=TZ_UTC)

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

    print(f"\n📊 Total Winter Trading Days: {len([b for b in bars_d1 if scope_start <= b['dt'] <= scope_end])}")
    print(f"🎯 Total Winter Institutional Sessions: {len(session_milestones)}")

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

            sim_baseline = simulate_trade_execution(
                entry_price=s['entry'],
                sl_price=s['sl'],
                direction=s['direction'],
                forward_m1=forward_m1,
                target_rr=2.5,
                be_rr=1.5,
                spread_pips=SPREAD_PIPS
            )

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
                'held_minutes': sim_baseline['held_minutes']
            })

    print(f"\n✅ Total Winter Candidate Setups Evaluated: {len(all_trades)}")

    df_trades = pd.DataFrame(all_trades)
    df_trades.to_csv(OUTPUT_DIR / "gbpusd_winter_all_trades_ledger.csv", index=False)

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

    calib_fills = df_fills[
        (df_fills['session'] != 'NY_Silver_Bullet') &
        (~df_fills['archetype_id'].isin(['SETUP-ARCH-009']))
    ]
    st_calib = stats(calib_fills)

    print("\n" + "=" * 90)
    print("❄️ GBPUSD WINTER 2026 AUDIT PERFORMANCE COMPARISON (JAN 2 - FEB 27, 2026)")
    print("=" * 90)
    print(f"Baseline Suite (All Sessions & Setups):    {st_base['fills']} Fills | {st_base['wins']}W - {st_base['losses']}L - {st_base['be']}BE | WR: {st_base['wr']}% | Net: {st_base['net_r']:+0.1f}R | PF: {st_base['pf']}")
    print(f"CALIBRATED SUITE (Target 2.5R, BE 1.5R):   {st_calib['fills']} Fills | {st_calib['wins']}W - {st_calib['losses']}L - {st_calib['be']}BE | WR: {st_calib['wr']}% | Net: {st_calib['net_r']:+0.1f}R | PF: {st_calib['pf']}")

    # Session Breakdown
    print("\n📍 Winter Performance by Institutional Session Window:")
    sess_summary = {}
    for sess in sorted(df_trades['session'].unique()):
        sub = df_fills[df_fills['session'] == sess]
        st = stats(sub)
        sess_summary[sess] = st
        print(f"  * {sess:<22}: {st['fills']:>2} Fills | {st['wins']:>2}W - {st['losses']:>2}L - {st['be']:>2}BE | WR: {st['wr']:>5.1f}% | Net: {st['net_r']:>+6.1f}R | PF: {st['pf']:>4.2f}")

    # Archetype Breakdown
    print("\n📍 Winter Performance by Setup Archetype (Calibrated):")
    arch_summary = {}
    for arch_id in sorted(calib_fills['archetype_id'].unique()):
        sub = calib_fills[calib_fills['archetype_id'] == arch_id]
        arch_name = calib_fills[calib_fills['archetype_id'] == arch_id]['archetype'].iloc[0]
        st = stats(sub)
        arch_summary[arch_id] = {**st, 'name': arch_name}
        print(f"  * [{arch_id}] {arch_name:<24}: {st['fills']:>2} Fills | {st['wins']:>2}W - {st['losses']:>2}L - {st['be']:>2}BE | WR: {st['wr']:>5.1f}% | Net: {st['net_r']:>+6.1f}R | PF: {st['pf']:>4.2f}")

    summary_out = {
        'audit_period': '2026-01-02 to 2026-02-27',
        'season': 'Winter (Low Volatility Regime)',
        'symbol': 'GBPUSD_o',
        'baseline': st_base,
        'calibrated': st_calib,
        'sessions': sess_summary,
        'archetypes': arch_summary,
        'execution_wall_time_s': round(time.time() - t_start_wall, 2)
    }

    with open(OUTPUT_DIR / "gbpusd_winter_summary_metrics.json", "w", encoding="utf-8") as f:
        json.dump(summary_out, f, indent=2)

    print(f"\n🎉 GBPUSD Winter 2026 Audit Completed in {summary_out['execution_wall_time_s']}s!")
    print(f"📁 Reports saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    run_gbpusd_winter_audit()
