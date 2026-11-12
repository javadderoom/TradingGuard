"""
TradingGuard HITL - Native MetaTrader 5 Strategy Tester Runner
Runs authentic full-year 2026 Strategy Tester executions on XAUUSD_o and GBPUSD_o.
Parses native MT5 tester reports and logs.
"""

import os
import sys
import time
import shutil
import datetime
import subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TERMINAL_EXE = r"C:\Program Files\LiteFinance MT5 Terminal\terminal64.exe"
DATA_PATH = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB")
TESTER_INI = DATA_PATH / "tester.ini"
TESTER_LOGS_DIR = DATA_PATH / "Tester" / "logs"
COMMON_FILES = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
REPORT_OUTPUT_DIR = BASE_DIR / "backtest_results" / "mt5_native_reports"
REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def create_tester_ini(
    symbol: str,
    from_date: str = "2026.02.01",
    to_date: str = "2026.11.04",
    report_name: str = "TradingGuard_Report",
    shutdown: int = 1,
    model: int = 0,
    deposit: int = 2000
) -> Path:
    ini_content = f"""[Common]
[Tester]
Expert=TradingGuard_Executor.ex5
Symbol={symbol}
Period=M1
Optimization=0
Model={model}
FromDate={from_date}
ToDate={to_date}
ForwardMode=0
Deposit={deposit}
Currency=USD
ProfitInPips=0
Leverage=100
ExecutionMode=100
OptimizationCriterion=0
Visual=0
Report={report_name}
ReplaceReport=1
ShutdownTerminal={shutdown}
[TesterInputs]
InpOrdersFile=orders_schedule.csv
InpMagicNumber=777001||777001||1||7770010||N
"""
    with open(TESTER_INI, "w", encoding="ascii") as f:
        f.write(ini_content)
    print(f"📄 Created tester.ini for {symbol} ({from_date} -> {to_date})")
    return TESTER_INI


def run_tester(timeout_sec: int = 300) -> bool:
    print(f"🚀 Launching MetaTrader 5 Strategy Tester: {TERMINAL_EXE} /config:{TESTER_INI}")
    t0 = time.time()
    try:
        proc = subprocess.run(
            [TERMINAL_EXE, f"/config:{TESTER_INI}"],
            timeout=timeout_sec,
            capture_output=True,
            text=True
        )
        elapsed = time.time() - t0
        print(f"⏱️ MT5 Strategy Tester finished in {elapsed:.2f} seconds (Exit Code: {proc.returncode})")
        return True
    except subprocess.TimeoutExpired:
        print(f"❌ MT5 Strategy Tester timed out after {timeout_sec} seconds")
        return False
    except Exception as e:
        print(f"❌ Error launching MT5 Strategy Tester: {e}")
        return False


def find_latest_tester_log() -> str:
    log_files = list(TESTER_LOGS_DIR.glob("*.log"))
    if not log_files:
        # Check Agent logs
        agent_dir = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Tester\065434634B76DD288A1DDF20131E8DDB")
        log_files = list(agent_dir.glob("Agent-*/logs/*.log"))
    
    if not log_files:
        return ""
    log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    latest = log_files[0]
    print(f"📋 Reading latest tester log: {latest}")
    try:
        content = latest.read_text(encoding="utf-16le", errors="ignore")
    except Exception:
        content = latest.read_text(encoding="utf-8", errors="ignore")
    return content


def find_generated_report(report_name: str) -> Path:
    candidates = [
        DATA_PATH / f"{report_name}.htm",
        DATA_PATH / f"{report_name}.html",
        DATA_PATH / "reports" / f"{report_name}.htm",
        Path(TERMINAL_EXE).parent / f"{report_name}.htm",
        BASE_DIR / f"{report_name}.htm",
        DATA_PATH / "Tester" / f"{report_name}.htm"
    ]
    for c in candidates:
        if c.exists():
            dest = REPORT_OUTPUT_DIR / c.name
            shutil.copy2(c, dest)
            print(f"📊 Found Report: {c} -> Copied to: {dest}")
            return dest
    return None


def run_full_audit_for_symbol(symbol: str, deposit: int = 2000):
    print("=" * 80)
    print(f"🏛️ TRADINGGUARD HITL - NATIVE MT5 STRATEGY TESTER EXECUTION: {symbol} (Deposit: ${deposit})")
    print("=" * 80)

    report_name = f"TradingGuard_{symbol}_Report"
    create_tester_ini(symbol=symbol, report_name=report_name, shutdown=1, deposit=deposit)
    
    success = run_tester(timeout_sec=300)
    if not success:
        print(f"❌ Test failed for {symbol}")
        return

    # Inspect logs
    time.sleep(1)
    log_content = find_latest_tester_log()
    if log_content:
        lines = log_content.splitlines()
        print(f"\n--- Strategy Tester Log Snippet (Last 25 lines) ---")
        for line in lines[-25:]:
            print(line)

    report_path = find_generated_report(report_name)
    if report_path:
        print(f"🎉 Report successfully saved to: {report_path}")
    else:
        print(f"⚠️ Report file {report_name}.htm not found in default locations. Checking directory...")
        for p in DATA_PATH.glob("*Report*"):
            print(f"  Found matching file in DATA_PATH: {p}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD_o"
    run_full_audit_for_symbol(target)
