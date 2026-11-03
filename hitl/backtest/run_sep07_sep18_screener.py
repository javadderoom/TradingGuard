"""
TradingGuard HITL - 2-Week Screener (Sep 07 - Sep 18, 2026)
Screens all 10 trading days (London Open & NY Open) for GBPUSD & EURUSD
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
from hitl.backtest.session_clock import get_session_times_for_date

SYMBOLS = ["GBPUSD", "EURUSD"]

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return

    # Map symbols
    symbols_map = {}
    for s in SYMBOLS:
        for suffix in ["_o", "", ".pro", "m"]:
            cand = s + suffix
            if mt5.symbol_info(cand) is not None:
                symbols_map[s] = cand
                break
    print(f"Mapped symbols: {symbols_map}")

    start_date = datetime.date(2026, 9, 7)
    end_date = datetime.date(2026, 9, 18)

    cur = start_date
    sessions = []
    while cur <= end_date:
        if cur.weekday() not in (5, 6):
            s_times = get_session_times_for_date(cur)
            sessions.append({
                "date": cur,
                "session_name": "London Open",
                "datetime": s_times["london"]["tehran_time"].replace(tzinfo=None),
                "broker_time": datetime.datetime(cur.year, cur.month, cur.day, 10, 0), # 07:00 UTC = 10:00 Broker (UTC+3)
                "hour": s_times["london"]["hour_tehran"],
                "utc_str": s_times["london"]["utc_str"]
            })
            sessions.append({
                "date": cur,
                "session_name": "NY Open",
                "datetime": s_times["new_york"]["tehran_time"].replace(tzinfo=None),
                "broker_time": datetime.datetime(cur.year, cur.month, cur.day, 15, 0), # 12:00 UTC = 15:00 Broker (UTC+3)
                "hour": s_times["new_york"]["hour_tehran"],
                "utc_str": s_times["new_york"]["utc_str"]
            })
        cur += datetime.timedelta(days=1)

    print(f"\nTotal sessions to screen: {len(sessions)}")
    print("=" * 80)

    qualified_sessions = []

    for idx, s in enumerate(sessions, 1):
        dt_broker = s["broker_time"]
        dt_tehran = s["datetime"]
        session_name = s["session_name"]
        date_str = s["date"].strftime("%Y-%m-%d")

        print(f"\n[{idx:02d}/{len(sessions)}] {date_str} | {session_name} ({s['utc_str']} | {dt_broker.strftime('%H:%M')} Broker)")

        rates_5m = {}
        rates_1h = {}
        for sym in SYMBOLS:
            real_sym = symbols_map[sym]
            r5 = mt5.copy_rates_from(real_sym, mt5.TIMEFRAME_M5, dt_broker, 85)
            r1 = mt5.copy_rates_from(real_sym, mt5.TIMEFRAME_H1, dt_broker, 20)
            rates_5m[sym] = _convert_records(r5)
            rates_1h[sym] = _convert_records(r1)

        smt_info = detect_forex_smt_divergence(rates_5m.get("EURUSD", []), rates_5m.get("GBPUSD", []), s["hour"])

        for sym in ["GBPUSD"]:
            res = screen_ict_session(rates_5m[sym], rates_1h[sym], sym, s["hour"], smt_info=smt_info)
            curr_price = rates_5m[sym][-1]['close'] if rates_5m[sym] else 0.0
            if res.get("has_setup"):
                print(f"  ⚡ {sym} @ {curr_price:.5f} -> QUALIFIED SETUP: {res.get('reason')}")
                qualified_sessions.append({
                    "date": date_str,
                    "session": session_name,
                    "broker_time": dt_broker,
                    "symbol": sym,
                    "price": curr_price,
                    "setup": res
                })
            else:
                print(f"  • {sym} @ {curr_price:.5f} -> STAND ASIDE: {res.get('reason')}")

    print("\n" + "=" * 80)
    print(f"SUMMARY: {len(qualified_sessions)} / {len(sessions)} sessions qualified for Council deliberation.")
    for q in qualified_sessions:
        print(f" - {q['date']} {q['session']} ({q['broker_time'].strftime('%H:%M')} Broker): {q['setup'].get('reason')}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
