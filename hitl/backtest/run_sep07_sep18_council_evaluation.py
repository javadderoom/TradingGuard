"""
TradingGuard HITL - 2-Week Full Council Deliberation (Sep 07 - Sep 18, 2026)
Convenes the full Antigravity AI Council on all candidate sessions.
Writes strictly approved Council orders to orders_schedule.csv.
"""

import sys
import time
import datetime
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.data_feed import HistoricalDataFeed, _convert_records
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.forex_cross_pair import detect_forex_smt_divergence, analyze_cross_pair_symbiosis, format_symbiotic_prompt
from hitl.backtest.council_replay import convene_council_on_historical_dossier

CANDIDATES = [
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

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    feed = HistoricalDataFeed()
    if not feed.engine.ensure_connected():
        print("Failed to connect to MT5")
        return

    sym = "GBPUSD"
    resolved_sym = feed.engine.resolve_symbol(sym)
    resolved_eur = feed.engine.resolve_symbol("EURUSD")

    print("=" * 85)
    print("🏛️ TRADINGGUARD HITL - FULL AI COUNCIL DELIBERATION (SEP 07 - SEP 18, 2026)")
    print(f"Target Symbol: {resolved_sym} | Total Candidate Sessions: {len(CANDIDATES)}")
    print("Mandate: Strict 7-Seat Council Deliberation (Zero Fabrications, CRO Invalidation Veto)")
    print("=" * 85)

    approved_orders = []
    deliberation_log = []

    for idx, c in enumerate(CANDIDATES, 1):
        dt = c["broker_time"]
        sess_name = f"{c['date']} {c['session']}"
        print(f"\n[{idx:02d}/{len(CANDIDATES)}] Convening Council for {sess_name} (Broker Time: {dt})...")

        # 1. Fetch SMT context
        r5_gbp = _convert_records(mt5.copy_rates_from(resolved_sym, mt5.TIMEFRAME_M5, dt, 85))
        r5_eur = _convert_records(mt5.copy_rates_from(resolved_eur, mt5.TIMEFRAME_M5, dt, 85))
        smt_info = detect_forex_smt_divergence(r5_eur, r5_gbp, c["hour"])
        symbiosis_info = analyze_cross_pair_symbiosis(r5_gbp, r5_eur, "GBPUSD", "EURUSD", smt_info)
        symbiosis_prompt = format_symbiotic_prompt(symbiosis_info)

        # 2. Prepare Session Dossier with MTF Chart Images (1D, 1H, 15M, 5M)
        dossier = feed.prepare_session_dossier(sym, dt)
        if not dossier:
            print(f"  ❌ Failed to prepare MTF dossier for {sess_name}")
            continue

        dossier["telemetry_prompt"] = symbiosis_prompt + "\n\n" + dossier.get("telemetry_prompt", "")

        # 3. Deliberate
        t0 = time.time()
        delib = convene_council_on_historical_dossier(dossier)
        elapsed = time.time() - t0

        if not delib:
            print(f"  ⚠️ Council returned empty deliberation ({elapsed:.1f}s). Stand aside.")
            continue

        decision = delib.get("decision", "STAND_ASIDE")
        entry = delib.get("entry")
        sl = delib.get("sl")
        tp = delib.get("tp")
        rr = delib.get("rr")

        deliberation_log.append({
            "session": sess_name,
            "decision": decision,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "rr": rr,
            "elapsed": elapsed
        })

        if decision in ("BUY_LIMIT", "SELL_LIMIT") and entry and sl and tp:
            # Check CRO rules: Min R:R >= 2.5R, risk cap <= $17
            risk_pips = abs(entry - sl) * 10000
            if risk_pips > 17.0:
                print(f"  🛑 CRO VETO: Risk {risk_pips:.1f} pips exceeds 17-pip cap! Overriding to STAND_ASIDE.")
                continue

            calc_rr = abs(tp - entry) / max(0.0001, abs(entry - sl))
            if calc_rr < 2.5:
                print(f"  🛑 CRO VETO: R:R {calc_rr:.2f}R is below institutional 2.5R minimum! Overriding to STAND_ASIDE.")
                continue

            order_id = f"ORD-{c['date'][5:].replace('-', '')}-{c['session'][:3].upper()}"
            approved_orders.append({
                "id": order_id,
                "symbol": "AUTO",
                "type": decision,
                "trigger_time": dt.strftime("%Y.%m.%d %H:%M:00"),
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "lot": 0.01,
                "ttl": 360
            })
            print(f"  ✅ APPROVED [{decision}] @ {entry:.5f} | SL: {sl:.5f} | TP: {tp:.5f} | R:R: {calc_rr:.2f}R ({elapsed:.1f}s)")
        else:
            print(f"  🛡️ STAND ASIDE (Decision: {decision}) ({elapsed:.1f}s)")

    print("\n" + "=" * 85)
    print(f"COUNCIL DELIBERATION COMPLETE: {len(approved_orders)} / {len(CANDIDATES)} Sessions Approved")
    print("=" * 85)

    for o in approved_orders:
        rr = abs(o['tp'] - o['entry']) / abs(o['sl'] - o['entry'])
        print(f" • {o['id']:16s} | {o['type']:10s} | Trigger: {o['trigger_time']} | Entry: {o['entry']:.5f} | SL: {o['sl']:.5f} | TP: {o['tp']:.5f} | {rr:.2f}R")

    # Write approved orders to orders_schedule.csv
    csv_lines = ["ID,Symbol,Type,TriggerTime,Entry,SL,TP,Lot,TTL\n"]
    for o in approved_orders:
        csv_lines.append(f"{o['id']},{o['symbol']},{o['type']},{o['trigger_time']},{o['entry']:.5f},{o['sl']:.5f},{o['tp']:.5f},{o['lot']:.2f},{o['ttl']}\n")

    common_path = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\Common\Files\orders_schedule.csv")
    local_path = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB\MQL5\Files\orders_schedule.csv")

    common_path.write_text("".join(csv_lines), encoding="utf-8")
    local_path.write_text("".join(csv_lines), encoding="utf-8")
    print(f"\nWritten {len(approved_orders)} approved order(s) to Common\\Files and MQL5\\Files.")

    mt5.shutdown()

if __name__ == "__main__":
    main()
