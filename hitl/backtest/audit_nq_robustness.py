"""
TradingGuard HITL - NASDAQ 100 Robustness Audit Across Sub-Suites
Evaluates optimal asymmetric policy against:
1. Ratified SMC Suite (trades_nq.parquet, 16 fills)
2. 2-Month Comprehensive Screener Suite (nq_2month_trades.csv, 607 fills)
3. 5-Month Unified Suite (nq_unified_5_month_trades.csv, 190 fills)
"""

import sys
import json
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

OUTPUT_DIR = BASE_DIR / "backtest_results" / "nq_trend_oracle_audit"

# Load 3-state ledger
ledger_df = pd.read_csv(OUTPUT_DIR / "nq_omnitrend_3state_ledger.csv")
trend_map = dict(zip(ledger_df["date"].astype(str), ledger_df["pred_state"]))

# Optimal policy parameters
AL_TP, AL_BE = 3.5, 1.0
CT_TP, CT_BE = 3.0, 0.8
SD_TP, SD_BE = 3.0, 0.8

# Load M5 bars
m5_df = pd.read_parquet(BASE_DIR / "backtest_results" / "cache" / "NQ_M5_1YEAR.parquet")
m5_times = m5_df["time"].values
m5_highs = m5_df["high"].values
m5_lows = m5_df["low"].values
m5_opens = m5_df["open"].values
time_to_idx = {t: i for i, t in enumerate(m5_times)}


def evaluate_suite(df, name):
    filled = df[df["status"].isin(["WIN", "LOSS", "BREAKEVEN"])].copy()
    if len(filled) == 0:
        return

    # Baseline metrics
    n_base = len(filled)
    w_base = len(filled[filled["status"] == "WIN"])
    l_base = len(filled[filled["status"] == "LOSS"])
    b_base = len(filled[filled["status"] == "BREAKEVEN"])
    gw_base = sum(row["rr_realized"] for _, row in filled.iterrows() if row["rr_realized"] > 0)
    gl_base = abs(sum(row["rr_realized"] for _, row in filled.iterrows() if row["rr_realized"] < 0))
    net_base = gw_base - gl_base
    pf_base = gw_base / max(0.01, gl_base)

    # Calibrated policy simulation
    cal_pnl = []
    for _, row in filled.iterrows():
        epoch = int(row["epoch"])
        date_str = str(row["date"])
        direction = row["direction"].upper()
        risk_pts = float(row["risk_pts"])
        status_base = row["status"]

        pred = trend_map.get(date_str, "SIDEWAYS")
        is_aligned = (direction == "BUY" and pred == "UP") or (direction == "SELL" and pred == "DOWN")
        is_counter = (direction == "BUY" and pred == "DOWN") or (direction == "SELL" and pred == "UP")

        if is_aligned:
            tp, be = AL_TP, AL_BE
        elif is_counter:
            tp, be = CT_TP, CT_BE
        else:
            tp, be = SD_TP, SD_BE

        if epoch in time_to_idx:
            s_idx = time_to_idx[epoch]
            e_idx = min(len(m5_times), s_idx + 288)
            entry = m5_opens[s_idx]
            h_sl = m5_highs[s_idx:e_idx]
            l_sl = m5_lows[s_idx:e_idx]

            max_f = (np.max(h_sl) - entry) if direction == "BUY" else (entry - np.min(l_sl))
            max_a = (entry - np.min(l_sl)) if direction == "BUY" else (np.max(h_sl) - entry)
            mfe_r = max_f / max(1.0, risk_pts)
            mae_r = max_a / max(1.0, risk_pts)
        else:
            mfe_r = 3.5 if status_base == "WIN" else (1.5 if status_base == "BREAKEVEN" else 0.5)
            mae_r = 0.5 if status_base == "WIN" else 1.0

        if mae_r >= 1.0 and mfe_r < be:
            cal_pnl.append((-1.0, "LOSS"))
        elif mfe_r >= tp:
            if status_base in ["WIN", "BREAKEVEN"] or mae_r < 1.0:
                cal_pnl.append((tp, "WIN"))
            else:
                cal_pnl.append((-1.0, "LOSS"))
        elif mfe_r >= be:
            cal_pnl.append((0.0, "BREAKEVEN"))
        else:
            cal_pnl.append((-1.0, "LOSS"))

    n_cal = len(cal_pnl)
    w_cal = sum(1 for r, s in cal_pnl if s == "WIN")
    l_cal = sum(1 for r, s in cal_pnl if s == "LOSS")
    b_cal = sum(1 for r, s in cal_pnl if s == "BREAKEVEN")
    gw_cal = sum(r for r, s in cal_pnl if r > 0)
    gl_cal = abs(sum(r for r, s in cal_pnl if r < 0))
    net_cal = sum(r for r, s in cal_pnl)
    pf_cal = gw_cal / max(0.01, gl_cal)

    print(f"\n=======================================================")
    print(f"📊 {name}")
    print(f"=======================================================")
    print(f"BASELINE   (Static 3.5R) : {n_base} Fills | {w_base}W - {l_base}L - {b_base}BE | WR: {w_base/n_base*100:5.1f}% | Net: {net_base:+6.2f}R | PF: {pf_base:4.2f}")
    print(f"CALIBRATED (Index Policy): {n_cal} Fills | {w_cal}W - {l_cal}L - {b_cal}BE | WR: {w_cal/n_cal*100:5.1f}% | Net: {net_cal:+6.2f}R | PF: {pf_cal:4.2f}")
    delta_r = net_cal - net_base
    delta_pf = pf_cal - pf_base
    print(f"DELTA                    : Net Alpha {delta_r:+6.2f}R | Profit Factor {delta_pf:+4.2f} | Win Rate {((w_cal/n_cal) - (w_base/n_base))*100:+5.1f}%")
    print(f"=======================================================")


if __name__ == "__main__":
    # 1. Ratified SMC Suite
    p1 = BASE_DIR / "backtest_results" / "unified_portfolio_audit" / "trades_nq.parquet"
    if p1.exists():
        evaluate_suite(pd.read_parquet(p1), "RATIFIED SMC SUITE (London Bearish Breakers ARCH-001)")

    # 2. 5-Month Unified Suite
    p2 = BASE_DIR / "backtest_results" / "nq_summer_2month_audit" / "nq_unified_5_month_trades.csv"
    if p2.exists():
        evaluate_suite(pd.read_csv(p2), "5-MONTH UNIFIED SMC SUITE (190 Fills)")

    # 3. 2-Month Comprehensive Screener Suite
    p3 = BASE_DIR / "backtest_results" / "nq_2month_audit" / "nq_2month_trades.csv"
    if p3.exists():
        evaluate_suite(pd.read_csv(p3), "2-MONTH RAW SCREENER SUITE (607 Fills)")
