"""
TradingGuard HITL - Institutional Quantitative Backtest Engine Base
Zero-lookahead, closed-bars-only simulator with authentic broker mechanics:
- Spread: Gold $0.22, GBPUSD 0.6 pip, NQ 1.0 pt
- Commission: $0.10 per 0.01 lot ($10.00 / lot)
- Slippage: Gold $0.05, GBPUSD 0.1 pip, NQ 0.25 pt
- SL-first collision resolution on closed M1 bars
- Breakeven ratchet dynamic management
- Dynamic Seasonal DST Session Clock (London BST/GMT, NY EDT/EST, Tehran UTC+3:30)
"""

import sys
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np

TZ_LONDON = ZoneInfo("Europe/London")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_UTC = datetime.timezone.utc


def get_session_times(d: datetime.date) -> Dict[str, Any]:
    lon_local = datetime.datetime(d.year, d.month, d.day, 8, 0, tzinfo=TZ_LONDON)
    lon_utc = lon_local.astimezone(TZ_UTC)

    ny_local = datetime.datetime(d.year, d.month, d.day, 8, 0, tzinfo=TZ_NEW_YORK)
    ny_utc = ny_local.astimezone(TZ_UTC)

    nyse_local = datetime.datetime(d.year, d.month, d.day, 9, 30, tzinfo=TZ_NEW_YORK)
    nyse_utc = nyse_local.astimezone(TZ_UTC)

    return {
        "date": d,
        "is_uk_dst": bool(lon_local.dst()),
        "is_us_dst": bool(ny_local.dst()),
        "london_open_utc": lon_utc,
        "ny_open_utc": ny_utc,
        "nyse_open_utc": nyse_utc,
        "london_open_hour": lon_utc.hour,
        "ny_open_hour": ny_utc.hour,
        "nyse_open_hour": nyse_utc.hour,
        "nyse_open_minute": nyse_utc.minute,
    }


