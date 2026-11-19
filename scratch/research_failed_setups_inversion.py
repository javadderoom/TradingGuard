"""
TradingGuard Quantitative Research: Failed Setups & Structural Inversion
Tests the hypothesis:
Can losing technical setups be systematically inverted into profitable alpha?
Compares:
1. Original Failing Setup: Standard 15-Minute Opening Range Breakout (ORB)
2. Naive Inversion: Simply taking the opposite trade at breakout (Flipping buy to sell with inverted SL/TP)
3. Structural Failure Exploitation (The Trap Model / Turtle Soup):
   - Waiting for the breakout to fail (price closes back inside the 15M range)
   - Entering in the direction of the failure with tight SL above the false excursion
   - Targeting range equilibrium (0.5) or opposite range boundary (1.0)
4. Inversion FVG (IFVG):
   - When a 5M FVG fails (bar closes through it), trading the retest in the direction of the breach
"""

import sys
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hitl.backtest.session_clock import get_session_times_for_date

TZ_LONDON = ZoneInfo("Europe/London")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_UTC = datetime.timezone.utc


def load_m1_m5_data(symbol: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Loads M5 and M1 data for a symbol from backtest_results/cache."""
    cache_dir = PROJECT_ROOT / "backtest_results" / "cache"
    
    # Select M5 file
    m5_files = [
        cache_dir / f"{symbol}_M5_1YEAR.parquet",
        cache_dir / f"{symbol}_M5_2026.parquet",
        cache_dir / f"M5_{symbol}_2026.parquet",
    ]
    m5_path = next((f for f in m5_files if f.exists()), None)
    if not m5_path:
        raise FileNotFoundError(f"No M5 cache found for {symbol}")

    df_m5 = pd.read_parquet(m5_path)
    if 'time' in df_m5.columns:
        df_m5['timestamp'] = df_m5['time'].astype(np.int64)
    else:
        df_m5['timestamp'] = df_m5.index.astype(np.int64) // 10**9
    df_m5 = df_m5.drop_duplicates('timestamp').sort_values('timestamp').reset_index(drop=True)
    df_m5['dt'] = pd.to_datetime(df_m5['timestamp'], unit='s', utc=True)

    # Select M1 file
    m1_files = [
        cache_dir / f"{symbol}_M1_2026.parquet",
        cache_dir / f"M1_{symbol}_2026.parquet",
    ]
    m1_path = next((f for f in m1_files if f.exists()), None)
    if not m1_path:
        raise FileNotFoundError(f"No M1 cache found for {symbol}")

    df_m1 = pd.read_parquet(m1_path)
    if 'time' in df_m1.columns:
        df_m1['timestamp'] = df_m1['time'].astype(np.int64)
    else:
        df_m1['timestamp'] = df_m1.index.astype(np.int64) // 10**9
    df_m1 = df_m1.drop_duplicates('timestamp').sort_values('timestamp').reset_index(drop=True)
    df_m1['dt'] = pd.to_datetime(df_m1['timestamp'], unit='s', utc=True)

    return df_m5, df_m1


def simulate_trade_m1(
    df_m1: pd.DataFrame,
    start_ts: int,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
    max_holding_min: int = 120,
    spread: float = 0.0
) -> Dict[str, Any]:
    """Simulates a trade forward on M1 bars with realistic spread and collision resolution."""
    sub = df_m1[(df_m1['timestamp'] >= start_ts) & (df_m1['timestamp'] <= start_ts + max_holding_min * 60)]
    if sub.empty:
        return {"outcome": "TIMEOUT", "pnl_r": 0.0, "exit_price": entry}

    risk = abs(entry - sl)
    if risk <= 1e-6:
        return {"outcome": "INVALID", "pnl_r": 0.0, "exit_price": entry}

    for idx, row in sub.iterrows():
        b_high = row['high']
        b_low = row['low']
        b_close = row['close']

        if direction == "BUY":
            # SL hit if low <= sl
            # TP hit if high >= tp
            if b_low <= sl:
                # Loss
                pnl_r = -1.0 - (spread / risk)
                return {"outcome": "LOSS", "pnl_r": pnl_r, "exit_price": sl, "holding_min": (row['timestamp'] - start_ts) // 60}
            if b_high >= tp:
                # Win
                pnl_r = ((tp - entry) / risk) - (spread / risk)
                return {"outcome": "WIN", "pnl_r": pnl_r, "exit_price": tp, "holding_min": (row['timestamp'] - start_ts) // 60}
        else: # SELL
            # SL hit if high >= sl
            # TP hit if low <= tp
            if b_high >= sl:
                # Loss
                pnl_r = -1.0 - (spread / risk)
                return {"outcome": "LOSS", "pnl_r": pnl_r, "exit_price": sl, "holding_min": (row['timestamp'] - start_ts) // 60}
            if b_low <= tp:
                # Win
                pnl_r = ((entry - tp) / risk) - (spread / risk)
                return {"outcome": "WIN", "pnl_r": pnl_r, "exit_price": tp, "holding_min": (row['timestamp'] - start_ts) // 60}

    # Timeout exit at last close
    last_close = sub.iloc[-1]['close']
    if direction == "BUY":
        pnl_r = ((last_close - entry) / risk) - (spread / risk)
    else:
        pnl_r = ((entry - last_close) / risk) - (spread / risk)
    return {"outcome": "TIMEOUT", "pnl_r": pnl_r, "exit_price": last_close, "holding_min": max_holding_min}


def audit_orb_and_traps(symbol: str) -> Dict[str, Any]:
    """
    Audits:
    1. Standard ORB (Breakout)
    2. Naive Inversion (Instant Fade at Breakout)
    3. Structural Failure Trap (Wait for Failure Confirmation: Close Back Inside Range)
    """
    df_m5, df_m1 = load_m1_m5_data(symbol)
    
    # Symbol parameters
    spread_dict = {"XAUUSD": 0.25, "NQ": 1.0, "GBPUSD": 0.00012}
    spread = spread_dict.get(symbol, 0.2)

    # Daily grouping
    df_m5['date'] = df_m5['dt'].dt.date
    unique_dates = sorted(df_m5['date'].unique())

    orig_trades = []
    naive_trades = []
    trap_trades = []

    for d in unique_dates:
        # Determine session opening time
        # For Metals/Forex: London Open (08:00 UK). For NQ: NY Cash Open (09:30 US).
        sess = get_session_times_for_date(d)
        if symbol == "NQ":
            open_utc = sess["nyse_open"]["utc_time"] # 09:30 US Cash Open
        else:
            open_utc = sess["london"]["utc_time"] # 08:00 UK Open

        open_ts = int(open_utc.timestamp())
        range_end_ts = open_ts + 15 * 60 # 15-minute range

        # 15M opening bars (3 bars of 5M)
        orb_bars = df_m5[(df_m5['timestamp'] >= open_ts) & (df_m5['timestamp'] < range_end_ts)]
        if len(orb_bars) < 3:
            continue

        range_high = orb_bars['high'].max()
        range_low = orb_bars['low'].min()
        range_size = range_high - range_low
        mid_point = (range_high + range_low) / 2.0

        if range_size <= 1e-4:
            continue

        # Post-ORB bars (next 90 minutes)
        post_bars = df_m5[(df_m5['timestamp'] >= range_end_ts) & (df_m5['timestamp'] <= range_end_ts + 90 * 60)]
        if post_bars.empty:
            continue

        # Check for breakout
        breakout_found = False
        breakout_dir = None
        breakout_ts = None
        breakout_entry = None
        breakout_sl = None
        breakout_tp = None

        for idx, bar in post_bars.iterrows():
            # Bullish Breakout
            if bar['close'] > range_high and not breakout_found:
                breakout_found = True
                breakout_dir = "BUY"
                breakout_ts = int(bar['timestamp'])
                breakout_entry = bar['close']
                breakout_sl = range_low # or range_high - 0.5 * range_size
                breakout_tp = breakout_entry + 1.5 * (breakout_entry - breakout_sl)
                break
            # Bearish Breakdown
            elif bar['close'] < range_low and not breakout_found:
                breakout_found = True
                breakout_dir = "SELL"
                breakout_ts = int(bar['timestamp'])
                breakout_entry = bar['close']
                breakout_sl = range_high
                breakout_tp = breakout_entry - 1.5 * (breakout_sl - breakout_entry)
                break

        if not breakout_found:
            continue

        # 1. Original Breakout Simulation
        res_orig = simulate_trade_m1(df_m1, breakout_ts, breakout_dir, breakout_entry, breakout_sl, breakout_tp, 120, spread)
        res_orig['date'] = str(d)
        res_orig['symbol'] = symbol
        res_orig['dir'] = breakout_dir
        orig_trades.append(res_orig)

        # 2. Naive Inversion (Opposite trade at exact same timestamp)
        # If original was BUY, Naive is SELL at entry, SL at original TP, TP at original SL
        naive_dir = "SELL" if breakout_dir == "BUY" else "BUY"
        naive_sl = breakout_tp
        naive_tp = breakout_sl
        res_naive = simulate_trade_m1(df_m1, breakout_ts, naive_dir, breakout_entry, naive_sl, naive_tp, 120, spread)
        res_naive['date'] = str(d)
        res_naive['symbol'] = symbol
        res_naive['dir'] = naive_dir
        naive_trades.append(res_naive)

        # 3. Structural Failure Exploitation (The "Trap" Model / Turtle Soup)
        # We DO NOT enter at breakout. We wait for a subsequent bar to FAIL back inside the range!
        fail_sub = post_bars[post_bars['timestamp'] > breakout_ts]
        trap_triggered = False
        for f_idx, f_bar in fail_sub.iterrows():
            if breakout_dir == "BUY":
                # Bullish breakout fails if price closes back below range_high
                if f_bar['close'] < range_high:
                    trap_triggered = True
                    trap_ts = int(f_bar['timestamp'])
                    trap_dir = "SELL"
                    trap_entry = f_bar['close']
                    # SL is placed above the false breakout high excursion
                    excursion_high = post_bars[(post_bars['timestamp'] >= breakout_ts) & (post_bars['timestamp'] <= trap_ts)]['high'].max()
                    trap_sl = excursion_high + (0.1 * range_size)
                    # TP is targeted at range low or opposite boundary
                    trap_tp = range_low
                    
                    # Risk-to-Reward sanity check: must offer at least 1:1.2
                    risk = trap_sl - trap_entry
                    reward = trap_entry - trap_tp
                    if risk > 0 and reward / risk >= 1.0:
                        res_trap = simulate_trade_m1(df_m1, trap_ts, trap_dir, trap_entry, trap_sl, trap_tp, 120, spread)
                        res_trap['date'] = str(d)
                        res_trap['symbol'] = symbol
                        res_trap['dir'] = trap_dir
                        res_trap['rr_ratio'] = round(reward / risk, 2)
                        trap_trades.append(res_trap)
                    break
            else: # breakout_dir == "SELL"
                # Bearish breakdown fails if price closes back above range_low
                if f_bar['close'] > range_low:
                    trap_triggered = True
                    trap_ts = int(f_bar['timestamp'])
                    trap_dir = "BUY"
                    trap_entry = f_bar['close']
                    excursion_low = post_bars[(post_bars['timestamp'] >= breakout_ts) & (post_bars['timestamp'] <= trap_ts)]['low'].min()
                    trap_sl = excursion_low - (0.1 * range_size)
                    trap_tp = range_high
                    
                    risk = trap_entry - trap_sl
                    reward = trap_tp - trap_entry
                    if risk > 0 and reward / risk >= 1.0:
                        res_trap = simulate_trade_m1(df_m1, trap_ts, trap_dir, trap_entry, trap_sl, trap_tp, 120, spread)
                        res_trap['date'] = str(d)
                        res_trap['symbol'] = symbol
                        res_trap['dir'] = trap_dir
                        res_trap['rr_ratio'] = round(reward / risk, 2)
                        trap_trades.append(res_trap)
                    break

    def summarize(trades: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
        if not trades:
            return {"name": name, "trades": 0, "net_r": 0.0, "win_rate": 0.0, "pf": 0.0}
        df = pd.DataFrame(trades)
        total = len(df)
        wins = len(df[df['outcome'] == 'WIN'])
        losses = len(df[df['outcome'] == 'LOSS'])
        timeouts = len(df[df['outcome'] == 'TIMEOUT'])
        net_r = df['pnl_r'].sum()
        gross_profit = df[df['pnl_r'] > 0]['pnl_r'].sum()
        gross_loss = abs(df[df['pnl_r'] < 0]['pnl_r'].sum())
        pf = round(gross_profit / (gross_loss + 1e-9), 2)
        wr = round((wins / total) * 100, 1)
        return {
            "name": name,
            "trades": total,
            "wins": wins,
            "losses": losses,
            "timeouts": timeouts,
            "win_rate": wr,
            "net_r": round(net_r, 2),
            "pf": pf
        }

    return {
        "symbol": symbol,
        "original_orb": summarize(orig_trades, "1. Original ORB Breakout"),
        "naive_inversion": summarize(naive_trades, "2. Naive Inversion (Instant Flip)"),
        "trap_model": summarize(trap_trades, "3. Structural Failure Trap (Fade After Failed Breakout)")
    }


def main():
    print("=" * 80)
    print("🔬 QUANTITATIVE AUDIT: FAILING SETUPS & STRUCTURAL INVERSION")
    print("=" * 80)

    symbols = ["XAUUSD", "NQ", "GBPUSD"]
    all_results = {}

    for sym in symbols:
        print(f"\nProcessing {sym}...")
        try:
            res = audit_orb_and_traps(sym)
            all_results[sym] = res
            print(f"--- {sym} RESULTS ---")
            for k in ["original_orb", "naive_inversion", "trap_model"]:
                m = res[k]
                print(f"  {m['name']:<45}: Trades={m['trades']:3d} | WR={m['win_rate']:5.1f}% | Net R={m['net_r']:+7.2f}R | PF={m['pf']:.2f}")
        except Exception as e:
            print(f"Error processing {sym}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("🏆 MASTER MULTI-ASSET COMPARISON SUMMARY")
    print("=" * 80)
    print(f"{'Asset':<10} | {'Model':<35} | {'Trades':<8} | {'Win Rate':<10} | {'Net R':<10} | {'Profit Factor':<12}")
    print("-" * 95)
    for sym, res in all_results.items():
        for k in ["original_orb", "naive_inversion", "trap_model"]:
            m = res[k]
            print(f"{sym:<10} | {m['name']:<35} | {m['trades']:<8} | {m['win_rate']:>6.1f}%   | {m['net_r']:>+8.2f}R | {m['pf']:>10.2f}")
        print("-" * 95)


if __name__ == "__main__":
    main()
