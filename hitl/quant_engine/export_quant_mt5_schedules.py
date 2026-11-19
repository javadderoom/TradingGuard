"""
TradingGuard HITL - Export Ratified Quant Alpha Schedules to MetaTrader 5 Strategy Tester
Reads backtest_results/quant_discovery/quant_alpha_trade_ledger.csv and quant_alpha_discovery_summary.json.
Generates fully compatible MetaTrader 5 orders_schedule.csv files for:
1. Master Consolidated Quant Portfolio (1,777 trades across XAUUSD, NQ, BTCUSD, GBPUSD).
2. Per-Asset Dedicated Schedules (Gold, Nasdaq 100, Bitcoin, Cable) with AUTO matching.
3. Automatically mirrors files to project root, MetaQuotes Common\\Files, and Terminal MQL5\\Files.
"""

import sys
import shutil
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LEDGER_CSV = BASE_DIR / "backtest_results" / "quant_discovery" / "quant_alpha_trade_ledger.csv"
SUMMARY_JSON = BASE_DIR / "backtest_results" / "quant_discovery" / "quant_alpha_discovery_summary.json"
SCHEDULES_DIR = BASE_DIR / "backtest_results" / "schedules"
SCHEDULES_DIR.mkdir(parents=True, exist_ok=True)

COMMON_FILES = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
TERMINAL_DIRS = [
    Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB"),
    Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\A19DFEF1E80BEC73AB07B83E44201DC0"),
]

# Broker symbol mapping for LiteFinance
BROKER_SYMBOLS = {
    "XAUUSD": "XAUUSD_o",
    "NQ": "NQ_o",
    "BTCUSD": "BTCUSD_o",
    "GBPUSD": "GBPUSD_o",
}

# Precision digits
DECIMAL_DIGITS = {
    "XAUUSD": 2,
    "NQ": 2,
    "BTCUSD": 2,
    "GBPUSD": 5,
}


