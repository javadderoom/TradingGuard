"""
TradingGuard HITL - Live TradingView Sentiment & Community Feed
Fetches public TradingView ideas and analyst sentiment for XAUUSD & EURUSD with zero API cost.
Provides the Council of AI Agents with live retail crowd positioning and contrarian intelligence.
"""

import re
import sys
import time
import html
import json
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.config import TELEGRAM_PROXY

CACHE_FILE = BASE_DIR / "analysis_assets" / "tv_sentiment_cache.json"
CACHE_TTL_SECONDS = 3600  # 1 hour cache


def _fetch_html(url: str, timeout: int = 12) -> Optional[str]:
    """Fetches URL with User-Agent header, trying direct first, then local proxy."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    # 1. Try direct request
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return resp.read().decode("utf-8", errors="ignore")
    except Exception as e_direct:
        pass

    # 2. Try proxy if available
    if TELEGRAM_PROXY:
        try:
            proxy_handler = urllib.request.ProxyHandler({
                "http": TELEGRAM_PROXY,
                "https": TELEGRAM_PROXY
            })
            opener = urllib.request.build_opener(proxy_handler)
            req = urllib.request.Request(url, headers=headers)
            with opener.open(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            pass

    return None


def fetch_tradingview_ideas(symbol: str = "XAUUSD") -> List[Dict[str, str]]:
    """
    Parses live public analyst ideas from TradingView for the specified symbol.
    Returns a list of structured idea dictionaries.
    """
    sym = "EURUSD" if "EUR" in symbol.upper() else "XAUUSD"
    url = f"https://www.tradingview.com/symbols/{sym}/ideas/"
    
    # Check cache
    now = time.time()
    cache_data = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                if sym in cache_data and (now - cache_data[sym].get("timestamp", 0) < CACHE_TTL_SECONDS):
                    return cache_data[sym].get("ideas", [])
        except Exception:
            pass

    html_text = _fetch_html(url)
    if not html_text:
        # Fallback to stale cache if network fails
        if sym in cache_data:
            return cache_data[sym].get("ideas", [])
        return []

    articles = re.findall(r'<article[^>]*>(.*?)</article>', html_text, re.DOTALL)
    ideas = []

    for art in articles[:10]:
        # Title
        t_match = re.search(r'<a[^>]+class="[^"]*title[^"]*"[^>]*>(.*?)</a>', art, re.DOTALL)
        if not t_match:
            continue
        title = html.unescape(re.sub(r'<[^>]+>', '', t_match.group(1)).strip())
        if not title or title.upper() == sym:
            # Skip empty or generic symbol titles if better text exists
            pass

        # Author
        author_match = re.search(r'data-username="([^"]+)"', art)
        if not author_match:
            author_match = re.search(r'href="/u/([^/"]+)/"', art)
        author = author_match.group(1) if author_match else "Community Analyst"

        # Sentiment Badge / Keywords
        art_lower = art.lower()
        if "badge-bullish" in art_lower or "long" in art_lower or "buy" in title.lower():
            sentiment = "BULLISH"
        elif "badge-bearish" in art_lower or "short" in art_lower or "sell" in title.lower():
            sentiment = "BEARISH"
        else:
            sentiment = "NEUTRAL"

        # Clean snippet text
        lines = [re.sub(r'<[^>]+>', ' ', line).strip() for line in art.split('\n')]
        lines = [l for l in lines if len(l) > 25 and not l.startswith('{') and 'svg' not in l and not l.startswith('http')]
        snippet = " ".join(lines[:2]).strip()
        snippet = html.unescape(snippet)
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."

        if title and title != sym:
            ideas.append({
                "author": author,
                "title": title,
                "sentiment": sentiment,
                "snippet": snippet
            })

    # Save to cache
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if sym not in cache_data:
            cache_data[sym] = {}
        cache_data[sym] = {
            "timestamp": now,
            "ideas": ideas
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception as e_cache:
        print(f"[Sentiment] Failed to write cache: {e_cache}")

    return ideas


def format_sentiment_summary(symbol: str = "XAUUSD") -> str:
    """
    Returns an institutional summary of retail/community sentiment for the Council prompt.
    """
    sym = "EURUSD" if "EUR" in symbol.upper() else "XAUUSD"
    ideas = fetch_tradingview_ideas(sym)
    
    if not ideas:
        return f"- TradingView Community: Insufficient live feed data. Defaulting to neutral sentiment baseline."

    bullish_count = sum(1 for i in ideas if i["sentiment"] == "BULLISH")
    bearish_count = sum(1 for i in ideas if i["sentiment"] == "BEARISH")
    neutral_count = len(ideas) - bullish_count - bearish_count
    total = len(ideas)

    bull_pct = int((bullish_count / total) * 100) if total > 0 else 50
    bear_pct = int((bearish_count / total) * 100) if total > 0 else 50

    lines = [
        f"TradingView Community Reconnaissance ({sym}):",
        f"• Retail/Community Consensus: {bull_pct}% Bullish | {bear_pct}% Bearish ({neutral_count} Neutral/Mixed)",
        f"• Top Published Community Analyst Ideas:"
    ]

    for idx, idea in enumerate(ideas[:4], 1):
        lines.append(f"  {idx}. [{idea['sentiment']}] \"{idea['title']}\" by @{idea['author']}")
        if idea["snippet"] and idea["snippet"] != idea["title"]:
            lines.append(f"     Argument: {idea['snippet']}")

    return "\n".join(lines)


if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print("--- Testing Gold (XAUUSD) Sentiment Feed ---")
    print(format_sentiment_summary("XAUUSD"))
    print("\n--- Testing Euro (EURUSD) Sentiment Feed ---")
    print(format_sentiment_summary("EURUSD"))
