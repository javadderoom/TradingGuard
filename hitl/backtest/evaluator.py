"""
TradingGuard HITL - Backtest Execution & Watchdog Evaluator
Replays forward M1 bars to simulate exact order fills, 45-minute TTL expirations,
Watchdog ATR momentum spike cancellations, and hard SL/TP trade outcomes.
"""

from typing import Dict, Any, List, Optional


def _calculate_atr_m1(bars: List[Dict[str, Any]], period: int = 14) -> float:
    if len(bars) < period:
        return 1.0
    tr_list = []
    for i in range(1, len(bars)):
        h = bars[i]['high']
        l = bars[i]['low']
        c_prev = bars[i-1]['close']
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        tr_list.append(tr)
    return sum(tr_list[-period:]) / period if tr_list else 1.0


def get_default_broker_spread(symbol: str) -> float:
    """Returns conservative institutional broker spread in price points."""
    sym = symbol.upper()
    if "XAU" in sym:
        return 0.15          # $0.15 spread on Gold
    elif "XAG" in sym:
        return 0.030         # 3.0 cents spread on Silver ($1.50 on 0.01 lot)
    elif "EUR" in sym:
        return 0.00018       # 1.8 pips on EURUSD
    elif "GBP" in sym:
        return 0.00025       # 2.5 pips on GBPUSD
    return 0.00020