def load_strategy_metadata() -> Dict[tuple, Dict[str, Any]]:
    """Loads TTL, BE Ratchet, and TP/SL parameters for each ratified rule."""
    if not SUMMARY_JSON.exists():
        print(f"[WARN] Summary JSON not found at {SUMMARY_JSON}")
        return {}

    with open(SUMMARY_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta = {}
    for asset, val in data.items():
        for s in val.get("strategies", []):
            key = (s.get("symbol"), s.get("rule_id"), s.get("direction"))
            meta[key] = {
                "tp_atr_mult": s.get("tp_atr_mult", 3.0),
                "sl_atr_mult": s.get("sl_atr_mult", 1.5),
                "be_ratchet_r": s.get("be_ratchet_r", 1.8),
                "ttl_bars": s.get("ttl_bars", 36),
                "ttl_minutes": s.get("ttl_bars", 36) * 5,
            }
    return meta


def build_schedule_lines(df: pd.DataFrame, meta: Dict[tuple, Dict[str, Any]], symbol_override: str = None, fixed_lot: float = 0.01) -> List[str]:
    """Builds CSV lines matching TradingGuard_Executor.mq5 schema:
    ID,Symbol,Type,TriggerTime,Entry,SL,TP,Lot,TTL,BE_Ratchet
    """
    lines = ["ID,Symbol,Type,TriggerTime,Entry,SL,TP,Lot,TTL,BE_Ratchet\n"]

    for idx, row in df.reset_index(drop=True).iterrows():
        raw_sym = str(row["symbol"]).upper()
        rule_id = str(row["rule_id"])
        direction = str(row["direction"]).upper()

        digits = DECIMAL_DIGITS.get(raw_sym, 2)
        entry = round(float(row["entry_price"]), digits)
        sl = round(float(row["sl_price"]), digits)
        tp = round(float(row["tp_price"]), digits)

        # Order Type: BUY or SELL
        o_type = "SELL" if direction == "SELL" else "BUY"

        # Lookup rule metadata
        rule_meta = meta.get((raw_sym, rule_id, direction), {})
        ttl_minutes = rule_meta.get("ttl_minutes", 180)
        be_ratchet = rule_meta.get("be_ratchet_r", 1.8)

        # Convert epoch timestamp to YYYY.MM.DD HH:MM:SS
        entry_ts = int(row["entry_time"])
        dt_utc = datetime.datetime.fromtimestamp(entry_ts, tz=datetime.timezone.utc)
        t_str = dt_utc.strftime("%Y.%m.%d %H:%M:%S")

        # Symbol string
        if symbol_override:
            sym_str = symbol_override
        else:
            sym_str = BROKER_SYMBOLS.get(raw_sym, raw_sym)

        # Order ID
        date_tag = dt_utc.strftime("%Y%m%d")
        o_id = f"Q-{raw_sym[:3]}-{date_tag}-{idx+1:04d}"

        line = f"{o_id},{sym_str},{o_type},{t_str},{entry:.{digits}f},{sl:.{digits}f},{tp:.{digits}f},{fixed_lot:.2f},{ttl_minutes},{be_ratchet:.1f}\n"
        lines.append(line)

    return lines


def export_all_quant_schedules(fixed_lot: float = 0.01):
    """Exports master and per-asset schedules and synchronizes to MT5 directories."""
    if not LEDGER_CSV.exists():
        raise FileNotFoundError(f"Quant trade ledger not found at: {LEDGER_CSV}")

    df_ledger = pd.read_csv(LEDGER_CSV)
    df_ledger.sort_values(by="entry_time", inplace=True)
    meta = load_strategy_metadata()

    print(f"Loaded {len(df_ledger):,d} ratified trades from {LEDGER_CSV.name}")
    print(f"Loaded metadata for {len(meta)} ratified rules.")

    exports: Dict[str, List[str]] = {}

    # 1. Consolidated Master Schedule (All symbols with broker suffix)
    master_lines = build_schedule_lines(df_ledger, meta, symbol_override=None, fixed_lot=fixed_lot)
    master_csv = SCHEDULES_DIR / "orders_schedule_consolidated_quant.csv"
    with open(master_csv, "w", encoding="utf-8") as f:
        f.writelines(master_lines)
    exports["orders_schedule.csv"] = master_lines
    print(f"Created Master Schedule: {master_csv.name} ({len(master_lines) - 1:,d} trades)")

    # 2. Per-Asset Dedicated Schedules (with AUTO so it matches any broker chart symbol)
    for sym in ["XAUUSD", "NQ", "BTCUSD", "GBPUSD"]:
        sub_df = df_ledger[df_ledger["symbol"] == sym].copy()
        if sub_df.empty:
            continue
        
        # Suffix-specific and AUTO versions
        sym_lines_auto = build_schedule_lines(sub_df, meta, symbol_override="AUTO", fixed_lot=fixed_lot)
        asset_csv = SCHEDULES_DIR / f"orders_schedule_{sym.lower()}_quant.csv"
        with open(asset_csv, "w", encoding="utf-8") as f:
            f.writelines(sym_lines_auto)

        exports[f"orders_schedule_{sym.lower()}.csv"] = sym_lines_auto
        print(f"Created {sym} Dedicated Schedule: {asset_csv.name} ({len(sym_lines_auto) - 1:,d} trades, AUTO symbol)")

    # 3. Synchronize to Root
    root_master = BASE_DIR / "orders_schedule.csv"
    with open(root_master, "w", encoding="utf-8") as f:
        f.writelines(master_lines)
    print(f"\nSynchronized canonical root file: {root_master.name}")

    # 4. Synchronize to MT5 Directories
    synced_destinations = []
    if COMMON_FILES.exists():
        synced_destinations.append(COMMON_FILES)

    for t_dir in TERMINAL_DIRS:
        mql5_files = t_dir / "MQL5" / "Files"
        if mql5_files.exists():
            synced_destinations.append(mql5_files)
        
        # Ensure EA .ex5 is present in Experts
        experts_dir = t_dir / "MQL5" / "Experts"
        local_ex5 = BASE_DIR / "mql5" / "TradingGuard_Executor.ex5"
        if experts_dir.exists() and local_ex5.exists():
            target_ex5 = experts_dir / "TradingGuard_Executor.ex5"
            shutil.copy2(local_ex5, target_ex5)
            print(f"Verified/Copied EA: {target_ex5}")

    print(f"\nMirroring schedules to {len(synced_destinations)} MetaTrader 5 directories:")
    for dest in synced_destinations:
        for fname, lines in exports.items():
            target_file = dest / fname
            with open(target_file, "w", encoding="utf-8") as f:
                f.writelines(lines)
            print(f"   -> {target_file}")

    print("\nAll Quantitative MetaTrader 5 schedules prepared and synchronized successfully!")


if __name__ == "__main__":
    export_all_quant_schedules()
