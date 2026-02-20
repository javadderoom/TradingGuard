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

from app.config import (
    NEWS_API_KEY,
    NEWS_PROXY_URL,
    NEWS_TIME_OFFSET_MINUTES,
    get_tehran_now,
)

log = logging.getLogger(__name__)


class NewsEvent(NamedTuple):
    time: datetime
    currency: str
    event: str
    impact: str


API_URL = "https://www.jblanked.com/news/api/mql5/calendar/today/?currency=USD&impact=High"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "news_cache.json")


def fetch_high_impact_news(hours_ahead: int = 24) -> list[NewsEvent]:
    """Fetch high-impact USD news events, using cache if available.

    Default lookahead is 24h so the app can show the full day's events.
    """
    if not NEWS_API_KEY:
        log.warning("No NEWS_API_KEY configured in config.py")
        return []
    
    cached = _load_cache()
    if cached is not None:
        filtered = _filter_by_time(cached, hours_ahead)
        log.info(
            "Using cached news data: total=%d filtered=%d lookahead=%dh",
            len(cached),
            len(filtered),
            hours_ahead,
        )
        return filtered
    
    events = _fetch_from_api()
    if events is None:
        return []
    _save_cache(events)
    filtered = _filter_by_time(events, hours_ahead)
    log.info(
        "News filter result: total=%d filtered=%d lookahead=%dh",
        len(events),
        len(filtered),
        hours_ahead,
    )
    return filtered


def _fetch_from_api() -> list[NewsEvent] | None:
    """Fetch today's calendar from JBlanked API.
    Returns None when request fails; otherwise returns parsed events
    (which may be an empty list).
    """
    data = _request_calendar_data()
    if data is None:
        return None

    events = []
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
            if NEWS_TIME_OFFSET_MINUTES:
                event_time = event_time + timedelta(minutes=NEWS_TIME_OFFSET_MINUTES)

            events.append(NewsEvent(
                time=event_time,
                currency=currency,
                event=item.get("Name", ""),
                impact=impact
            ))
        except (ValueError, KeyError, TypeError):
            continue

    log.info(
        "Fetched %d high-impact USD news events from API (offset=%d min)",
        len(events),
        NEWS_TIME_OFFSET_MINUTES,
    )
    return events


def _request_calendar_data() -> list[dict] | None:
    """Request raw news data with resilient proxy handling."""
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {NEWS_API_KEY}",
        }
    except Exception as exc:
        log.warning("Failed to prepare request headers: %s", exc)
        return None

    attempts = []
    if NEWS_PROXY_URL:
        attempts.append(
            ("configured-proxy", False, {"http": NEWS_PROXY_URL, "https": NEWS_PROXY_URL})
        )
    attempts.append(("environment-proxy", True, None))
    attempts.append(("direct", False, {}))

    for mode, trust_env, proxies in attempts:
        session = requests.Session()
        session.trust_env = trust_env
        try:
            response = session.get(API_URL, headers=headers, timeout=15, proxies=proxies)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ProxyError as exc:
            log.warning("News API proxy failed (%s): %s", mode, exc)
            continue
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                body_text = ""
                try:
                    body_text = (exc.response.text or "").strip().lower()
                except Exception:
                    body_text = ""

                if "requires credits" in body_text or "do not have any" in body_text:
                    log.error(
                        "News API key is valid, but account credits are empty. "
                        "Top up at https://www.jblanked.com/api/billing/"
                    )
                else:
                    log.error(
                        "Invalid API key or unauthorized API access. "
                        "Check key/account at https://www.jblanked.com/profile/"
                    )
            else:
                log.warning("News API HTTP error (%s): %s", mode, exc)
            return None
        except Exception as exc:
            log.warning("News API request failed (%s): %s", mode, exc)
            continue
        finally:
            session.close()

    log.warning("All News API connection attempts failed")
    return None


def _filter_by_time(events: list[NewsEvent], hours_ahead: int) -> list[NewsEvent]:
    """Filter events to only those within the time window."""
    now = get_tehran_now()
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
        cached_offset = cache.get("offset_minutes")
        
        if not cached_date or not cached_events:
            return None
        
        cache_date = datetime.fromisoformat(cached_date).date()
        if cache_date != get_tehran_now().date():
            log.info("News cache is from %s, refreshing", cache_date)
            return None
        # Legacy cache entries had no offset metadata and may contain
        # previously shifted times; force refresh once to avoid stale bias.
        if cached_offset is None:
            log.info("News cache has no offset metadata, refreshing")
            return None
        if cached_offset is not None and int(cached_offset) != NEWS_TIME_OFFSET_MINUTES:
            log.info(
                "News cache offset mismatch (cache=%s, current=%s), refreshing",
                cached_offset,
                NEWS_TIME_OFFSET_MINUTES,
            )
            return None
        
        events = []
        for e in cached_events:
            cached_time = datetime.fromisoformat(e["time"])
            events.append(NewsEvent(
                time=cached_time,
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
            "date": get_tehran_now().isoformat(),
            "offset_minutes": NEWS_TIME_OFFSET_MINUTES,
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
    now = get_tehran_now()
    for event in events:
        event_start = event.time - timedelta(minutes=buffer_minutes)
        event_end = event.time + timedelta(minutes=buffer_minutes)
        if event_start <= now <= event_end:
            return True
    return False


def get_next_high_impact_news(events: list[NewsEvent]) -> NewsEvent | None:
    """Get the next upcoming high-impact news event."""
    now = get_tehran_now()
    future_events = [e for e in events if e.time > now]
    if future_events:
        return min(future_events, key=lambda e: e.time)
    return None
