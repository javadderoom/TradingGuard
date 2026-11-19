"""
TradingGuard Canonical Gold Annual Integrity Audit & Remediation Verification
Evaluates the authentic impact of the latest anti-cheat and microstructure remediation on Gold (XAUUSD):
1. Strict Symmetric Risk Cap ($12.00 max risk, reject_over_risk=True -> REJECTED_RISK_CAP)
2. Intrabar Conflict & Same-Bar Fill Blow-Through Resolution (Pessimistic Mandate -> LOSS on bar idx)
3. Prior-Day (T-1) Indexing Fix in fast_screener.py & mtf_structure.py
4. Lot-Scaled Commissions ($0.10 * lot / 0.01) across WIN, LOSS, BREAKEVEN
5. 23:45–01:05 Daily Rollover Freeze & 5x Spread Multiplier
6. Point-in-Time Causal Bar-Close Visibility (closed_bars_only=True)

Outputs:
- backtest_results/gold_integrity_audit/smc_historical_candidates_ledger.csv
- backtest_results/gold_integrity_audit/smc_dynamic_causal_ledger.csv
- backtest_results/gold_integrity_audit/quant_annual_trades_ledger.csv
- backtest_results/gold_integrity_audit/quant_2025_oos_trades_ledger.csv
- backtest_results/gold_integrity_audit/run_manifest.json
- backtest_results/gold_integrity_audit/gold_integrity_audit_summary.json
"""

import sys
import os
import json
import time
import hashlib
import datetime
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo
from bisect import bisect_right
from typing import Dict, List, Any, Tuple, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np

from hitl.backtest.evaluator import evaluate_council_decision, get_optimal_trade_management
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.causal_feed import get_causal_slice, get_causal_d1_slice
from hitl.quant_engine.vectorized_backtester import VectorizedBacktester
from hitl.quant_engine.rule_engine import QuantRule
from hitl.quant_engine.state_space import MathematicalStateSpace

