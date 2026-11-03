"""
TradingGuard HITL - Zero-Cost Macro & Fundamental Calendar Engine
Fetches, caches, and parses high-impact economic events (FOMC, NFP, CPI, Rates)
from official public feeds via local proxy, converted to Tehran local time.
"""

import os
import sys
import json
import time
import datetime
import urllib.request
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.config import TELEGRAM_PROXY, ASSETS_DIR

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CACHE_FILE = ASSETS_DIR / "calendar_cache.json"
CACHE_TTL_SECONDS = 7200 # 2 hours
TEHRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30))


def fetch_calendar_data(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Fetches economic calendar JSON using local proxy, cached for 2 hours."""
    now = time.time()
    
    # Return from cache if fresh
    if not force_refresh and CACHE_FILE.exists():
        try:
            mtime = CACHE_FILE.stat().st_mtime
            if now - mtime < CACHE_TTL_SECONDS:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[Macro Calendar] Cache read error: {e}")

    # Fetch from public endpoint via configured proxy
    try:
        proxies = {}
        if TELEGRAM_PROXY:
            proxies = {"http": TELEGRAM_PROXY, "https": TELEGRAM_PROXY}
            
        proxy_handler = urllib.request.ProxyHandler(proxies)
        opener = urllib.request.build_opener(proxy_handler)
        req = urllib.request.Request(
            CALENDAR_URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        
        with opener.open(req, timeout=12) as resp:
            content = resp.read().decode("utf-8")
            data = json.loads(content)
            
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            return data
    except Exception as e:
        print(f"[Macro Calendar] Fetch error: {e}")
        # Fallback to stale cache if network fails
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []


def get_symbol_currencies(symbol: str) -> List[str]:
    """Returns relevant macro currencies for a given symbol."""
    sym = symbol.upper()
    if "XAU" in sym or "GOLD" in sym:
        return ["USD"]
    elif "EUR" in sym:
        return ["USD", "EUR"]
    elif "BTC" in sym or "ETH" in sym:
        return ["USD"]
    elif "GBP" in sym:
        return ["USD", "GBP"]
    elif "JPY" in sym:
        return ["USD", "JPY"]
    return ["USD"]


def get_upcoming_events(symbol: str = "XAUUSD", hours_ahead: int = 24) -> List[Dict[str, Any]]:
    """
    Returns high and medium impact events for the symbol happening within the next N hours.
    All timestamps converted to Tehran local time.
    """
    raw_events = fetch_calendar_data()
    if not raw_events:
        return []

    target_currencies = set(get_symbol_currencies(symbol))
    now_tehran = datetime.datetime.now(TEHRAN_TZ)
    horizon_tehran = now_tehran + datetime.timedelta(hours=hours_ahead)

    filtered = []
    for ev in raw_events:
        c = ev.get("country", "")
        impact = ev.get("impact", "")
        if c not in target_currencies:
            continue
        if impact not in ["High", "Medium"]:
            continue

        date_str = ev.get("date", "")
        try:
            ev_dt = datetime.datetime.fromisoformat(date_str).astimezone(TEHRAN_TZ)
        except Exception:
            continue

        # Include if event is today or within the time horizon
        if now_tehran - datetime.timedelta(minutes=30) <= ev_dt <= horizon_tehran:
            diff_min = int((ev_dt - now_tehran).total_seconds() / 60)
            filtered.append({
                "title": ev.get("title", "Unknown"),
                "country": c,
                "impact": impact,
                "datetime_tehran": ev_dt,
                "time_str": ev_dt.strftime("%H:%M"),
                "date_str": ev_dt.strftime("%Y-%m-%d"),
                "forecast": ev.get("forecast", "-"),
                "previous": ev.get("previous", "-"),
                "minutes_away": diff_min
            })

    # Sort chronologically
    filtered.sort(key=lambda x: x["datetime_tehran"])
    return filtered


def check_news_danger(symbol: str = "XAUUSD", window_minutes: int = 20) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Evaluates whether a High-impact economic news release is imminent (within window_minutes)
    or occurred recently (within 5 minutes).
    Returns (is_danger, nearest_event).
    """
    events = get_upcoming_events(symbol, hours_ahead=2)
    for ev in events:
        if ev["impact"] == "High":
            m = ev["minutes_away"]
            # Dangerous if within window_minutes in future or within 5 minutes past
            if -5 <= m <= window_minutes:
                return True, ev
    return False, None


def format_fundamental_summary(symbol: str = "XAUUSD") -> str:
    """Formats a concise fundamental briefing string for AI or human review."""
    events = get_upcoming_events(symbol, hours_ahead=18)
    if not events:
        return "No high/medium impact macro releases scheduled for the next 18 hours."

    lines = []
    for e in events:
        badge = "🔴 HIGH" if e["impact"] == "High" else "🟡 MED"
        away_str = f"in {e['minutes_away']}m" if e["minutes_away"] > 0 else f"{abs(e['minutes_away'])}m ago"
        lines.append(
            f"• [{badge}] {e['time_str']} Tehran ({e['country']}) - {e['title']} "
            f"[Fcst: {e['forecast']} | Prev: {e['previous']}] ({away_str})"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    print("Testing Macro Calendar Module...")
    events = get_upcoming_events("XAUUSD", hours_ahead=72)
    print(f"Upcoming events found: {len(events)}")
    for ev in events[:5]:
        print(f" {ev['date_str']} {ev['time_str']} Tehran | {ev['country']} [{ev['impact']}] {ev['title']} ({ev['minutes_away']}m away)")
    
    danger, ev = check_news_danger("XAUUSD")
    print(f"News Danger Active: {danger} (Event: {ev})")
