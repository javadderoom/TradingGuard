import sys
import time
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

TERMINAL_EXE = r"C:\Program Files\LiteFinance MT5 Terminal\terminal64.exe"
DATA_PATH = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB")
TESTER_INI = DATA_PATH / "tester.ini"
REPORT_NAME = "TradingGuard_Gold_Today_Report"
REPORT_OUTPUT_DIR = BASE_DIR / "backtest_results" / "mt5_native_reports"
REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from hitl.backtest.run_mt5_native_backtest import create_tester_ini

def run():
    print("🛑 Closing running terminal64 instances to allow headless Strategy Tester execution...")
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    time.sleep(2)

    # MT5 Strategy Tester requires FromDate in past (e.g. 2026.11.01) up to today (2026.11.11)
    create_tester_ini(
        symbol="XAUUSD_o",
        from_date="2026.11.01",
        to_date="2026.11.11",
        report_name=REPORT_NAME,
        shutdown=1,
        deposit=2000
    )

    print(f"🚀 Launching MT5 Strategy Tester: {TERMINAL_EXE} /config:{TESTER_INI}")
    t0 = time.time()
    try:
        proc = subprocess.run([TERMINAL_EXE, f"/config:{TESTER_INI}"], timeout=180, capture_output=True, text=True)
        elapsed = time.time() - t0
        print(f"⏱️ MT5 Strategy Tester finished in {elapsed:.2f} seconds (Exit Code: {proc.returncode})")
    except subprocess.TimeoutExpired:
        print("❌ MT5 Strategy Tester timed out!")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Search for generated report
    candidates = [
        DATA_PATH / f"{REPORT_NAME}.htm",
        DATA_PATH / f"{REPORT_NAME}.html",
        DATA_PATH / "reports" / f"{REPORT_NAME}.htm",
        Path(TERMINAL_EXE).parent / f"{REPORT_NAME}.htm",
        BASE_DIR / f"{REPORT_NAME}.htm",
        DATA_PATH / "Tester" / f"{REPORT_NAME}.htm"
    ]
    found = None
    for c in candidates:
        if c.exists():
            dest = REPORT_OUTPUT_DIR / c.name
            shutil.copy2(c, dest)
            print(f"📊 Report found: {c} -> Copied to: {dest}")
            found = dest
            break

    if not found:
        print("🔍 Searching DATA_PATH for recent reports:")
        for p in DATA_PATH.glob("*Report*.htm*"):
            print(f"   Found: {p}")
            dest = REPORT_OUTPUT_DIR / p.name
            shutil.copy2(p, dest)
            found = dest

    # Relaunch GUI terminal
    print("🔄 Relaunching LiteFinance MT5 Terminal GUI in background...")
    subprocess.Popen([TERMINAL_EXE])
    print("✅ LiteFinance MT5 Terminal GUI restarted.")

    return found

if __name__ == "__main__":
    run()
