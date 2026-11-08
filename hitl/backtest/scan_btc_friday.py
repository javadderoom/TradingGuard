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

def run_screener_scan():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return

    sym = "BTCUSD"
    # We will test key session checkpoints and also scan each hour of Friday Nov 06
    # Let's inspect the 3 primary sessions first:
    sessions = [
        {"name": "London Open (10:00 Broker / 11:30 Tehran)", "dt": datetime.datetime(2026, 11, 6, 10, 0), "hour": 10},
        {"name": "NY Open (15:00 Broker / 16:30 Tehran)", "dt": datetime.datetime(2026, 11, 6, 15, 0), "hour": 15},
        {"name": "NY Silver Bullet (17:00 Broker / 18:30 Tehran)", "dt": datetime.datetime(2026, 11, 6, 17, 0), "hour": 17},
    ]

    print("=" * 80)
    print("SCANNING PRIMARY SESSIONS ON BTCUSD - FRIDAY NOV 06, 2026")
    print("=" * 80)

    for s in sessions:
        dt = s["dt"]
        bars_5m = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M5, dt, 120))
        bars_1h = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_H1, dt, 120))
        bars_1d = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_D1, dt, 60))
        bars_15m = _convert_records(mt5.copy_rates_from(sym, mt5.TIMEFRAME_M15, dt, 120))

        res = screen_ict_session(
            bars_5m=bars_5m,
            bars_1h=bars_1h,
            symbol=sym,
            session_hour=s["hour"],
            bars_1m=None,
            bars_1d=bars_1d
        )
        print(f"\n[{s['name']}]")
        print(f"  Price at T: {bars_5m[-1]['close']:.2f}")
        print(f"  Setup Detected: {res.get('has_setup')} | Type: {res.get('setup_type')} | Arch: {res.get('archetype_id')}")
        if res.get('has_setup'):
            print(f"  Details: {res}")

    print("\n" + "=" * 80)
    print("SCANNING ALL CLOSED M5 BARS ON FRIDAY NOV 06, 2026 (00:00 - 23:55)")
    print("=" * 80)

    t_start = datetime.datetime(2026, 11, 6, 0, 0)
    t_end = datetime.datetime(2026, 11, 6, 23, 55)
    all_m5 = _convert_records(mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, t_start, t_end + datetime.timedelta(minutes=5)))

    detected_setups = []
    for i, bar in enumerate(all_m5):
        bar_dt = datetime.datetime.fromtimestamp(bar['time'])
        # Extract 120 M5 bars up to bar_dt
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
        if res.get("has_setup") and res.get("setup_type") != "NONE":
            detected_setups.append({
                "bar_time": bar_dt,
                "price": bar['close'],
                "result": res
            })

    print(f"\nTotal setups detected throughout the day: {len(detected_setups)}")
    for d in detected_setups:
        r = d["result"]
        print(f"Time: {d['bar_time']} | Close: {d['price']:.2f} | Setup: {r.get('setup_type')} | Arch: {r.get('archetype_id')} | Entry: {r.get('entry_price')} | SL: {r.get('stop_loss')}")

    mt5.shutdown()

if __name__ == "__main__":
    run_screener_scan()
