"""
TradingGuard HITL - Export Master Production Trades Schedule to MT5
Exports all 149 audited production trades into MetaTrader 5 orders_schedule.csv format.
Supports full portfolio, standalone Gold (XAUUSD_o), and standalone Cable (GBPUSD_o).
"""

import sys
import shutil
import pandas as pd
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CSV_SOURCE = BASE_DIR / "backtest_results" / "master_portfolio_audit" / "master_portfolio_trades_2026.csv"

COMMON_FILES = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
TERMINAL_FILES = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB\MQL5\Files")


def export_schedule(symbol_filter: str = None) -> Path:
    if not CSV_SOURCE.exists():
        raise FileNotFoundError(f"Master trades source not found at: {CSV_SOURCE}")

    df = pd.read_csv(CSV_SOURCE)
    if symbol_filter:
        df = df[df["symbol"].str.contains(symbol_filter, case=False, na=False)].copy()

    lines = ["ID,Symbol,Type,TriggerTime,Entry,SL,TP,Lot,TTL\n"]
    for idx, row in df.iterrows():
        sym = row["symbol"]
        is_xau = "XAU" in sym
        digits = 2 if is_xau else 5
        entry = round(float(row["entry_price"]), digits)
        sl = round(float(row["stop_loss"]), digits)
        risk = round(float(row["risk_pts"]), digits)
        target_rr = float(row["target_rr"])
        direction = str(row["direction"]).upper()

        if direction == "LONG":
            tp = round(entry + (target_rr * risk), digits)
            o_type = "BUY_LIMIT"
        else:
            tp = round(entry - (target_rr * risk), digits)
            o_type = "SELL_LIMIT"

        t_str = f"{row['date'].replace('-', '.')} {int(row['session_hour']):02d}:00:00"
        o_id = f"ORD-{sym[:3]}-{row['date'].replace('-', '')}-{int(row['session_hour']):02d}00-{idx+1:03d}"
        
        # Format string
        if is_xau:
            line = f"{o_id},{sym},{o_type},{t_str},{entry:.2f},{sl:.2f},{tp:.2f},0.01,480\n"
        else:
            line = f"{o_id},{sym},{o_type},{t_str},{entry:.5f},{sl:.5f},{tp:.5f},0.01,480\n"
        lines.append(line)

    suffix = f"_{symbol_filter.lower()}" if symbol_filter else ""
    local_out = BASE_DIR / f"orders_schedule{suffix}.csv"
    with open(local_out, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"✅ Exported {len(lines) - 1} orders to {local_out.name}")

    # Copy to MT5 Common/Files and Terminal/MQL5/Files
    for dest_dir in [COMMON_FILES, TERMINAL_FILES]:
        if dest_dir.exists():
            target_path = dest_dir / "orders_schedule.csv"
            shutil.copy2(local_out, target_path)
            print(f"   -> Synced to: {target_path}")

    return local_out


if __name__ == "__main__":
    filter_arg = sys.argv[1] if len(sys.argv) > 1 else None
    export_schedule(filter_arg)
