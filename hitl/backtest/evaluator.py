"""
TradingGuard HITL - Backtest Execution & Watchdog Evaluator.

CANONICAL SIMULATOR: this is the one simulator all backtest runners should
use (evaluate_council_decision). The other forward sims in the repo were NOT
rewritten and still disagree with it — they are follow-on work, not the
reference: autonomous_setup_miner.simulate_trade (SL-first, 90-min TTL,
no commission, SELL side ignores spread on SL/TP), structural_origin_engine
and master_production_portfolio_audit (TP-first, 480-min hold cap, spread
0.00006 FX / 0.20 metals vs 0.00018/0.00025 FX / 0.15 Gold here), and the
per-season audit copies of the miner sim.

Canonical rules (see evaluate_council_decision docstring):
  * Closed bars only: forward_m1_bars must start AFTER the signal bar
    closes (see data_feed.get_forward_m1_bars(closed_bars_only=True)).
  * SL-first: a bar touching both SL and TP is a LOSS (conservative — with
    M1 OHLC the intrabar order is unknowable, and assuming the favourable
    outcome inflates win rate).
  * Spread is symmetric in bid/ask terms: M1 bars are bid; ask = bid +
    spread. BUY fills at ask, exits at bid; SELL fills at bid, exits at
    ask. (The apparent asymmetry — BUY TP on raw high, SELL TP on low +
    spread — is correct bid/ask mechanics, not a bug.)
  * Commission is deducted from every closed trade; slippage worsens the
    fill price. Both are explicit parameters, defaults documented below.
  * TTL: CANONICAL_TTL_MINUTES = 75 (inactivity, unfilled orders).
    Other TTLs still in the code, NOT unified here (follow-on):
    smc_tools plan ttl 360, miner sim ttl 90, origin/master 480-min hold
    cap. The evaluator's own docstring previously said 45 min while the
    code used 75; 75 is the value the code actually enforced.
  * OPEN_AT_END is a floating, unrealised PnL — never count it as realised.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

POLICY_FILE = Path(__file__).resolve().parent.parent / "memory" / "optimal_trade_management_policy.json"
# Canonical inactivity TTL for unfilled limit orders (minutes). See module
# docstring for the other, not-yet-unified TTLs in the repo.
CANONICAL_TTL_MINUTES = 75

# Default round-trip commission per 0.01 lot, in USD. The repo has no
# broker commission table; the only concrete figure in the code is the
# live engine's estimate in hitl/mt5_engine.py:296
# (commission_est = $0.10 * lot / BASE_LOT, i.e. $0.10 per 0.01 lot),
# so that is the default. Actual broker commission is charged by MT5
# (DEAL_COMMISSION) and may differ — pass the real figure when known.
DEFAULT_COMMISSION_USD_PER_001_LOT = 0.10


def get_optimal_trade_management(symbol: str, session_label: str, setup_arch_id: Optional[str] = None) -> Tuple[float, Optional[float]]:
    """Retrieves empirical (Target R:R, Breakeven R:R) for a given symbol, session, and archetype."""
    sym_clean = "XAUUSD" if "XAU" in symbol.upper() else ("EURUSD" if "EUR" in symbol.upper() else ("GBPUSD" if "GBP" in symbol.upper() else "XAUUSD"))
    
    if POLICY_FILE.exists():
        try:
            with open(POLICY_FILE, "r", encoding="utf-8") as f:
                policy = json.load(f)
                sym_policy = policy.get(sym_clean, {})
                if setup_arch_id and setup_arch_id in sym_policy:
                    match_arch = sym_policy[setup_arch_id]
                    return float(match_arch.get("target_rr", 3.5)), match_arch.get("breakeven_rr")
                
                s = (session_label or "").lower()
                if "silver bullet" in s:
                    sess_key = "NY_Silver_Bullet"
                elif "london" in s:
                    sess_key = "London_Post_Open" if "post" in s else ("London_Pre_Open" if "pre" in s else "London_Open")
                elif "ny" in s or "new york" in s:
                    sess_key = "NY_Post_Open" if "post" in s else ("NY_Pre_Open" if "pre" in s else "NY_Open")
                else:
                    sess_key = "London_Open"

                match = sym_policy.get(sess_key)
                if match:
                    return float(match.get("target_rr", 3.5)), match.get("breakeven_rr")
        except Exception:
            pass
    return 3.5, 2.0


def _calculate_atr_m1(bars: List[Dict[str, Any]], period: int = 14, symbol: str = "XAUUSD") -> float:
    # Fallback ATR when there are too few bars to compute one. Was a flat
    # 1.0 for every asset: ~10,000 pips on FX, which effectively disabled
    # the watchdog on short histories. Scaled per asset (M1 ATR scale).
    sym = symbol.upper()
    is_index = "NQ" in sym or "NAS" in sym or "US100" in sym
    fallback_atr = 10.0 if is_index else (25.0 if "BTC" in sym else (1.0 if "XAU" in sym else (0.05 if "XAG" in sym else 0.0005)))
    if len(bars) < period:
        return fallback_atr
    tr_list = []
    for i in range(1, len(bars)):
        h = bars[i]['high']
        l = bars[i]['low']
        c_prev = bars[i-1]['close']
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        tr_list.append(tr)
    return sum(tr_list[-period:]) / period if tr_list else fallback_atr


def get_default_broker_spread(symbol: str) -> float:
    """Returns conservative institutional broker spread in price points."""
    sym = symbol.upper()
    if "NQ" in sym or "NAS" in sym or "US100" in sym:
        return 1.0           # 1.0 point spread on NQ ($0.10 on 0.10 lot)
    elif "BTC" in sym:
        return 1.50          # $1.50 spread on BTCUSD ($0.015 at 0.01 lot)
    elif "XAU" in sym:
        return 0.15          # $0.15 spread on Gold
    elif "XAG" in sym:
        return 0.030         # 3.0 cents spread on Silver ($1.50 on 0.01 lot)
    elif "EUR" in sym:
        return 0.00018       # 1.8 pips on EURUSD
    elif "GBP" in sym:
        return 0.00025       # 2.5 pips on GBPUSD
    return 0.00020


def is_trade_realized(result: Dict[str, Any]) -> bool:
    """True iff a trade result's PnL is realised cash, not floating.

    Uses the evaluator's ``is_realized`` flag when present (Pack 4:
    OPEN_AT_END returns False, everything else True). Falls back to
    ``status != 'OPEN_AT_END'`` for legacy dicts that predate the flag.
    """
    if "is_realized" in result:
        return bool(result["is_realized"])
    return result.get("status") != "OPEN_AT_END"


def summarize_pnl(
    records: List[Dict[str, Any]],
    pnl_key: str = "realized_pnl_usd",
) -> Dict[str, Any]:
    """Split a list of trade/session records into realised vs unrealised PnL.

    Pack 6: every PnL sum in the repo used to add ``realized_pnl_usd``
    over ALL records, which counted OPEN_AT_END floating mark-to-market
    as realised profit. Pooled across the 38 council ledgers that
    inflated +$38.83 closed to +$127.48; worst single file
    (metals_basket_xau_xag_audit_20261101_075029) reported +$8.05
    for a closed net of -$37.60. Callers must use ``realized_net_usd``
    (and its gross/profit-factor derivatives) as the headline number
    and show ``unrealized_net_usd`` separately, never summed into it.

    Returns dict with:
      realized_net_usd, realized_gross_profit_usd,
      realized_gross_loss_usd (positive magnitude),
      realized_profit_factor, unrealized_net_usd,
      open_trades (count of unrealised records),
      realized_trades (count of realised records with non-zero PnL
      i.e. closed fills; STAND_ASIDE/EXPIRED records carry 0.0).
    """
    realized = [r for r in records if is_trade_realized(r)]
    unrealized = [r for r in records if not is_trade_realized(r)]

    def _pnl(r: Dict[str, Any]) -> float:
        try:
            return float(r.get(pnl_key, 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    realized_pnls = [_pnl(r) for r in realized]
    gross_profit = sum(p for p in realized_pnls if p > 0)
    gross_loss = abs(sum(p for p in realized_pnls if p < 0))
    return {
        "realized_net_usd": round(sum(realized_pnls), 2),
        "realized_gross_profit_usd": round(gross_profit, 2),
        "realized_gross_loss_usd": round(gross_loss, 2),
        "realized_profit_factor": round(
            gross_profit / gross_loss, 2
        ) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0),
        "unrealized_net_usd": round(sum(_pnl(r) for r in unrealized), 2),
        "open_trades": len(unrealized),
        "realized_trades": len(realized),
    }


def evaluate_council_decision(
    decision_dict: Dict[str, Any],
    forward_m1_bars: List[Dict[str, Any]],
    symbol: str = "XAUUSD",
    spread_pts: Optional[float] = None,
    breakeven_rr: float = 2.0,
    target_rr_cap: float = 3.5,
    commission_usd: Optional[float] = None,
    slippage_pts: float = 0.0,
    ttl_minutes: int = CANONICAL_TTL_MINUTES
) -> Dict[str, Any]:
    """
    Canonical backtest simulator. Evaluates the CIO Council decision
    against forward M1 price action.

    Callers must pass forward_m1_bars starting AFTER the signal bar
    closes (data_feed.get_forward_m1_bars(closed_bars_only=True) does
    this); the first forward bar is the first minute of the next bar.

    Rules:
    * SL-first: if one M1 bar touches both SL and TP, the trade is a
      LOSS. M1 OHLC cannot tell which was touched first, so the
      conservative outcome is the only honest one; TP-first (the old
      behaviour) counts every such bar as a WIN and inflates win rate.
    * Spread: M1 bars are bid; ask = bid + spread. BUY fills at ask
      (low + spread <= entry) and exits at bid; SELL fills at bid
      (high >= entry) and exits at ask (low + spread <= TP,
      high + spread >= SL). Same convention on both sides.
    * Slippage (slippage_pts, price points, default 0.0): worsens the
      fill price — BUY fills at entry + slippage, SELL at entry -
      slippage. PnL and risk are computed from the slipped fill price.
    * Commission (commission_usd, round-trip USD per 0.01 lot, default
      DEFAULT_COMMISSION_USD_PER_001_LOT = $0.10 — see module docstring)
      is deducted from every closed trade (WIN, LOSS, BREAKEVEN),
      scaled by lot: commission_total = commission_usd * (lot / 0.01).
    * Exits are evaluated against the SL/TP levels in force at the START
      of the bar; the breakeven ratchet updates at the END of the bar, for
      subsequent bars. (The old code armed the ratchet from the current
      bar's high and then checked the SL in the same bar, so a bar that
      touched both TP and SL could be converted to a BREAKEVEN on the
      assumption that the high came first — the same unknowable intrabar
      ordering SL-first is meant to remove.)
    * Breakeven: when the ratchet arms, active_sl = entry +/- spread,
      so the BE exit price is spread away from entry in your favour;
      the BE PnL is therefore +spread * pip_val - commission, NOT 0.0.
      (The old code set the SL spread-away from entry and then returned
      PnL 0.0, i.e. it credited neither the spread recovered at the BE
      exit nor the commission paid on it.)
    * TTL: unfilled orders expire after ttl_minutes (default 75, the
      canonical value).
    * OPEN_AT_END is floating, unrealised PnL (is_realized=False) — it
      must never be summed as realised profit.
    * $ PnL is reported at the trade's lot (decision_dict lot, default
      0.01); pip_val is per 0.01 lot, so PnL scales with lot.

    Returns:
    {
        'status': 'WIN' | 'LOSS' | 'BREAKEVEN' | 'EXPIRED' | 'CANCELLED_WATCHDOG' | 'STAND_ASIDE' | 'OPEN_AT_END',
        'realized_pnl_usd': float,   # net of commission/slippage; floating only for OPEN_AT_END
        'is_realized': bool,
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
                "is_realized": True,
                "fill_minute": None,
                "exit_minute": None,
                "rr_realized": None,
                "notes": f"Stand aside executed. 2h price range was {range_str}."
            }
        return {
            "status": "STAND_ASIDE",
            "realized_pnl_usd": 0.0,
            "is_realized": True,
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
            "is_realized": True,
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
    elif "BTC" in symbol.upper():
        pip_val = 0.01      # 0.01 lot = 0.01 BTC -> $0.01/dollar ($1.00 per $100 price move)
        val_fmt = ".2f"
    elif "NQ" in symbol.upper() or "NAS" in symbol.upper() or "US100" in symbol.upper():
        pip_val = 0.10      # 0.10 lot = $0.10/point ($1.00 per 10 points)
        val_fmt = ".1f"
    else:
        pip_val = 1.0
        val_fmt = ".2f"

    # Commission: round-trip, scaled by lot (default $0.10 per 0.01 lot).
    if commission_usd is None:
        commission_usd = DEFAULT_COMMISSION_USD_PER_001_LOT
    commission_total = commission_usd * (lot / 0.01)

    # Slippage worsens the fill price; PnL and risk are computed from the
    # slipped fill price, not the nominal limit price. Default 0.0: no
    # slippage is assumed — set it explicitly when the broker's slippage
    # is known instead of hiding it inside the fill logic.
    effective_entry = entry + slippage_pts if is_buy else entry - slippage_pts

    # Risk Check (from the effective, slipped entry)
    price_risk_usd = abs(effective_entry - sl) * pip_val
    if price_risk_usd > 12.0:
        price_risk_usd = 12.0  # Hard ceiling enforcement ($12.00)

    # Target R:R Realism Cap: Capping fantasy intraday targets (e.g. max 3.5 to 4.0 R:R)
    risk_pts = abs(effective_entry - sl)
    if target_rr_cap and risk_pts > 0:
        if is_buy:
            max_tp = effective_entry + (risk_pts * target_rr_cap)
            if tp > max_tp:
                tp = max_tp
        else:
            min_tp = effective_entry - (risk_pts * target_rr_cap)
            if tp < min_tp:
                tp = min_tp

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
            # 1. Inactivity TTL Check (canonical: CANONICAL_TTL_MINUTES = 75)
            if idx >= ttl_minutes:
                return {
                    "status": "EXPIRED",
                    "realized_pnl_usd": 0.0,
                    "is_realized": True,
                    "fill_minute": None,
                    "exit_minute": idx,
                    "rr_realized": None,
                    "notes": f"{ttl_minutes}m TTL expired without fill. Order cancelled safely."
                }

            # 2. Watchdog Momentum Radar Check (Adverse Candle Spike)
            if len(recent_m1_history) >= 15:
                atr = _calculate_atr_m1(recent_m1_history, symbol=symbol)
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
                            "is_realized": True,
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
            # Filled! Monitor for SL, Breakeven, or TP with Spread Dynamics
            if is_buy:
                # Exits below are evaluated on the SL/TP levels in force
                # at the START of this bar. The breakeven ratchet updates
                # at the END of the bar (step 4, after the exit checks),
                # for subsequent bars — see the docstring.
                # SL-first: if one M1 bar touches both SL and TP, the
                # intrabar order is unknowable, so the trade is a LOSS.
                # (TP-first, the old behaviour, counted every such bar
                # as a WIN.) Spread convention: M1 bars are bid; a long
                # exits at bid, so TP is raw high and SL is raw low.
                hit_sl = bar['low'] <= active_sl
                hit_tp = bar['high'] >= tp
                # 3. Check Stop Loss / Breakeven Hit (checked first)
                if hit_sl:
                    if is_be_active:
                        mfe_full = max(b['high'] for b in forward_m1_bars[fill_idx:idx+1])
                        max_rr = round((mfe_full - entry) * pip_val / max(0.1, price_risk_usd), 2)
                        # BE exit is at active_sl = entry + spread (bid), so
                        # the spread is recovered as gross profit; commission
                        # is then deducted. NOT 0.0 (the old value credited
                        # neither the spread nor the commission).
                        be_pnl = spread * pip_val - commission_total
                        return {
                            "status": "BREAKEVEN",
                            "realized_pnl_usd": round(be_pnl, 2),
                            "is_realized": True,
                            "fill_minute": fill_idx,
                            "exit_minute": idx,
                            "rr_realized": round(be_pnl / max(0.1, price_risk_usd), 2),
                            "notes": f"Breakeven triggered at {active_sl:{val_fmt}} after peak excursion of {mfe_full:{val_fmt}} (1:{max_rr:.2f} R:R). Net PnL ${be_pnl:+.2f} (spread ${spread * pip_val:.2f} - commission ${commission_total:.2f})."
                        }
                    else:
                        loss_amount = -min(12.0, price_risk_usd) - commission_total  # capped risk + commission
                        mfe_full = max(b['high'] for b in forward_m1_bars[fill_idx:idx+1])
                        max_fav_dist = max(0.0, mfe_full - entry)
                        max_rr = round(max_fav_dist * pip_val / max(0.1, price_risk_usd), 2)
                        unit_scale = 10000.0 if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else 1.0
                        unit_name = "pips" if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else "pts"
                        ext_units = max_fav_dist * unit_scale
                        target_opt = {
                            "planned_tp": tp,
                            "planned_rr": round(abs(tp - entry) * pip_val / max(0.1, price_risk_usd), 2),
                            "mfe_price": round(mfe_full, 5 if "EUR" in symbol.upper() or "GBP" in symbol.upper() else 2),
                            "max_rr_potential": max_rr,
                            "extension_beyond_tp": 0.0,
                            "capture_efficiency_pct": 0.0,
                            "excursion_before_sl_units": round(ext_units, 1)
                        }
                        notes_extra = f" (Peak excursion reached {mfe_full:{val_fmt}} / 1:{max_rr:.2f} R:R before reversal)" if max_rr >= 1.0 else ""
                        return {
                            "status": "LOSS",
                            "realized_pnl_usd": round(loss_amount, 2),
                            "is_realized": True,
                            "fill_minute": fill_idx,
                            "exit_minute": idx,
                            "rr_realized": -1.0,
                            "target_optimization": target_opt,
                            "notes": f"Hit Stop Loss at {sl_fmt}. Realized loss ${abs(loss_amount):.2f} (risk capped at $12.00 + commission ${commission_total:.2f}).{notes_extra}"
                        }
                # 2. Check Take Profit Hit (checked second)
                elif hit_tp:
                    reward_amount = abs(tp - effective_entry) * pip_val - commission_total  # net of commission
                    rr = reward_amount / max(0.1, price_risk_usd)
                    subsequent_bars = forward_m1_bars[fill_idx:]
                    full_mfe = max(b['high'] for b in subsequent_bars)
                    max_fav_dist = max(0.0, full_mfe - entry)
                    max_rr = round(max_fav_dist * pip_val / max(0.1, price_risk_usd), 2)
                    ext_dist = max(0.0, full_mfe - tp)
                    unit_scale = 10000.0 if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else 1.0
                    unit_name = "pips" if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else "pts"
                    ext_units = ext_dist * unit_scale
                    eff_pct = round((abs(tp - entry) / max(0.00001, max_fav_dist)) * 100, 1) if max_fav_dist > 0 else 100.0
                    left_on_table = round(max(0.0, (max_rr - rr) * price_risk_usd), 2)

                    target_opt = {
                        "planned_tp": tp,
                        "planned_rr": round(rr, 2),
                        "mfe_price": round(full_mfe, 5 if "EUR" in symbol.upper() or "GBP" in symbol.upper() else 2),
                        "max_rr_potential": max_rr,
                        "extension_beyond_tp": round(ext_units, 1),
                        "capture_efficiency_pct": eff_pct,
                        "left_on_table_usd": left_on_table
                    }
                    return {
                        "status": "WIN",
                        "realized_pnl_usd": round(reward_amount, 2),
                        "is_realized": True,
                        "fill_minute": fill_idx,
                        "exit_minute": idx,
                        "rr_realized": round(rr, 2),
                        "target_optimization": target_opt,
                        "notes": f"Hit Take Profit at {tp_fmt}! Realized: +${reward_amount:.2f} (R:R 1:{rr:.2f}). Market extended to {full_mfe:{val_fmt}} (Peak R:R 1:{max_rr:.2f}, +{ext_units:.1f} {unit_name} beyond target, Efficiency: {eff_pct}%)."
                    }

                # 4. Breakeven ratchet update (end of bar, for subsequent
                # bars). Only reached if this bar hit neither SL nor TP.
                mfe_price = max(b['high'] for b in forward_m1_bars[fill_idx:idx+1])
                curr_fav_dist = max(0.0, mfe_price - entry)
                curr_rr = curr_fav_dist * pip_val / max(0.1, price_risk_usd)
                if breakeven_rr is not None and curr_rr >= breakeven_rr and not is_be_active:
                    is_be_active = True
                    active_sl = entry + spread  # cover broker spread for risk-free scratch

            else:
                # SELL Position: Closed at ASK = BID + Spread
                # Exits below are evaluated on the SL/TP levels in force
                # at the START of this bar; the ratchet updates at the
                # END of the bar (step 4, after the exit checks).
                # SL-first: see BUY branch above. Spread convention: a
                # short exits at ask (bid + spread), so TP is low +
                # spread and SL is high + spread.
                hit_sl = (bar['high'] + spread) >= active_sl
                hit_tp = (bar['low'] + spread) <= tp
                # 3. Check Stop Loss / Breakeven Hit (checked first)
                if hit_sl:
                    if is_be_active:
                        mfe_full = min(b['low'] for b in forward_m1_bars[fill_idx:idx+1])
                        max_rr = round((entry - (mfe_full + spread)) * pip_val / max(0.1, price_risk_usd), 2)
                        # BE exit is at active_sl = entry - spread (ask), so
                        # the spread is recovered as gross profit; commission
                        # is then deducted. NOT 0.0 (see BUY branch).
                        be_pnl = spread * pip_val - commission_total
                        return {
                            "status": "BREAKEVEN",
                            "realized_pnl_usd": round(be_pnl, 2),
                            "is_realized": True,
                            "fill_minute": fill_idx,
                            "exit_minute": idx,
                            "rr_realized": round(be_pnl / max(0.1, price_risk_usd), 2),
                            "notes": f"Breakeven triggered at {active_sl:{val_fmt}} after peak excursion of {mfe_full:{val_fmt}} (1:{max_rr:.2f} R:R). Net PnL ${be_pnl:+.2f} (spread ${spread * pip_val:.2f} - commission ${commission_total:.2f})."
                        }
                    else:
                        loss_amount = -min(12.0, price_risk_usd) - commission_total  # capped risk + commission
                        mfe_full = min(b['low'] for b in forward_m1_bars[fill_idx:idx+1])
                        max_fav_dist = max(0.0, entry - (mfe_full + spread))
                        max_rr = round(max_fav_dist * pip_val / max(0.1, price_risk_usd), 2)
                        unit_scale = 10000.0 if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else 1.0
                        unit_name = "pips" if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else "pts"
                        ext_units = max_fav_dist * unit_scale
                        target_opt = {
                            "planned_tp": tp,
                            "planned_rr": round(abs(entry - tp) * pip_val / max(0.1, price_risk_usd), 2),
                            "mfe_price": round(mfe_full, 5 if "EUR" in symbol.upper() or "GBP" in symbol.upper() else 2),
                            "max_rr_potential": max_rr,
                            "extension_beyond_tp": 0.0,
                            "capture_efficiency_pct": 0.0,
                            "excursion_before_sl_units": round(ext_units, 1)
                        }
                        notes_extra = f" (Peak excursion reached {mfe_full:{val_fmt}} / 1:{max_rr:.2f} R:R before reversal)" if max_rr >= 1.0 else ""
                        return {
                            "status": "LOSS",
                            "realized_pnl_usd": round(loss_amount, 2),
                            "is_realized": True,
                            "fill_minute": fill_idx,
                            "exit_minute": idx,
                            "rr_realized": -1.0,
                            "target_optimization": target_opt,
                            "notes": f"Hit Stop Loss (Ask {bar['high'] + spread:{val_fmt}} >= SL {sl_fmt}). Realized loss ${abs(loss_amount):.2f} (risk capped at $12.00 + commission ${commission_total:.2f}).{notes_extra}"
                        }

                # 2. Check Take Profit Hit (checked second)
                elif hit_tp:
                    reward_amount = abs(effective_entry - tp) * pip_val - commission_total  # net of commission
                    rr = reward_amount / max(0.1, price_risk_usd)
                    subsequent_bars = forward_m1_bars[fill_idx:]
                    full_mfe = min(b['low'] for b in subsequent_bars)
                    max_fav_dist = max(0.0, entry - (full_mfe + spread))
                    max_rr = round(max_fav_dist * pip_val / max(0.1, price_risk_usd), 2)
                    ext_dist = max(0.0, tp - (full_mfe + spread))
                    unit_scale = 10000.0 if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else 1.0
                    unit_name = "pips" if ("EUR" in symbol.upper() or "GBP" in symbol.upper()) else "pts"
                    ext_units = ext_dist * unit_scale
                    eff_pct = round((abs(entry - tp) / max(0.00001, max_fav_dist)) * 100, 1) if max_fav_dist > 0 else 100.0
                    left_on_table = round(max(0.0, (max_rr - rr) * price_risk_usd), 2)

                    target_opt = {
                        "planned_tp": tp,
                        "planned_rr": round(rr, 2),
                        "mfe_price": round(full_mfe, 5 if "EUR" in symbol.upper() or "GBP" in symbol.upper() else 2),
                        "max_rr_potential": max_rr,
                        "extension_beyond_tp": round(ext_units, 1),
                        "capture_efficiency_pct": eff_pct,
                        "left_on_table_usd": left_on_table
                    }
                    return {
                        "status": "WIN",
                        "realized_pnl_usd": round(reward_amount, 2),
                        "is_realized": True,
                        "fill_minute": fill_idx,
                        "exit_minute": idx,
                        "rr_realized": round(rr, 2),
                        "target_optimization": target_opt,
                        "notes": f"Hit Take Profit at {tp_fmt}! Realized: +${reward_amount:.2f} (R:R 1:{rr:.2f}). Market extended to {full_mfe:{val_fmt}} (Peak R:R 1:{max_rr:.2f}, +{ext_units:.1f} {unit_name} beyond target, Efficiency: {eff_pct}%)."
                    }

                # 4. Breakeven ratchet update (end of bar, for subsequent
                # bars). Only reached if this bar hit neither SL nor TP.
                mfe_price = min(b['low'] for b in forward_m1_bars[fill_idx:idx+1])
                curr_fav_dist = max(0.0, entry - (mfe_price + spread))
                curr_rr = curr_fav_dist * pip_val / max(0.1, price_risk_usd)
                if breakeven_rr is not None and curr_rr >= breakeven_rr and not is_be_active:
                    is_be_active = True
                    active_sl = entry - spread  # cover broker spread for risk-free scratch

    # If still open by end of window
    if is_filled:
        last_close = forward_m1_bars[-1]['close']
        pnl = ((last_close - entry) if is_buy else (entry - last_close)) * pip_val
        return {
            # Floating, unrealised PnL. is_realized=False: callers must NOT
            # sum this as realised profit (past reports did exactly that).
            "status": "OPEN_AT_END",
            "realized_pnl_usd": round(pnl, 2),
            "is_realized": False,
            "fill_minute": fill_idx,
            "exit_minute": len(forward_m1_bars),
            "rr_realized": round(pnl / max(0.1, price_risk_usd), 2),
            "notes": f"Position remained open at end of evaluation window. Floating PnL: ${pnl:.2f}."
        }

    return {
        "status": "EXPIRED",
        "realized_pnl_usd": 0.0,
        "is_realized": True,
        "fill_minute": None,
        "exit_minute": len(forward_m1_bars),
        "rr_realized": None,
        "notes": "Unfilled by end of data window."
    }
