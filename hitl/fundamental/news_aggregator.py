"""
TradingGuard Fundamental Engine - Layer 2 Multi-Source Live Macro News & Calendar Aggregator
Ingests central bank releases, institutional FX/macro desks, bond/commodity/crypto verticals,
and Google News macro queries via stdlib XML parsing (no feedparser required),
plus upcoming/recently-released economic calendar events.
"""

import concurrent.futures
import datetime
import email.utils
import html
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Set, Tuple

from hitl.config import ASSETS_DIR
from hitl.fundamental.http_utils import fetch_text, read_json_cache, write_json_atomic
from hitl.macro_calendar import get_recent_released_events, get_upcoming_events

logger = logging.getLogger(__name__)

NEWS_CACHE_FILE = ASSETS_DIR / "macro_news_cache.json"
NEWS_TTL_SEC = 15 * 60  # 15 minutes

# Verified live endpoints organized by institutional authority tier (tier 1 wins dedup ties)
MACRO_FEEDS: List[Dict[str, Any]] = [
    # Tier 1: Central Banks & Primary Institutional Macro Desks
    {"name": "Fed Monetary Policy", "tier": 1, "url": "https://www.federalreserve.gov/feeds/press_monetary.xml"},
    {"name": "Bank of England", "tier": 1, "url": "https://www.bankofengland.co.uk/rss/news"},
    {"name": "ForexLive", "tier": 1, "url": "https://www.forexlive.com/feed/news"},
    {"name": "FXStreet", "tier": 1, "url": "https://www.fxstreet.com/rss/news"},
    # Tier 2: Macro, Bonds, Commodities, Equities, Crypto Verticals
    {"name": "Investing Economy", "tier": 2, "url": "https://www.investing.com/rss/news_14.rss"},
    {"name": "Investing Indicators/Bonds", "tier": 2, "url": "https://www.investing.com/rss/news_95.rss"},
    {"name": "Investing Forex", "tier": 2, "url": "https://www.investing.com/rss/news_1.rss"},
    {"name": "Investing Commodities", "tier": 2, "url": "https://www.investing.com/rss/news_11.rss"},
    {"name": "Investing Crypto", "tier": 2, "url": "https://www.investing.com/rss/news_301.rss"},
    {"name": "CNBC Economy", "tier": 2, "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"},
    {"name": "CNBC World", "tier": 2, "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362"},
    # Tier 3: Dynamic Cross-Asset & Geopolitical Macro Search Queries
    {
        "name": "GNews Rates/CB",
        "tier": 3,
        "url": "https://news.google.com/rss/search?q=treasury+yields+OR+federal+reserve+OR+inflation+OR+bond+yields+when:2d&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "GNews Geo/China/Bonds",
        "tier": 3,
        "url": "https://news.google.com/rss/search?q=geopolitics+OR+oil+OR+tariffs+OR+china+stocks+liquidity+OR+sovereign+bonds+when:2d&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "GNews Assets Macro",
        "tier": 3,
        "url": "https://news.google.com/rss/search?q=gold+dollar+OR+nasdaq+OR+bitcoin+macro+when:2d&hl=en-US&gl=US&ceid=US:en",
    },
]

_STOPWORDS = {
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "by", "as",
    "with", "from", "is", "are", "was", "were", "be", "after", "before", "amid",
    "over", "under", "into", "new", "says", "report", "news", "wrap", "update",
}


def _strip_html(raw: str) -> str:
    txt = html.unescape(raw or "")
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _parse_pub_dt(date_str: str) -> Optional[datetime.datetime]:
    """Parses RSS/Atom timestamps (RFC 2822, ISO 8601, YYYY-MM-DD HH:MM:SS) to aware UTC datetime."""
    s = (date_str or "").strip()
    if not s:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        pass
    try:
        iso_s = s.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(iso_s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s[:19], fmt).replace(tzinfo=datetime.timezone.utc)
        except Exception:
            continue
    return None


def _tokenize_title(title: str) -> Set[str]:
    words = re.findall(r"[a-z0-9]{2,}", (title or "").lower())
    return {w for w in words if w not in _STOPWORDS}