def load_and_resample(parquet_path: str, symbol: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Loads M1 parquet and builds clean M5, H1, D1 bars with strict boundary alignment."""
    df_m1 = pd.read_parquet(parquet_path)
    if 'time' in df_m1.columns:
        df_m1['timestamp'] = df_m1['time']
    else:
        df_m1['timestamp'] = df_m1.index.astype(np.int64) // 10**9

    df_m1['dt'] = pd.to_datetime(df_m1['timestamp'], unit='s', utc=True)
    df_m1 = df_m1.sort_values('timestamp').reset_index(drop=True)

    # Resample M5
    df_m1['m5_bucket'] = df_m1['timestamp'] // 300 * 300
    df_m5 = df_m1.groupby('m5_bucket').agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        tick_volume=('tick_volume', 'sum')
    ).reset_index().rename(columns={'m5_bucket': 'timestamp'})
    df_m5['dt'] = pd.to_datetime(df_m5['timestamp'], unit='s', utc=True)
    df_m5['time'] = df_m5['timestamp']
    df_m5 = df_m5.sort_values('timestamp').reset_index(drop=True)

    # Resample H1
    df_m1['h1_bucket'] = df_m1['timestamp'] // 3600 * 3600
    df_h1 = df_m1.groupby('h1_bucket').agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        tick_volume=('tick_volume', 'sum')
    ).reset_index().rename(columns={'h1_bucket': 'timestamp'})
    df_h1['dt'] = pd.to_datetime(df_h1['timestamp'], unit='s', utc=True)
    df_h1['time'] = df_h1['timestamp']
    df_h1 = df_h1.sort_values('timestamp').reset_index(drop=True)

    # Resample D1 (UTC midnight)
    df_m1['d1_bucket'] = df_m1['timestamp'] // 86400 * 86400
    df_d1 = df_m1.groupby('d1_bucket').agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        tick_volume=('tick_volume', 'sum')
    ).reset_index().rename(columns={'d1_bucket': 'timestamp'})
    df_d1['dt'] = pd.to_datetime(df_d1['timestamp'], unit='s', utc=True)
    df_d1['time'] = df_d1['timestamp']
    df_d1 = df_d1.sort_values('timestamp').reset_index(drop=True)

    # Indicators on H1: EMA50 and 5-bar lag slope
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df_h1['ema50_slope5'] = df_h1['ema50'] - df_h1['ema50'].shift(5)

    # ATR14 on M5
    high_low = df_m5['high'] - df_m5['low']
    high_close = (df_m5['high'] - df_m5['close'].shift(1)).abs()
    low_close = (df_m5['low'] - df_m5['close'].shift(1)).abs()
    tr_m5 = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df_m5['atr14'] = tr_m5.rolling(14).mean().bfill()
    df_m5['ema20'] = df_m5['close'].ewm(span=20, adjust=False).mean()

    # ADR14 on D1
    hl_d = df_d1['high'] - df_d1['low']
    hc_d = (df_d1['high'] - df_d1['close'].shift(1)).abs()
    lc_d = (df_d1['low'] - df_d1['close'].shift(1)).abs()
    tr_d = pd.concat([hl_d, hc_d, lc_d], axis=1).max(axis=1)
    df_d1['adr14'] = tr_d.shift(1).rolling(14).mean().bfill()

    return df_m1, df_m5, df_h1, df_d1


def simulate_order_execution(
    df_m1: pd.DataFrame,
    start_m1_idx: int,
    decision: str,  # 'BUY' or 'SELL'
    entry: float,
    sl: float,
    target_rr: float,
    symbol: str,
    spread: float,
    slippage: float,
    commission_per_001_lot: float = 0.10,
    be_ratchet_rr: Optional[float] = 1.8,
    ttl_minutes: int = 60,
    lot: float = 0.01
) -> Dict[str, Any]:
    """
    Simulates forward order execution bar-by-bar on closed M1 bars.
    Strict rules:
    - SL-first collision resolution if both SL and TP are touched in same bar -> LOSS
    - Limit order fill: BUY at Ask = Low + Spread <= Entry; SELL at Bid = High >= Entry
    - Slippage applied: BUY fills at Entry + Slippage; SELL at Entry - Slippage
    - Exits evaluated against active SL/TP in force at start of bar
    - Breakeven ratchet armed at end of bar for subsequent bars
    - Commission deducted from every closed trade
    """
    is_buy = (decision.upper() == "BUY")

    if "XAU" in symbol.upper():
        pip_val = 1.0       # 0.01 lot = $1.00 / point
    elif "GBP" in symbol.upper() or "EUR" in symbol.upper():
        pip_val = 1000.0    # 0.01 lot = $0.10 / pip ($1000/unit)
    elif "NQ" in symbol.upper() or "SPX" in symbol.upper() or "YM" in symbol.upper():
        pip_val = 0.10      # 0.10 lot = $0.10 / point
    else:
        pip_val = 1.0

    commission_total = commission_per_001_lot * (lot / 0.01)

    effective_entry = entry + slippage if is_buy else entry - slippage
    risk_pts = abs(effective_entry - sl)
    if risk_pts <= 0:
        return {"status": "INVALID_RISK", "realized_r": 0.0, "realized_pnl_usd": 0.0, "notes": "Risk <= 0"}

    tp = effective_entry + (risk_pts * target_rr) if is_buy else effective_entry - (risk_pts * target_rr)
    price_risk_usd = risk_pts * pip_val

    is_filled = False
    fill_idx = None
    active_sl = sl
    is_be_active = False

    n_bars = len(df_m1)
    end_idx = min(n_bars, start_m1_idx + 1440)  # max 24 hours simulation window

    # Slice forward M1
    forward_highs = df_m1['high'].values[start_m1_idx:end_idx]
    forward_lows = df_m1['low'].values[start_m1_idx:end_idx]
    forward_closes = df_m1['close'].values[start_m1_idx:end_idx]
    forward_times = df_m1['timestamp'].values[start_m1_idx:end_idx]

    for rel_idx in range(len(forward_highs)):
        h = forward_highs[rel_idx]
        l = forward_lows[rel_idx]
        c = forward_closes[rel_idx]
        t = forward_times[rel_idx]

        if not is_filled:
            # Check TTL
            if rel_idx >= ttl_minutes:
                return {
                    "status": "EXPIRED",
                    "realized_r": 0.0,
                    "realized_pnl_usd": 0.0,
                    "is_realized": True,
                    "fill_minute": None,
                    "exit_minute": rel_idx,
                    "notes": f"TTL {ttl_minutes}m expired without fill"
                }

            # Check limit fill with spread
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

                # SL-first collision resolution: touching both SL and TP in the same bar is a LOSS
                if hit_sl and hit_tp:
                    loss_amount = -price_risk_usd - commission_total
                    return {
                        "status": "LOSS_COLLISION",
                        "realized_r": -1.0,
                        "realized_pnl_usd": round(loss_amount, 2),
                        "is_realized": True,
                        "fill_minute": fill_idx,
                        "exit_minute": rel_idx,
                        "notes": "Both SL and TP touched on same M1 bar (SL-first loss)"
                    }

                if hit_sl:
                    if is_be_active:
                        be_pnl = spread * pip_val - commission_total
                        realized_r = round(be_pnl / price_risk_usd, 3)
                        return {
                            "status": "BREAKEVEN",
                            "realized_r": realized_r,
                            "realized_pnl_usd": round(be_pnl, 2),
                            "is_realized": True,
                            "fill_minute": fill_idx,
                            "exit_minute": rel_idx,
                            "notes": f"Hit Breakeven SL"
                        }
                    else:
                        loss_amount = -price_risk_usd - commission_total
                        return {
                            "status": "LOSS",
                            "realized_r": -1.0,
                            "realized_pnl_usd": round(loss_amount, 2),
                            "is_realized": True,
                            "fill_minute": fill_idx,
                            "exit_minute": rel_idx,
                            "notes": f"Hit Stop Loss"
                        }

                elif hit_tp:
                    reward_amount = (tp - effective_entry) * pip_val - commission_total
                    realized_r = round(reward_amount / price_risk_usd, 3)
                    return {
                        "status": "WIN",
                        "realized_r": realized_r,
                        "realized_pnl_usd": round(reward_amount, 2),
                        "is_realized": True,
                        "fill_minute": fill_idx,
                        "exit_minute": rel_idx,
                        "notes": f"Hit Take Profit at {target_rr}R"
                    }

                # Breakeven Ratchet Check (updates at end of bar for next bars)
                if be_ratchet_rr is not None and not is_be_active:
                    current_mfe = h - effective_entry
                    if current_mfe >= (be_ratchet_rr * risk_pts):
                        is_be_active = True
                        active_sl = effective_entry + spread

            else:
                # SELL side
                hit_sl = (h + spread >= active_sl)
                hit_tp = (l + spread <= tp)

                # SL-first collision resolution
                if hit_sl and hit_tp:
                    loss_amount = -price_risk_usd - commission_total
                    return {
                        "status": "LOSS_COLLISION",
                        "realized_r": -1.0,
                        "realized_pnl_usd": round(loss_amount, 2),
                        "is_realized": True,
                        "fill_minute": fill_idx,
                        "exit_minute": rel_idx,
                        "notes": "Both SL and TP touched on same M1 bar (SL-first loss)"
                    }

                if hit_sl:
                    if is_be_active:
                        be_pnl = spread * pip_val - commission_total
                        realized_r = round(be_pnl / price_risk_usd, 3)
                        return {
                            "status": "BREAKEVEN",
                            "realized_r": realized_r,
                            "realized_pnl_usd": round(be_pnl, 2),
                            "is_realized": True,
                            "fill_minute": fill_idx,
                            "exit_minute": rel_idx,
                            "notes": "Hit Breakeven SL"
                        }
                    else:
                        loss_amount = -price_risk_usd - commission_total
                        return {
                            "status": "LOSS",
                            "realized_r": -1.0,
                            "realized_pnl_usd": round(loss_amount, 2),
                            "is_realized": True,
                            "fill_minute": fill_idx,
                            "exit_minute": rel_idx,
                            "notes": "Hit Stop Loss"
                        }

                elif hit_tp:
                    reward_amount = (effective_entry - tp) * pip_val - commission_total
                    realized_r = round(reward_amount / price_risk_usd, 3)
                    return {
                        "status": "WIN",
                        "realized_r": realized_r,
                        "realized_pnl_usd": round(reward_amount, 2),
                        "is_realized": True,
                        "fill_minute": fill_idx,
                        "exit_minute": rel_idx,
                        "notes": f"Hit Take Profit at {target_rr}R"
                    }

                # Breakeven Ratchet Check (updates at end of bar for next bars)
                if be_ratchet_rr is not None and not is_be_active:
                    current_mfe = effective_entry - (l + spread)
                    if current_mfe >= (be_ratchet_rr * risk_pts):
                        is_be_active = True
                        active_sl = effective_entry - spread

    return {
        "status": "OPEN_AT_END",
        "realized_r": 0.0,
        "realized_pnl_usd": 0.0,
        "is_realized": False,
        "notes": "Unclosed after 24h"
    }


def compute_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes comprehensive institutional quantitative metrics."""
    if not trades:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "be": 0, "expired": 0,
            "win_rate_pct": 0.0, "net_r": 0.0, "realized_net_usd": 0.0,
            "profit_factor": 0.0, "ev_r": 0.0, "max_drawdown_r": 0.0,
            "max_drawdown_usd": 0.0, "t_stat": 0.0, "p_val": 1.0
        }

    closed_trades = [t for t in trades if t["status"] in ("WIN", "LOSS", "LOSS_COLLISION", "BREAKEVEN")]
    expired_count = sum(1 for t in trades if t["status"] == "EXPIRED")
    n = len(closed_trades)
    if n == 0:
        return {
            "total_trades": len(trades), "closed_trades": 0, "wins": 0, "losses": 0, "be": 0, "expired": expired_count,
            "win_rate_pct": 0.0, "net_r": 0.0, "realized_net_usd": 0.0,
            "profit_factor": 0.0, "ev_r": 0.0, "max_drawdown_r": 0.0,
            "max_drawdown_usd": 0.0, "t_stat": 0.0, "p_val": 1.0
        }

    wins = sum(1 for t in closed_trades if t["status"] == "WIN")
    losses = sum(1 for t in closed_trades if "LOSS" in t["status"])
    be = sum(1 for t in closed_trades if t["status"] == "BREAKEVEN")
    win_rate = (wins / n) * 100.0

    r_values = [t["realized_r"] for t in closed_trades]
    usd_values = [t["realized_pnl_usd"] for t in closed_trades]

    net_r = sum(r_values)
    net_usd = sum(usd_values)

    gross_profit_usd = sum(p for p in usd_values if p > 0)
    gross_loss_usd = abs(sum(p for p in usd_values if p < 0))
    pf = (gross_profit_usd / gross_loss_usd) if gross_loss_usd > 0 else (99.0 if gross_profit_usd > 0 else 0.0)

    ev_r = net_r / n

    # Drawdown in R and USD
    cum_r = np.cumsum(r_values)
    peak_r = np.maximum.accumulate(cum_r)
    dd_r = peak_r - cum_r
    max_dd_r = float(np.max(dd_r)) if len(dd_r) > 0 else 0.0

    cum_usd = np.cumsum(usd_values)
    peak_usd = np.maximum.accumulate(cum_usd)
    dd_usd = peak_usd - cum_usd
    max_dd_usd = float(np.max(dd_usd)) if len(dd_usd) > 0 else 0.0

    # T-statistic on R distribution
    mean_r = np.mean(r_values)
    std_r = np.std(r_values, ddof=1) if n > 1 else 0.0
    if std_r > 0 and n > 1:
        t_stat = float(mean_r / (std_r / np.sqrt(n)))
        # approximate two-tailed p-value via normal distribution if scipy not available
        from math import erf
        p_val = 2.0 * (1.0 - 0.5 * (1.0 + erf(abs(t_stat) / np.sqrt(2.0))))
    else:
        t_stat = 0.0
        p_val = 1.0

    return {
        "total_setups": len(trades),
        "closed_trades": n,
        "wins": wins,
        "losses": losses,
        "breakevens": be,
        "expired": expired_count,
        "win_rate_pct": round(win_rate, 2),
        "net_r": round(net_r, 2),
        "realized_net_usd": round(net_usd, 2),
        "profit_factor": round(pf, 2),
        "ev_r": round(ev_r, 3),
        "max_drawdown_r": round(max_dd_r, 2),
        "max_drawdown_usd": round(max_dd_usd, 2),
        "t_stat": round(t_stat, 2),
        "p_val": round(p_val, 4)
    }
