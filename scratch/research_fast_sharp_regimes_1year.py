"""
TradingGuard HITL - 1-Year Fast & Sharp Market Quantitative Research
Evaluates Symmetric, Direction-Agnostic Setup Archetypes Across 1-Year Data (2025-2026)
Governed by Strict Prior Market Regime Classification:
- REGIME_HEAVY_TREND_BULL: Only Pro-Trend Bullish Continuation (Zero Short Fades)
- REGIME_HEAVY_TREND_BEAR: Only Pro-Trend Bearish Continuation (Zero Long Knife-Catches)
- REGIME_RANGE_BOUND: Symmetric Liquidity Sweep & Reversal (Judas Fades to Equilibrium)
- REGIME_FAST_EXPANSION: Symmetric Opening Range Breakout (ORB)
"""

import sys
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np

# Force unbuffered output so logs print immediately
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hitl.backtest.session_clock import get_session_times_for_date

TZ_LONDON = ZoneInfo("Europe/London")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_UTC = datetime.timezone.utc


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculates Wilder's ADX."""
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    pos_di = 100 * pd.Series(pos_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-9)
    neg_di = 100 * pd.Series(neg_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-9)
    
    dx = 100 * (pos_di - neg_di).abs() / ((pos_di + neg_di) + 1e-9)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    return adx


