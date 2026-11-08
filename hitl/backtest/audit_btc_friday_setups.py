import sys
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.data_feed import _convert_records
from hitl.setup_registry import setup_registry
from hitl.backtest.evaluator import evaluate_council_decision

def audit_btc_friday():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return

    sym = "BTCUSD"
    t_start = datetime.datetime(2026, 11, 6, 0, 0)
    t_end = datetime.datetime(2026, 11, 6, 23, 55)

    # Fetch all M5 and M1 bars for the day and following hours
    all_m5 = _convert_records(mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, t_start, t_end + datetime.timedelta(minutes=5)))
    print(f"Total M5 bars on Friday Nov 06: {len(all_m5)}")

    trades = []
    active_trade_until = 0 # epoch timestamp when active trade exits

    for i, bar in enumerate(all_m5):
        bar_epoch = bar['time']
        bar_dt = datetime.datetime.fromtimestamp(bar_epoch)

        # Skip if a position is currently open
        if bar_epoch < active_trade_until:
            continue

        bars_5m = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M5, bar_dt, 120))
        bars_1h = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_H1, bar_dt, 120))
        bars_1d = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_D1, bar_dt, 60))

        if not (bars_5m and bars_1h and bars_1d):
            continue

        res = screen_ict_session(
            bars_5m=bars_5m,
            bars_1h=bars_1h,
            symbol=sym,
            session_hour=bar_dt.hour,
            bars_1m=None,
            bars_1d=bars_1d
        )

        if not res.get("has_setup") or res.get("setup_type") == "NONE":
            continue

        arch_id = res.get("archetype_id")
        setup_type = res.get("setup_type")
        entry_p = res.get("entry_ref")
        sl_p = res.get("sl_ref")

        if not (entry_p and sl_p):
            continue

        # Forward M1 evaluation (up to 8 hours ahead)
        forward_m1 = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, bar_dt + datetime.timedelta(hours=8), 480))
        forward_window = [b for b in forward_m1 if b['time'] > bar_epoch][:480]

        if not forward_window:
            continue

        is_buy = "BULLISH" in setup_type or "LONG" in setup_type
        direction = "BUY" if is_buy else "SELL"
        risk_pts = abs(entry_p - sl_p)

        target_rr = res.get("recommended_target_rr", 3.5)
        tp_p = entry_p + (target_rr * risk_pts) if is_buy else entry_p - (target_rr * risk_pts)

        decision_dict = {
            "decision": direction,
            "entry": round(entry_p, 2),
            "sl": round(sl_p, 2),
            "tp": round(tp_p, 2),
            "lot": 0.01
        }

        eval_res = evaluate_council_decision(
            decision_dict=decision_dict,
            forward_m1_bars=forward_window,
            symbol=sym,
            slippage_pts=0.0,
            ttl_minutes=60
        )

        status = eval_res["status"]
        pnl = eval_res["realized_pnl_usd"]
        rr = eval_res.get("rr_realized", 0.0)

        trade_info = {
            "signal_time": bar_dt,
            "archetype_id": arch_id,
            "setup_type": setup_type,
            "direction": direction,
            "entry": entry_p,
            "sl": sl_p,
            "tp": tp_p,
            "risk_pts": risk_pts,
            "risk_usd": risk_pts * 0.01,
            "status": status,
            "realized_pnl_usd": pnl,
            "rr_realized": rr,
            "notes": eval_res.get("notes", "")
        }
        trades.append(trade_info)

        rr_str = f"{rr:+.2f}R" if rr is not None else "N/A"
        print(f"[{bar_dt.strftime('%H:%M')}] {setup_type} ({arch_id}) | Dir: {direction} | Entry: {entry_p:.2f} | SL: {sl_p:.2f} | TP: {tp_p:.2f} | Risk: ${risk_pts*0.01:.2f} | Status: {status} | PnL: ${pnl:+.2f} ({rr_str})")

        # If filled, advance active_trade_until to exit minute
        if status in ("WIN", "LOSS", "BREAKEVEN"):
            exit_min = eval_res.get("exit_minute", 60)
            fill_min = eval_res.get("fill_minute", 0)
            active_trade_until = bar_epoch + (exit_min * 60)
        elif status == "EXPIRED":
            # order waited fill_timeout_bars (12 bars * 5m = 60m)
            active_trade_until = bar_epoch + (12 * 5 * 60)

    print("\n" + "=" * 80)
    print("FRIDAY NOV 06, 2026 - BTCUSD CONTINUOUS SCREENER SUMMARY")
    print("=" * 80)
    total_trades = len(trades)
    filled = [t for t in trades if t["status"] in ("WIN", "LOSS", "BREAKEVEN")]
    wins = [t for t in filled if t["status"] == "WIN"]
    losses = [t for t in filled if t["status"] == "LOSS"]
    bes = [t for t in filled if t["status"] == "BREAKEVEN"]
    expired = [t for t in trades if t["status"] == "EXPIRED"]

    net_pnl = sum(t["realized_pnl_usd"] for t in trades)
    net_r = sum(t["rr_realized"] for t in trades if t["rr_realized"] is not None)

    print(f"Total Signals Generated: {total_trades}")
    print(f"Filled Trades: {len(filled)} (Wins: {len(wins)}, Losses: {len(losses)}, BE: {len(bes)}, Expired: {len(expired)})")
    if filled:
        wr = len(wins) / len(filled) * 100
        print(f"Win Rate: {wr:.1f}%")
    print(f"Net Realized PnL: ${net_pnl:+.2f}")
    print(f"Net Realized R: {net_r:+.2f}R")

    mt5.shutdown()
    return trades

if __name__ == "__main__":
    audit_btc_friday()
