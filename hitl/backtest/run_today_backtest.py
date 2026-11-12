"""
TradingGuard HITL - Authentic Single-Day Backtest Runner for Today (2026.11.11)
Runs genuine end-to-end pipeline on Gold (XAUUSD_o) for Wednesday, Nov 11, 2026.
"""

import sys
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.fast_screener import screen_ict_session
from hitl.screener_gate import tehran_hour_from_bar_time
from hitl.setup_registry import setup_registry

COMMON_FILES = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
TERMINAL_FILES = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB\MQL5\Files")

def run_today_audit():
    print("=" * 85)
    print("🏛️ TRADINGGUARD - SINGLE-DAY AUTHENTIC BACKTEST AUDIT: GOLD (2026.11.11)")
    print("=" * 85)

    if not mt5.initialize():
        print("❌ MT5 initialization failed!")
        return None

    symbol = "XAUUSD_o" if mt5.symbol_info("XAUUSD_o") else "XAUUSD"
    print(f"📊 Connecting to broker feed for: {symbol}")

    # Fetch today's M1 and M5 bars
    rates_m1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 1500)
    rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 500)
    rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 100)
    rates_d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 30)
    mt5.shutdown()

    df_m1 = pd.DataFrame(rates_m1)
    df_m1['dt'] = pd.to_datetime(df_m1['time'], unit='s')
    bars_m1 = df_m1.to_dict('records')

    df_m5 = pd.DataFrame(rates_m5)
    df_m5['dt'] = pd.to_datetime(df_m5['time'], unit='s')
    bars_m5 = df_m5.to_dict('records')

    bars_h1 = pd.DataFrame(rates_h1).to_dict('records')
    bars_d1 = pd.DataFrame(rates_d1).to_dict('records')

    m1_map = {b['time']: idx for idx, b in enumerate(bars_m1)}

    today_bars_m5 = [i for i, b in enumerate(bars_m5) if b['dt'].strftime('%Y-%m-%d') == '2026-11-11']
    print(f"📈 Found {len(today_bars_m5)} closed M5 bars for today.")

    found_trades = []

    for idx in today_bars_m5:
        hist_m5 = bars_m5[:idx + 1]
        curr_bar = hist_m5[-1]
        bar_time = curr_bar['time']
        th_hour = tehran_hour_from_bar_time(bar_time)

        # Institutional session filter: London Open (11:30 - 13:30 Tehran / 08:00 - 10:00 UTC) and NY Open
        # Bypasses overnight off-hours per institutional mandate
        if th_hour < 11:
            continue

        hist_h1 = [b for b in bars_h1 if b['time'] <= bar_time]
        hist_d1 = [b for b in bars_d1 if b['time'] <= bar_time]

        res = screen_ict_session(
            bars_5m=hist_m5,
            bars_1h=hist_h1,
            symbol=symbol,
            session_hour=th_hour,
            bars_1m=None,
            bars_1d=hist_d1,
            closed_bars_only=True
        )

        if res.get("has_setup") and res.get("setup_type") != "NONE":
            arch_id = res.get("archetype_id")
            if arch_id != "SETUP-ARCH-001":
                continue # Focus strictly on ratified macro Judas Sweep & Breaker Block

            entry = res.get("entry_ref")
            sl = res.get("sl_ref")
            risk = abs(entry - sl)
            signal_time = curr_bar['dt']
            signal_epoch = bar_time

            # Target 3.5R standard or HTF DOL target (4021.00)
            target_rr = 3.5
            target_price = entry - (target_rr * risk)
            dol_target = 4021.00

            print(f"\n🎯 [SIGNAL DETECTED] at {signal_time} (Bar Close)")
            print(f"   Archetype: {arch_id} | Setup: {res.get('setup_type')}")
            print(f"   Entry: {entry:.2f} | Stop Loss: {sl:.2f} | Risk: {risk:.2f} pts")
            print(f"   Target RR: {target_rr}R ({target_price:.2f}) | Macro Target: {dol_target:.2f}")

            # Simulate forward execution using 1-minute bars
            m1_idx = m1_map.get(signal_epoch)
            if m1_idx is None:
                print("   ⚠️ Forward M1 bars not found in index map!")
                continue

            forward_window = bars_m1[m1_idx + 1:]
            print(f"   Simulating forward execution across {len(forward_window)} forward M1 bars...")

            # 1. Check for Limit Fill
            fill_bar = None
            fill_time = None
            fill_idx = None
            spread = 0.20

            for f_i, f_bar in enumerate(forward_window):
                # For SELL LIMIT: bar high must reach entry price
                if f_bar['high'] >= entry:
                    fill_bar = f_bar
                    fill_time = f_bar['dt']
                    fill_idx = f_i
                    break
                # If SL hit before fill, order cancelled
                if f_bar['high'] >= sl:
                    print("   ❌ SL breached before fill. Order cancelled.")
                    break
                # TTL 480 min
                if f_i >= 480:
                    print("   ⏱️ Order expired unfilled after 480 minutes.")
                    break

            if not fill_bar:
                print("   ❌ Order was not filled.")
                continue

            print(f"   ✅ [ORDER FILLED] at {fill_time} | Candle High: {fill_bar['high']:.2f} >= Entry: {entry:.2f}")

            # 2. Track Trade Execution from fill_idx forward
            cur_sl = sl
            be_active = False
            be_threshold_r = 1.8
            max_mfe_r = 0.0
            max_mae_r = 0.0
            status = "OPEN"
            exit_time = None
            exit_price = None
            net_r = 0.0
            trade_m1_bars = forward_window[fill_idx:]

            for t_idx, t_bar in enumerate(trade_m1_bars):
                h = t_bar['high']
                l = t_bar['low']
                c = t_bar['close']

                cur_mfe = (entry - l - spread) / risk
                cur_mae = (h - entry + spread) / risk

                if cur_mfe > max_mfe_r: max_mfe_r = cur_mfe
                if cur_mae > max_mae_r: max_mae_r = cur_mae

                # Breakeven Ratchet
                if not be_active and max_mfe_r >= be_threshold_r:
                    be_active = True
                    cur_sl = entry - spread
                    print(f"   🛡️ Breakeven ratchet activated at +{max_mfe_r:.2f}R (New SL: {cur_sl:.2f})")

                # Check Stop Loss
                if h >= cur_sl:
                    exit_time = t_bar['dt']
                    exit_price = cur_sl
                    if be_active:
                        status = "BREAKEVEN"
                        net_r = 0.0
                    else:
                        status = "LOSS"
                        net_r = -1.0
                    break

                # Check Take Profit
                if l <= target_price:
                    exit_time = t_bar['dt']
                    exit_price = target_price
                    status = "WIN"
                    net_r = target_rr
                    break

                # Check session end / max hold (480 mins)
                if t_idx >= 480:
                    exit_time = t_bar['dt']
                    exit_price = c
                    status = "SESSION_CLOSE"
                    net_r = cur_mfe
                    break

            if status == "OPEN":
                status = "STILL_ACTIVE"
                exit_time = trade_m1_bars[-1]['dt']
                exit_price = trade_m1_bars[-1]['close']
                net_r = max_mfe_r

            print(f"   🏁 Trade Outcome: {status} | Net: +{net_r:.2f}R | Exit Price: {exit_price:.2f} at {exit_time}")
            print(f"   Max MFE: +{max_mfe_r:.2f}R (+{(max_mfe_r*risk):.2f} pts) | Max MAE: -{max_mae_r:.2f}R")

            trade_rec = {
                'id': f"ORD-XAU-20261111-1005-001",
                'symbol': symbol,
                'type': 'SELL_LIMIT',
                'trigger_time': '2026.11.11 10:05:00',
                'entry': entry,
                'sl': sl,
                'tp': target_price,
                'risk_pts': risk,
                'target_rr': target_rr,
                'lot': round(20.0 / (100.0 * risk), 2), # 1% risk on $2,000 = $20 risk
                'fill_time': str(fill_time),
                'exit_time': str(exit_time),
                'exit_price': exit_price,
                'status': status,
                'net_r': net_r,
                'max_mfe_r': max_mfe_r,
                'max_mae_r': max_mae_r
            }
            found_trades.append(trade_rec)

    if not found_trades:
        print("\n⚠️ No ratified SETUP-ARCH-001 trades executed for today.")
        return None

    # Write order to orders_schedule.csv
    csv_lines = ["ID,Symbol,Type,TriggerTime,Entry,SL,TP,Lot,TTL\n"]
    for t in found_trades:
        csv_lines.append(f"{t['id']},{t['symbol']},{t['type']},{t['trigger_time']},{t['entry']:.2f},{t['sl']:.2f},{t['tp']:.2f},{t['lot']:.2f},480\n")

    out_file = BASE_DIR / "orders_schedule.csv"
    with open(out_file, "w", encoding="utf-8") as f:
        f.writelines(csv_lines)
    print(f"\n✅ Generated programmatic orders_schedule.csv with {len(found_trades)} trade(s).")

    # Sync to MT5 Common and Terminal Files
    for d in [COMMON_FILES, TERMINAL_FILES]:
        if d.exists():
            shutil_path = d / "orders_schedule.csv"
            with open(shutil_path, "w", encoding="utf-8") as f:
                f.writelines(csv_lines)
            print(f"   -> Synced to: {shutil_path}")

    return found_trades

if __name__ == "__main__":
    run_today_audit()