def load_and_prepare_dataset(parquet_path: str, symbol: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Loads 1-year M5 dataset and resamples H1 and D1 structures."""
    df_m5 = pd.read_parquet(parquet_path)
    if 'time' in df_m5.columns:
        df_m5['timestamp'] = df_m5['time'].astype(np.int64)
    else:
        df_m5['timestamp'] = df_m5.index.astype(np.int64) // 10**9

    df_m5 = df_m5.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
    df_m5['dt'] = pd.to_datetime(df_m5['timestamp'], unit='s', utc=True)

    # ATR14 on M5
    tr_m5 = pd.concat([
        df_m5['high'] - df_m5['low'],
        (df_m5['high'] - df_m5['close'].shift(1)).abs(),
        (df_m5['low'] - df_m5['close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    df_m5['atr14'] = tr_m5.rolling(14).mean().bfill()
    df_m5['ema20'] = df_m5['close'].ewm(span=20, adjust=False).mean()

    # Resample H1
    df_m5['h1_bucket'] = df_m5['timestamp'] // 3600 * 3600
    df_h1 = df_m5.groupby('h1_bucket').agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        tick_volume=('tick_volume', 'sum')
    ).reset_index().rename(columns={'h1_bucket': 'timestamp'})
    df_h1['dt'] = pd.to_datetime(df_h1['timestamp'], unit='s', utc=True)
    df_h1 = df_h1.sort_values('timestamp').reset_index(drop=True)

    # H1 Indicators: EMA20, EMA50, ADX14
    df_h1['ema20'] = df_h1['close'].ewm(span=20, adjust=False).mean()
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df_h1['adx14'] = calculate_adx(df_h1, period=14)
    df_h1['ema50_slope'] = df_h1['ema50'] - df_h1['ema50'].shift(3)

    # Resample D1 (UTC midnight)
    df_m5['d1_bucket'] = df_m5['timestamp'] // 86400 * 86400
    df_d1 = df_m5.groupby('d1_bucket').agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        tick_volume=('tick_volume', 'sum')
    ).reset_index().rename(columns={'d1_bucket': 'timestamp'})
    df_d1['dt'] = pd.to_datetime(df_d1['timestamp'], unit='s', utc=True)
    df_d1 = df_d1.sort_values('timestamp').reset_index(drop=True)

    tr_d = pd.concat([
        df_d1['high'] - df_d1['low'],
        (df_d1['high'] - df_d1['close'].shift(1)).abs(),
        (df_d1['low'] - df_d1['close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    df_d1['adr14'] = tr_d.shift(1).rolling(14).mean().bfill()
    df_d1['ema20'] = df_d1['close'].ewm(span=20, adjust=False).mean()

    return df_m5, df_h1, df_d1


def classify_market_regime_fast(
    current_time_epoch: int,
    h1_ts: np.ndarray,
    h1_closes: np.ndarray,
    h1_ema20s: np.ndarray,
    h1_ema50s: np.ndarray,
    h1_adxs: np.ndarray,
    h1_slopes: np.ndarray,
) -> Dict[str, Any]:
    """Fast binary-search regime classifier running in <1 microsecond."""
    idx = np.searchsorted(h1_ts, current_time_epoch - 3600, side='right') - 1
    if idx < 55:
        return {"regime": "RANGE_BOUND", "adx": 15.0, "rationale": "Insufficient H1 history"}

    h1_close = h1_closes[idx]
    h1_ema20 = h1_ema20s[idx]
    h1_ema50 = h1_ema50s[idx]
    h1_adx = h1_adxs[idx]
    h1_slope = h1_slopes[idx]

    is_bullish_alignment = (h1_close > h1_ema20) and (h1_ema20 > h1_ema50) and (h1_slope > 0)
    is_bearish_alignment = (h1_close < h1_ema20) and (h1_ema20 < h1_ema50) and (h1_slope < 0)

    if h1_adx >= 22.0 and is_bullish_alignment:
        regime = "HEAVY_TREND_BULL"
        rationale = f"H1 EMA20({h1_ema20:.2f}) > EMA50({h1_ema50:.2f}) with ADX={h1_adx:.1f} and positive slope"
    elif h1_adx >= 22.0 and is_bearish_alignment:
        regime = "HEAVY_TREND_BEAR"
        rationale = f"H1 EMA20({h1_ema20:.2f}) < EMA50({h1_ema50:.2f}) with ADX={h1_adx:.1f} and negative slope"
    elif h1_adx < 20.0 or (not is_bullish_alignment and not is_bearish_alignment):
        regime = "RANGE_BOUND"
        rationale = f"H1 ADX low ({h1_adx:.1f}) or mixed EMA alignment"
    else:
        regime = "TRANSITION"
        rationale = f"ADX={h1_adx:.1f} in transition zone"

    return {
        "regime": regime,
        "adx": round(float(h1_adx), 1),
        "h1_close": float(h1_close),
        "h1_ema20": float(h1_ema20),
        "h1_ema50": float(h1_ema50),
        "rationale": rationale
    }


def simulate_m5_execution(
    df_m5: pd.DataFrame,
    start_idx: int,
    decision: str,  # 'BUY' or 'SELL'
    entry: float,
    sl: float,
    target_rr: float,
    symbol: str,
    spread: float,
    slippage: float,
    commission_per_001_lot: float = 0.10,
    be_ratchet_rr: Optional[float] = 1.5,
    max_bars: int = 144,  # max 12 hours (144 M5 bars)
    ttl_bars: int = 12,   # 1 hour limit TTL
    lot: float = 0.01
) -> Dict[str, Any]:
    """Simulates realistic limit order execution on closed M5 bars with SL-first collision resolution."""
    is_buy = (decision.upper() == "BUY")

    if "XAU" in symbol.upper():
        pip_val = 1.0       # 0.01 lot = $1.00 / point
    elif "GBP" in symbol.upper() or "EUR" in symbol.upper():
        pip_val = 1000.0    # 0.01 lot = $0.10 / pip
    elif "NQ" in symbol.upper() or "SPX" in symbol.upper() or "YM" in symbol.upper():
        pip_val = 0.10      # 0.10 lot = $0.10 / point
    else:
        pip_val = 1.0

    commission_total = commission_per_001_lot * (lot / 0.01)
    effective_entry = entry + slippage if is_buy else entry - slippage
    risk_pts = abs(effective_entry - sl)
    if risk_pts <= 0:
        return {"status": "INVALID_RISK", "realized_r": 0.0, "realized_pnl_usd": 0.0}

    tp = effective_entry + (risk_pts * target_rr) if is_buy else effective_entry - (risk_pts * target_rr)
    price_risk_usd = risk_pts * pip_val

    is_filled = False
    fill_idx = None
    active_sl = sl
    is_be_active = False

    n_bars = len(df_m5)
    end_idx = min(n_bars, start_idx + max_bars)

    for rel_idx, bar_idx in enumerate(range(start_idx, end_idx)):
        bar = df_m5.iloc[bar_idx]
        h = bar['high']
        l = bar['low']
        c = bar['close']

        if not is_filled:
            if rel_idx >= ttl_bars:
                return {"status": "EXPIRED", "realized_r": 0.0, "realized_pnl_usd": 0.0, "is_realized": True}
            # Check Limit fill with spread
            if is_buy and (l + spread) <= entry:
                is_filled = True
                fill_idx = rel_idx
            elif (not is_buy) and h >= entry:
                is_filled = True
                fill_idx = rel_idx
        else:
            # Filled: Monitor SL / TP / BE
            if is_buy:
                hit_sl = (l <= active_sl)
                hit_tp = (h >= tp)

                # SL-first collision resolution
                if hit_sl and hit_tp:
                    loss_amount = -price_risk_usd - commission_total
                    return {"status": "LOSS_COLLISION", "realized_r": -1.0, "realized_pnl_usd": round(loss_amount, 2), "is_realized": True}
                if hit_sl:
                    if is_be_active:
                        be_pnl = spread * pip_val - commission_total
                        return {"status": "BREAKEVEN", "realized_r": round(be_pnl / price_risk_usd, 3), "realized_pnl_usd": round(be_pnl, 2), "is_realized": True}
                    else:
                        loss_amount = -price_risk_usd - commission_total
                        return {"status": "LOSS", "realized_r": -1.0, "realized_pnl_usd": round(loss_amount, 2), "is_realized": True}
                if hit_tp:
                    win_amount = (risk_pts * target_rr * pip_val) - commission_total
                    return {"status": "WIN", "realized_r": target_rr, "realized_pnl_usd": round(win_amount, 2), "is_realized": True}
                # Check BE Ratchet
                if be_ratchet_rr is not None and not is_be_active:
                    if (h - effective_entry) >= (risk_pts * be_ratchet_rr):
                        active_sl = effective_entry + spread
                        is_be_active = True
            else:
                hit_sl = ((h + spread) >= active_sl)
                hit_tp = ((l + spread) <= tp)

                if hit_sl and hit_tp:
                    loss_amount = -price_risk_usd - commission_total
                    return {"status": "LOSS_COLLISION", "realized_r": -1.0, "realized_pnl_usd": round(loss_amount, 2), "is_realized": True}
                if hit_sl:
                    if is_be_active:
                        be_pnl = spread * pip_val - commission_total
                        return {"status": "BREAKEVEN", "realized_r": round(be_pnl / price_risk_usd, 3), "realized_pnl_usd": round(be_pnl, 2), "is_realized": True}
                    else:
                        loss_amount = -price_risk_usd - commission_total
                        return {"status": "LOSS", "realized_r": -1.0, "realized_pnl_usd": round(loss_amount, 2), "is_realized": True}
                if hit_tp:
                    win_amount = (risk_pts * target_rr * pip_val) - commission_total
                    return {"status": "WIN", "realized_r": target_rr, "realized_pnl_usd": round(win_amount, 2), "is_realized": True}
                # Check BE Ratchet
                if be_ratchet_rr is not None and not is_be_active:
                    if (effective_entry - l) >= (risk_pts * be_ratchet_rr):
                        active_sl = effective_entry - spread
                        is_be_active = True

    return {"status": "TIMEOUT", "realized_r": 0.0, "realized_pnl_usd": 0.0, "is_realized": True}


def run_full_year_backtest(symbol: str, parquet_path: str) -> Dict[str, Any]:
    """Runs systematic 1-year backtest of symmetric fast & sharp models governed by regime classification."""
    print(f"\n=======================================================")
    print(f"Loading 1-Year Dataset for {symbol}: {parquet_path}")
    print(f"=======================================================")

    df_m5, df_h1, df_d1 = load_and_prepare_dataset(parquet_path, symbol)
    print(f"Loaded {len(df_m5)} M5 bars, {len(df_h1)} H1 bars, {len(df_d1)} D1 bars.")
    start_date = df_m5['dt'].iloc[0].strftime("%Y-%m-%d")
    end_date = df_m5['dt'].iloc[-1].strftime("%Y-%m-%d")
    print(f"Date Range: {start_date} to {end_date}")

    # Extract H1 numpy arrays for fast O(1) binary search
    h1_ts = df_h1['timestamp'].values
    h1_closes = df_h1['close'].values
    h1_ema20s = df_h1['ema20'].values
    h1_ema50s = df_h1['ema50'].values
    h1_adxs = df_h1['adx14'].values
    h1_slopes = df_h1['ema50_slope'].values

    # Broker specs
    if "XAU" in symbol.upper():
        spread = 0.22
        slippage = 0.05
        contract_size = 100.0  # 1 lot = 100 oz, 0.01 lot = 1 oz ($1.00/pt)
        min_tick = 0.01
    elif "GBP" in symbol.upper():
        spread = 0.00006
        slippage = 0.00001
        contract_size = 100000.0 # 0.01 lot = 1000 units ($0.10/pip)
        min_tick = 0.00001
    elif "NQ" in symbol.upper():
        spread = 1.0
        slippage = 0.25
        contract_size = 20.0     # 0.01 lot = $0.20/pt, at 0.1 lot = $0.10/pt
        min_tick = 0.25
    else:
        spread = 0.5
        slippage = 0.1
        contract_size = 1.0
        min_tick = 0.01

    max_risk_usd = 10.0  # 1.0% on $1,000 account
    lot_size = 0.01

    trades: List[Dict[str, Any]] = []

    # Group M5 by date (UTC date)
    df_m5['date'] = df_m5['dt'].dt.date
    dates = df_m5['date'].unique()

    total_days = len(dates)
    print(f"Total Trading Days to Analyze: {total_days}")

    # Track trades taken per day/session to avoid stacking identical entries
    for d_idx, d in enumerate(dates):
        day_m5 = df_m5[df_m5['date'] == d]
        if len(day_m5) < 50:
            continue

        sess_times = get_session_times_for_date(d)
        is_uk_dst = sess_times.get("is_uk_dst", False)
        is_us_dst = sess_times.get("is_us_dst", False)

        # Dynamic London & NY Open UTC hours
        lon_open_utc_hour = 7 if is_uk_dst else 8
        ny_open_utc_hour = 12 if is_us_dst else 13
        nyse_cash_utc_hour = 13 if is_us_dst else 14
        nyse_cash_utc_min = 30

        # Asian Range: 00:00 to London Open
        asian_bars = day_m5[(day_m5['dt'].dt.hour >= 0) & (day_m5['dt'].dt.hour < lon_open_utc_hour)]
        asian_high = asian_bars['high'].max() if not asian_bars.empty else None
        asian_low = asian_bars['low'].min() if not asian_bars.empty else None

        # Track session trade limits (max 1 trade per model per session)
        session_trades = {"ORB_LON": 0, "ORB_NYSE": 0, "CONT_LON": 0, "CONT_NY": 0, "JUDAS_LON": 0, "JUDAS_NY": 0}

        # Track Initial Balances for ORB (first 15m of session)
        ib_lon_bars = day_m5[(day_m5['dt'].dt.hour == lon_open_utc_hour) & (day_m5['dt'].dt.minute < 15)]
        ib_lon_high = ib_lon_bars['high'].max() if len(ib_lon_bars) >= 2 else None
        ib_lon_low = ib_lon_bars['low'].min() if len(ib_lon_bars) >= 2 else None

        ib_nyse_bars = day_m5[(day_m5['dt'].dt.hour == nyse_cash_utc_hour) & (day_m5['dt'].dt.minute >= 30) & (day_m5['dt'].dt.minute < 45)]
        ib_nyse_high = ib_nyse_bars['high'].max() if len(ib_nyse_bars) >= 2 else None
        ib_nyse_low = ib_nyse_bars['low'].min() if len(ib_nyse_bars) >= 2 else None

        # Iterate through day's M5 bars starting from London Open
        for i_loc in range(len(day_m5)):
            m5_bar = day_m5.iloc[i_loc]
            global_m5_idx = m5_bar.name
            dt = m5_bar['dt']
            t_epoch = int(m5_bar['timestamp'])
            hour = dt.hour
            minute = dt.minute

            # Only trade during active London & NY sessions
            is_london = (hour >= lon_open_utc_hour) and (hour < lon_open_utc_hour + 4)
            is_ny = (hour >= ny_open_utc_hour) and (hour < ny_open_utc_hour + 5)
            is_nyse_cash = ((hour == nyse_cash_utc_hour and minute >= 30) or (hour > nyse_cash_utc_hour and hour < nyse_cash_utc_hour + 3))

            if not (is_london or is_ny):
                continue

            # Classify regime at this exact bar in <1 microsecond
            reg_info = classify_market_regime_fast(t_epoch, h1_ts, h1_closes, h1_ema20s, h1_ema50s, h1_adxs, h1_slopes)
            regime = reg_info['regime']

            atr = m5_bar['atr14']
            if atr <= 0:
                continue

            # ----------------------------------------------------
            # MODEL 1: PRO-TREND FAST DISPLACEMENT & RETRACEMENT
            # ----------------------------------------------------
            sess_key = "CONT_LON" if is_london else "CONT_NY"
            if session_trades[sess_key] == 0 and global_m5_idx >= 15:
                # Bullish Continuation (ONLY in HEAVY_TREND_BULL)
                if regime == "HEAVY_TREND_BULL":
                    # Check for recent bullish displacement bar (within last 3 bars)
                    disp_bar = day_m5.iloc[max(0, i_loc - 1)]
                    body = disp_bar['close'] - disp_bar['open']
                    candle_range = disp_bar['high'] - disp_bar['low']

                    if body >= 1.25 * atr and (body / (candle_range + 1e-9)) >= 0.60:
                        # Displacement broke prior swing high
                        prior_swing_high = df_m5['high'].iloc[global_m5_idx - 12:global_m5_idx - 2].max()
                        if disp_bar['close'] > prior_swing_high:
                            # FVG exists (disp_bar['low'] > bar[i-2]['high'])
                            c_prev2 = df_m5.iloc[global_m5_idx - 3]
                            if disp_bar['low'] > c_prev2['high']:
                                raw_entry = disp_bar['low']
                                swing_low = df_m5['low'].iloc[global_m5_idx - 12:global_m5_idx].min()
                                raw_sl = swing_low - max(1.5 * spread, 0.25 * atr)
                                struct_risk_pts = raw_entry - raw_sl

                                if struct_risk_pts > 0:
                                    # Prop Risk Guard: Limit Entry Retracement if risk > max_risk_usd
                                    if "XAU" in symbol.upper():
                                        dollar_per_pt = 1.0  # 0.01 lot
                                    elif "GBP" in symbol.upper():
                                        dollar_per_pt = 1000.0
                                    elif "NQ" in symbol.upper():
                                        dollar_per_pt = 0.10
                                    else:
                                        dollar_per_pt = 1.0

                                    allowed_risk_pts = max_risk_usd / dollar_per_pt
                                    actual_entry = raw_sl + allowed_risk_pts if struct_risk_pts > allowed_risk_pts else raw_entry
                                    actual_sl = raw_sl

                                    res = simulate_m5_execution(
                                        df_m5=df_m5,
                                        start_idx=global_m5_idx,
                                        decision="BUY",
                                        entry=actual_entry,
                                        sl=actual_sl,
                                        target_rr=2.5,
                                        symbol=symbol,
                                        spread=spread,
                                        slippage=slippage,
                                        be_ratchet_rr=1.5
                                    )
                                    if res['status'] != "INVALID_RISK":
                                        trades.append({
                                            "date": d,
                                            "dt": dt,
                                            "symbol": symbol,
                                            "model": "MODEL1_PRO_TREND_CONT",
                                            "direction": "BUY",
                                            "regime": regime,
                                            "entry": round(actual_entry, 5),
                                            "sl": round(actual_sl, 5),
                                            "status": res['status'],
                                            "realized_r": res['realized_r'],
                                            "realized_pnl_usd": res['realized_pnl_usd']
                                        })
                                        session_trades[sess_key] += 1

                # Bearish Continuation (ONLY in HEAVY_TREND_BEAR)
                elif regime == "HEAVY_TREND_BEAR":
                    disp_bar = day_m5.iloc[max(0, i_loc - 1)]
                    body = disp_bar['open'] - disp_bar['close']
                    candle_range = disp_bar['high'] - disp_bar['low']

                    if body >= 1.25 * atr and (body / (candle_range + 1e-9)) >= 0.60:
                        prior_swing_low = df_m5['low'].iloc[global_m5_idx - 12:global_m5_idx - 2].min()
                        if disp_bar['close'] < prior_swing_low:
                            c_prev2 = df_m5.iloc[global_m5_idx - 3]
                            if disp_bar['high'] < c_prev2['low']:
                                raw_entry = disp_bar['high']
                                swing_high = df_m5['high'].iloc[global_m5_idx - 12:global_m5_idx].max()
                                raw_sl = swing_high + max(1.5 * spread, 0.25 * atr)
                                struct_risk_pts = raw_sl - raw_entry

                                if struct_risk_pts > 0:
                                    if "XAU" in symbol.upper():
                                        dollar_per_pt = 1.0
                                    elif "GBP" in symbol.upper():
                                        dollar_per_pt = 1000.0
                                    elif "NQ" in symbol.upper():
                                        dollar_per_pt = 0.10
                                    else:
                                        dollar_per_pt = 1.0

                                    allowed_risk_pts = max_risk_usd / dollar_per_pt
                                    actual_entry = raw_sl - allowed_risk_pts if struct_risk_pts > allowed_risk_pts else raw_entry
                                    actual_sl = raw_sl

                                    res = simulate_m5_execution(
                                        df_m5=df_m5,
                                        start_idx=global_m5_idx,
                                        decision="SELL",
                                        entry=actual_entry,
                                        sl=actual_sl,
                                        target_rr=2.5,
                                        symbol=symbol,
                                        spread=spread,
                                        slippage=slippage,
                                        be_ratchet_rr=1.5
                                    )
                                    if res['status'] != "INVALID_RISK":
                                        trades.append({
                                            "date": d,
                                            "dt": dt,
                                            "symbol": symbol,
                                            "model": "MODEL1_PRO_TREND_CONT",
                                            "direction": "SELL",
                                            "regime": regime,
                                            "entry": round(actual_entry, 5),
                                            "sl": round(actual_sl, 5),
                                            "status": res['status'],
                                            "realized_r": res['realized_r'],
                                            "realized_pnl_usd": res['realized_pnl_usd']
                                        })
                                        session_trades[sess_key] += 1

            # ----------------------------------------------------
            # MODEL 2: FAST SESSION OPENING RANGE BREAKOUT (ORB)
            # ----------------------------------------------------
            # London ORB (08:15 to 09:30 UTC)
            if (hour == lon_open_utc_hour and minute >= 15) or (hour == lon_open_utc_hour + 1 and minute <= 30):
                if session_trades["ORB_LON"] == 0 and ib_lon_high is not None and ib_lon_low is not None:
                    ib_range = ib_lon_high - ib_lon_low
                    ib_mid = (ib_lon_high + ib_lon_low) / 2.0

                    # Bullish ORB: Breakout above IB high (Permitted if not in HEAVY_TREND_BEAR)
                    if regime != "HEAVY_TREND_BEAR" and regime != "RANGE_BOUND":
                        if m5_bar['close'] > ib_lon_high and (m5_bar['close'] - m5_bar['open']) > 0.4 * atr:
                            entry = ib_lon_high
                            sl = ib_mid
                            if (entry - sl) > 0:
                                res = simulate_m5_execution(
                                    df_m5=df_m5,
                                    start_idx=global_m5_idx,
                                    decision="BUY",
                                    entry=entry,
                                    sl=sl,
                                    target_rr=3.0,
                                    symbol=symbol,
                                    spread=spread,
                                    slippage=slippage,
                                    be_ratchet_rr=1.5
                                )
                                if res['status'] != "INVALID_RISK":
                                    trades.append({
                                        "date": d,
                                        "dt": dt,
                                        "symbol": symbol,
                                        "model": "MODEL2_SESSION_ORB",
                                        "direction": "BUY",
                                        "regime": regime,
                                        "entry": round(entry, 5),
                                        "sl": round(sl, 5),
                                        "status": res['status'],
                                        "realized_r": res['realized_r'],
                                        "realized_pnl_usd": res['realized_pnl_usd']
                                    })
                                    session_trades["ORB_LON"] += 1

                    # Bearish ORB: Breakout below IB low (Permitted if not in HEAVY_TREND_BULL)
                    if regime != "HEAVY_TREND_BULL" and regime != "RANGE_BOUND":
                        if m5_bar['close'] < ib_lon_low and (m5_bar['open'] - m5_bar['close']) > 0.4 * atr:
                            entry = ib_lon_low
                            sl = ib_mid
                            if (sl - entry) > 0:
                                res = simulate_m5_execution(
                                    df_m5=df_m5,
                                    start_idx=global_m5_idx,
                                    decision="SELL",
                                    entry=entry,
                                    sl=sl,
                                    target_rr=3.0,
                                    symbol=symbol,
                                    spread=spread,
                                    slippage=slippage,
                                    be_ratchet_rr=1.5
                                )
                                if res['status'] != "INVALID_RISK":
                                    trades.append({
                                        "date": d,
                                        "dt": dt,
                                        "symbol": symbol,
                                        "model": "MODEL2_SESSION_ORB",
                                        "direction": "SELL",
                                        "regime": regime,
                                        "entry": round(entry, 5),
                                        "sl": round(sl, 5),
                                        "status": res['status'],
                                        "realized_r": res['realized_r'],
                                        "realized_pnl_usd": res['realized_pnl_usd']
                                    })
                                    session_trades["ORB_LON"] += 1

            # NYSE Cash ORB (14:45 to 16:00 UTC)
            if is_nyse_cash and hour == nyse_cash_utc_hour and minute >= 45:
                if session_trades["ORB_NYSE"] == 0 and ib_nyse_high is not None and ib_nyse_low is not None:
                    ib_mid = (ib_nyse_high + ib_nyse_low) / 2.0

                    if regime != "HEAVY_TREND_BEAR" and regime != "RANGE_BOUND":
                        if m5_bar['close'] > ib_nyse_high and (m5_bar['close'] - m5_bar['open']) > 0.4 * atr:
                            entry = ib_nyse_high
                            sl = ib_mid
                            if (entry - sl) > 0:
                                res = simulate_m5_execution(
                                    df_m5=df_m5,
                                    start_idx=global_m5_idx,
                                    decision="BUY",
                                    entry=entry,
                                    sl=sl,
                                    target_rr=3.0,
                                    symbol=symbol,
                                    spread=spread,
                                    slippage=slippage,
                                    be_ratchet_rr=1.5
                                )
                                if res['status'] != "INVALID_RISK":
                                    trades.append({
                                        "date": d,
                                        "dt": dt,
                                        "symbol": symbol,
                                        "model": "MODEL2_SESSION_ORB",
                                        "direction": "BUY",
                                        "regime": regime,
                                        "entry": round(entry, 5),
                                        "sl": round(sl, 5),
                                        "status": res['status'],
                                        "realized_r": res['realized_r'],
                                        "realized_pnl_usd": res['realized_pnl_usd']
                                    })
                                    session_trades["ORB_NYSE"] += 1

                    if regime != "HEAVY_TREND_BULL" and regime != "RANGE_BOUND":
                        if m5_bar['close'] < ib_nyse_low and (m5_bar['open'] - m5_bar['close']) > 0.4 * atr:
                            entry = ib_nyse_low
                            sl = ib_mid
                            if (sl - entry) > 0:
                                res = simulate_m5_execution(
                                    df_m5=df_m5,
                                    start_idx=global_m5_idx,
                                    decision="SELL",
                                    entry=entry,
                                    sl=sl,
                                    target_rr=3.0,
                                    symbol=symbol,
                                    spread=spread,
                                    slippage=slippage,
                                    be_ratchet_rr=1.5
                                )
                                if res['status'] != "INVALID_RISK":
                                    trades.append({
                                        "date": d,
                                        "dt": dt,
                                        "symbol": symbol,
                                        "model": "MODEL2_SESSION_ORB",
                                        "direction": "SELL",
                                        "regime": regime,
                                        "entry": round(entry, 5),
                                        "sl": round(sl, 5),
                                        "status": res['status'],
                                        "realized_r": res['realized_r'],
                                        "realized_pnl_usd": res['realized_pnl_usd']
                                    })
                                    session_trades["ORB_NYSE"] += 1

            # ----------------------------------------------------------------------
            # MODEL 3: FAST LIQUIDITY SWEEP & REJECTION (ONLY in RANGE / TRANSITION)
            # ----------------------------------------------------------------------
            # Strictly blocked if regime is HEAVY_TREND!
            judas_key = "JUDAS_LON" if is_london else "JUDAS_NY"
            if session_trades[judas_key] == 0 and regime in ["RANGE_BOUND", "TRANSITION"]:
                if asian_high is not None and asian_low is not None:
                    # Bullish Sweep of Asian Low
                    if m5_bar['low'] < (asian_low - 0.25 * atr) and m5_bar['close'] > asian_low:
                        if (m5_bar['close'] - m5_bar['open']) > 0:  # Green rejection
                            entry = asian_low
                            sl = m5_bar['low'] - max(1.5 * spread, 0.25 * atr)
                            if (entry - sl) > 0:
                                res = simulate_m5_execution(
                                    df_m5=df_m5,
                                    start_idx=global_m5_idx,
                                    decision="BUY",
                                    entry=entry,
                                    sl=sl,
                                    target_rr=2.5,
                                    symbol=symbol,
                                    spread=spread,
                                    slippage=slippage,
                                    be_ratchet_rr=1.2
                                )
                                if res['status'] != "INVALID_RISK":
                                    trades.append({
                                        "date": d,
                                        "dt": dt,
                                        "symbol": symbol,
                                        "model": "MODEL3_SWEEP_REVERSAL",
                                        "direction": "BUY",
                                        "regime": regime,
                                        "entry": round(entry, 5),
                                        "sl": round(sl, 5),
                                        "status": res['status'],
                                        "realized_r": res['realized_r'],
                                        "realized_pnl_usd": res['realized_pnl_usd']
                                    })
                                    session_trades[judas_key] += 1

                    # Bearish Sweep of Asian High
                    elif m5_bar['high'] > (asian_high + 0.25 * atr) and m5_bar['close'] < asian_high:
                        if (m5_bar['open'] - m5_bar['close']) > 0:  # Red rejection
                            entry = asian_high
                            sl = m5_bar['high'] + max(1.5 * spread, 0.25 * atr)
                            if (sl - entry) > 0:
                                res = simulate_m5_execution(
                                    df_m5=df_m5,
                                    start_idx=global_m5_idx,
                                    decision="SELL",
                                    entry=entry,
                                    sl=sl,
                                    target_rr=2.5,
                                    symbol=symbol,
                                    spread=spread,
                                    slippage=slippage,
                                    be_ratchet_rr=1.2
                                )
                                if res['status'] != "INVALID_RISK":
                                    trades.append({
                                        "date": d,
                                        "dt": dt,
                                        "symbol": symbol,
                                        "model": "MODEL3_SWEEP_REVERSAL",
                                        "direction": "SELL",
                                        "regime": regime,
                                        "entry": round(entry, 5),
                                        "sl": round(sl, 5),
                                        "status": res['status'],
                                        "realized_r": res['realized_r'],
                                        "realized_pnl_usd": res['realized_pnl_usd']
                                    })
                                    session_trades[judas_key] += 1

    df_trades = pd.DataFrame(trades)
    print(f"\n=======================================================")
    print(f"Backtest Completed for {symbol}: Total Trades = {len(df_trades)}")
    print(f"=======================================================")

    return {
        "symbol": symbol,
        "trades": df_trades
    }


def analyze_performance(df_trades: pd.DataFrame, label: str):
    """Outputs comprehensive, unvarnished quantitative performance metrics."""
    if df_trades.empty:
        print(f"\n[{label}] No trades recorded.")
        return

    filled = df_trades[df_trades['status'] != "EXPIRED"]
    wins = filled[filled['status'] == "WIN"]
    losses = filled[filled['status'].str.startswith("LOSS")]
    breakevens = filled[filled['status'] == "BREAKEVEN"]

    total_r = filled['realized_r'].sum()
    total_pnl = filled['realized_pnl_usd'].sum()
    n_filled = len(filled)
    n_wins = len(wins)
    n_losses = len(losses)
    n_be = len(breakevens)
    win_rate = (n_wins / n_filled * 100) if n_filled > 0 else 0.0

    gross_profit = wins['realized_pnl_usd'].sum()
    gross_loss = abs(losses['realized_pnl_usd'].sum())
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    # Compute Max Drawdown in R
    cum_r = filled['realized_r'].cumsum()
    peak_r = cum_r.cummax()
    dd_r = peak_r - cum_r
    max_dd_r = dd_r.max() if not dd_r.empty else 0.0

    print(f"\n--- PERFORMANCE SUMMARY: {label} ---")
    print(f"Total Signals: {len(df_trades)} | Filled Trades: {n_filled} | Expired: {len(df_trades) - n_filled}")
    print(f"Wins: {n_wins} | Losses: {n_losses} | Breakevens: {n_be}")
    print(f"Win Rate (on fills): {win_rate:.1f}%")
    print(f"Gross Profit: +${gross_profit:.2f} | Gross Loss: -${gross_loss:.2f}")
    print(f"Net PnL (0.01 lot): ${total_pnl:+.2f} USD")
    print(f"Net Realized R: {total_r:+.2f} R")
    print(f"Profit Factor: {profit_factor:.2f}")
    print(f"Max Drawdown: -{max_dd_r:.2f} R")

    # Directional Breakdown: Long vs Short
    buys = filled[filled['direction'] == "BUY"]
    sells = filled[filled['direction'] == "SELL"]

    buy_r = buys['realized_r'].sum()
    buy_wr = (len(buys[buys['status'] == "WIN"]) / len(buys) * 100) if len(buys) > 0 else 0.0
    buy_gp = buys[buys['status'] == "WIN"]['realized_pnl_usd'].sum()
    buy_gl = abs(buys[buys['status'].str.startswith("LOSS")]['realized_pnl_usd'].sum())
    buy_pf = (buy_gp / buy_gl) if buy_gl > 0 else (99.0 if buy_gp > 0 else 0.0)

    sell_r = sells['realized_r'].sum()
    sell_wr = (len(sells[sells['status'] == "WIN"]) / len(sells) * 100) if len(sells) > 0 else 0.0
    sell_gp = sells[sells['status'] == "WIN"]['realized_pnl_usd'].sum()
    sell_gl = abs(sells[sells['status'].str.startswith("LOSS")]['realized_pnl_usd'].sum())
    sell_pf = (sell_gp / sell_gl) if sell_gl > 0 else (99.0 if sell_gp > 0 else 0.0)

    print(f"  > LONG  (BUY) : {len(buys)} trades | WinRate: {buy_wr:.1f}% | Net R: {buy_r:+.2f}R | PF: {buy_pf:.2f}")
    print(f"  > SHORT (SELL): {len(sells)} trades | WinRate: {sell_wr:.1f}% | Net R: {sell_r:+.2f}R | PF: {sell_pf:.2f}")

    # Model Breakdown
    print("\nModel Breakdown:")
    for m in df_trades['model'].unique():
        m_trades = filled[filled['model'] == m]
        if m_trades.empty:
            continue
        m_r = m_trades['realized_r'].sum()
        m_wr = (len(m_trades[m_trades['status'] == "WIN"]) / len(m_trades) * 100)
        m_gp = m_trades[m_trades['status'] == "WIN"]['realized_pnl_usd'].sum()
        m_gl = abs(m_trades[m_trades['status'].str.startswith("LOSS")]['realized_pnl_usd'].sum())
        m_pf = (m_gp / m_gl) if m_gl > 0 else (99.0 if m_gp > 0 else 0.0)
        print(f"  - {m}: {len(m_trades)} trades | WinRate: {m_wr:.1f}% | Net R: {m_r:+.2f}R | PF: {m_pf:.2f}")


if __name__ == "__main__":
    assets = [
        ("XAUUSD", "backtest_results/cache/XAUUSD_M5_1YEAR.parquet"),
        ("GBPUSD", "backtest_results/cache/GBPUSD_M5_1YEAR.parquet"),
        ("NQ", "backtest_results/cache/NQ_M5_1YEAR.parquet")
    ]

    all_dfs = []
    for sym, path in assets:
        res = run_full_year_backtest(sym, path)
        analyze_performance(res['trades'], sym)
        all_dfs.append(res['trades'])

    combined_df = pd.concat(all_dfs, ignore_index=True)
    analyze_performance(combined_df, "PORTFOLIO COMBINED (1-YEAR)")
    combined_df.to_csv("scratch/one_year_fast_sharp_regimes_results.csv", index=False)
    print("\nResults saved to scratch/one_year_fast_sharp_regimes_results.csv")

