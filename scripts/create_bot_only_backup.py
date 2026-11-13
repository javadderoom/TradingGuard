"""
TradingGuard — Bot Only Package Utility
Packages exclusively the live trading bot runtime:
- hitl/ (bot, live radar, mt5 engine, watchdog, council, memory)
- config, .env, requirements.txt, HOW_TO_RUN_SCRIPTS.md
- Produces a lightweight (< 2 MB) standalone zip
"""

import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ZIP = ROOT.parent / "TradingGuard_Bot_Only.zip"

EXCLUDE_DIRS = {
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "dist",
    ".git",
    "cache",
    "soli_chrome_profile",
}

EXCLUDE_EXTENSIONS = {
    ".parquet",
    ".pyc",
    ".pyo",
    ".pyd",
    ".zip",
    ".log",
}

INCLUDE_ROOT_FILES = [
    ".env",
    "requirements.txt",
    "docs/HOW_TO_RUN_SCRIPTS.md",
    "docs/SYSTEM_EXECUTION_MIRROR.md",
]

def create_bot_backup() -> Path:
    print(f"Packaging Bot-Only version from {ROOT}...")
    total_files = 0
    total_uncompressed = 0

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        # Include hitl/
        hitl_dir = ROOT / "hitl"
        for dirpath, dirnames, filenames in os.walk(hitl_dir):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".git")]
            for f in filenames:
                ext = os.path.splitext(f)[1].lower()
                if ext in EXCLUDE_EXTENSIONS:
                    continue
                
                full_path = Path(dirpath) / f
                rel_path = full_path.relative_to(ROOT)
                
                if any(part in EXCLUDE_DIRS for part in rel_path.parts):
                    continue
                    
                zipf.write(full_path, arcname=str(rel_path))
                total_files += 1
                total_uncompressed += full_path.stat().st_size

        # Include root helper files
        for rel in INCLUDE_ROOT_FILES:
            full_path = ROOT / rel
            if full_path.exists() and full_path.is_file():
                zipf.write(full_path, arcname=rel)
                total_files += 1
                total_uncompressed += full_path.stat().st_size

    zip_size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
    uncompressed_mb = total_uncompressed / (1024 * 1024)

    print("\n" + "=" * 60)
    print("  TRADINGGUARD BOT-ONLY PACKAGE COMPLETE")
    print("=" * 60)
    print(f"Destination:    {OUTPUT_ZIP}")
    print(f"Total files:    {total_files}")
    print(f"Uncompressed:   {uncompressed_mb:.2f} MB")
    print(f"Zip File Size:  {zip_size_mb:.2f} MB")
    print("=" * 60)
    return OUTPUT_ZIP

if __name__ == "__main__":
    create_bot_backup()
