"""
TradingGuard HITL - Continuous Intraday Multi-Event Backtester (Sep 21 - Oct 02, 2026)
Runs an authentic end-to-end backtest on the key inflection points across Cable (GBPUSD).
Evaluates each setup with the full 6-Seat AI Council under newly ratified:
- SETUP-ARCH-010: Prominent Liquidity Sweep with M1 MSS Displacement
- RULE-EXEC-039: Pro-Trend Prominent Sweep Execution Protocol
- RULE-EXEC-040: Precision LTF (M1) Stop Compression Protocol
- RULE-TARGET-040: Pro-Trend Liquidity Expansion Targeting (R:R >= 1:3.0)

Strictly zero manual CSV injections. Output is written directly to orders_schedule.csv.
"""

import sys
import time
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import MetaTrader5 as mt5
from hitl.backtest.data_feed import HistoricalDataFeed, _convert_records
from hitl.backtest.council_replay import convene_council_on_historical_dossier
from hitl.backtest.forex_cross_pair import detect_forex_smt_divergence, analyze_cross_pair_symbiosis, format_symbiotic_prompt

# Distinct structural inflection candidates across Sep 21 - Oct 02, 2026
TARGET_INFLECTIONS = [
    {
        "id": "INFLECT-01-SEP21-NY",
        "date": "2026-09-21",
        "python_dt": datetime.datetime(2026, 9, 21, 19, 15),
        "hour": 15,
        "description": "Sep 21 NY Open: 1.34000 Institutional Level Sweep into Downward Displacement"
    },
    {
        "id": "INFLECT-02-SEP22-LON",
        "date": "2026-09-22",
        "python_dt": datetime.datetime(2026, 9, 22, 12, 15),
        "hour": 8,
        "description": "Sep 22 London Open: Asian High Sweep (1.33872) into Structural Breakdown"
    },
    {
        "id": "INFLECT-03-SEP24-LON",
        "date": "2026-09-24",
        "python_dt": datetime.datetime(2026, 9, 24, 14, 55),
        "hour": 11,
        "description": "Sep 24 London Session: Sweep (1.32560) into Confirmed Bearish MSS"
    }
]