def _jaccard_similarity(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def parse_rss_xml(
    xml_text: str,
    source_name: str,
    tier: int,
    now_utc: Optional[datetime.datetime] = None,
    hours_back: int = 48,
) -> List[Dict[str, Any]]:
    """Parses RSS 2.0 or Atom XML string into normalized event items filtered to `hours_back`."""
    if not xml_text or "<" not in xml_text:
        return []
    now = now_utc or datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=hours_back)

    try:
        root = ET.fromstring(xml_text.lstrip("\ufeff \t\r\n"))
    except Exception as e:
        logger.debug(f"[NewsAgg] XML parse failed for {source_name}: {e}")
        return []

    def _local_tag(el: ET.Element) -> str:
        return el.tag.split("}")[-1].lower()

    def _child_text(parent: ET.Element, *names: str) -> str:
        targets = {n.lower() for n in names}
        for child in parent:
            if _local_tag(child) in targets:
                return (child.text or "").strip()
        return ""

    items_out: List[Dict[str, Any]] = []
    # Find <item> (RSS) or <entry> (Atom)
    candidates = [el for el in root.iter() if _local_tag(el) in ("item", "entry")]

    for el in candidates[:25]:
        title = _strip_html(_child_text(el, "title"))
        if not title or len(title) < 8:
            continue

        desc = _strip_html(_child_text(el, "description", "summary", "content"))
        if len(desc) > 220:
            desc = desc[:217] + "..."

        dt_raw = _child_text(el, "pubDate", "published", "updated", "date")
        dt = _parse_pub_dt(dt_raw)
        if dt is None:
            # Keep items without parseable timestamps as low-recency within window only for Tier 1 CB feeds
            if tier == 1:
                dt = now
            else:
                continue

        if dt < cutoff or dt > now + datetime.timedelta(hours=1):
            continue

        age_hours = max(0.0, (now - dt).total_seconds() / 3600.0)
        items_out.append({
            "source": source_name,
            "tier": tier,
            "title": title,
            "summary": desc if desc and desc.lower() != title.lower() else "",
            "published_utc": dt.strftime("%Y-%m-%d %H:%M UTC"),
            "timestamp": dt.timestamp(),
            "age_hours": round(age_hours, 1),
        })

    return items_out


def deduplicate_news_items(items: List[Dict[str, Any]], max_items: int = 40) -> List[Dict[str, Any]]:
    """
    Sorts news items by authority tier ascending (Tier 1 priority) then recency descending,
    and deduplicates near-identical headlines via normalized token Jaccard similarity >= 0.60.
    """
    # Sort within 6-hour buckets so Tier 1 stays prioritized over stale copies, while fresh news stays near top
    ordered = sorted(
        items,
        key=lambda x: (-int(x.get("timestamp", 0)), int(x.get("tier", 3))),
    )
    # Two-pass: ensure Tier 1/2 wins over Tier 3 when timestamps are within 6h of each other
    kept: List[Dict[str, Any]] = []
    kept_tokens: List[Tuple[Set[str], Dict[str, Any]]] = []

    for item in ordered:
        toks = _tokenize_title(item.get("title", ""))
        dup_idx = None
        for idx, (existing_toks, existing_item) in enumerate(kept_tokens):
            if _jaccard_similarity(toks, existing_toks) >= 0.60:
                dup_idx = idx
                break
        if dup_idx is None:
            kept.append(item)
            kept_tokens.append((toks, item))
        else:
            # Prefer higher-authority (lower tier number) source when duplicate detected
            prev = kept[dup_idx]
            if item.get("tier", 3) < prev.get("tier", 3) and abs(item.get("timestamp", 0) - prev.get("timestamp", 0)) <= 6 * 3600:
                kept[dup_idx] = item
                kept_tokens[dup_idx] = (toks, item)

    return kept[:max_items]


def _serialize_cal_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(ev)
    if "datetime_tehran" in out and hasattr(out["datetime_tehran"], "isoformat"):
        out["datetime_tehran"] = out["datetime_tehran"].isoformat()
    return out


def fetch_global_macro_events(
    hours_back: int = 48,
    max_items: int = 40,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Parallel fetches all macro RSS feeds (15m disk cache), deduplicates headlines,
    and attaches upcoming 72h + recently-released 12h economic calendar prints.
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    raw_items: List[Dict[str, Any]] = []
    feed_health: Dict[str, str] = {}
    used_cache = False

    if not force_refresh:
        cached, fresh = read_json_cache(NEWS_CACHE_FILE, NEWS_TTL_SEC)
        if cached and fresh and cached.get("events"):
            raw_items = cached["events"]
            feed_health = cached.get("feed_health", {})
            used_cache = True

    if not used_cache:
        def _grab(feed: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]], str]:
            xml_txt = fetch_text(feed["url"], timeout=8)
            if not xml_txt:
                return feed["name"], [], "FAIL"
            parsed = parse_rss_xml(xml_txt, feed["name"], feed["tier"], now_utc=now_utc, hours_back=hours_back)
            return feed["name"], parsed, f"OK({len(parsed)})"

        collected: List[Dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            for fname, parsed_list, status in ex.map(_grab, MACRO_FEEDS):
                feed_health[fname] = status
                collected.extend(parsed_list)

        if collected:
            raw_items = deduplicate_news_items(collected, max_items=max_items)
            write_json_atomic(
                NEWS_CACHE_FILE,
                {
                    "fetched_at_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "feed_health": feed_health,
                    "events": raw_items,
                },
            )
        else:
            stale, _ = read_json_cache(NEWS_CACHE_FILE, NEWS_TTL_SEC)
            if stale and stale.get("events"):
                raw_items = stale["events"]
                feed_health = stale.get("feed_health", {})

    upcoming_cal = [_serialize_cal_event(e) for e in get_upcoming_events("ALL", hours_ahead=72)]
    recent_cal = [_serialize_cal_event(e) for e in get_recent_released_events("ALL", hours_back=12)]

    return {
        "fetched_at_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "events": raw_items[:max_items],
        "upcoming_calendar": upcoming_cal[:20],
        "recent_releases": recent_cal[:15],
        "feed_health": feed_health,
    }
