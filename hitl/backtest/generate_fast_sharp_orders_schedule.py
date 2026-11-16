"""
TradingGuard HITL - Programmatic Orders Schedule Generator for MetaTrader 5
Generates authentic orders_schedule.csv for MT5 Strategy Tester execution
covering ratified fast & sharp market archetypes:
  - SETUP-ARCH-017 (Multi-Asset 15m Opening Range Breakout)
  - SETUP-ARCH-018 (Multi-Asset Judas Liquidity Sweep Reversal in Range)
Governed by:
  - Prior Market Regime Classification (Zero Contradictions)
  - Directional Symmetry (Zero Directional Bias)
  - Prop Firm Risk Budget: $10.00 Max Risk on $1,000 Account (1.0% Equity)
"""

import sys
import datetime
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hitl.backtest.session_clock import get_session_times_for_date

COMMON_FILES = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
TERMINAL_FILES = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB\MQL5\Files")


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
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
    return dx.ewm(alpha=1/period, adjust=False).mean()


def load_dataset(parquet_path: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df_m5 = pd.read_parquet(parquet_path)
    if 'time' in df_m5.columns:
        df_m5['timestamp'] = df_m5['time'].astype(np.int64)
    else:
        df_m5['timestamp'] = df_m5.index.astype(np.int64) // 10**9

    df_m5 = df_m5.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
    df_m5['dt'] = pd.to_datetime(df_m5['timestamp'], unit='s', utc=True)

    tr_m5 = pd.concat([
        df_m5['high'] - df_m5['low'],
        (df_m5['high'] - df_m5['close'].shift(1)).abs(),
        (df_m5['low'] - df_m5['close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    df_m5['atr14'] = tr_m5.rolling(14).mean().bfill()

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

    df_h1['ema20'] = df_h1['close'].ewm(span=20, adjust=False).mean()
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df_h1['adx14'] = calculate_adx(df_h1, period=14)
    df_h1['ema50_slope'] = df_h1['ema50'] - df_h1['ema50'].shift(3)

    return df_m5, df_h1


def classify_regime(
    t_epoch: int,
    h1_ts: np.ndarray,
    h1_closes: np.ndarray,
    h1_ema20s: np.ndarray,
    h1_ema50s: np.ndarray,
    h1_adxs: np.ndarray,
    h1_slopes: np.ndarray,
) -> str:
    idx = np.searchsorted(h1_ts, t_epoch - 3600, side='right') - 1
    if idx < 55:
        return "RANGE_BOUND"
    h1_close = h1_closes[idx]
    h1_ema20 = h1_ema20s[idx]
    h1_ema50 = h1_ema50s[idx]
    h1_adx = h1_adxs[idx]
    h1_slope = h1_slopes[idx]

    is_bull = (h1_close > h1_ema20) and (h1_ema20 > h1_ema50) and (h1_slope > 0)
    is_bear = (h1_close < h1_ema20) and (h1_ema20 < h1_ema50) and (h1_slope < 0)

    if h1_adx >= 22.0 and is_bull:
        return "HEAVY_TREND_BULL"
    elif h1_adx >= 22.0 and is_bear:
        return "HEAVY_TREND_BEAR"
    elif h1_adx < 20.0 or (not is_bull and not is_bear):
        return "RANGE_BOUND"
    else:
        return "TRANSITION"


def generate_orders_for_asset(symbol: str, parquet_path: str, broker_sym: str) -> List[Dict[str, Any]]:
    print(f"Generating orders for {symbol} ({broker_sym})...")
    df_m5, df_h1 = load_dataset(parquet_path)

    h1_ts = df_h1['timestamp'].values
    h1_closes = df_h1['close'].values
    h1_ema20s = df_h1['ema20'].values
    h1_ema50s = df_h1['ema50'].values
    h1_adxs = df_h1['adx14'].values
    h1_slopes = df_h1['ema50_slope'].values

    is_gold = "XAU" in symbol.upper()
    is_fx = "GBP" in symbol.upper()
    is_nq = "NQ" in symbol.upper()

    digits = 2 if is_gold else (5 if is_fx else 1)
    max_risk_usd = 10.0  # $10.00 risk budget

    df_m5['date'] = df_m5['dt'].dt.date
    dates = df_m5['date'].unique()

    orders = []

    for d in dates:
        day_m5 = df_m5[df_m5['date'] == d]
        if len(day_m5) < 50:
            continue

        sess_times = get_session_times_for_date(d)
        is_uk_dst = sess_times.get("is_uk_dst", False)
        is_us_dst = sess_times.get("is_us_dst", False)

        lon_open_hour = 7 if is_uk_dst else 8
        ny_open_hour = 12 if is_us_dst else 13
        nyse_cash_hour = 13 if is_us_dst else 14

        asian_bars = day_m5[(day_m5['dt'].dt.hour >= 0) & (day_m5['dt'].dt.hour < lon_open_hour)]
        asian_high = asian_bars['high'].max() if not asian_bars.empty else None
        asian_low = asian_bars['low'].min() if not asian_bars.empty else None

        ib_lon_bars = day_m5[(day_m5['dt'].dt.hour == lon_open_hour) & (day_m5['dt'].dt.minute < 15)]
        ib_lon_high = ib_lon_bars['high'].max() if len(ib_lon_bars) >= 2 else None
        ib_lon_low = ib_lon_bars['low'].min() if len(ib_lon_bars) >= 2 else None

        ib_nyse_bars = day_m5[(day_m5['dt'].dt.hour == nyse_cash_hour) & (day_m5['dt'].dt.minute >= 30) & (day_m5['dt'].dt.minute < 45)]
        ib_nyse_high = ib_nyse_bars['high'].max() if len(ib_nyse_bars) >= 2 else None
        ib_nyse_low = ib_nyse_bars['low'].min() if len(ib_nyse_bars) >= 2 else None

        session_trades = {"ORB_LON": 0, "ORB_NYSE": 0, "JUDAS_LON": 0, "JUDAS_NY": 0}

        for i_loc in range(len(day_m5)):
            bar = day_m5.iloc[i_loc]
            dt = bar['dt']
            t_epoch = int(bar['timestamp'])
            hour = dt.hour
            minute = dt.minute

            is_london = (hour >= lon_open_hour) and (hour < lon_open_hour + 4)
            is_ny = (hour >= ny_open_hour) and (hour < ny_open_hour + 5)
            is_nyse_cash = ((hour == nyse_cash_hour and minute >= 30) or (hour > nyse_cash_hour and hour < nyse_cash_hour + 3))

            if not (is_london or is_ny):
                continue

            regime = classify_regime(t_epoch, h1_ts, h1_closes, h1_ema20s, h1_ema50s, h1_adxs, h1_slopes)
            atr = bar['atr14']
            if atr <= 0:
                continue

            # Model 2: London ORB (08:15 - 09:30 UTC) for Gold and FX
            if (is_gold or is_fx) and ((hour == lon_open_hour and minute >= 15) or (hour == lon_open_hour + 1 and minute <= 30)):
                if session_trades["ORB_LON"] == 0 and ib_lon_high is not None and ib_lon_low is not None:
                    ib_mid = (ib_lon_high + ib_lon_low) / 2.0
                    # Bullish ORB
                    if regime not in ["HEAVY_TREND_BEAR", "RANGE_BOUND"]:
                        if bar['close'] > ib_lon_high and (bar['close'] - bar['open']) > 0.4 * atr:
                            raw_entry = ib_lon_high
                            raw_sl = ib_mid
                            risk_pts = raw_entry - raw_sl
                            if risk_pts > 0:
                                # Prop Firm Sizing & Entry Retracement
                                if is_gold:
                                    lot = 0.01
                                    max_pts = max_risk_usd / 1.0  # 10.0 pts
                                    entry = (raw_sl + max_pts) if risk_pts > max_pts else raw_entry
                                    sl = raw_sl
                                    risk_pts = entry - sl
                                elif is_fx:
                                    # Pip value at 0.01 is $0.10; for $10 risk on risk_pts:
                                    lot = round(max_risk_usd / (risk_pts * 100000.0), 2)
                                    lot = max(0.01, min(lot, 0.20))
                                    entry = raw_entry
                                    sl = raw_sl
                                tp = entry + (risk_pts * 3.0)
                                trigger_str = datetime.datetime.fromtimestamp(t_epoch).strftime("%Y.%m.%d %H:%M:%S")
                                orders.append({
                                    "ID": f"TG-ORB-{broker_sym[:3]}-{d.strftime('%Y%m%d')}-{hour:02d}{minute:02d}",
                                    "Symbol": broker_sym,
                                    "Type": "BUY_LIMIT",
                                    "TriggerTime": trigger_str,
                                    "Entry": round(entry, digits),
                                    "SL": round(sl, digits),
                                    "TP": round(tp, digits),
                                    "Lot": lot,
                                    "TTL": 60,
                                    "BE_Ratchet": 1.5,
                                    "Model": "SETUP-ARCH-017",
                                    "Regime": regime
                                })
                                session_trades["ORB_LON"] += 1

                    # Bearish ORB
                    if regime not in ["HEAVY_TREND_BULL", "RANGE_BOUND"]:
                        if bar['close'] < ib_lon_low and (bar['open'] - bar['close']) > 0.4 * atr:
                            raw_entry = ib_lon_low
                            raw_sl = ib_mid
                            risk_pts = raw_sl - raw_entry
                            if risk_pts > 0:
                                if is_gold:
                                    lot = 0.01
                                    max_pts = max_risk_usd / 1.0
                                    entry = (raw_sl - max_pts) if risk_pts > max_pts else raw_entry
                                    sl = raw_sl
                                    risk_pts = sl - entry
                                elif is_fx:
                                    lot = round(max_risk_usd / (risk_pts * 100000.0), 2)
                                    lot = max(0.01, min(lot, 0.20))
                                    entry = raw_entry
                                    sl = raw_sl
                                tp = entry - (risk_pts * 3.0)
                                trigger_str = datetime.datetime.fromtimestamp(t_epoch).strftime("%Y.%m.%d %H:%M:%S")
                                orders.append({
                                    "ID": f"TG-ORB-{broker_sym[:3]}-{d.strftime('%Y%m%d')}-{hour:02d}{minute:02d}",
                                    "Symbol": broker_sym,
                                    "Type": "SELL_LIMIT",
                                    "TriggerTime": trigger_str,
                                    "Entry": round(entry, digits),
                                    "SL": round(sl, digits),
                                    "TP": round(tp, digits),
                                    "Lot": lot,
                                    "TTL": 60,
                                    "BE_Ratchet": 1.5,
                                    "Model": "SETUP-ARCH-017",
                                    "Regime": regime
                                })
                                session_trades["ORB_LON"] += 1

            # Model 2: NYSE Cash ORB (14:45 - 16:00 UTC) for All Assets
            if is_nyse_cash and hour == nyse_cash_hour and minute >= 45:
                if session_trades["ORB_NYSE"] == 0 and ib_nyse_high is not None and ib_nyse_low is not None:
                    ib_mid = (ib_nyse_high + ib_nyse_low) / 2.0
                    # Bullish ORB
                    if regime not in ["HEAVY_TREND_BEAR", "RANGE_BOUND"]:
                        if bar['close'] > ib_nyse_high and (bar['close'] - bar['open']) > 0.4 * atr:
                            raw_entry = ib_nyse_high
                            raw_sl = ib_mid
                            risk_pts = raw_entry - raw_sl
                            if risk_pts > 0:
                                if is_gold:
                                    lot = 0.01
                                    max_pts = max_risk_usd / 1.0
                                    entry = (raw_sl + max_pts) if risk_pts > max_pts else raw_entry
                                    sl = raw_sl
                                    risk_pts = entry - sl
                                elif is_nq:
                                    lot = round(max_risk_usd / (risk_pts * 1.0), 1)
                                    lot = max(0.1, min(lot, 1.0))
                                    entry = raw_entry
                                    sl = raw_sl
                                elif is_fx:
                                    lot = round(max_risk_usd / (risk_pts * 100000.0), 2)
                                    lot = max(0.01, min(lot, 0.20))
                                    entry = raw_entry
                                    sl = raw_sl
                                tp = entry + (risk_pts * 3.0)
                                trigger_str = datetime.datetime.fromtimestamp(t_epoch).strftime("%Y.%m.%d %H:%M:%S")
                                orders.append({
                                    "ID": f"TG-ORB-{broker_sym[:3]}-{d.strftime('%Y%m%d')}-{hour:02d}{minute:02d}",
                                    "Symbol": broker_sym,
                                    "Type": "BUY_LIMIT",
                                    "TriggerTime": trigger_str,
                                    "Entry": round(entry, digits),
                                    "SL": round(sl, digits),
                                    "TP": round(tp, digits),
                                    "Lot": lot,
                                    "TTL": 60,
                                    "BE_Ratchet": 1.5,
                                    "Model": "SETUP-ARCH-017",
                                    "Regime": regime
                                })
                                session_trades["ORB_NYSE"] += 1

                    # Bearish ORB
                    if regime not in ["HEAVY_TREND_BULL", "RANGE_BOUND"]:
                        if bar['close'] < ib_nyse_low and (bar['open'] - bar['close']) > 0.4 * atr:
                            raw_entry = ib_nyse_low
                            raw_sl = ib_mid
                            risk_pts = raw_sl - raw_entry
                            if risk_pts > 0:
                                if is_gold:
                                    lot = 0.01
                                    max_pts = max_risk_usd / 1.0
                                    entry = (raw_sl - max_pts) if risk_pts > max_pts else raw_entry
                                    sl = raw_sl
                                    risk_pts = sl - entry
                                elif is_nq:
                                    lot = round(max_risk_usd / (risk_pts * 1.0), 1)
                                    lot = max(0.1, min(lot, 1.0))
                                    entry = raw_entry
                                    sl = raw_sl
                                elif is_fx:
                                    lot = round(max_risk_usd / (risk_pts * 100000.0), 2)
                                    lot = max(0.01, min(lot, 0.20))
                                    entry = raw_entry
                                    sl = raw_sl
                                tp = entry - (risk_pts * 3.0)
                                trigger_str = datetime.datetime.fromtimestamp(t_epoch).strftime("%Y.%m.%d %H:%M:%S")
                                orders.append({
                                    "ID": f"TG-ORB-{broker_sym[:3]}-{d.strftime('%Y%m%d')}-{hour:02d}{minute:02d}",
                                    "Symbol": broker_sym,
                                    "Type": "SELL_LIMIT",
                                    "TriggerTime": trigger_str,
                                    "Entry": round(entry, digits),
                                    "SL": round(sl, digits),
                                    "TP": round(tp, digits),
                                    "Lot": lot,
                                    "TTL": 60,
                                    "BE_Ratchet": 1.5,
                                    "Model": "SETUP-ARCH-017",
                                    "Regime": regime
                                })
                                session_trades["ORB_NYSE"] += 1

            # Model 3: Judas Liquidity Sweep Reversal in Range (ONLY in RANGE / TRANSITION)
            judas_key = "JUDAS_LON" if is_london else "JUDAS_NY"
            if session_trades[judas_key] == 0 and regime in ["RANGE_BOUND", "TRANSITION"]:
                if asian_high is not None and asian_low is not None:
                    # Bullish Low Sweep
                    if bar['low'] < (asian_low - 0.25 * atr) and bar['close'] > asian_low:
                        if (bar['close'] - bar['open']) > 0:
                            entry = asian_low
                            sl = bar['low'] - (0.5 * atr)
                            risk_pts = entry - sl
                            if risk_pts > 0:
                                if is_gold:
                                    lot = 0.01
                                    max_pts = max_risk_usd / 1.0
                                    entry = (sl + max_pts) if risk_pts > max_pts else entry
                                    risk_pts = entry - sl
                                elif is_nq:
                                    lot = round(max_risk_usd / (risk_pts * 1.0), 1)
                                    lot = max(0.1, min(lot, 1.0))
                                elif is_fx:
                                    lot = round(max_risk_usd / (risk_pts * 100000.0), 2)
                                    lot = max(0.01, min(lot, 0.20))
                                tp = entry + (risk_pts * 2.5)
                                trigger_str = datetime.datetime.fromtimestamp(t_epoch).strftime("%Y.%m.%d %H:%M:%S")
                                orders.append({
                                    "ID": f"TG-JSR-{broker_sym[:3]}-{d.strftime('%Y%m%d')}-{hour:02d}{minute:02d}",
                                    "Symbol": broker_sym,
                                    "Type": "BUY_LIMIT",
                                    "TriggerTime": trigger_str,
                                    "Entry": round(entry, digits),
                                    "SL": round(sl, digits),
                                    "TP": round(tp, digits),
                                    "Lot": lot,
                                    "TTL": 60,
                                    "BE_Ratchet": 1.2,
                                    "Model": "SETUP-ARCH-018",
                                    "Regime": regime
                                })
                                session_trades[judas_key] += 1

                    # Bearish High Sweep
                    elif bar['high'] > (asian_high + 0.25 * atr) and bar['close'] < asian_high:
                        if (bar['open'] - bar['close']) > 0:
                            entry = asian_high
                            sl = bar['high'] + (0.5 * atr)
                            risk_pts = sl - entry
                            if risk_pts > 0:
                                if is_gold:
                                    lot = 0.01
                                    max_pts = max_risk_usd / 1.0
                                    entry = (sl - max_pts) if risk_pts > max_pts else entry
                                    risk_pts = sl - entry
                                elif is_nq:
                                    lot = round(max_risk_usd / (risk_pts * 1.0), 1)
                                    lot = max(0.1, min(lot, 1.0))
                                elif is_fx:
                                    lot = round(max_risk_usd / (risk_pts * 100000.0), 2)
                                    lot = max(0.01, min(lot, 0.20))
                                tp = entry - (risk_pts * 2.5)
                                trigger_str = datetime.datetime.fromtimestamp(t_epoch).strftime("%Y.%m.%d %H:%M:%S")
                                orders.append({
                                    "ID": f"TG-JSR-{broker_sym[:3]}-{d.strftime('%Y%m%d')}-{hour:02d}{minute:02d}",
                                    "Symbol": broker_sym,
                                    "Type": "SELL_LIMIT",
                                    "TriggerTime": trigger_str,
                                    "Entry": round(entry, digits),
                                    "SL": round(sl, digits),
                                    "TP": round(tp, digits),
                                    "Lot": lot,
                                    "TTL": 60,
                                    "BE_Ratchet": 1.2,
                                    "Model": "SETUP-ARCH-018",
                                    "Regime": regime
                                })
                                session_trades[judas_key] += 1

    print(f"  -> Generated {len(orders)} orders for {symbol}.")
    return orders


def main():
    print("=== GENERATING MULTI-ASSET FAST & SHARP ORDERS FOR MT5 STRATEGY TESTER ===")
    gold_orders = generate_orders_for_asset("XAUUSD", "backtest_results/cache/XAUUSD_M5_1YEAR.parquet", "XAUUSD_o")
    nq_orders = generate_orders_for_asset("NQ", "backtest_results/cache/NQ_M5_1YEAR.parquet", "NQ")
    cable_orders = generate_orders_for_asset("GBPUSD", "backtest_results/cache/GBPUSD_M5_1YEAR.parquet", "GBPUSD_o")

    all_orders = gold_orders + nq_orders + cable_orders
    all_orders.sort(key=lambda x: x["TriggerTime"])
    print(f"\nTotal Orders Generated across Portfolio: {len(all_orders)}")

    df_out = pd.DataFrame(all_orders)
    # Save master schedule
    master_csv = PROJECT_ROOT / "orders_schedule.csv"
    
    # Format matching TradingGuard_Executor.mq5:
    # ID,Symbol,Type,TriggerTime,Entry,SL,TP,Lot,TTL,BE_Ratchet
    cols = ["ID", "Symbol", "Type", "TriggerTime", "Entry", "SL", "TP", "Lot", "TTL", "BE_Ratchet"]
    df_out[cols].to_csv(master_csv, index=False)
    print(f"Saved master orders schedule: {master_csv} ({len(df_out)} rows)")

    # Sync to MT5 directories
    for d in [COMMON_FILES, TERMINAL_FILES]:
        if d.exists():
            target = d / "orders_schedule.csv"
            shutil.copy2(master_csv, target)
            print(f"Synced to MT5: {target}")


if __name__ == "__main__":
    main()
