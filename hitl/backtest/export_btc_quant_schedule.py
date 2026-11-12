"""
TradingGuard HITL - Export Authentic Bitcoin (BTCUSD) Quant Orders for MT5 Strategy Tester
Calibrated to $2,000 USD Capital with 0.25% Risk per trade ($5.00 USD).
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


def export_btc_schedule(capital: float = 2000.0, risk_pct: float = 0.25):
    if not SOURCE_CSV.exists():
        raise FileNotFoundError(f"Source CSV not found: {SOURCE_CSV}")

    df = pd.read_csv(SOURCE_CSV)
    
    # Filter for BTCUSD within 2026 audit window (2026-02-01 to 2026-11-05)
    btc = df[(df["symbol"] == "BTCUSD") & (df["entry_datetime"] >= "2026-02-01") & (df["entry_datetime"] <= "2026-11-05")].copy()
    btc.sort_values(by="entry_datetime", inplace=True)

    risk_usd = capital * (risk_pct / 100.0) # $5.00 USD for 0.25% on $2,000
    lines = ["ID,Symbol,Type,TriggerTime,Entry,SL,TP,Lot,TTL\n"]

    rule_ttls = {
        "R14_015": 180,  # 36 bars * 5 min
        "R14_024": 240,  # 48 bars * 5 min
        "R14_010": 240,  # 48 bars * 5 min
    }

    for idx, row in btc.reset_index(drop=True).iterrows():
        entry = round(float(row["entry_price"]), 2)
        sl = round(float(row["sl_price"]), 2)
        tp = round(float(row["tp_price"]), 2)
        direction = str(row["direction"]).upper()
        o_type = "SELL" if direction == "SELL" else "BUY"

        risk_pts = abs(entry - sl)
        if risk_pts <= 0:
            risk_pts = 100.0

        # Contract size is 1.0 BTC, volume_min=0.01, volume_step=0.01
        lot = round(risk_usd / risk_pts, 2)
        lot = max(0.01, min(lot, 1.0))

        rule_id = str(row["rule_id"])
        ttl = rule_ttls.get(rule_id, 240)

        # Format trigger time as YYYY.MM.DD HH:MM:SS
        t_str = str(row["entry_datetime"]).replace("-", ".")
        o_id = f"ORD-BTC-{t_str[:10].replace('.', '')}-{idx+1:04d}"

        line = f"{o_id},BTCUSD,{o_type},{t_str},{entry:.2f},{sl:.2f},{tp:.2f},{lot:.2f},{ttl}\n"
        lines.append(line)

    local_out = BASE_DIR / "orders_schedule_btc.csv"
    with open(local_out, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"✅ Exported {len(lines) - 1} BTCUSD orders to {local_out.name}")
    print(f"   Capital: ${capital:.2f} | Risk per Trade: ${risk_usd:.2f} ({risk_pct}%)")

    # Sync to MT5 directories
    for dest_dir in [COMMON_FILES, TERMINAL_FILES]:
        if dest_dir.exists():
            target = dest_dir / "orders_schedule.csv"
            shutil.copy2(local_out, target)
            print(f"   -> Synced to: {target}")


if __name__ == "__main__":
    export_btc_schedule()
