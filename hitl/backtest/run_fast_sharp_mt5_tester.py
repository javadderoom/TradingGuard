"""
TradingGuard HITL - Autonomous Native MetaTrader 5 Strategy Tester Runner
Runs authentic, in-terminal Strategy Tester executions for Fast & Sharp Market Setups
(SETUP-ARCH-017 ORB and SETUP-ARCH-018 Judas Reversal in Range)
across XAUUSD_o, NQ, and GBPUSD_o on LiteFinance MT5.
Parses native MT5 reports and archives certified broker reports & equity curves.
"""

import os
import re
import sys
import time
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TERMINAL_EXE = r"C:\Program Files\LiteFinance MT5 Terminal\terminal64.exe"
DATA_PATH = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB")
TESTER_INI = DATA_PATH / "tester.ini"
TESTER_LOGS_DIR = DATA_PATH / "Tester" / "logs"
REPORT_OUTPUT_DIR = BASE_DIR / "backtest_results" / "mt5_native_reports"
REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def ensure_terminal_closed():
    """Force terminates running terminal and tester agents to allow Strategy Tester execution."""
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"], capture_output=True)
    # Ensure port 3000 is not blocked by third-party processes (e.g. Next.js)
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue).OwningProcess"],
            capture_output=True, text=True
        )
        pids = set(res.stdout.strip().split())
        for pid in pids:
            if pid and pid.isdigit():
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    except Exception:
        pass
    time.sleep(3)


def create_tester_ini(
    symbol: str,
    from_date: str = "2026.01.01",
    to_date: str = "2026.11.16",
    deposit: int = 1000,
    period: str = "M1",
    model: int = 0,
    report_name: str = "TradingGuard_FastSharp_Report"
) -> Path:
    ini_content = f"""[Common]
[Tester]
Expert=TradingGuard_Executor.ex5
Symbol={symbol}
Period={period}
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
ShutdownTerminal=1
[TesterInputs]
InpOrdersFile=orders_schedule.csv
InpMagicNumber=777001||777001||1||7770010||N
"""
    with open(TESTER_INI, "w", encoding="ascii") as f:
        f.write(ini_content)
    print(f"📄 Created tester.ini for {symbol} (Period={period}, Deposit=${deposit}, {from_date} -> {to_date})")
    return TESTER_INI


def parse_mt5_html_report(report_path: Path) -> Dict[str, Any]:
    """Parses native MT5 HTML Strategy Tester report into structured dictionary."""
    if not report_path.exists():
        return {"error": f"Report file not found: {report_path}"}

    # MetaTrader 5 outputs reports in UTF-16 LE
    content = ""
    for enc in ["utf-16", "utf-8", "cp1252"]:
        try:
            with open(report_path, "r", encoding=enc, errors="ignore") as f:
                content = f.read()
            if "Strategy Tester Report" in content or "Total Net Profit" in content:
                break
        except Exception:
            continue

    html = content
    metrics = {}
    patterns = {
        "symbol": r"Symbol:</td>\s*<td[^>]*><b>(.*?)</b>",
        "period": r"Period:</td>\s*<td[^>]*><b>(.*?)</b>",
        "deposit": r"Initial Deposit:</td>\s*<td[^>]*><b>(.*?)</b>",
        "total_net_profit": r"Total Net Profit:</td>\s*<td[^>]*><b>(.*?)</b>",
        "gross_profit": r"Gross Profit:</td>\s*<td[^>]*><b>(.*?)</b>",
        "gross_loss": r"Gross Loss:</td>\s*<td[^>]*><b>(.*?)</b>",
        "profit_factor": r"Profit Factor:</td>\s*<td[^>]*><b>(.*?)</b>",
        "expected_payoff": r"Expected Payoff:</td>\s*<td[^>]*><b>(.*?)</b>",
        "abs_drawdown": r"Balance Drawdown Absolute:</td>\s*<td[^>]*><b>(.*?)</b>",
        "max_drawdown": r"Balance Drawdown Maximal:</td>\s*<td[^>]*><b>(.*?)</b>",
        "rel_drawdown": r"Balance Drawdown Relative:</td>\s*<td[^>]*><b>(.*?)</b>",
        "total_trades": r"Total Trades:</td>\s*<td[^>]*><b>(.*?)</b>",
        "profit_trades": r"Profit Trades \(% of total\):</td>\s*<td[^>]*><b>(.*?)</b>",
        "loss_trades": r"Loss Trades \(% of total\):</td>\s*<td[^>]*><b>(.*?)</b>",
        "short_trades": r"Short Trades \(won %\):</td>\s*<td[^>]*><b>(.*?)</b>",
        "long_trades": r"Long Trades \(won %\):</td>\s*<td[^>]*><b>(.*?)</b>",
        "history_quality": r"History Quality:</td>\s*<td[^>]*><b>(.*?)</b>",
        "bars": r"Bars:</td>\s*<td[^>]*><b>(.*?)</b>",
        "ticks": r"Ticks:</td>\s*<td[^>]*><b>(.*?)</b>",
    }

    for key, pattern in patterns.items():
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            val = m.group(1).replace("&nbsp;", " ").strip()
            metrics[key] = val
        else:
            metrics[key] = "N/A"

    return metrics


