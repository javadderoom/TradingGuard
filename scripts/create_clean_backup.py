"""
TradingGuard — Clean Project Backup Utility
Zips the entire codebase while excluding bulky dependencies and caches:
- node_modules, __pycache__, .git, .venv, dist, .pytest_cache
- Large parquet cache files (.parquet) and compiled binaries (.pyc, .pyd)
"""

import os
import zipfile
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_ZIP = ROOT.parent / f"TradingGuard_clean_backup_{TIMESTAMP}.zip"

EXCLUDE_DIRS = {
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "dist",
    ".git",
    "cache",  # backtest_results/cache parquet data
    "soli_chrome_profile",  # Chrome profile cache
}

EXCLUDE_EXTENSIONS = {
    ".parquet",
    ".pyc",
    ".pyo",
    ".pyd",
    ".zip",
    ".log",
}

def create_backup(dest_path: Path = None) -> Path:
    target_zip = dest_path or OUTPUT_ZIP
    print(f"Scanning {ROOT}...")
    total_files = 0
    total_uncompressed_bytes = 0

    with zipfile.ZipFile(target_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".git")]
            
            for f in filenames:
                ext = os.path.splitext(f)[1].lower()
                if ext in EXCLUDE_EXTENSIONS:
                    continue
                
                full_path = Path(dirpath) / f
                rel_path = full_path.relative_to(ROOT)
                
                if any(part in EXCLUDE_DIRS for part in rel_path.parts):
                    continue
                    
                try:
                    size = full_path.stat().st_size
                    zipf.write(full_path, arcname=str(rel_path))
                    total_files += 1
                    total_uncompressed_bytes += size
                except Exception as e:
                    print(f"Skipping {rel_path}: {e}")

    zip_size_mb = target_zip.stat().st_size / (1024 * 1024)
    uncompressed_mb = total_uncompressed_bytes / (1024 * 1024)

    print("\n" + "=" * 60)
    print("  TRADINGGUARD CLEAN BACKUP COMPLETE")
    print("=" * 60)
    print(f"Destination:    {target_zip}")
    print(f"Total files:    {total_files}")
    print(f"Uncompressed:   {uncompressed_mb:.2f} MB")
    print(f"Zip File Size:  {zip_size_mb:.2f} MB")
    print("=" * 60)
    return target_zip

if __name__ == "__main__":
    create_backup()
