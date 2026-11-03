"""
TradingGuard HITL - Native MetaTrader 5 Strategy Tester Bridge
Replaces custom Python mathematical trade simulations with authentic
in-terminal MetaTrader 5 execution via MQL5 Expert Advisor & real ticks.
"""

import os
import csv
import sys
import subprocess
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

TERMINAL_EXE = r"C:\Program Files\LiteFinance MT5 Terminal\terminal64.exe"
DATA_PATH = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB")
FILES_DIR = DATA_PATH / "MQL5" / "Files"
EXPERTS_DIR = DATA_PATH / "MQL5" / "Experts"


class MT5StrategyTesterBridge:
    def __init__(self, terminal_exe: str = TERMINAL_EXE, data_path: Path = DATA_PATH):
        self.terminal_exe = terminal_exe
        self.data_path = data_path
        self.files_dir = data_path / "MQL5" / "Files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.orders_csv = self.files_dir / "orders_schedule.csv"
        self.ini_file = self.data_path / "tester.ini"
        self.report_base = self.data_path / "TradingGuard_Report"

    def write_orders_schedule(self, orders: List[Dict[str, Any]]) -> None:
        """
        Writes planned council orders to MQL5/Files/orders_schedule.csv
        Header: ID,Symbol,Type,TriggerTime,Entry,SL,TP,Lot,TTL
        """
        with open(self.orders_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Symbol", "Type", "TriggerTime", "Entry", "SL", "TP", "Lot", "TTL"])
            for o in orders:
                # Format time as YYYY.MM.DD HH:MM:SS
                t = o["trigger_time"]
                if isinstance(t, (datetime.datetime, datetime.date)):
                    t_str = t.strftime("%Y.%m.%d %H:%M:%S")
                else:
                    t_str = str(t).replace("-", ".")
                
                writer.writerow([
                    o.get("id", "ORD-001"),
                    o.get("symbol", "GBPUSD_o"),
                    o.get("type", "SELL_LIMIT"),
                    t_str,
                    f"{o['entry']:.5f}",
                    f"{o['sl']:.5f}",
                    f"{o['tp']:.5f}",
                    f"{o.get('lot', 0.01):.2f}",
                    int(o.get("ttl_minutes", 75))
                ])

    def generate_tester_ini(
        self,
        symbol: str,
        from_date: datetime.date,
        to_date: datetime.date,
        period: str = "M1",
        deposit: int = 10000,
        currency: str = "USD",
        leverage: int = 100,
        model: int = 1 # 1 = Every tick based on real ticks, 0 = Every tick
    ) -> Path:
        """Generates MT5 tester.ini configuration file."""
        from_str = from_date.strftime("%Y.%m.%d")
        to_str = to_date.strftime("%Y.%m.%d")
        
        ini_content = f"""[Common]
[Tester]
Expert=TradingGuard_Executor.ex5
Symbol={symbol}
Period={period}
Deposit={deposit}
Currency={currency}
Leverage={leverage}
Model={model}
ExecutionMode=0
Optimization=0
FromDate={from_str}
ToDate={to_str}
ForwardMode=0
Report=TradingGuard_Report
ReplaceReport=1
ShutdownTerminal=1
"""
        with open(self.ini_file, "w", encoding="ansi") as f:
            f.write(ini_content)
        return self.ini_file

    def run_strategy_tester(self, timeout_sec: int = 180) -> bool:
        """Launches MT5 Strategy Tester in headless mode."""
        cmd = [self.terminal_exe, f"/config:{self.ini_file}"]
        try:
            proc = subprocess.run(cmd, timeout=timeout_sec, capture_output=True, text=True)
            return True
        except subprocess.TimeoutExpired:
            print("[MT5Tester] Test timed out")
            return False
        except Exception as e:
            print(f"[MT5Tester] Error running MT5 tester: {e}")
            return False

    def parse_report(self) -> Dict[str, Any]:
        """Parses the generated MT5 Strategy Tester report (HTML / XML / HTM)."""
        # Look for TradingGuard_Report.htm or .xml or in terminal directory
        candidates = [
            self.data_path / "TradingGuard_Report.htm",
            self.data_path / "TradingGuard_Report.html",
            self.data_path / "reports" / "TradingGuard_Report.htm",
            Path(TERMINAL_EXE).parent / "TradingGuard_Report.htm"
        ]
        
        report_path = None
        for c in candidates:
            if c.exists():
                report_path = c
                break
                
        if not report_path:
            return {
                "success": False,
                "error": "Report file not found. Terminal may still be running or test produced no trades.",
                "trades": []
            }

        with open(report_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        return {
            "success": True,
            "report_path": str(report_path),
            "content_length": len(content),
            "raw_snippet": content[:1000]
        }