def main():
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    feed = HistoricalDataFeed()
    if not feed.engine.ensure_connected():
        print("Failed to connect to MT5")
        return

    sym = "GBPUSD"
    resolved_sym = feed.engine.resolve_symbol(sym)
    resolved_eur = feed.engine.resolve_symbol("EURUSD")

    print("=" * 90)
    print("🏛️ TRADINGGUARD HITL - FULL AI COUNCIL CONTINUOUS INFLECTION TEST (SEP 21 - OCT 02)")
    print(f"Target: {resolved_sym} | Total Candidate Inflections: {len(TARGET_INFLECTIONS)}")
    print("Governance: RULE-EXEC-039, RULE-EXEC-040 (M1 Compression), RULE-TARGET-040 (HTF Expansion)")
    print("=" * 90)

    approved_orders = []
    deliberation_log = []

    for idx, target in enumerate(TARGET_INFLECTIONS, 1):
        dt = target.get("broker_time") or target.get("python_dt")
        t_id = target["id"]
        desc = target["description"]
        print(f"\n[{idx:02d}/{len(TARGET_INFLECTIONS)}] {t_id} | {dt.strftime('%Y-%m-%d %H:%M')}")
        print(f"  Description: {desc}")

        # Fetch market data
        r5_gbp = _convert_records(mt5.copy_rates_from(resolved_sym, mt5.TIMEFRAME_M5, dt, 85))
        r5_eur = _convert_records(mt5.copy_rates_from(resolved_eur, mt5.TIMEFRAME_M5, dt, 85))
        smt_info = detect_forex_smt_divergence(r5_eur, r5_gbp, target["hour"]) if (r5_eur and r5_gbp) else None
        symbiosis_info = analyze_cross_pair_symbiosis(r5_gbp, r5_eur, "GBPUSD", "EURUSD", smt_info)
        symbiosis_prompt = format_symbiotic_prompt(symbiosis_info)

        dossier = feed.prepare_session_dossier(sym, dt)
        if not dossier:
            print(f"  ❌ Failed to prepare MTF dossier for {t_id}")
            continue

        dossier["telemetry_prompt"] = symbiosis_prompt + "\n\n" + dossier.get("telemetry_prompt", "")

        t0 = time.time()
        print("  ⏳ Convening 6-Seat AI Council via agy.exe...")
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
            "id": t_id,
            "broker_time": dt,
            "decision": decision,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "rr": rr,
            "elapsed": elapsed
        })

        if decision in ("BUY_LIMIT", "SELL_LIMIT") and entry and sl and tp:
            # Enforce RULE-CORE-005: Programmatic Structural SL Pinning (prevents LLM arithmetic slips)
            pip_size = 0.00010 if "GBP" in sym else 0.00020
            if "SELL" in decision and r5_gbp:
                recent_sweep = max(b['high'] for b in r5_gbp[-15:])
                exact_sl = round(recent_sweep + pip_size, 5)
                if abs(sl - exact_sl) > 0.00030:
                    print(f"  🔧 Auto-calibrating SL from {sl:.5f} to exact RULE-CORE-005 structural anchor: {exact_sl:.5f}")
                    sl = exact_sl
            elif "BUY" in decision and r5_gbp:
                recent_sweep = min(b['low'] for b in r5_gbp[-15:])
                exact_sl = round(recent_sweep - pip_size, 5)
                if abs(sl - exact_sl) > 0.00030:
                    print(f"  🔧 Auto-calibrating SL from {sl:.5f} to exact RULE-CORE-005 structural anchor: {exact_sl:.5f}")
                    sl = exact_sl

            # Enforce RULE-CORE-006 / RULE-TARGET-041: Pro-Trend External Structural Target Expansion
            tele = dossier.get("telemetry", {})
            macro_filter = dossier.get("macro_bias_data", {}).get("execution_filter", "")
            if "SELL" in decision and ("SELL" in macro_filter or macro_filter == "SELECTIVE_BI_DIRECTIONAL"):
                bench_low = tele.get("bench_low")
                htf_target = tele.get("htf_expansion_bearish")
                if bench_low and abs(tp - bench_low) < 0.00050 and htf_target and htf_target < tp:
                    print(f"  🎯 RULE-TARGET-041: Expanding pro-trend TP from internal support {tp:.5f} to External Structural Expansion: {htf_target:.5f}")
                    tp = round(htf_target, 5)
            elif "BUY" in decision and ("BUY" in macro_filter or macro_filter == "SELECTIVE_BI_DIRECTIONAL"):
                bench_high = tele.get("bench_high")
                htf_target = tele.get("htf_expansion_bullish")
                if bench_high and abs(tp - bench_high) < 0.00050 and htf_target and htf_target > tp:
                    print(f"  🎯 RULE-TARGET-041: Expanding pro-trend TP from internal resistance {tp:.5f} to External Structural Expansion: {htf_target:.5f}")
                    tp = round(htf_target, 5)

            risk_pips = abs(entry - sl) * 10000
            calc_rr = abs(tp - entry) / max(0.0001, abs(entry - sl))

            # CRO Risk Check ($17 ceiling & 2.5R floor)
            if risk_pips > 17.0:
                print(f"  🛑 CRO VETO: Risk {risk_pips:.1f} pips exceeds $17 cap! Overriding to STAND_ASIDE.")
                continue

            if calc_rr < 2.5:
                print(f"  🛑 CRO VETO: Calculated R:R ({calc_rr:.2f}R) is below institutional 2.5R threshold! Overriding to STAND_ASIDE.")
                continue

            broker_dt = dossier.get("broker_time", dt)
            order_id = f"ORD-{broker_dt.strftime('%m%d')}-{broker_dt.strftime('%H%M')}"
            approved_orders.append({
                "id": order_id,
                "symbol": "AUTO",
                "type": decision,
                "trigger_time": broker_dt.strftime("%Y.%m.%d %H:%M:00"),
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "lot": 0.01,
                "ttl": 360
            })
            print(f"  ✅ APPROVED [{decision}] @ {entry:.5f} | SL: {sl:.5f} | TP: {tp:.5f} | R:R: {calc_rr:.2f}R ({elapsed:.1f}s)")
        else:
            print(f"  🛡️ STAND ASIDE (Decision: {decision}) ({elapsed:.1f}s)")

    print("\n" + "=" * 90)
    print(f"COUNCIL EVALUATION COMPLETE: {len(approved_orders)} / {len(TARGET_INFLECTIONS)} Inflections Approved")
    print("=" * 90)

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
