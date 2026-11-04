"""
TradingGuard HITL - Master Quantitative Gold (XAUUSD) Strategy Audit
Examines the 2-Month Broker Dataset (September 1, 2026 - November 4, 2026):
- Instrument: XAUUSD (Gold standalone, 100% zero silver assistance)
- Sessions: London Open, London Expansion, NY Open, NY Silver Bullet (All trading days)
- Setups:
  1. Judas_Sweep_Breaker (SETUP-ARCH-001)
  2. Judas_Sweep_FVG (SETUP-ARCH-002)
  3. MSS_Breaker_Retest (SETUP-ARCH-003)
  4. Session_Expansion_FVG (SETUP-ARCH-004)
  5. Pro_Trend_Retest_OTE (SETUP-ARCH-009)
  6. Prominent_Sweep_MSS (SETUP-ARCH-010)
- Structural Confluence: 1H MSS (PRO_EXPANSION vs HTF_RETRACEMENT)
- Macro Context: Inside Day & Mid-Range Equilibrium (25%-75%)
- Optimization Grids:
  * TP Logic: Fixed 2.0R to 5.0R vs Dynamic (4.5R / 2.2R) vs Structural Liquidity Pools
  * SL Logic: Sweep Wick vs FVG Distal vs ATR Buffer
  * Post-Entry Management: Static vs Early BE (+1.5R) vs Conservative BE (+2.0R) vs Multi-Stage Partial (60/40) vs Trailing Runner
"""

import sys
import json
import math
import time
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Tuple, Optional

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.session_clock import get_session_times_for_date
from hitl.backtest.mtf_structure import analyze_mtf_state, classify_setup_phase

OUTPUT_DIR = BASE_DIR / "backtest_results" / "gold_2month_quant_audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TZ_UTC = datetime.timezone.utc
TZ_TEHRAN = ZoneInfo("Asia/Tehran")


