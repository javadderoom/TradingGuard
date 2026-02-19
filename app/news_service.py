"""
TradingGuard — News Service
Fetches high-impact USD news events using JBlanked free API (1 req/day).
Caches results to avoid repeated API calls.
"""

import json
import logging
import os
from datetime import datetime, date, timedelta
from typing import NamedTuple

import requests

from app.config import NEWS_API_KEY

log = logging.getLogger(__name__)


class NewsEvent(NamedTuple):
    time: datetime
    currency: str
    event: str
    impact: str


API_URL = "https://www.jblanked.com/news/api/mql5/calendar/today/?currency=USD&impact=High"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "news_cache.json")


def fetch_high_impact_news(hours_ahead: int = 4) -> list[NewsEvent]:
    """Fetch high-impact USD news events, using cache if available."""
    if not NEWS_API_KEY:
        log.warning("No NEWS_API_KEY configured in config.py")
        return []
    
    cached = _load_cache()
    if cached is not None:
        log.info("Using cached news data")
        return _filter_by_time(cached, hours_ahead)
    
    events = _fetch_from_api()
    if events:
        _save_cache(events)
    return events


def _fetch_from_api() -> list[NewsEvent]:
    """Fetch today's calendar from JBlanked API."""
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {NEWS_API_KEY}",
        }
        response = requests.get(API_URL, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.HTTPError as exc:
        if exc.response.status_code == 401:
            log.error("Invalid API key. Get your free key at https://www.jblanked.com/profile/")
        else:
            log.warning("Failed to fetch news from API: %s", exc)
        return []
    except Exception as exc:
        log.warning("Failed to fetch news from API: %s", exc)
        return []
    
    events = []
    today = date.today()
    
    for item in data:
        try:
            impact = item.get("Impact", "").lower()
            if "high" not in impact:
                continue
            
            currency = item.get("Currency", "")
            if "usd" not in currency.lower():
                continue
            
            date_str = item.get("Date", "")
            if not date_str:
                continue
            
            event_time = datetime.strptime(date_str, "%Y.%m.%d %H:%M:%S")
            
            events.append(NewsEvent(
                time=event_time,
                currency=currency,
                event=item.get("Name", ""),
                impact=impact
            ))
        except (ValueError, KeyError):
            continue
    
    log.info("Fetched %d high-impact USD news events from API", len(events))
    return events


def _filter_by_time(events: list[NewsEvent], hours_ahead: int) -> list[NewsEvent]:
    """Filter events to only those within the time window."""
    now = datetime.now()
    cutoff = now + timedelta(hours=hours_ahead)
    return [e for e in events if now <= e.time <= cutoff]


def _load_cache() -> list[NewsEvent] | None:
    """Load cached news events if fresh."""
    if not os.path.exists(CACHE_FILE):
        return None
    
    try:
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
        
        cached_date = cache.get("date")
        cached_events = cache.get("events", [])
        
        if not cached_date or not cached_events:
            return None
        
        cache_date = datetime.fromisoformat(cached_date).date()
        if cache_date != date.today():
            log.info("News cache is from %s, refreshing", cache_date)
            return None
        
        events = []
        for e in cached_events:
            events.append(NewsEvent(
                time=datetime.fromisoformat(e["time"]),
                currency=e["currency"],
                event=e["event"],
                impact=e["impact"]
            ))
        return events
        
    except Exception as exc:
        log.warning("Failed to load news cache: %s", exc)
        return None


def _save_cache(events: list[NewsEvent]) -> None:
    """Save events to cache file."""
    try:
        cache = {
            "date": datetime.now().isoformat(),
            "events": [
                {
                    "time": e.time.isoformat(),
                    "currency": e.currency,
                    "event": e.event,
                    "impact": e.impact
                }
                for e in events
            ]
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
        log.info("News cache saved")
    except Exception as exc:
        log.warning("Failed to save news cache: %s", exc)


def is_news_active(events: list[NewsEvent], buffer_minutes: int = 30) -> bool:
    """Check if any high-impact news is currently active."""
    now = datetime.now()
    for event in events:
        event_start = event.time - timedelta(minutes=buffer_minutes)
        event_end = event.time + timedelta(minutes=buffer_minutes)
        if event_start <= now <= event_end:
            return True
    return False


def get_next_high_impact_news(events: list[NewsEvent]) -> NewsEvent | None:
    """Get the next upcoming high-impact news event."""
    now = datetime.now()
    future_events = [e for e in events if e.time > now]
    if future_events:
        return min(future_events, key=lambda e: e.time)
    return None