OUT_DIR = PROJECT_ROOT / "backtest_results" / "gold_integrity_audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(filepath: Path) -> str:
    """Calculates SHA-256 hash of a file."""
    if not filepath.exists():
        return ""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_gold_annual_integrity_audit() -> Dict[str, Any]:
    print("=" * 95)
    print("⚖️ TRADINGGUARD CANONICAL GOLD ANNUAL INTEGRITY AUDIT")
    print("Verifying the Authentic Effect of Latest Remediation on 1-Year Gold Backtests")
    print("=" * 95)

    start_audit_time = time.time()

    # -------------------------------------------------------------------------
    # PART 1: SMC/ICT HISTORICAL CANDIDATE RE-EVALUATION
    # -------------------------------------------------------------------------
    print("\n--- PART 1: Re-evaluating 679 Historical Candidate Setups Through Canonical Evaluator ---")
    m1_path = PROJECT_ROOT / "backtest_results" / "cache" / "M1_XAUUSD_o_2026.parquet"
    df_m1 = pd.read_parquet(m1_path)
    bars_m1_records = df_m1.to_dict("records")
    m1_time_to_idx = {int(b["time"]): idx for idx, b in enumerate(bars_m1_records)}
    print(f"Loaded {len(bars_m1_records):,} continuous M1 bars for 2026.")

    old_ledger_path = PROJECT_ROOT / "backtest_results" / "gold_annual_4season_master_synthesis" / "annual_master_all_trades_ledger.csv"
    df_old_ledger = pd.read_csv(old_ledger_path)
    print(f"Loaded {len(df_old_ledger)} historical candidate rows from 4-season synthesis.")

    smc_historical_records = []
    same_bar_losses_count = 0
    rejected_risk_count = 0

    for idx, row in df_old_ledger.iterrows():
        time_str = str(row["time_utc"]).strip()
        date_str = str(row["date"]).strip()
        dt_str = time_str if (len(time_str) > 5 and "-" in time_str) else f"{date_str} {time_str}"
        try:
            if len(dt_str) == 16:
                dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
            elif len(dt_str) == 19:
                dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
            else:
                continue
        except Exception:
            continue

        epoch = int(dt.timestamp())
        m1_idx = m1_time_to_idx.get(epoch)
        if m1_idx is None:
            continue

        forward_bars = bars_m1_records[m1_idx + 1 : m1_idx + 300]
        if not forward_bars:
            continue

        direction = str(row["direction"]).upper()
        is_short = "SHORT" in direction or "SELL" in direction
        entry = float(row["entry"])
        sl = float(row["sl"])
        risk = abs(entry - sl)
        if risk <= 0:
            continue

        arch_id = str(row["archetype_id"])
        target_rr = 3.5
        be_rr = 1.8
        if arch_id == "SETUP-ARCH-012":
            target_rr, be_rr = 2.5, 1.5
        elif arch_id == "SETUP-ARCH-014":
            target_rr, be_rr = 3.5, 1.8

        tp = (entry - target_rr * risk) if is_short else (entry + target_rr * risk)

        decision = {
            "decision": "SELL_LIMIT" if is_short else "BUY_LIMIT",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "lot": 0.01,
            "setup_arch_id": arch_id
        }

        # Canonical execution with all hardened features
        res = evaluate_council_decision(
            decision_dict=decision,
            forward_m1_bars=forward_bars,
            symbol="XAUUSD",
            breakeven_rr=be_rr,
            target_rr_cap=target_rr,
            commission_usd=0.10,
            max_risk_usd=12.0,
            reject_over_risk=True
        )

        if res["status"] == "REJECTED_RISK_CAP":
            rejected_risk_count += 1
        if "blow-through" in res.get("notes", "") or (res["status"] == "LOSS" and res.get("exit_minute") == 1):
            same_bar_losses_count += 1

        rec = {
            "date": row["date"],
            "time_utc": row["time_utc"],
            "session": row["session"],
            "archetype_id": arch_id,
            "direction": "SHORT" if is_short else "LONG",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "risk_pts": round(risk, 2),
            "legacy_status": row["status"],
            "legacy_net_r": row.get("net_r", 0.0),
            "canonical_status": res["status"],
            "canonical_pnl_usd": res["realized_pnl_usd"],
            "canonical_rr": res.get("rr_realized"),
            "fill_minute": res.get("fill_minute"),
            "exit_minute": res.get("exit_minute"),
            "is_realized": res["is_realized"],
            "notes": res.get("notes", "")
        }
        smc_historical_records.append(rec)

    df_hist_re = pd.DataFrame(smc_historical_records)
    hist_ledger_csv = OUT_DIR / "smc_historical_candidates_ledger.csv"
    df_hist_re.to_csv(hist_ledger_csv, index=False)
    print(f"Saved {len(df_hist_re)} re-evaluated candidate setups to {hist_ledger_csv.name}")

    def summarize_smc(df: pd.DataFrame, status_col: str, pnl_col: str, rr_col: str) -> Dict[str, Any]:
        fills = df[df[status_col].isin(["WIN", "LOSS", "BREAKEVEN"])]
        w = len(fills[fills[status_col] == "WIN"])
        l = len(fills[fills[status_col] == "LOSS"])
        be = len(fills[fills[status_col] == "BREAKEVEN"])
        n = len(fills)
        net_usd = fills[pnl_col].sum() if pnl_col in fills else 0.0
        net_r = fills[rr_col].sum() if rr_col in fills else 0.0
        gw = fills[fills[pnl_col] > 0][pnl_col].sum() if pnl_col in fills else (fills[fills[rr_col] > 0][rr_col].sum())
        gl = abs(fills[fills[pnl_col] < 0][pnl_col].sum()) if pnl_col in fills else abs(fills[fills[rr_col] < 0][rr_col].sum())
        pf = round(gw / max(0.001, gl), 2)
        wr = round((w / n * 100.0), 1) if n > 0 else 0.0
        return {
            "fills": n, "wins": w, "losses": l, "breakevens": be,
            "win_rate_pct": wr, "net_r": round(net_r, 2), "net_pnl_usd": round(net_usd, 2),
            "profit_factor": pf
        }

    # Baseline & Calibrated for Historical Candidates
    # Exclude all root-level decommissioned archetypes on Gold
    GOLD_DECOMMISSIONED = [
        "SETUP-ARCH-002", "SETUP-ARCH-004", "SETUP-ARCH-009", "SETUP-ARCH-010",
        "SETUP-ARCH-012", "SETUP-ARCH-014", "SETUP-ARCH-019"
    ]
    hist_base = summarize_smc(df_hist_re, "canonical_status", "canonical_pnl_usd", "canonical_rr")
    df_hist_calib = df_hist_re[
        (df_hist_re["session"] != "NY_Silver_Bullet") &
        (~df_hist_re["archetype_id"].isin(GOLD_DECOMMISSIONED))
    ]
    hist_calib = summarize_smc(df_hist_calib, "canonical_status", "canonical_pnl_usd", "canonical_rr")

    print(f"  PART 1 BASELINE (ALL FILLS):  {hist_base['fills']} Fills | {hist_base['wins']}W - {hist_base['losses']}L - {hist_base['breakevens']}BE | WR: {hist_base['win_rate_pct']}% | Net: {hist_base['net_r']:+.2f}R | USD: ${hist_base['net_pnl_usd']:+.2f} | PF: {hist_base['profit_factor']}")
    print(f"  PART 1 CALIBRATED SUITE:      {hist_calib['fills']} Fills | {hist_calib['wins']}W - {hist_calib['losses']}L - {hist_calib['breakevens']}BE | WR: {hist_calib['win_rate_pct']}% | Net: {hist_calib['net_r']:+.2f}R | USD: ${hist_calib['net_pnl_usd']:+.2f} | PF: {hist_calib['profit_factor']}")

    # -------------------------------------------------------------------------
    # PART 2: SMC/ICT DYNAMIC CAUSAL SCREENING (T-1 INDEXING & CLOSED BARS)
    # -------------------------------------------------------------------------
    print("\n--- PART 2: Dynamic Causal Screening Across 2026 M1 Bars with Corrected T-1 Indexing ---")
    df_bars_indexed = df_m1.set_index(pd.to_datetime(df_m1["time"], unit="s", utc=True)).sort_index()

    def _resamp_df(rule: str):
        r = df_bars_indexed["close"].resample(rule).ohlc().dropna()
        r["open"] = df_bars_indexed["open"].resample(rule).first()
        r["high"] = df_bars_indexed["high"].resample(rule).max()
        r["low"] = df_bars_indexed["low"].resample(rule).min()
        r["close"] = df_bars_indexed["close"].resample(rule).last()
        out = []
        for idx, row in r.iterrows():
            out.append({
                "time": int(idx.timestamp()),
                "dt": idx.to_pydatetime(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
        out.sort(key=lambda x: x["time"])
        return out

    bars_m5 = _resamp_df("5min")
    bars_h1 = _resamp_df("1h")
    bars_d1 = _resamp_df("1D")

    times_m5 = [b["time"] for b in bars_m5]
    times_h1 = [b["time"] for b in bars_h1]
    times_d1 = [b["time"] for b in bars_d1]

    trading_dates = sorted(list(set(b["dt"].date() for b in bars_m5)))
    session_offsets_utc = [
        ("London_Open", 8, 0),
        ("London_Continuation", 9, 30),
        ("NY_Open", 13, 0),
        ("NY_Silver_Bullet", 15, 0)
    ]

    smc_dynamic_records = []
    dyn_rejected_risk = 0

    for day_idx in range(5, len(trading_dates)):
        day_date = trading_dates[day_idx]
        if day_date.weekday() in (5, 6):
            continue

        for sess_name, h_utc, m_utc in session_offsets_utc:
            sess_dt = datetime.datetime(day_date.year, day_date.month, day_date.day, h_utc, m_utc, tzinfo=datetime.timezone.utc)
            sess_epoch = int(sess_dt.timestamp())

            idx_5m = bisect_right(times_m5, sess_epoch - 300)
            idx_h1 = bisect_right(times_h1, sess_epoch - 3600)
            idx_d1 = bisect_right(times_d1, sess_epoch - 86400)

            slice_5m = bars_m5[max(0, idx_5m - 120) : idx_5m]
            slice_1h = bars_h1[max(0, idx_h1 - 60) : idx_h1]
            slice_1d = bars_d1[max(0, idx_d1 - 15) : idx_d1]

            if len(slice_5m) < 40 or len(slice_1h) < 10 or len(slice_1d) < 2:
                continue

            res = screen_ict_session(
                bars_5m=slice_5m,
                bars_1h=slice_1h,
                symbol="XAUUSD",
                session_hour=h_utc,
                bars_1d=slice_1d,
                closed_bars_only=True
            )

            if not res.get("has_setup"):
                continue

            arch_id = res.get("archetype_id", "SETUP-ARCH-003")
            entry = float(res.get("entry_ref", 0.0))
            sl = float(res.get("sl_ref", 0.0))
            setup_type = str(res.get("setup_type", ""))
            is_short = "BEARISH" in setup_type or "SHORT" in setup_type

            risk = abs(entry - sl)
            if risk <= 0:
                continue

            target_rr, be_rr = get_optimal_trade_management("XAUUSD", sess_name, setup_arch_id=arch_id)
            tp = (entry - target_rr * risk) if is_short else (entry + target_rr * risk)

            decision = {
                "decision": "SELL_LIMIT" if is_short else "BUY_LIMIT",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "lot": 0.01,
                "setup_arch_id": arch_id
            }

            m1_idx = m1_time_to_idx.get(sess_epoch)
            if m1_idx is None:
                continue
            forward_m1 = bars_m1_records[m1_idx + 1 : m1_idx + 300]
            if not forward_m1:
                continue

            eval_res = evaluate_council_decision(
                decision_dict=decision,
                forward_m1_bars=forward_m1,
                symbol="XAUUSD",
                breakeven_rr=be_rr,
                target_rr_cap=target_rr,
                commission_usd=0.10,
                max_risk_usd=12.0,
                reject_over_risk=True
            )

            if eval_res["status"] == "REJECTED_RISK_CAP":
                dyn_rejected_risk += 1

            smc_dynamic_records.append({
                "date": day_date.strftime("%Y-%m-%d"),
                "session": sess_name,
                "epoch": sess_epoch,
                "archetype_id": arch_id,
                "direction": "SHORT" if is_short else "LONG",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "risk_pts": round(risk, 2),
                "status": eval_res["status"],
                "realized_pnl_usd": eval_res["realized_pnl_usd"],
                "rr_realized": eval_res.get("rr_realized"),
                "fill_minute": eval_res.get("fill_minute"),
                "exit_minute": eval_res.get("exit_minute"),
                "is_realized": eval_res["is_realized"],
                "notes": eval_res.get("notes", "")
            })

    df_dyn_re = pd.DataFrame(smc_dynamic_records)
    dyn_ledger_csv = OUT_DIR / "smc_dynamic_causal_ledger.csv"
    df_dyn_re.to_csv(dyn_ledger_csv, index=False)
    print(f"Saved {len(df_dyn_re)} dynamically screened setups to {dyn_ledger_csv.name}")

    dyn_base = summarize_smc(df_dyn_re, "status", "realized_pnl_usd", "rr_realized")
    df_dyn_calib = df_dyn_re[
        (df_dyn_re["session"] != "NY_Silver_Bullet") &
        (~df_dyn_re["archetype_id"].isin(GOLD_DECOMMISSIONED))
    ]
    dyn_calib = summarize_smc(df_dyn_calib, "status", "realized_pnl_usd", "rr_realized")

    print(f"  PART 2 BASELINE (ALL FILLS):  {dyn_base['fills']} Fills | {dyn_base['wins']}W - {dyn_base['losses']}L - {dyn_base['breakevens']}BE | WR: {dyn_base['win_rate_pct']}% | Net: {dyn_base['net_r']:+.2f}R | USD: ${dyn_base['net_pnl_usd']:+.2f} | PF: {dyn_base['profit_factor']}")
    print(f"  PART 2 CALIBRATED SUITE:      {dyn_calib['fills']} Fills | {dyn_calib['wins']}W - {dyn_calib['losses']}L - {dyn_calib['breakevens']}BE | WR: {dyn_calib['win_rate_pct']}% | Net: {dyn_calib['net_r']:+.2f}R | USD: ${dyn_calib['net_pnl_usd']:+.2f} | PF: {dyn_calib['profit_factor']}")

    # -------------------------------------------------------------------------
    # PART 3: QUANT STRATEGY SUITE 1-YEAR AUDIT (XAUUSD_M5_1YEAR.parquet)
    # -------------------------------------------------------------------------
    print("\n--- PART 3: Autonomous Quant Suite 1-Year Audit Under Lot-Scaled Friction & Rollover Freeze ---")
    quant_m5_path = PROJECT_ROOT / "backtest_results" / "cache" / "XAUUSD_M5_1YEAR.parquet"
    raw_df_quant = pd.read_parquet(quant_m5_path).drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    ss = MathematicalStateSpace()
    state_quant = ss.transform(raw_df_quant)

    annual_ratified_path = PROJECT_ROOT / "backtest_results" / "quant_discovery" / "annual_1year" / "xauusd" / "annual_ratified_strategies.json"
    with open(annual_ratified_path, "r", encoding="utf-8") as f:
        annual_quant_data = json.load(f)
    rules_dict = {item["rule"]["rule_id"]: QuantRule.from_dict(item["rule"]) for item in annual_quant_data}

    # The 3 ratified orthogonal rules in LiveQuantBridge
    ratified_quant_ids = ["R15_048", "R14_058", "R15_023"]
    bt_quant = VectorizedBacktester(symbol="XAUUSD", spread=0.22, commission_usd=0.10, risk_per_trade_usd=12.0)

    quant_1y_trades = []
    quant_1y_rules_summary = {}

    for rid in ratified_quant_ids:
        r = rules_dict[rid]
        res = bt_quant.run(state_quant, r)
        quant_1y_rules_summary[rid] = res.summary()

        for t in res.trades:
            quant_1y_trades.append({
                "rule_id": rid,
                "direction": r.direction,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "entry_datetime": pd.to_datetime(t.entry_time, unit="s").strftime("%Y-%m-%d %H:%M:%S"),
                "exit_datetime": pd.to_datetime(t.exit_time, unit="s").strftime("%Y-%m-%d %H:%M:%S"),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "sl_price": t.sl_price,
                "tp_price": t.tp_price,
                "status": t.status,
                "realized_r": round(t.r_realized, 2),
                "pnl_usd": round(t.pnl_usd, 2),
                "bars_held": t.bars_held
            })

    df_quant_1y = pd.DataFrame(quant_1y_trades).sort_values("entry_time").reset_index(drop=True)
    quant_ledger_csv = OUT_DIR / "quant_annual_trades_ledger.csv"
    df_quant_1y.to_csv(quant_ledger_csv, index=False)
    print(f"Saved {len(df_quant_1y)} quant trades to {quant_ledger_csv.name}")

    tot_q_wins = len(df_quant_1y[df_quant_1y["status"] == "WIN"])
    tot_q_losses = len(df_quant_1y[df_quant_1y["status"] == "LOSS"])
    tot_q_be = len(df_quant_1y[df_quant_1y["status"] == "BREAKEVEN"])
    tot_q_fills = len(df_quant_1y)
    tot_q_wr = (tot_q_wins / tot_q_fills * 100.0) if tot_q_fills > 0 else 0.0
    tot_q_net_r = df_quant_1y["realized_r"].sum()
    tot_q_pnl_usd = df_quant_1y["pnl_usd"].sum()
    gw_q = df_quant_1y[df_quant_1y["pnl_usd"] > 0]["pnl_usd"].sum()
    gl_q = abs(df_quant_1y[df_quant_1y["pnl_usd"] < 0]["pnl_usd"].sum())
    tot_q_pf = gw_q / gl_q if gl_q > 0 else 0.0

    print(f"  PART 3 QUANT COMBINED 1-YEAR: {tot_q_fills} Fills | {tot_q_wins}W - {tot_q_losses}L - {tot_q_be}BE | WR: {tot_q_wr:.1f}% | Net: {tot_q_net_r:+.2f}R | USD: ${tot_q_pnl_usd:+.2f} | PF: {tot_q_pf:.2f}")

    # -------------------------------------------------------------------------
    # PART 4: 2025 OUT-OF-SAMPLE BENCHMARK ON GOLD (M5_XAUUSD_o_2025.parquet)
    # -------------------------------------------------------------------------
    print("\n--- PART 4: 2025 Out-Of-Sample Benchmark (Untouched Holdout Vault 3) ---")
    oos_2025_path = PROJECT_ROOT / "backtest_results" / "cache" / "M5_XAUUSD_o_2025.parquet"
    raw_2025 = pd.read_parquet(oos_2025_path).drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    state_2025 = ss.transform(raw_2025)

    quant_2025_trades = []
    quant_2025_rules_summary = {}

    for rid in ratified_quant_ids:
        r = rules_dict[rid]
        res = bt_quant.run(state_2025, r)
        quant_2025_rules_summary[rid] = res.summary()

        for t in res.trades:
            quant_2025_trades.append({
                "rule_id": rid,
                "direction": r.direction,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "entry_datetime": pd.to_datetime(t.entry_time, unit="s").strftime("%Y-%m-%d %H:%M:%S"),
                "exit_datetime": pd.to_datetime(t.exit_time, unit="s").strftime("%Y-%m-%d %H:%M:%S"),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "sl_price": t.sl_price,
                "tp_price": t.tp_price,
                "status": t.status,
                "realized_r": round(t.r_realized, 2),
                "pnl_usd": round(t.pnl_usd, 2),
                "bars_held": t.bars_held
            })

    df_quant_2025 = pd.DataFrame(quant_2025_trades).sort_values("entry_time").reset_index(drop=True)
    quant_2025_csv = OUT_DIR / "quant_2025_oos_trades_ledger.csv"
    df_quant_2025.to_csv(quant_2025_csv, index=False)
    print(f"Saved {len(df_quant_2025)} 2025 OOS trades to {quant_2025_csv.name}")

    tot_25_wins = len(df_quant_2025[df_quant_2025["status"] == "WIN"])
    tot_25_losses = len(df_quant_2025[df_quant_2025["status"] == "LOSS"])
    tot_25_be = len(df_quant_2025[df_quant_2025["status"] == "BREAKEVEN"])
    tot_25_fills = len(df_quant_2025)
    tot_25_wr = (tot_25_wins / tot_25_fills * 100.0) if tot_25_fills > 0 else 0.0
    tot_25_net_r = df_quant_2025["realized_r"].sum()
    tot_25_pnl_usd = df_quant_2025["pnl_usd"].sum()
    gw_25 = df_quant_2025[df_quant_2025["pnl_usd"] > 0]["pnl_usd"].sum()
    gl_25 = abs(df_quant_2025[df_quant_2025["pnl_usd"] < 0]["pnl_usd"].sum())
    tot_25_pf = gw_25 / gl_25 if gl_25 > 0 else 0.0

    print(f"  PART 4 QUANT COMBINED 2025 OOS: {tot_25_fills} Fills | {tot_25_wins}W - {tot_25_losses}L - {tot_25_be}BE | WR: {tot_25_wr:.1f}% | Net: {tot_25_net_r:+.2f}R | USD: ${tot_25_pnl_usd:+.2f} | PF: {tot_25_pf:.2f}")

    # -------------------------------------------------------------------------
    # CRYPTOGRAPHIC RUN MANIFEST & SUMMARY EXPORT
    # -------------------------------------------------------------------------
    git_sha = ""
    try:
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        pass

    manifest = {
        "audit_name": "GOLD_ANNUAL_INTEGRITY_AUDIT_2026",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_commit": git_sha,
        "governing_rules": "docs/BACKTEST_INTEGRITY_RULES.md",
        "code_hashes": {
            "evaluator.py": sha256_file(PROJECT_ROOT / "hitl" / "backtest" / "evaluator.py"),
            "fast_screener.py": sha256_file(PROJECT_ROOT / "hitl" / "backtest" / "fast_screener.py"),
            "causal_feed.py": sha256_file(PROJECT_ROOT / "hitl" / "backtest" / "causal_feed.py"),
            "vectorized_backtester.py": sha256_file(PROJECT_ROOT / "hitl" / "quant_engine" / "vectorized_backtester.py"),
            "run_gold_annual_integrity_audit.py": sha256_file(Path(__file__))
        },
        "input_hashes": {
            "M1_XAUUSD_o_2026.parquet": sha256_file(m1_path),
            "XAUUSD_M5_1YEAR.parquet": sha256_file(quant_m5_path),
            "M5_XAUUSD_o_2025.parquet": sha256_file(oos_2025_path),
            "annual_master_all_trades_ledger.csv": sha256_file(old_ledger_path)
        },
        "output_hashes": {
            "smc_historical_candidates_ledger.csv": sha256_file(hist_ledger_csv),
            "smc_dynamic_causal_ledger.csv": sha256_file(dyn_ledger_csv),
            "quant_annual_trades_ledger.csv": sha256_file(quant_ledger_csv),
            "quant_2025_oos_trades_ledger.csv": sha256_file(quant_2025_csv)
        },
        "parameters": {
            "symbol": "XAUUSD",
            "spread_gold": 0.22,
            "commission_usd_per_001_lot": 0.10,
            "max_risk_usd": 12.0,
            "reject_over_risk": True,
            "ttl_minutes": 75,
            "rollover_blackout": "23:45 to 01:05 server time (5x spread)"
        }
    }

    manifest_path = OUT_DIR / "run_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n🔐 Cryptographic Run Manifest generated at {manifest_path.name}")

    summary = {
        "execution_time_seconds": round(time.time() - start_audit_time, 2),
        "smc_historical_reevaluation": {
            "baseline": hist_base,
            "calibrated": hist_calib,
            "same_bar_losses": same_bar_losses_count,
            "rejected_risk_cap": rejected_risk_count
        },
        "smc_dynamic_causal": {
            "baseline": dyn_base,
            "calibrated": dyn_calib,
            "rejected_risk_cap": dyn_rejected_risk
        },
        "quant_annual_1year": {
            "combined": {
                "fills": tot_q_fills,
                "wins": tot_q_wins,
                "losses": tot_q_losses,
                "breakevens": tot_q_be,
                "win_rate_pct": round(tot_q_wr, 1),
                "net_r": round(tot_q_net_r, 2),
                "net_pnl_usd": round(tot_q_pnl_usd, 2),
                "profit_factor": round(tot_q_pf, 2)
            },
            "rules": quant_1y_rules_summary
        },
        "quant_2025_oos": {
            "combined": {
                "fills": tot_25_fills,
                "wins": tot_25_wins,
                "losses": tot_25_losses,
                "breakevens": tot_25_be,
                "win_rate_pct": round(tot_25_wr, 1),
                "net_r": round(tot_25_net_r, 2),
                "net_pnl_usd": round(tot_25_pnl_usd, 2),
                "profit_factor": round(tot_25_pf, 2)
            },
            "rules": quant_2025_rules_summary
        }
    }

    summary_path = OUT_DIR / "gold_integrity_audit_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"📊 Audit Summary exported to {summary_path.name}")
    print("=" * 95)
    return summary


if __name__ == "__main__":
    run_gold_annual_integrity_audit()