def evaluate_council_decision(
    decision_dict: Dict[str, Any],
    forward_m1_bars: List[Dict[str, Any]],
    symbol: str = "XAUUSD",
    spread_pts: Optional[float] = None
) -> Dict[str, Any]:
    """
    Evaluates the CIO Council decision against forward M1 price action.
    Returns:
    {
        'status': 'WIN' | 'LOSS' | 'EXPIRED' | 'CANCELLED_WATCHDOG' | 'STAND_ASIDE' | 'OPEN_AT_END',
        'realized_pnl_usd': float,
        'fill_minute': int or None,
        'exit_minute': int or None,
        'rr_realized': float or None,
        'notes': str
    }
    """
    decision = decision_dict.get("decision", "STAND_ASIDE")
    
    if decision == "STAND_ASIDE":
        # Calculate market trend after stand aside
        if forward_m1_bars:
            start_p = forward_m1_bars[0]['open']
            max_p = max(b['high'] for b in forward_m1_bars[:120])
            min_p = min(b['low'] for b in forward_m1_bars[:120])
            spread_range = max_p - min_p
            if "EUR" in symbol.upper() or "GBP" in symbol.upper():
                range_str = f"{spread_range * 10000:.1f} pips ({spread_range:.5f})"
            else:
                range_str = f"{spread_range:.2f} pts"
            return {
                "status": "STAND_ASIDE",
                "realized_pnl_usd": 0.0,
                "fill_minute": None,
                "exit_minute": None,
                "rr_realized": None,
                "notes": f"Stand aside executed. 2h price range was {range_str}."
            }
        return {
            "status": "STAND_ASIDE",
            "realized_pnl_usd": 0.0,
            "fill_minute": None,
            "exit_minute": None,
            "rr_realized": None,
            "notes": "Stand aside executed."
        }

    entry = decision_dict.get("entry")
    sl = decision_dict.get("sl")
    tp = decision_dict.get("tp")
    lot = decision_dict.get("lot", 0.01)

    if not (entry and sl and tp):
        return {
            "status": "INVALID_PARAMS",
            "realized_pnl_usd": 0.0,
            "fill_minute": None,
            "exit_minute": None,
            "rr_realized": None,
            "notes": "Missing entry/sl/tp parameters in CIO directive."
        }

    is_buy = "BUY" in decision.upper()
    if "XAU" in symbol.upper():
        pip_val = 1.0       # 0.01 lot = $1.00/point ($1/dollar)
        val_fmt = ".2f"
    elif "XAG" in symbol.upper():
        pip_val = 50.0      # 0.01 lot = 50 oz -> $50.00/point ($0.50/cent)
        val_fmt = ".3f"
    elif "EUR" in symbol.upper() or "GBP" in symbol.upper():
        pip_val = 1000.0    # 0.01 lot = $0.10/pip (1000x)
        val_fmt = ".5f"
    else:
        pip_val = 1.0
        val_fmt = ".2f"

    # Risk Check
    price_risk_usd = abs(entry - sl) * pip_val
    if price_risk_usd > 17.0:
        price_risk_usd = 17.0  # Hard ceiling enforcement ($17.00)

    is_filled = False
    fill_idx = None
    active_sl = sl
    is_be_active = False
    sl_fmt = f"{sl:{val_fmt}}"
    tp_fmt = f"{tp:{val_fmt}}"

    spread = spread_pts if spread_pts is not None else get_default_broker_spread(symbol)

    # Step through forward M1 bars
    recent_m1_history = []

    for idx, bar in enumerate(forward_m1_bars):
        recent_m1_history.append(bar)

        if not is_filled:
            # 1. Inactivity TTL Check (75 Minutes)
            if idx >= 75:
                return {
                    "status": "EXPIRED",
                    "realized_pnl_usd": 0.0,
                    "fill_minute": None,
                    "exit_minute": idx,
                    "rr_realized": None,
                    "notes": f"75m TTL expired without fill. Order cancelled safely."
                }

            # 2. Watchdog Momentum Radar Check (Adverse Candle Spike)
            if len(recent_m1_history) >= 15:
                atr = _calculate_atr_m1(recent_m1_history)
                candle_body = abs(bar['close'] - bar['open'])
                is_adverse = (bar['close'] < bar['open']) if is_buy else (bar['close'] > bar['open'])
                
                # Calibrate per RULE-METALS-011: 3.5x ATR for Precious Metals, 2.0x for Forex
                is_metal = ("XAU" in symbol.upper() or "XAG" in symbol.upper())
                spike_mult = 3.5 if is_metal else 2.0
                if is_adverse and candle_body >= (spike_mult * atr):
                    # Check distance to entry
                    dist_to_entry = abs(bar['close'] - entry)
                    if dist_to_entry <= (3.0 * atr):
                        return {
                            "status": "CANCELLED_WATCHDOG",
                            "realized_pnl_usd": 0.0,
                            "fill_minute": None,
                            "exit_minute": idx,
                            "rr_realized": None,
                            "notes": f"Watchdog detected sharp adverse spike ({candle_body:.2f} >= {spike_mult}xATR {spike_mult*atr:.2f}). Order auto-cancelled."
                        }

            # 3. Check Fill (Realistic Bid/Ask Spread Simulation)
            # BUY orders fill at ASK = Bid + Spread
            if is_buy and (bar['low'] + spread) <= entry:
                is_filled = True
                fill_idx = idx
            # SELL orders fill at BID
            elif (not is_buy) and bar['high'] >= entry:
                is_filled = True
                fill_idx = idx

        else:
            # Filled! Monitor for SL or TP with Spread Dynamics (Pure Target / Stop - No Breakeven Choking)
            if is_buy:
                # BUY Position: Closed at BID
                if bar['low'] <= sl:
                    loss_amount = -min(17.0, price_risk_usd)
                    # Target Optimization Metric: Record peak excursion before stopping out
                    mfe_price = max(b['high'] for b in forward_m1_bars[fill_idx:idx+1])
                    max_fav_dist = max(0.0, mfe_price - entry)
                    max_rr = round(max_fav_dist * pip_val / max(0.1, price_risk_usd), 2)
                    unit_scale = 10000.0 if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else 1.0
                    unit_name = "pips" if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else "pts"
                    ext_units = max_fav_dist * unit_scale
                    
                    target_opt = {
                        "planned_tp": tp,
                        "planned_rr": round(abs(tp - entry) * pip_val / max(0.1, price_risk_usd), 2),
                        "mfe_price": round(mfe_price, 5 if "EUR" in symbol.upper() or "GBP" in symbol.upper() else 2),
                        "max_rr_potential": max_rr,
                        "extension_beyond_tp": 0.0,
                        "capture_efficiency_pct": 0.0,
                        "excursion_before_sl_units": round(ext_units, 1)
                    }
                    notes_extra = f" (Peak excursion reached {mfe_price:{val_fmt}} / 1:{max_rr:.2f} R:R before reversal)" if max_rr >= 1.0 else ""
                    return {
                        "status": "LOSS",
                        "realized_pnl_usd": round(loss_amount, 2),
                        "fill_minute": fill_idx,
                        "exit_minute": idx,
                        "rr_realized": -1.0,
                        "target_optimization": target_opt,
                        "notes": f"Hit Stop Loss at {sl_fmt}. Realized loss strictly capped at ${abs(loss_amount):.2f}.{notes_extra}"
                    }
                elif bar['high'] >= tp:
                    reward_amount = abs(tp - entry) * pip_val
                    rr = reward_amount / max(0.1, price_risk_usd)
                    # Target Optimization Engine: Calculate full run-out beyond initial target
                    subsequent_bars = forward_m1_bars[fill_idx:]
                    mfe_price = max(b['high'] for b in subsequent_bars)
                    max_fav_dist = max(0.0, mfe_price - entry)
                    max_rr = round(max_fav_dist * pip_val / max(0.1, price_risk_usd), 2)
                    ext_dist = max(0.0, mfe_price - tp)
                    unit_scale = 10000.0 if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else 1.0
                    unit_name = "pips" if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else "pts"
                    ext_units = ext_dist * unit_scale
                    eff_pct = round((abs(tp - entry) / max(0.00001, max_fav_dist)) * 100, 1) if max_fav_dist > 0 else 100.0
                    left_on_table = round(max(0.0, (max_rr - rr) * price_risk_usd), 2)

                    target_opt = {
                        "planned_tp": tp,
                        "planned_rr": round(rr, 2),
                        "mfe_price": round(mfe_price, 5 if "EUR" in symbol.upper() or "GBP" in symbol.upper() else 2),
                        "max_rr_potential": max_rr,
                        "extension_beyond_tp": round(ext_units, 1),
                        "capture_efficiency_pct": eff_pct,
                        "left_on_table_usd": left_on_table
                    }
                    return {
                        "status": "WIN",
                        "realized_pnl_usd": round(reward_amount, 2),
                        "fill_minute": fill_idx,
                        "exit_minute": idx,
                        "rr_realized": round(rr, 2),
                        "target_optimization": target_opt,
                        "notes": f"Hit Take Profit at {tp_fmt}! Realized: +${reward_amount:.2f} (R:R 1:{rr:.2f}). Market extended to {mfe_price:{val_fmt}} (Peak R:R 1:{max_rr:.2f}, +{ext_units:.1f} {unit_name} beyond target, Efficiency: {eff_pct}%)."
                    }
            else:
                # SELL Position: Closed at ASK = BID + Spread
                if (bar['high'] + spread) >= sl:
                    loss_amount = -min(17.0, price_risk_usd)
                    # Target Optimization Metric: Record peak excursion before stopping out
                    mfe_price = min(b['low'] for b in forward_m1_bars[fill_idx:idx+1])
                    max_fav_dist = max(0.0, entry - (mfe_price + spread))
                    max_rr = round(max_fav_dist * pip_val / max(0.1, price_risk_usd), 2)
                    unit_scale = 10000.0 if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else 1.0
                    unit_name = "pips" if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else "pts"
                    ext_units = max_fav_dist * unit_scale
                    
                    target_opt = {
                        "planned_tp": tp,
                        "planned_rr": round(abs(entry - tp) * pip_val / max(0.1, price_risk_usd), 2),
                        "mfe_price": round(mfe_price, 5 if "EUR" in symbol.upper() or "GBP" in symbol.upper() else 2),
                        "max_rr_potential": max_rr,
                        "extension_beyond_tp": 0.0,
                        "capture_efficiency_pct": 0.0,
                        "excursion_before_sl_units": round(ext_units, 1)
                    }
                    notes_extra = f" (Peak excursion reached {mfe_price:{val_fmt}} / 1:{max_rr:.2f} R:R before reversal)" if max_rr >= 1.0 else ""
                    return {
                        "status": "LOSS",
                        "realized_pnl_usd": round(loss_amount, 2),
                        "fill_minute": fill_idx,
                        "exit_minute": idx,
                        "rr_realized": -1.0,
                        "target_optimization": target_opt,
                        "notes": f"Hit Stop Loss (Ask {bar['high'] + spread:{val_fmt}} >= SL {sl_fmt}). Realized loss strictly capped at ${abs(loss_amount):.2f}.{notes_extra}"
                    }
                elif (bar['low'] + spread) <= tp:
                    reward_amount = abs(entry - tp) * pip_val
                    rr = reward_amount / max(0.1, price_risk_usd)
                    # Target Optimization Engine: Calculate full run-out beyond initial target
                    subsequent_bars = forward_m1_bars[fill_idx:]
                    mfe_price = min(b['low'] for b in subsequent_bars)
                    max_fav_dist = max(0.0, entry - (mfe_price + spread))
                    max_rr = round(max_fav_dist * pip_val / max(0.1, price_risk_usd), 2)
                    ext_dist = max(0.0, tp - (mfe_price + spread))
                    unit_scale = 10000.0 if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else 1.0
                    unit_name = "pips" if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else "pts"
                    ext_units = ext_dist * unit_scale
                    eff_pct = round((abs(entry - tp) / max(0.00001, max_fav_dist)) * 100, 1) if max_fav_dist > 0 else 100.0
                    left_on_table = round(max(0.0, (max_rr - rr) * price_risk_usd), 2)

                    target_opt = {
                        "planned_tp": tp,
                        "planned_rr": round(rr, 2),
                        "mfe_price": round(mfe_price, 5 if "EUR" in symbol.upper() or "GBP" in symbol.upper() else 2),
                        "max_rr_potential": max_rr,
                        "extension_beyond_tp": round(ext_units, 1),
                        "capture_efficiency_pct": eff_pct,
                        "left_on_table_usd": left_on_table
                    }
                    return {
                        "status": "WIN",
                        "realized_pnl_usd": round(reward_amount, 2),
                        "fill_minute": fill_idx,
                        "exit_minute": idx,
                        "rr_realized": round(rr, 2),
                        "target_optimization": target_opt,
                        "notes": f"Hit Take Profit at {tp_fmt}! Realized: +${reward_amount:.2f} (R:R 1:{rr:.2f}). Market extended to {mfe_price:{val_fmt}} (Peak R:R 1:{max_rr:.2f}, +{ext_units:.1f} {unit_name} beyond target, Efficiency: {eff_pct}%)."
                    }
                    reward_amount = abs(entry - tp) * pip_val
                    rr = reward_amount / max(0.1, price_risk_usd)
                    # Target Optimization Engine: Calculate full run-out beyond initial target
                    subsequent_bars = forward_m1_bars[fill_idx:]
                    mfe_price = min(b['low'] for b in subsequent_bars)
                    max_fav_dist = max(0.0, entry - (mfe_price + spread))
                    max_rr = round(max_fav_dist * pip_val / max(0.1, price_risk_usd), 2)
                    ext_dist = max(0.0, tp - (mfe_price + spread))
                    unit_scale = 10000.0 if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else 1.0
                    unit_name = "pips" if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else "pts"
                    ext_units = ext_dist * unit_scale
                    eff_pct = round((abs(entry - tp) / max(0.00001, max_fav_dist)) * 100, 1) if max_fav_dist > 0 else 100.0
                    left_on_table = round(max(0.0, (max_rr - rr) * price_risk_usd), 2)

                    target_opt = {
                        "planned_tp": tp,
                        "planned_rr": round(rr, 2),
                        "mfe_price": round(mfe_price, 5 if "EUR" in symbol.upper() or "GBP" in symbol.upper() else 2),
                        "max_rr_potential": max_rr,
                        "extension_beyond_tp": round(ext_units, 1),
                        "capture_efficiency_pct": eff_pct,
                        "left_on_table_usd": left_on_table
                    }
                    return {
                        "status": "WIN",
                        "realized_pnl_usd": round(reward_amount, 2),
                        "fill_minute": fill_idx,
                        "exit_minute": idx,
                        "rr_realized": round(rr, 2),
                        "target_optimization": target_opt,
                        "notes": f"Hit Take Profit (Ask cleared TP {tp_fmt})! Realized: +${reward_amount:.2f} (R:R 1:{rr:.2f}). Market extended to {mfe_price:{val_fmt}} (Peak R:R 1:{max_rr:.2f}, +{ext_units:.1f} {unit_name} beyond target, Efficiency: {eff_pct}%)."
                    }

    # If still open by end of window
    if is_filled:
        last_close = forward_m1_bars[-1]['close']
        pnl = ((last_close - entry) if is_buy else (entry - last_close)) * pip_val
        return {
            "status": "OPEN_AT_END",
            "realized_pnl_usd": round(pnl, 2),
            "fill_minute": fill_idx,
            "exit_minute": len(forward_m1_bars),
            "rr_realized": round(pnl / max(0.1, price_risk_usd), 2),
            "notes": f"Position remained open at end of evaluation window. Floating PnL: ${pnl:.2f}."
        }

    return {
        "status": "EXPIRED",
        "realized_pnl_usd": 0.0,
        "fill_minute": None,
        "exit_minute": len(forward_m1_bars),
        "rr_realized": None,
        "notes": "Unfilled by end of data window."
    }
