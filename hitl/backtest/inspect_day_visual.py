"""
TradingGuard HITL - Interactive Visual Backtest Inspector Launcher
Usage:
    python hitl/backtest/inspect_day_visual.py --dates 2026-11-11 2026-11-10
"""

import sys
import webbrowser
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hitl.backtest.export_visual_replay import compile_visual_replay


def main():
    parser = argparse.ArgumentParser(description="Inspect historical trading days visually on chart")
    parser.add_argument(
        "--dates",
        nargs="+",
        default=["2026-11-11", "2026-11-10", "2026-11-09", "2026-11-06", "2026-11-05", "2026-11-04", "2026-11-03", "2026-11-02"],
        help="List of YYYY-MM-DD dates to compile and inspect"
    )
    parser.add_argument("--no-browser", action="store_true", help="Compile without launching system browser")
    args = parser.parse_args()

    out_path = compile_visual_replay(args.dates, symbol="XAUUSD_o", refresh_live=True)
    if not args.no_browser:
        print(f"🌐 Opening interactive chart in browser: {out_path}")
        webbrowser.open(out_path.as_uri())


if __name__ == "__main__":
    main()
