"""
Exports authentic 2026 NASDAQ 100 orders schedule for MetaTrader 5 Strategy Tester.
Dynamically calculates lot size calibrated to $2,000 USD capital (1% risk = $20/trade).
"""

import sys
import shutil
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SOURCE_CSV = BASE_DIR / "backtest_results" / "quant_discovery" / "annual_orders_schedule.csv"

COMMON_FILES = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
TERMINAL_FILES = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB\MQL5\Files")


def export_nq_schedule(capital: float = 2000.0, risk_pct: float = 1.0):
    df = pd.read_csv(SOURCE_CSV)
    
    # Filter for NQ within 2026 audit window
    nq = df[(df["symbol"] == "NQ") & (df["entry_datetime"] >= "2026-02-01") & (df["entry_datetime"] <= "2026-11-05")].copy()
    nq.sort_values(by="entry_datetime", inplace=True)

    risk_usd = capital * (risk_pct / 100.0) # $20.00 for $2000 acct
    lines = ["ID,Symbol,Type,TriggerTime,Entry,SL,TP,Lot,TTL\n"]

    for idx, row in nq.reset_index(drop=True).iterrows():
        entry = round(float(row["entry_price"]), 1)
        sl = round(float(row["sl_price"]), 1)
        tp = round(float(row["tp_price"]), 1)
        direction = str(row["direction"]).upper()
        o_type = "BUY_LIMIT" if direction == "BUY" else "SELL_LIMIT"

        risk_pts = abs(entry - sl)
        if risk_pts <= 0:
            risk_pts = 20.0

        # In LiteFinance NQ: Contract size is 1.0, MinLot=0.1, Step=0.1
        # risk_usd = lot * contract_size (1.0) * risk_pts
        # lot = risk_usd / risk_pts
        lot = round(risk_usd / risk_pts, 1)
        lot = max(0.1, min(lot, 2.0))

        # Format trigger time as YYYY.MM.DD HH:MM:SS
        t_str = str(row["entry_datetime"]).replace("-", ".")
        o_id = f"ORD-NQ-{t_str[:10].replace('.', '')}-{idx+1:03d}"

        line = f"{o_id},NQ,{o_type},{t_str},{entry:.1f},{sl:.1f},{tp:.1f},{lot:.1f},480\n"
        lines.append(line)

    local_out = BASE_DIR / "orders_schedule_nq.csv"
    with open(local_out, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"✅ Exported {len(lines) - 1} NQ orders to {local_out.name} (Capital: ${capital:.0f}, Risk/Trade: ${risk_usd:.2f})")

    # Sync to MT5 directories
    for dest_dir in [COMMON_FILES, TERMINAL_FILES]:
        if dest_dir.exists():
            target = dest_dir / "orders_schedule.csv"
            shutil.copy2(local_out, target)
            print(f"   -> Synced to: {target}")


if __name__ == "__main__":
    export_nq_schedule(capital=2000.0, risk_pct=1.0)