def load_mt5_historical_bars(symbol: str = "XAUUSD_o"):
    """Loads all M1, M5, M15, H1, D1 bars into memory for high-speed local processing."""
    print(f"📥 Loading continuous historical bars from MT5 for {symbol}...")
    mt5.symbol_select(symbol, True)

    t_start = datetime.datetime(2026, 9, 1, 0, 0, tzinfo=TZ_UTC)
    t_end = datetime.datetime(2026, 11, 4, 15, 0, tzinfo=TZ_UTC)

    # 1. Daily bars (from 2026-06-01 for 20-day ADR and macro swing history)
    t_daily_start = datetime.datetime(2026, 6, 1, 0, 0, tzinfo=TZ_UTC)
    r_d1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, t_daily_start, t_end)

    # 2. H1 bars (from 2026-08-01 for 1H MSS state machine)
    t_h1_start = datetime.datetime(2026, 8, 1, 0, 0, tzinfo=TZ_UTC)
    r_h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, t_h1_start, t_end)

    # 3. M15 bars
    r_m15 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, t_daily_start, t_end)

    # 4. M5 bars
    r_m5 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, t_daily_start, t_end)

    # 5. Continuous M1 bars
    r_m1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, t_start, t_end)

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
    bars_m15 = _conv(r_m15)
    bars_m5 = _conv(r_m5)
    bars_m1 = _conv(r_m1)

    print(f"✅ Loaded: {len(bars_d1)} D1 bars | {len(bars_h1)} H1 bars | {len(bars_m15)} M15 bars | {len(bars_m5)} M5 bars | {len(bars_m1)} M1 bars")
    return {
        'd1': bars_d1,
        'h1': bars_h1,
        'm15': bars_m15,
        'm5': bars_m5,
        'm1': bars_m1
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
    be_rr: Optional[float] = 2.0,
    trail_runner: bool = False,
    partial_scale_pct: float = 0.0,
    partial_target_rr: float = 2.5,
    ttl_minutes: int = 75,
    watchdog_enabled: bool = True,
    spread_usd: float = 0.20
) -> Dict[str, Any]:
    """
    High-fidelity forward trade execution simulator on M1 bars:
    - Verifies limit fill (Ask for Buy, Bid for Sell)
    - Enforces 75m TTL expiration
    - Enforces Watchdog adverse momentum cancellations
    - Tracks MAE and MFE continuously
    - Implements Dynamic Breakeven ratchet
    - Implements Partial profit scaling (e.g. 60% locked at partial_target_rr)
    - Implements Trailing Runner behind intermediate M15/M1 swing pivots
    """
    is_buy = (direction == "LONG" or direction == "BUY")
    risk_pts = abs(entry_price - sl_price)
    if risk_pts <= 0:
        return {'status': 'INVALID', 'net_r': 0.0, 'realized_usd': 0.0}

    # TP price based on target R:R
    if is_buy:
        tp_price = entry_price + (risk_pts * target_rr)
        partial_tp = entry_price + (risk_pts * partial_target_rr) if partial_scale_pct > 0 else tp_price
    else:
        tp_price = entry_price - (risk_pts * target_rr)
        partial_tp = entry_price - (risk_pts * partial_target_rr) if partial_scale_pct > 0 else tp_price

    is_filled = False
    fill_idx = None
    active_sl = sl_price
    is_be_activated = False
    is_partial_taken = False
    
    max_fav_dist = 0.0
    max_adv_dist = 0.0
    
    # 0.01 lot on Gold: 1 pt = $1.00
    risk_usd = risk_pts * 1.0
    
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
                # 3.5x ATR spike against proposed order
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
            # Track MAE & MFE
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

            # B. Partial Scale-Out (e.g. Lock 60% profit at partial_target_rr)
            realized_partial_usd = 0.0
            if partial_scale_pct > 0 and not is_partial_taken:
                hit_partial = (bar['high'] >= partial_tp) if is_buy else (bar['low'] <= partial_tp)
                if hit_partial:
                    is_partial_taken = True
                    # Lock partial profit
                    realized_partial_usd = (partial_target_rr * risk_usd) * partial_scale_pct
                    is_be_activated = True
                    active_sl = entry_price + (spread_usd if is_buy else -spread_usd)

            # C. Trailing Runner Logic
            if trail_runner and cur_rr >= 2.0:
                # Trail behind recent 15-minute swing pivot
                lookback_m1 = recent_m1[max(0, idx - 30):idx + 1]
                if len(lookback_m1) >= 10:
                    if is_buy:
                        recent_low = min(b['low'] for b in lookback_m1[:-3])
                        if recent_low > active_sl:
                            active_sl = recent_low
                    else:
                        recent_high = max(b['high'] for b in lookback_m1[:-3])
                        if recent_high < active_sl:
                            active_sl = recent_high

            # D. Check Stop Loss Hit
            hit_sl = (bar['low'] <= active_sl) if is_buy else (bar['high'] >= active_sl)
            if hit_sl:
                held_mins = idx - fill_idx
                mae_r = round(max_adv_dist / risk_pts, 2)
                mfe_r = round(max_fav_dist / risk_pts, 2)

                if is_partial_taken:
                    # Remaining portion stopped out at active_sl
                    rem_pct = 1.0 - partial_scale_pct
                    rem_dist = (active_sl - entry_price) if is_buy else (entry_price - active_sl)
                    rem_r = rem_dist / risk_pts
                    net_r = (partial_target_rr * partial_scale_pct) + (rem_r * rem_pct)
                    net_usd = net_r * risk_usd
                    status = "WIN_PARTIAL" if net_r > 0 else "BREAKEVEN"
                    return {
                        'status': status,
                        'fill_idx': fill_idx,
                        'exit_idx': idx,
                        'net_r': round(net_r, 2),
                        'realized_usd': round(net_usd, 2),
                        'mae_r': mae_r,
                        'mfe_r': mfe_r,
                        'held_minutes': held_mins
                    }

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

            # E. Check Full Take Profit Hit (if not purely trailing runner)
            if not trail_runner:
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

    # If trade remained open until end of forward data (12 hours)
    held_mins = len(forward_m1) - fill_idx if is_filled else len(forward_m1)
    if is_filled:
        final_bar = forward_m1[-1]
        final_price = final_bar['close']
        fav_dist = (final_price - entry_price) if is_buy else (entry_price - final_price)
        final_r = fav_dist / risk_pts
        final_usd = final_r * risk_usd
        return {
            'status': 'OPEN_EXPANSION' if final_r > 1.0 else 'OPEN_CLOSE',
            'fill_idx': fill_idx,
            'exit_idx': len(forward_m1) - 1,
            'net_r': round(final_r, 2),
            'realized_usd': round(final_usd, 2),
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


def run_gold_master_audit():
    """Main audit orchestrator across 2 months of real MT5 data."""
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    t_start_wall = time.time()
    print("=" * 85)
    print("🏆 TRADINGGUARD - 2-MONTH MASTER QUANTITATIVE GOLD (XAUUSD) AUDIT")
    print("Horizon: September 1, 2026 to November 4, 2026 (Continuous M1 Microstructure)")
    print("Mandate: 100% Pure Standalone Gold Execution (Zero SMT/Silver Dependency)")
    print("=" * 85)

    if not mt5.initialize():
        print("❌ Error: MT5 initialization failed.")
        return

    # 1. Ingest Bars
    data = load_mt5_historical_bars("XAUUSD_o")
    bars_d1 = data['d1']
    bars_h1 = data['h1']
    bars_m15 = data['m15']
    bars_m5 = data['m5']
    bars_m1 = data['m1']

    # Map M1 bars by timestamp for instant forward slicing
    m1_time_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    # 2. Extract All Unique Trading Days in Scope
    scope_start = datetime.datetime(2026, 9, 1, 0, 0, tzinfo=TZ_UTC)
    scope_end = datetime.datetime(2026, 11, 4, 13, 0, tzinfo=TZ_UTC)

    # Filter D1 bars in scope
    d1_in_scope = [b for b in bars_d1 if b['dt'] >= datetime.datetime(2026, 8, 25, tzinfo=TZ_UTC)]

    print(f"\n📊 Total Trading Days to Audit: {len([b for b in bars_d1 if scope_start <= b['dt'] <= scope_end])}")

    # Generate session milestones across every trading day
    session_milestones = []
    for d_bar in bars_d1:
        dt_day = d_bar['dt'].date()
        if dt_day < scope_start.date() or dt_day > scope_end.date():
            continue
        if dt_day.weekday() in (5, 6):  # Skip weekends
            continue

        sess_times = get_session_times_for_date(dt_day)
        
        # 1. London Open (07:00 UTC in Summer / 08:00 UTC in Winter)
        t_lon = sess_times['london']['utc_time']
        # 2. London Continuation (90 mins after Open)
        t_lon_cont = t_lon + datetime.timedelta(minutes=90)
        # 3. New York Open (12:00 UTC in Summer / 13:00 UTC in Winter)
        t_ny = sess_times['new_york']['utc_time']
        # 4. NY Cash Open / Silver Bullet (13:30 UTC in Summer / 14:30 UTC in Winter)
        t_nyse = sess_times['nyse_open']['utc_time']

        session_milestones.append((t_lon, "London_Open", sess_times))
        session_milestones.append((t_lon_cont, "London_Continuation", sess_times))
        session_milestones.append((t_ny, "NY_Open", sess_times))
        session_milestones.append((t_nyse, "NY_Silver_Bullet", sess_times))

    print(f"🎯 Total Institutional Checkpoints: {len(session_milestones)} Sessions")

    # 3. Comprehensive Setup Detection & Multi-Variant Simulation
    all_trade_records = []
    stand_aside_count = 0
    setup_count = 0

    print("\n⏳ Sweeping through session milestones and running forward M1 execution engine...")

    for ms_dt, sess_label, sess_times in session_milestones:
        ms_ts = int(ms_dt.timestamp())

        # Get historical bars strictly prior to milestone (Zero Lookahead)
        hist_d1 = [b for b in bars_d1 if b['time'] < ms_ts]
        hist_h1 = [b for b in bars_h1 if b['time'] < ms_ts]
        hist_m15 = [b for b in bars_m15 if b['time'] < ms_ts]
        hist_m5 = [b for b in bars_m5 if b['time'] < ms_ts]

        if not (hist_d1 and hist_h1 and hist_m5):
            continue

        # Get forward 12 hours of M1 bars for trade execution
        m1_idx = m1_time_map.get(ms_ts)
        if m1_idx is None:
            # find closest next bar
            m1_candidates = [idx for idx, b in enumerate(bars_m1) if b['time'] >= ms_ts]
            if not m1_candidates:
                continue
            m1_idx = m1_candidates[0]

        # 12 hours = 720 M1 bars
        forward_m1 = bars_m1[m1_idx:m1_idx + 720]
        if len(forward_m1) < 120:
            continue

        current_price = hist_m5[-1]['close']
        m5_atr = get_atr(hist_m5[-20:], 14)

        # Compute MTF State (Daily DOL + 1H MSS)
        mtf_state = analyze_mtf_state(bars_1d=hist_d1, bars_1h=hist_h1, bars_5m=hist_m5, symbol="XAUUSD")
        h1_state = mtf_state.get('h1_state', 'NEUTRAL')
        is_inside_day = mtf_state.get('is_inside_day', False)
        in_mid_equilibrium = mtf_state.get('in_mid_equilibrium', False)
        pdr = mtf_state.get('pdr', 0.0)

        # Calculate ADR(20)
        adr_20 = 0.0
        if len(hist_d1) >= 20:
            adr_20 = sum((b['high'] - b['low']) for b in hist_d1[-20:]) / 20.0

        # Session Range Boundaries (Asian Range: 00:00 - 07:00 UTC / 03:30 - 10:30 Tehran)
        # Find bars for Asian session today
        day_date = ms_dt.date()
        asian_bars = [b for b in hist_m5 if b['dt'].date() == day_date and b['dt'].hour < 7]
        asian_high = max(b['high'] for b in asian_bars) if asian_bars else hist_m5[-20]['high']
        asian_low = min(b['low'] for b in asian_bars) if asian_bars else hist_m5[-20]['low']
        asian_range = asian_high - asian_low

        # Detect Setups across M5 and M15
        recent_m5 = hist_m5[-24:]  # Last 2 hours
        recent_m15 = hist_m15[-16:] # Last 4 hours

        detected_setups = []

        # Tool 1: Judas Swing Liquidity Sweep & Breaker Block (SETUP-ARCH-001)
        # Check if Asian High or Low was pierced and then rejected
        high_pierced = any(b['high'] >= asian_high for b in recent_m5[-8:])
        low_pierced = any(b['low'] <= asian_low for b in recent_m5[-8:])

        # Find M5 Breaker
        # Swing High & Low in recent M5
        sh_m5, sl_m5 = find_swing_points(recent_m5, window=2)
        
        # Bullish Judas Sweep + MSS/Breaker
        if low_pierced and current_price > (asian_low + 1.0) and sh_m5:
            last_sh = sh_m5[-1]['price']
            if current_price > last_sh:
                # Bullish Breaker / MSS
                entry_p = last_sh
                sl_p = min(asian_low - 1.50, entry_p - 5.50)
                detected_setups.append({
                    'archetype': 'JUDAS_SWEEP_BREAKER',
                    'archetype_id': 'SETUP-ARCH-001',
                    'direction': 'LONG',
                    'entry': entry_p,
                    'sl': sl_p,
                    'timeframe': 'M5',
                    'reason': f"Asian Low swept ({asian_low:.2f}) + M5 Bullish Breaker displaced above {last_sh:.2f}"
                })

        # Bearish Judas Sweep + MSS/Breaker
        if high_pierced and current_price < (asian_high - 1.0) and sl_m5:
            last_sl = sl_m5[-1]['price']
            if current_price < last_sl:
                # Bearish Breaker / MSS
                entry_p = last_sl
                sl_p = max(asian_high + 1.50, entry_p + 5.50)
                detected_setups.append({
                    'archetype': 'JUDAS_SWEEP_BREAKER',
                    'archetype_id': 'SETUP-ARCH-001',
                    'direction': 'SHORT',
                    'entry': entry_p,
                    'sl': sl_p,
                    'timeframe': 'M5',
                    'reason': f"Asian High swept ({asian_high:.2f}) + M5 Bearish Breaker displaced below {last_sl:.2f}"
                })

        # Tool 2: Judas Swing Liquidity Sweep & Fair Value Gap (SETUP-ARCH-002)
        # Detect 5M FVG
        for i in range(len(recent_m5) - 1, 2, -1):
            c1, c2, c3 = recent_m5[i - 2], recent_m5[i - 1], recent_m5[i]
            # Bullish FVG
            if c3['low'] > c1['high'] and (c3['low'] - c1['high']) >= 1.20:
                if low_pierced:
                    entry_p = c3['low']
                    sl_p = min(asian_low - 1.50, c1['high'] - 1.50)
                    detected_setups.append({
                        'archetype': 'JUDAS_SWEEP_FVG',
                        'archetype_id': 'SETUP-ARCH-002',
                        'direction': 'LONG',
                        'entry': entry_p,
                        'sl': sl_p,
                        'timeframe': 'M5',
                        'reason': f"Asian Low swept + Bullish FVG ({c1['high']:.2f} - {c3['low']:.2f})"
                    })
                    break
            # Bearish FVG
            elif c1['low'] > c3['high'] and (c1['low'] - c3['high']) >= 1.20:
                if high_pierced:
                    entry_p = c3['high']
                    sl_p = max(asian_high + 1.50, c1['low'] + 1.50)
                    detected_setups.append({
                        'archetype': 'JUDAS_SWEEP_FVG',
                        'archetype_id': 'SETUP-ARCH-002',
                        'direction': 'SHORT',
                        'entry': entry_p,
                        'sl': sl_p,
                        'timeframe': 'M5',
                        'reason': f"Asian High swept + Bearish FVG ({c3['high']:.2f} - {c1['low']:.2f})"
                    })
                    break

        # Tool 3: Confirmed MSS Breaker Retest (SETUP-ARCH-003)
        if sh_m5 and sl_m5:
            last_sh = sh_m5[-1]['price']
            last_sl = sl_m5[-1]['price']
            # Bullish Retest: Price previously broke above last_sh and is now retesting it within $1.50
            if current_price > last_sh and abs(current_price - last_sh) <= 1.80 and not in_mid_equilibrium:
                entry_p = last_sh
                sl_p = entry_p - 5.00
                detected_setups.append({
                    'archetype': 'MSS_BREAKER_RETEST',
                    'archetype_id': 'SETUP-ARCH-003',
                    'direction': 'LONG',
                    'entry': entry_p,
                    'sl': sl_p,
                    'timeframe': 'M5',
                    'reason': f"Bullish Breaker Retest at {entry_p:.2f}"
                })
            elif current_price < last_sl and abs(current_price - last_sl) <= 1.80 and not in_mid_equilibrium:
                entry_p = last_sl
                sl_p = entry_p + 5.00
                detected_setups.append({
                    'archetype': 'MSS_BREAKER_RETEST',
                    'archetype_id': 'SETUP-ARCH-003',
                    'direction': 'SHORT',
                    'entry': entry_p,
                    'sl': sl_p,
                    'timeframe': 'M5',
                    'reason': f"Bearish Breaker Retest at {entry_p:.2f}"
                })

        # Tool 4: Institutional Session Range Expansion / Momentum FVG (SETUP-ARCH-004)
        # Catches runaway expansion days (e.g. today Nov 4 London Open impulse)
        # Condition: High volume candle displacing clean out of Asian / prior session range
        for i in range(len(recent_m5) - 1, 1, -1):
            bar = recent_m5[i]
            body = abs(bar['close'] - bar['open'])
            # Impulse displacement: single 5M candle >= 5.00 points breaking past Asian extreme
            if bar['close'] > bar['open'] and body >= 4.50 and bar['close'] > (asian_high + 2.00):
                # Bullish expansion FVG
                entry_p = bar['open'] + 0.5 * body  # 50% displacement candle retest
                sl_p = bar['open'] - 1.50
                detected_setups.append({
                    'archetype': 'SESSION_EXPANSION_FVG',
                    'archetype_id': 'SETUP-ARCH-004',
                    'direction': 'LONG',
                    'entry': entry_p,
                    'sl': sl_p,
                    'timeframe': 'M5',
                    'reason': f"London/NY Impulse Expansion (+{body:.2f} pts) breaking Asian High"
                })
                break
            elif bar['close'] < bar['open'] and body >= 4.50 and bar['close'] < (asian_low - 2.00):
                # Bearish expansion FVG
                entry_p = bar['open'] - 0.5 * body
                sl_p = bar['open'] + 1.50
                detected_setups.append({
                    'archetype': 'SESSION_EXPANSION_FVG',
                    'archetype_id': 'SETUP-ARCH-004',
                    'direction': 'SHORT',
                    'entry': entry_p,
                    'sl': sl_p,
                    'timeframe': 'M5',
                    'reason': f"London/NY Impulse Expansion (-{body:.2f} pts) breaking Asian Low"
                })
                break

        # Tool 5: Pro-Trend Session Retest / OTE 62-79% Retracement (SETUP-ARCH-009)
        # Valid when prior session had strong directional movement (total range >= 15 pts)
        if asian_range >= 12.0 and not in_mid_equilibrium:
            if current_price <= (asian_high - 0.618 * asian_range) and 'BULLISH' in h1_state:
                entry_p = asian_high - 0.705 * asian_range
                sl_p = asian_low - 1.50
                detected_setups.append({
                    'archetype': 'PRO_TREND_RETEST_OTE',
                    'archetype_id': 'SETUP-ARCH-009',
                    'direction': 'LONG',
                    'entry': entry_p,
                    'sl': sl_p,
                    'timeframe': 'M15',
                    'reason': f"Bullish Trend OTE 70.5% Discount Retracement at {entry_p:.2f}"
                })
            elif current_price >= (asian_low + 0.618 * asian_range) and 'BEARISH' in h1_state:
                entry_p = asian_low + 0.705 * asian_range
                sl_p = asian_high + 1.50
                detected_setups.append({
                    'archetype': 'PRO_TREND_RETEST_OTE',
                    'archetype_id': 'SETUP-ARCH-009',
                    'direction': 'SHORT',
                    'entry': entry_p,
                    'sl': sl_p,
                    'timeframe': 'M15',
                    'reason': f"Bearish Trend OTE 70.5% Premium Retracement at {entry_p:.2f}"
                })

        # Tool 6: Prominent Swing Liquidity Sweep with Micro MSS Displacement (SETUP-ARCH-010)
        # Check if prominent swing was swept in last 3 bars
        if sh_m5 and len(sh_m5) >= 2:
            prev_peak = sh_m5[-2]['price']
            last_peak = sh_m5[-1]['price']
            if last_peak > prev_peak and (last_peak - prev_peak) <= 3.50 and current_price < prev_peak:
                entry_p = prev_peak
                sl_p = last_peak + 1.50
                detected_setups.append({
                    'archetype': 'PROMINENT_SWEEP_MSS',
                    'archetype_id': 'SETUP-ARCH-010',
                    'direction': 'SHORT',
                    'entry': entry_p,
                    'sl': sl_p,
                    'timeframe': 'M5',
                    'reason': f"Prominent High ({prev_peak:.2f}) swept to {last_peak:.2f} + immediate MSS displacement"
                })

        if sl_m5 and len(sl_m5) >= 2:
            prev_trough = sl_m5[-2]['price']
            last_trough = sl_m5[-1]['price']
            if last_trough < prev_trough and (prev_trough - last_trough) <= 3.50 and current_price > prev_trough:
                entry_p = prev_trough
                sl_p = last_trough - 1.50
                detected_setups.append({
                    'archetype': 'PROMINENT_SWEEP_MSS',
                    'archetype_id': 'SETUP-ARCH-010',
                    'direction': 'LONG',
                    'entry': entry_p,
                    'sl': sl_p,
                    'timeframe': 'M5',
                    'reason': f"Prominent Low ({prev_trough:.2f}) swept to {last_trough:.2f} + immediate MSS displacement"
                })

        if not detected_setups:
            stand_aside_count += 1
            continue

        setup_count += len(detected_setups)

        # 4. Run Multi-Variant Forward Simulations for Each Detected Setup
        for s in detected_setups:
            arch = s['archetype']
            dir_str = s['direction']
            raw_entry = s['entry']
            raw_sl = s['sl']
            tf = s['timeframe']

            # Classify structural phase
            phase_info = classify_setup_phase(mtf_state, dir_str, symbol="XAUUSD")
            phase = phase_info['phase']  # PRO_EXPANSION vs HTF_RETRACEMENT vs BALANCED_RANGE

            # Stop Loss Variants
            risk_raw = abs(raw_entry - raw_sl)
            # Enforce reasonable stop distance on Gold: $3.50 to $8.00
            if risk_raw < 3.50:
                sl_calibrated = (raw_entry - 3.50) if dir_str == "LONG" else (raw_entry + 3.50)
            elif risk_raw > 8.00:
                sl_calibrated = (raw_entry - 8.00) if dir_str == "LONG" else (raw_entry + 8.00)
            else:
                sl_calibrated = raw_sl

            # SIMULATION MATRIX:
            # 1. Base Static 3.0R
            sim_static_3r = simulate_trade_execution(raw_entry, sl_calibrated, dir_str, forward_m1, target_rr=3.0, be_rr=None)
            
            # 2. Dynamic Target: 4.5R if PRO_EXPANSION, 2.2R if RETRACEMENT, with 2.0R BE
            dyn_target = 4.5 if phase == "PRO_EXPANSION" else (2.2 if phase == "HTF_RETRACEMENT" else 3.0)
            dyn_be = 2.0 if phase == "PRO_EXPANSION" else 1.5
            sim_dynamic = simulate_trade_execution(raw_entry, sl_calibrated, dir_str, forward_m1, target_rr=dyn_target, be_rr=dyn_be)

            # 3. Fixed Grid Targets: 2.0R, 2.5R, 3.5R, 4.5R
            sim_2r = simulate_trade_execution(raw_entry, sl_calibrated, dir_str, forward_m1, target_rr=2.0, be_rr=None)
            sim_4r = simulate_trade_execution(raw_entry, sl_calibrated, dir_str, forward_m1, target_rr=4.0, be_rr=None)

            # 4. Breakeven Variants (at 1.5R BE vs 1.8R BE vs 2.0R BE vs No BE on 3.5R target)
            sim_be_15 = simulate_trade_execution(raw_entry, sl_calibrated, dir_str, forward_m1, target_rr=3.5, be_rr=1.5)
            sim_be_18 = simulate_trade_execution(raw_entry, sl_calibrated, dir_str, forward_m1, target_rr=3.5, be_rr=1.8)
            sim_be_20 = simulate_trade_execution(raw_entry, sl_calibrated, dir_str, forward_m1, target_rr=3.5, be_rr=2.0)
            sim_no_be = simulate_trade_execution(raw_entry, sl_calibrated, dir_str, forward_m1, target_rr=3.5, be_rr=None)

            # 4b. Calibrated Optimal Configurations (Target 3.5R & 3.0R with BE 1.8R)
            sim_opt_35 = sim_be_18
            sim_opt_30 = simulate_trade_execution(raw_entry, sl_calibrated, dir_str, forward_m1, target_rr=3.0, be_rr=1.8)

            # 5. Multi-Stage Partial Scaling (60% at 2.5R, trail remainder)
            sim_partial_scale = simulate_trade_execution(
                raw_entry, sl_calibrated, dir_str, forward_m1,
                target_rr=6.0, be_rr=2.0, trail_runner=True,
                partial_scale_pct=0.60, partial_target_rr=2.5
            )

            # 6. Full Trailing Runner (Move to BE at 2R, trail 15M pivots with no hard TP ceiling)
            sim_full_runner = simulate_trade_execution(
                raw_entry, sl_calibrated, dir_str, forward_m1,
                target_rr=99.0, be_rr=2.0, trail_runner=True
            )

            record = {
                'timestamp': ms_dt.strftime("%Y-%m-%d %H:%M"),
                'session': sess_label,
                'archetype': arch,
                'archetype_id': s['archetype_id'],
                'timeframe': tf,
                'direction': dir_str,
                'entry': round(raw_entry, 2),
                'sl': round(sl_calibrated, 2),
                'risk_usd': round(abs(raw_entry - sl_calibrated), 2),
                'phase': phase,
                'h1_state': h1_state,
                'is_inside_day': is_inside_day,
                'in_mid_equilibrium': in_mid_equilibrium,
                'adr_20': round(adr_20, 2),
                'sim_static_3r': sim_static_3r,
                'sim_dynamic': sim_dynamic,
                'sim_2r': sim_2r,
                'sim_4r': sim_4r,
                'sim_be_15': sim_be_15,
                'sim_be_18': sim_be_18,
                'sim_be_20': sim_be_20,
                'sim_no_be': sim_no_be,
                'sim_opt_35': sim_opt_35,
                'sim_opt_30': sim_opt_30,
                'sim_partial_scale': sim_partial_scale,
                'sim_full_runner': sim_full_runner
            }
            all_trade_records.append(record)

    # 5. Compile Statistical Scorecard Across All Dimensions
    print("\n" + "=" * 85)
    print("📈 COMPILING COMPREHENSIVE QUANTITATIVE MATRIX...")
    print(f"Total Unique Setups Evaluated Across 2 Months: {len(all_trade_records)}")

    # Helper to calculate stats for a simulation key
    def _calc_stats(trades: List[Dict[str, Any]], sim_key: str):
        total = len(trades)
        if total == 0:
            return {'total': 0, 'filled': 0, 'wins': 0, 'losses': 0, 'be': 0, 'win_rate': 0.0, 'pf': 0.0, 'net_r': 0.0, 'exp_r': 0.0}

        filled = [t for t in trades if t[sim_key]['status'] in ('WIN', 'LOSS', 'BREAKEVEN', 'WIN_PARTIAL', 'OPEN_EXPANSION', 'OPEN_CLOSE')]
        fill_count = len(filled)
        if fill_count == 0:
            return {'total': total, 'filled': 0, 'wins': 0, 'losses': 0, 'be': 0, 'win_rate': 0.0, 'pf': 0.0, 'net_r': 0.0, 'exp_r': 0.0}

        wins = [t for t in filled if t[sim_key]['net_r'] > 0]
        losses = [t for t in filled if t[sim_key]['net_r'] < 0]
        bes = [t for t in filled if t[sim_key]['net_r'] == 0]

        win_count = len(wins)
        loss_count = len(losses)
        be_count = len(bes)

        gross_win_r = sum(t[sim_key]['net_r'] for t in wins)
        gross_loss_r = abs(sum(t[sim_key]['net_r'] for t in losses))
        net_r = gross_win_r - gross_loss_r

        pf = round(gross_win_r / gross_loss_r, 2) if gross_loss_r > 0 else (99.0 if gross_win_r > 0 else 0.0)
        wr = round((win_count / fill_count) * 100, 1)
        exp_r = round(net_r / fill_count, 2)

        return {
            'total': total,
            'filled': fill_count,
            'fill_rate': round((fill_count / total) * 100, 1),
            'wins': win_count,
            'losses': loss_count,
            'be': be_count,
            'win_rate': wr,
            'gross_win_r': round(gross_win_r, 2),
            'gross_loss_r': round(gross_loss_r, 2),
            'net_r': round(net_r, 2),
            'profit_factor': pf,
            'expectancy_r': exp_r
        }

    # SECTION 1: ARCHETYPE (TOOL) BREAKDOWN (Dynamic Policy)
    archetype_stats = {}
    archetypes = sorted(list(set(t['archetype'] for t in all_trade_records)))
    for a in archetypes:
        subset = [t for t in all_trade_records if t['archetype'] == a]
        archetype_stats[a] = {
            'M5': _calc_stats([t for t in subset if t['timeframe'] == 'M5'], 'sim_dynamic'),
            'M15': _calc_stats([t for t in subset if t['timeframe'] == 'M15'], 'sim_dynamic'),
            'Overall': _calc_stats(subset, 'sim_dynamic')
        }

    # SECTION 2: STRUCTURAL PHASE BREAKDOWN (PRO_EXPANSION vs HTF_RETRACEMENT)
    phase_stats = {
        'PRO_EXPANSION': _calc_stats([t for t in all_trade_records if t['phase'] == 'PRO_EXPANSION'], 'sim_dynamic'),
        'HTF_RETRACEMENT': _calc_stats([t for t in all_trade_records if t['phase'] == 'HTF_RETRACEMENT'], 'sim_dynamic'),
        'BALANCED_RANGE': _calc_stats([t for t in all_trade_records if t['phase'] == 'BALANCED_RANGE'], 'sim_dynamic')
    }

    # SECTION 3: TP LOGIC MATRIX
    tp_matrix = {
        'Fixed 2.0R': _calc_stats(all_trade_records, 'sim_2r'),
        'Fixed 3.0R': _calc_stats(all_trade_records, 'sim_static_3r'),
        'Fixed 4.0R': _calc_stats(all_trade_records, 'sim_4r'),
        'Dynamic (4.5R / 2.2R)': _calc_stats(all_trade_records, 'sim_dynamic')
    }

    # SECTION 4: POST-ENTRY TRADE MANAGEMENT MATRIX
    mgmt_matrix = {
        'Policy A: Static Set-and-Forget (No BE)': _calc_stats(all_trade_records, 'sim_no_be'),
        'Policy B1: Early Breakeven at 1.5R': _calc_stats(all_trade_records, 'sim_be_15'),
        'Policy B2: Optimal Breakeven at 1.8R': _calc_stats(all_trade_records, 'sim_be_18'),
        'Policy C: Conservative Breakeven at 2.0R': _calc_stats(all_trade_records, 'sim_be_20'),
        'Policy D: Multi-Stage Partial Scaling (60% at 2.5R + Runner)': _calc_stats(all_trade_records, 'sim_partial_scale'),
        'Policy E: Full Trailing Runner (Trail 15M Pivots, No Hard Cap)': _calc_stats(all_trade_records, 'sim_full_runner')
    }

    # SECTION 5: RANGE / CHOP FILTER AUDIT
    filter_matrix = {
        'Inside_Day_Chop': _calc_stats([t for t in all_trade_records if t['is_inside_day'] and t['in_mid_equilibrium']], 'sim_dynamic'),
        'Clean_Expansion_Environment': _calc_stats([t for t in all_trade_records if not (t['is_inside_day'] and t['in_mid_equilibrium'])], 'sim_dynamic')
    }

    # SECTION 6: OPTIMIZED TRADINGGUARD SUITE (Prime Sessions & Positive Edge Setups)
    prime_sessions = ['London_Open', 'London_Continuation', 'NY_Open']
    positive_tools = ['PROMINENT_SWEEP_MSS', 'MSS_BREAKER_RETEST', 'JUDAS_SWEEP_BREAKER']
    
    prime_trades_35 = []
    prime_trades_30 = []
    for t in all_trade_records:
        if t['session'] in prime_sessions:
            if t['archetype'] in positive_tools:
                prime_trades_35.append(t)
                prime_trades_30.append(t)
            elif t['archetype'] == 'SESSION_EXPANSION_FVG' and t['phase'] == 'PRO_EXPANSION':
                prime_trades_35.append(t)
                prime_trades_30.append(t)

    optimized_suite = {
        'Config_1_Target_35_BE_18': _calc_stats(prime_trades_35, 'sim_opt_35'),
        'Config_2_Target_30_BE_18': _calc_stats(prime_trades_30, 'sim_opt_30'),
        'Config_3_Target_35_BE_15': _calc_stats(prime_trades_35, 'sim_be_15'),
        'Archetype_Breakdown_Optimal_35': {
            'PROMINENT_SWEEP_MSS': _calc_stats([t for t in prime_trades_35 if t['archetype'] == 'PROMINENT_SWEEP_MSS'], 'sim_opt_35'),
            'MSS_BREAKER_RETEST': _calc_stats([t for t in prime_trades_35 if t['archetype'] == 'MSS_BREAKER_RETEST'], 'sim_opt_35'),
            'JUDAS_SWEEP_BREAKER': _calc_stats([t for t in prime_trades_35 if t['archetype'] == 'JUDAS_SWEEP_BREAKER'], 'sim_opt_35'),
            'SESSION_EXPANSION_FVG': _calc_stats([t for t in prime_trades_35 if t['archetype'] == 'SESSION_EXPANSION_FVG'], 'sim_opt_35')
        },
        'Phase_Breakdown_Optimal_35': {
            'PRO_EXPANSION': _calc_stats([t for t in prime_trades_35 if t['phase'] == 'PRO_EXPANSION'], 'sim_opt_35'),
            'HTF_RETRACEMENT': _calc_stats([t for t in prime_trades_35 if t['phase'] == 'HTF_RETRACEMENT'], 'sim_opt_35')
        }
    }

    # Save to JSON
    summary_report = {
        'meta': {
            'symbol': 'XAUUSD',
            'period': '2026-09-01 to 2026-11-04',
            'total_calendar_days': 65,
            'total_checkpoints': len(session_milestones),
            'total_setups': len(all_trade_records),
            'stand_asides': stand_aside_count,
            'audit_generated_at': datetime.datetime.now().isoformat()
        },
        'archetype_performance': archetype_stats,
        'phase_performance': phase_stats,
        'tp_logic_matrix': tp_matrix,
        'trade_management_matrix': mgmt_matrix,
        'filter_audit': filter_matrix,
        'optimized_core_suite': optimized_suite,
        'trades': all_trade_records
    }

    json_path = OUTPUT_DIR / "gold_master_audit_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary_report, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Saved full raw dataset to {json_path}")
    print("=" * 85)
    print("🏁 MASTER AUDIT EXECUTION COMPLETE")
    print(f"Elapsed Time: {time.time() - t_start_wall:.1f} seconds")
    print("=" * 85)


if __name__ == "__main__":
    run_gold_master_audit()
