"""Sentiment ingestion pipeline: collect macro headlines, infer sentiment, and
persist a daily snapshot. Best-effort and failure-tolerant — never raises.

On inference failure the snapshot is NOT written: the prior row ages toward
`sentiment_max_age_days`, so signals.generate_trade_signal forces a conservative
HOLD (Rule 3 / capital protection) rather than acting on a fabricated neutral.
"""

import logging
import sqlite3
from collections.abc import Callable

from ai.gemini_orchestrator import generate_sentiment_inference
from ai.news_collector import fetch_macroeconomic_headlines
from database.connection import write_sentiment_snapshot
from utils.timeutil import now_utc

logger = logging.getLogger("worker")


def execute_sentiment_pipeline(
    conn: sqlite3.Connection,
    *,
    api_key: str,
    feed_urls: list[str] | None = None,
    keywords: list[str] | None = None,
    market_metrics: dict[str, float] | None = None,
    model_name: str = "gemini-2.0-flash",
    date: str | None = None,
    generate_content_fn: Callable[[str], str] | None = None,
) -> dict:
    """Collect headlines, infer sentiment, and persist on success. Never raises."""
    headlines: list[dict[str, str]] = []
    try:
        headlines = fetch_macroeconomic_headlines(feed_urls, keywords)
    except Exception:
        logger.exception("Headline collection failed; proceeding with none")

    result = generate_sentiment_inference(
        headlines, market_metrics, api_key=api_key,
        model_name=model_name, generate_content_fn=generate_content_fn,
    )
    if result.get("failed"):
        logger.warning(
            "Sentiment inference failed; skipping persistence to preserve the "
            "staleness fail-safe")
        return result

    day = date or now_utc().date().isoformat()
    titles = [h["title"] for h in headlines]
    write_sentiment_snapshot(
        conn, day, result["sentiment_score"],
        result["dominant_risk_factor"], result["analytical_summary"], titles,
    )
    logger.info("Sentiment snapshot persisted for %s (score=%.2f)",
                day, result["sentiment_score"])
    return result
