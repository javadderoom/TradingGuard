"""
TradingGuard HITL - Continuous Intraday Multi-Event Backtester (Sep 07 - Sep 18, 2026)
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

# Distinct structural inflection candidates across the 2-week period
TARGET_INFLECTIONS = [
    {
        "id": "INFLECT-01-SEP08-NY",
        "date": "2026-09-08",
        "python_dt": datetime.datetime(2026, 9, 8, 15, 30),
        "hour": 15,
        "description": "Sep 08 NY Open: Bullish Range Low Sweep into FVG"
    },
    {
        "id": "INFLECT-02-SEP11-EQH",
        "date": "2026-09-11",
        "python_dt": datetime.datetime(2026, 9, 11, 21, 15),
        "hour": 20,
        "description": "Sep 11 NY PM: Equal Highs (EQH) Sweep & OTE Premium Mitigation (Circle 1)"
    },
    {
        "id": "INFLECT-03-SEP14-ORIGIN",
        "date": "2026-09-14",
        "python_dt": datetime.datetime(2026, 9, 14, 19, 10),
        "hour": 18,
        "description": "Sep 14 NY PM: Breakdown Origin Retest & Prominent Sweep (Circle 2)"
    },
    {
        "id": "INFLECT-04-SEP16-PDH",
        "date": "2026-09-16",
        "python_dt": datetime.datetime(2026, 9, 16, 12, 35),
        "hour": 12,
        "description": "Sep 16 London/NY Crossover: PDH Sweep + M1 MSS Displacement (Circle 3)"
    },
    {
        "id": "INFLECT-05-SEP17-SWEEP",
        "date": "2026-09-17",
        "python_dt": datetime.datetime(2026, 9, 17, 15, 0),
        "hour": 14,
        "description": "Sep 17 NY Pre-Open: Prominent Sweep Re-test in Trend Cascade"
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
    print("🏛️ TRADINGGUARD HITL - FULL AI COUNCIL CONTINUOUS INFLECTION TEST (SEP 07 - SEP 18)")
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
                # If TP was anchored prematurely at internal minor support, expand to external structural target
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

            # CRO Risk Check ($12 ceiling & 2.5R floor)
            if risk_pips * 0.10 > 12.0:
                print(f"  🛑 CRO VETO: Risk {risk_pips:.1f} pips (${risk_pips * 0.10:.2f}) exceeds $12 cap! Overriding to STAND_ASIDE.")
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
