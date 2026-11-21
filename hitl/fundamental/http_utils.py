"""
TradingGuard Fundamental Engine - Resilient HTTP & Atomic Cache Utilities
"""

import json
import logging
import os
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional, Tuple

from hitl.config import TELEGRAM_PROXY

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml,application/json,text/csv;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_text(url: str, timeout: int = 8, prefer_proxy: bool = False) -> Optional[str]:
    """
    Fetches text content from a URL with direct/proxy fallback.
    If prefer_proxy=True (e.g. CFTC endpoints on restricted networks), attempts proxy first.
    """
    openers = []
    direct_opener = urllib.request.build_opener()
    proxy_opener = None
    if TELEGRAM_PROXY:
        proxy_handler = urllib.request.ProxyHandler({
            "http": TELEGRAM_PROXY,
            "https": TELEGRAM_PROXY,
        })
        proxy_opener = urllib.request.build_opener(proxy_handler)

    if prefer_proxy and proxy_opener is not None:
        openers = [("proxy", proxy_opener), ("direct", direct_opener)]
    else:
        openers = [("direct", direct_opener)]
        if proxy_opener is not None:
            openers.append(("proxy", proxy_opener))

    last_err = None
    for mode, opener in openers:
        try:
            req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
            with opener.open(req, timeout=timeout) as resp:
                status = getattr(resp, "status", 200)
                if status == 200:
                    raw = resp.read()
                    return raw.decode("utf-8", errors="replace")
        except Exception as e:
            last_err = f"{mode}:{type(e).__name__}:{e}"

    if last_err:
        logger.debug(f"[HTTP] Failed {url}: {last_err}")
    return None


def fetch_json(url: str, timeout: int = 8, prefer_proxy: bool = False) -> Optional[Any]:
    """Fetches and parses JSON from a URL."""
    txt = fetch_text(url, timeout=timeout, prefer_proxy=prefer_proxy)
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception as e:
        logger.debug(f"[HTTP] JSON decode error for {url}: {e}")
        return None


def read_json_cache(path: Path, ttl_seconds: float) -> Tuple[Optional[Any], bool]:
    """
    Reads JSON cache file.
    Returns (data, is_fresh):
      - (data, True) if file exists, parses cleanly, and age < ttl_seconds
      - (data, False) if file exists and parses cleanly, but age >= ttl_seconds (usable for stale fallback)
      - (None, False) if missing or corrupt
    """
    if not path.exists():
        return None, False
    try:
        mtime = path.stat().st_mtime
        age = time.time() - mtime
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data, (age < ttl_seconds)
    except Exception as e:
        logger.warning(f"[Cache] Failed to read {path}: {e}")
        return None, False


def write_json_atomic(path: Path, data: Any) -> bool:
    """Atomically writes JSON data to disk using a unique temp file replace."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f".{os.getpid()}.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp_path.replace(path)
        return True
    except Exception as e:
        logger.error(f"[Cache] Failed atomic write to {path}: {e}")
        return False
