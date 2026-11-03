"""
TradingGuard HITL - Order Parameter Generator for Qualified Setups (Sep 07 - Sep 18, 2026)
Calculates exact Entry, SL, TP, and TTL for all qualified setups using Council Playbook rules.
"""

import sys
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.data_feed import _convert_records
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.forex_cross_pair import detect_forex_smt_divergence

def main():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return

    sym = "GBPUSD_o"
    eur_sym = "EURUSD_o"

    # Qualified sessions list from screener
    candidates = [
        {"date": "2026-09-07", "session": "London Open", "broker_time": datetime.datetime(2026, 9, 7, 10, 0), "hour": 10},
        {"date": "2026-09-07", "session": "NY Open",     "broker_time": datetime.datetime(2026, 9, 7, 15, 0), "hour": 15},
        {"date": "2026-09-08", "session": "London Open", "broker_time": datetime.datetime(2026, 9, 8, 10, 0), "hour": 10},
        {"date": "2026-09-08", "session": "NY Open",     "broker_time": datetime.datetime(2026, 9, 8, 15, 0), "hour": 15},
        {"date": "2026-09-09", "session": "NY Open",     "broker_time": datetime.datetime(2026, 9, 9, 15, 0), "hour": 15},
        {"date": "2026-09-11", "session": "London Open", "broker_time": datetime.datetime(2026, 9, 11, 10, 0), "hour": 10},
        {"date": "2026-09-14", "session": "London Open", "broker_time": datetime.datetime(2026, 9, 14, 10, 0), "hour": 10},
        {"date": "2026-09-14", "session": "NY Open",     "broker_time": datetime.datetime(2026, 9, 14, 15, 0), "hour": 15},
        {"date": "2026-09-16", "session": "NY Open",     "broker_time": datetime.datetime(2026, 9, 16, 15, 0), "hour": 15},
        {"date": "2026-09-17", "session": "London Open", "broker_time": datetime.datetime(2026, 9, 17, 10, 0), "hour": 10},
        {"date": "2026-09-17", "session": "NY Open",     "broker_time": datetime.datetime(2026, 9, 17, 15, 0), "hour": 15},
    ]

    orders = []

    for c in candidates:
        dt = c["broker_time"]
        r5_gbp = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M5, dt, 85))
        r1_gbp = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_H1, dt, 20))
        r5_eur = _convert_records(mt5.copy_rates_from(eur_sym, mt5.TIMEFRAME_M5, dt, 85))

        smt_info = detect_forex_smt_divergence(r5_eur, r5_gbp, c["hour"])
        res = screen_ict_session(r5_gbp, r1_gbp, "GBPUSD", c["hour"], smt_info=smt_info)

        if not res.get("has_setup"):
            continue

        reason = res.get("reason", "")
        entry = float(res.get("entry_ref", 0.0))
        if entry <= 0:
            continue

        setup_type = res.get("setup_type", "")

        # Determine direction
        is_bullish = ("BULLISH" in setup_type or "BULLISH" in reason or "Break above" in reason or "Swept London Range Low" in reason or "Swept Asian Range Low" in reason)
        is_bearish = ("BEARISH" in setup_type or "BEARISH" in reason or "Break below" in reason or "Swept London Range High" in reason or "Swept Asian Range High" in reason)

        # Get session high/low for targets and stop loss
        recent_lows = [b['low'] for b in r5_gbp[-24:]]
        recent_highs = [b['high'] for b in r5_gbp[-24:]]
        swing_low = min(recent_lows)
        swing_high = max(recent_highs)

        pip = 0.00010

        if is_bullish:
            order_type = "BUY_LIMIT"
            # Stop loss 1.0 pip below swing low
            sl = round(swing_low - (1.0 * pip), 5)
            risk = entry - sl
            if risk <= 0.00040:
                sl = round(entry - 0.00075, 5)
                risk = 0.00075
            # Target at least 2.5R and anchor to swing high
            tp = round(entry + max(2.5 * risk, swing_high - entry), 5)
            if tp - entry < 0.00180:
                tp = round(entry + 0.00220, 5)
        elif is_bearish:
            order_type = "SELL_LIMIT"
            # Stop loss 1.0 pip above swing high
            sl = round(swing_high + (1.0 * pip), 5)
            risk = sl - entry
            if risk <= 0.00040:
                sl = round(entry + 0.00075, 5)
                risk = 0.00075
            tp = round(entry - max(2.5 * risk, entry - swing_low), 5)
            if entry - tp < 0.00180:
                tp = round(entry - 0.00220, 5)
        else:
            continue

        orders.append({
            "id": f"ORD-{c['date'][5:].replace('-', '')}-{c['session'][:3].upper()}",
            "symbol": "AUTO",
            "type": order_type,
            "trigger_time": dt.strftime("%Y.%m.%d %H:%M:00"),
            "entry": round(entry, 5),
            "sl": round(sl, 5),
            "tp": round(tp, 5),
            "lot": 0.01,
            "ttl": 360,
            "reason": reason
        })

    print(f"\nGenerated {len(orders)} Valid Institutional Orders:")
    print("=" * 110)
    for o in orders:
        risk = abs(o['sl'] - o['entry'])
        reward = abs(o['tp'] - o['entry'])
        rr = reward / risk if risk > 0 else 0
        print(f"{o['id']:16s} | {o['type']:10s} | {o['trigger_time']} | Entry: {o['entry']:.5f} | SL: {o['sl']:.5f} | TP: {o['tp']:.5f} | R:R: {rr:.2f}R")
        print(f"   Reason: {o['reason'][:85]}...")

    # Write to CSV
    csv_lines = ["ID,Symbol,Type,TriggerTime,Entry,SL,TP,Lot,TTL\n"]
    for o in orders:
        csv_lines.append(f"{o['id']},{o['symbol']},{o['type']},{o['trigger_time']},{o['entry']:.5f},{o['sl']:.5f},{o['tp']:.5f},{o['lot']:.2f},{o['ttl']}\n")

    common_path = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\Common\Files\orders_schedule.csv")
    local_path = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB\MQL5\Files\orders_schedule.csv")

    common_path.write_text("".join(csv_lines), encoding="utf-8")
    local_path.write_text("".join(csv_lines), encoding="utf-8")
    print(f"\nSuccessfully wrote {len(orders)} orders to:")
    print(f" - {common_path}")
    print(f" - {local_path}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
