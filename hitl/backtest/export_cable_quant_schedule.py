"""
TradingGuard HITL - Export Cable (GBPUSD_o) Quant Orders for MT5 Strategy Tester
Calibrated to $2,000 USD Capital with 0.5% Risk per trade ($10.00 USD).
Generates orders_schedule.csv for LiteFinance MT5 Strategy Tester.
"""

import sys
import shutil
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SOURCE_CSV = BASE_DIR / "backtest_results" / "quant_discovery" / "annual_1year" / "consolidated_annual_orders_schedule.csv"

COMMON_FILES = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
TERMINAL_FILES = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB\MQL5\Files")


def export_cable_quant_schedule(capital: float = 2000.0, risk_pct: float = 0.5):
    if not SOURCE_CSV.exists():
        raise FileNotFoundError(f"Source CSV not found: {SOURCE_CSV}")

    df = pd.read_csv(SOURCE_CSV)
    
    # Filter for GBPUSD within 2026 audit window
    gbp = df[(df["symbol"] == "GBPUSD") & (df["entry_datetime"] >= "2026-02-01") & (df["entry_datetime"] <= "2026-11-05")].copy()
    gbp.sort_values(by="entry_datetime", inplace=True)

    risk_usd = capital * (risk_pct / 100.0) # $10.00 USD for 0.5% on $2,000
    lines = ["ID,Symbol,Type,TriggerTime,Entry,SL,TP,Lot,TTL\n"]

    for idx, row in gbp.reset_index(drop=True).iterrows():
        entry = round(float(row["entry_price"]), 5)
        sl = round(float(row["sl_price"]), 5)
        tp = round(float(row["tp_price"]), 5)
        direction = str(row["direction"]).upper()
        o_type = "SELL" if direction == "SELL" else "BUY"

        risk_pts = abs(entry - sl)
        if risk_pts <= 0.0001:
            risk_pts = 0.0010

        # Contract size is 100,000 units
        lot = round(risk_usd / (100000.0 * risk_pts), 2)
        lot = max(0.01, min(lot, 2.0))

        # Format trigger time as YYYY.MM.DD HH:MM:SS
        t_str = str(row["entry_datetime"]).replace("-", ".")
        o_id = f"ORD-GBP-Q-{t_str[:10].replace('.', '')}-{idx+1:04d}"

        # In LiteFinance, Cable symbol is GBPUSD_o
        line = f"{o_id},GBPUSD_o,{o_type},{t_str},{entry:.5f},{sl:.5f},{tp:.5f},{lot:.2f},240\n"
        lines.append(line)

    local_out = BASE_DIR / "orders_schedule_cable_quant.csv"
    with open(local_out, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"✅ Exported {len(lines) - 1} GBPUSD Quant orders to {local_out.name}")
    print(f"   Capital: ${capital:.2f} | Risk per Trade: ${risk_usd:.2f} ({risk_pct}%)")

    # Sync to MT5 directories
    for dest_dir in [COMMON_FILES, TERMINAL_FILES]:
        if dest_dir.exists():
            target = dest_dir / "orders_schedule.csv"
            shutil.copy2(local_out, target)
            print(f"   -> Synced to: {target}")


if __name__ == "__main__":
    export_cable_quant_schedule()
