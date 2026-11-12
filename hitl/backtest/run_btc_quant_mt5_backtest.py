"""
TradingGuard HITL - Autonomous MetaTrader 5 Strategy Tester Runner for Bitcoin (BTCUSD) Quant Strategy
Evaluates authentic 1,030 machine-discovered quant orders across 2026.02.01 - 2026.11.05
Initial Deposit: $2,000 USD | Risk: 0.25% ($5.00 USD / trade)
"""

import os
import sys
import time
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TERMINAL_EXE = r"C:\Program Files\LiteFinance MT5 Terminal\terminal64.exe"
DATA_PATH = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB")
TESTER_INI = DATA_PATH / "tester.ini"
REPORT_OUTPUT_DIR = BASE_DIR / "backtest_results" / "mt5_native_reports"
REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def ensure_terminal_closed():
    """Force terminates any open terminal instances to allow Strategy Tester launch."""
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    time.sleep(2)


def create_tester_ini(
    symbol: str = "BTCUSD",
    from_date: str = "2026.02.01",
    to_date: str = "2026.11.05",
    deposit: int = 2000,
    period: str = "M1",
    report_name: str = "TradingGuard_BTCUSD_Quant_Report"
) -> Path:
    ini_content = f"""[Common]
[Tester]
Expert=TradingGuard_Executor.ex5
Symbol={symbol}
Period={period}
Optimization=0
Model=0
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
ShutdownTerminal=1
[TesterInputs]
InpOrdersFile=orders_schedule.csv
InpMagicNumber=777001||777001||1||7770010||N
"""
    with open(TESTER_INI, "w", encoding="ascii") as f:
        f.write(ini_content)
    print(f"📄 Created tester.ini for {symbol} (Deposit: ${deposit}, {from_date} -> {to_date}, Period: {period})")
    return TESTER_INI


def run_btc_quant_test():
    print("=" * 80)
    print("🏛️ AUTONOMOUS MT5 STRATEGY TESTER EXECUTION: BITCOIN (BTCUSD) QUANT")
    print("   Capital: $2,000 USD | Risk: 0.25% per trade ($5.00)")
    print("=" * 80)

    # 1. Close terminal
    print("🛑 Closing running terminal instance...")
    ensure_terminal_closed()

    # 2. Write INI
    create_tester_ini(symbol="BTCUSD", deposit=2000, period="M1", report_name="TradingGuard_BTCUSD_Quant_Report")

    # 3. Launch Strategy Tester
    print(f"🚀 Launching MT5 Strategy Tester: {TERMINAL_EXE} /config:{TESTER_INI}")
    t0 = time.time()
    try:
        proc = subprocess.run(
            [TERMINAL_EXE, f"/config:{TESTER_INI}"],
            timeout=400,
            capture_output=True,
            text=True
        )
        elapsed = time.time() - t0
        print(f"⏱️ MT5 Strategy Tester finished in {elapsed:.2f} seconds (Exit Code: {proc.returncode})")
    except subprocess.TimeoutExpired:
        print("❌ Test timed out after 400s")
        return False
    except Exception as e:
        print(f"❌ Launch error: {e}")
        return False

    # 4. Check report
    report_file = DATA_PATH / "TradingGuard_BTCUSD_Quant_Report.htm"
    if report_file.exists():
        dest = REPORT_OUTPUT_DIR / "TradingGuard_BTCUSD_Quant_Report.htm"
        shutil.copy2(report_file, dest)
        print(f"🎉 SUCCESS! Report saved to: {dest}")

        # Copy any PNG charts
        for p in DATA_PATH.glob("*BTCUSD*Report*.png"):
            dest_png = REPORT_OUTPUT_DIR / p.name
            shutil.copy2(p, dest_png)
            print(f"📊 Copied chart: {p.name}")
        return True
    else:
        print(f"⚠️ Report file not found at {report_file}")
        return False


if __name__ == "__main__":
    run_btc_quant_test()
