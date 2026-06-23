"""Macro-news harvesting: parse configured RSS feeds, filter to gold-relevant
headlines, dedupe, and return them for sentiment inference.

Unlike analytics/, this module does I/O (RSS fetches via feedparser), but the
network boundary is a single seam (`feedparser.parse`) so tests monkeypatch it.
A single failing feed is logged and skipped — collection is best-effort.
"""

import logging

import feedparser

logger = logging.getLogger("ai")

# Configurable in a future phase via system_settings/UI; module defaults for now.
DEFAULT_FEED_URLS: list[str] = [
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "https://www.investing.com/rss/news_285.rss",  # commodities
    "https://www.federalreserve.gov/feeds/press_all.xml",
]

DEFAULT_KEYWORDS: list[str] = [
    "fed", "inflation", "gold reserves", "interest rate", "central bank",
    "recession", "treasury", "dollar", "geopolitical", "cpi", "rate cut",
    "rate hike", "safe haven",
]


def fetch_macroeconomic_headlines(
    feed_urls: list[str] | None = None,
    keywords: list[str] | None = None,
    *,
    max_headlines: int = 30,
) -> list[dict[str, str]]:
    """Return up to `max_headlines` keyword-matching, de-duplicated headlines.

    Each item is {"title": str, "link": str}. Matching is case-insensitive
    substring on the title; dedupe is by normalized (lower/stripped) title,
    first occurrence wins. A feed whose parse raises is skipped, not fatal.
    """
    feed_urls = feed_urls if feed_urls is not None else DEFAULT_FEED_URLS
    keywords = keywords if keywords is not None else DEFAULT_KEYWORDS
    lowered = [k.lower() for k in keywords]

    headlines: list[dict[str, str]] = []
    seen: set[str] = set()
    for url in feed_urls:
        try:
            parsed = feedparser.parse(url)
        except Exception:
            logger.exception("Failed to parse feed %s; skipping", url)
            continue
        for entry in getattr(parsed, "entries", []):
            title = str(entry.get("title", "")).strip()
            if not title:
                continue
            lower_title = title.lower()
            if not any(k in lower_title for k in lowered):
                continue
            if lower_title in seen:
                continue
            seen.add(lower_title)
            headlines.append({"title": title, "link": str(entry.get("link", ""))})
            if len(headlines) >= max_headlines:
                return headlines
    return headlines