def run_single_symbol_backtest(
    symbol: str,
    from_date: str = "2026.01.01",
    to_date: str = "2026.11.16",
    period: str = "M1",
    deposit: int = 1000,
    timeout_sec: int = 900
) -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print(f"🚀 RUNNING MT5 STRATEGY TESTER: {symbol} (Period={period}, Deposit=${deposit})")
    print(f"   Date Range: {from_date} -> {to_date}")
    print("=" * 80)

    # 1. Close any running terminal
    ensure_terminal_closed()

    # 2. Write INI
    report_name = f"TradingGuard_FastSharp_{symbol}_Report"
    create_tester_ini(
        symbol=symbol,
        from_date=from_date,
        to_date=to_date,
        deposit=deposit,
        period=period,
        model=0,
        report_name=report_name
    )

    # 3. Launch Strategy Tester
    cmd = [TERMINAL_EXE, f"/config:{TESTER_INI}"]
    print(f"Executing: {' '.join(cmd)}")
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, timeout=timeout_sec, capture_output=True, text=True)
        elapsed = time.time() - t0
        print(f"⏱️ MT5 Strategy Tester finished in {elapsed:.2f} seconds (Exit Code: {proc.returncode})")
    except subprocess.TimeoutExpired:
        print(f"❌ MT5 Strategy Tester timed out after {timeout_sec}s")
        ensure_terminal_closed()
        return {"error": "Timeout"}
    except Exception as e:
        print(f"❌ Launch error: {e}")
        return {"error": str(e)}

    # 4. Check for generated HTML report
    report_file = DATA_PATH / f"{report_name}.htm"
    if not report_file.exists():
        # Check alternative report filenames
        report_file_html = DATA_PATH / f"{report_name}.html"
        if report_file_html.exists():
            report_file = report_file_html

    if not report_file.exists():
        print(f"⚠️ Report file not found in {DATA_PATH}. Checking latest log...")
        if TESTER_LOGS_DIR.exists():
            logs = sorted(TESTER_LOGS_DIR.glob("*.log"), key=os.path.getmtime, reverse=True)
            if logs:
                print(f"Latest Tester Log ({logs[0].name}):")
                try:
                    with open(logs[0], "r", encoding="utf-16", errors="ignore") as lf:
                        print("".join(lf.readlines()[-30:]))
                except Exception:
                    pass
        return {"error": "Report not generated"}

    # Copy report and associated chart images to REPORT_OUTPUT_DIR
    dest_report = REPORT_OUTPUT_DIR / f"{report_name}.htm"
    shutil.copy2(report_file, dest_report)
    print(f"✅ Saved HTML Report: {dest_report}")

    # Copy associated chart images (e.g. -holding.png, -hst.png, -mfemae.png, .png)
    base_stem = report_name
    for img in DATA_PATH.glob(f"{base_stem}*.png"):
        dest_img = REPORT_OUTPUT_DIR / img.name
        shutil.copy2(img, dest_img)
        print(f"   -> Copied chart: {dest_img.name}")

    # Parse and return metrics
    metrics = parse_mt5_html_report(dest_report)
    metrics["symbol"] = symbol
    metrics["report_path"] = str(dest_report)
    metrics["elapsed_sec"] = round(time.time() - t0, 1)

    print(f"\n--- METATRADER 5 RESULTS: {symbol} ---")
    print(f"History Quality: {metrics.get('history_quality')} | Bars: {metrics.get('bars')} | Ticks: {metrics.get('ticks')}")
    print(f"Total Trades:    {metrics.get('total_trades')}")
    print(f"Profit Trades:   {metrics.get('profit_trades')}")
    print(f"Loss Trades:     {metrics.get('loss_trades')}")
    print(f"Total Net Profit:${metrics.get('total_net_profit')} USD")
    print(f"Gross Profit:    ${metrics.get('gross_profit')} USD")
    print(f"Gross Loss:      ${metrics.get('gross_loss')} USD")
    print(f"Profit Factor:   {metrics.get('profit_factor')}")
    print(f"Expected Payoff: ${metrics.get('expected_payoff')}")
    print(f"Max Drawdown:    {metrics.get('max_drawdown')}")
    print(f"Long Trades:     {metrics.get('long_trades')}")
    print(f"Short Trades:    {metrics.get('short_trades')}")

    return metrics


def run_portfolio_mt5_backtests(from_date: str = "2026.01.01", to_date: str = "2026.11.16"):
    symbols = ["XAUUSD_o", "NQ", "GBPUSD_o"]
    results = {}

    for sym in symbols:
        res = run_single_symbol_backtest(
            symbol=sym,
            from_date=from_date,
            to_date=to_date,
            period="M1",
            deposit=1000,
            timeout_sec=900
        )
        results[sym] = res
        time.sleep(3)

    print("\n" + "=" * 80)
    print("🏆 METATRADER 5 STRATEGY TESTER MULTI-ASSET PORTFOLIO AUDIT COMPLETE")
    print("=" * 80)
    for sym, m in results.items():
        if "error" in m:
            print(f"{sym:10s}: FAILED - {m['error']}")
        else:
            print(f"{sym:10s}: Net Profit: ${m.get('total_net_profit')} | PF: {m.get('profit_factor')} | Trades: {m.get('total_trades')} | Max DD: {m.get('max_drawdown')}")

    # Re-launch terminal in normal mode to keep MT5 background services running
    print("\nRestarting MT5 terminal in live mode...")
    subprocess.Popen([TERMINAL_EXE])


if __name__ == "__main__":
    from_d = sys.argv[1] if len(sys.argv) > 1 else "2026.01.01"
    to_d = sys.argv[2] if len(sys.argv) > 2 else "2026.11.16"
    run_portfolio_mt5_backtests(from_date=from_d, to_date=to_d)
