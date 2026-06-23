"""Background worker daemon: schedule, ingest, persist, repeat.

The daemon wakes at WINDOW_HOUR:WINDOW_MINUTE local time each day, runs the
price-ingestion pipeline with failure tolerance, then sleeps until the next
window. Scheduling and cycle functions accept injected `now`/`sleep_fn`/
`max_cycles` so they are deterministic under test.
"""

import logging
import os
import time
from collections.abc import Callable
from datetime import datetime

from database.connection import (
    fetch_historical_matrix,
    get_db_connection,
    seed_default_settings,
)
from utils.timeutil import next_local_time_utc, now_utc
from worker.api_client import execute_ingestion_pipeline
from worker.sentiment_pipeline import execute_sentiment_pipeline

logger = logging.getLogger("worker")

WINDOW_HOUR = 17
WINDOW_MINUTE = 0
_DEFAULT_TZ = "Asia/Kuala_Lumpur"

# Intra-window retry backoff (seconds) before falling back to the next window.
RETRY_BACKOFFS_SECONDS = (30.0, 120.0, 480.0)

# Guard added to each scheduled sleep so an early-returning time.sleep still
# lands past the window boundary, avoiding a same-window double-fire.
WINDOW_GUARD_PAD_SECONDS = 1.0


def sleep_until_next_window(now: datetime | None = None,
                            tz_name: str | None = None) -> float:
    """Return seconds until the next WINDOW_HOUR:WINDOW_MINUTE local instant."""
    now = now or now_utc()
    tz_name = tz_name or os.environ.get("TIMEZONE", _DEFAULT_TZ)
    target = next_local_time_utc(WINDOW_HOUR, WINDOW_MINUTE, tz_name, now=now)
    return (target - now).total_seconds()


def run_daily_cycle(conn, api_key: str, *, sleep_fn=time.sleep) -> bool:
    """Run the price-ingestion pipeline with bounded retry + backoff.

    Retries up to len(RETRY_BACKOFFS_SECONDS) times on failure, sleeping the
    corresponding backoff between attempts. Never raises. Returns True on
    success, False if every attempt failed (the daemon then waits for the
    next window).
    """
    total_attempts = len(RETRY_BACKOFFS_SECONDS) + 1
    for attempt in range(total_attempts):
        try:
            rates = execute_ingestion_pipeline(conn, api_key)
            logger.info("Price ingestion succeeded on attempt %d: %s",
                        attempt + 1, rates)
            return True
        except Exception:
            logger.exception("Price ingestion failed on attempt %d/%d",
                             attempt + 1, total_attempts)
        if attempt < len(RETRY_BACKOFFS_SECONDS):
            sleep_fn(RETRY_BACKOFFS_SECONDS[attempt])
    logger.error("Price ingestion failed after %d attempts; waiting for next window",
                 total_attempts)
    return False


def _latest_market_metrics(conn) -> dict[str, float]:
    """Lightweight quant context for the sentiment prompt from the latest spot row."""
    df = fetch_historical_matrix(conn, limit_days=1)
    if df.empty:
        return {}
    row = df.iloc[-1]
    gold = float(row["gold_rate_per_oz"])
    silver = float(row["silver_rate_per_oz"])
    metrics = {"gold_rate_per_oz": gold, "silver_rate_per_oz": silver}
    if silver > 0:
        metrics["gold_silver_ratio"] = gold / silver
    return metrics


def run_sentiment_cycle(conn) -> None:
    """Best-effort sentiment ingestion; skip cleanly if unconfigured. Never raises."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.info("GEMINI_API_KEY not set; skipping sentiment cycle")
        return
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    try:
        execute_sentiment_pipeline(
            conn, api_key=api_key, model_name=model_name,
            market_metrics=_latest_market_metrics(conn),
        )
    except Exception:
        logger.exception("Sentiment cycle failed; daemon continues")


def _require_env(name: str) -> str:
    """Return a required environment variable or raise RuntimeError."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def initialize_background_daemon(*, max_cycles: int | None = None,
                                 sleep_fn: Callable[[float], None] = time.sleep) -> None:
    """Verify prerequisites, then loop: ingest then sleep until next window."""
    api_key = _require_env("COMMODITY_API_KEY")
    logger.info("Worker daemon starting")
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        try:
            with get_db_connection() as conn:
                seed_default_settings(conn)
                run_daily_cycle(conn, api_key)
                run_sentiment_cycle(conn)
        except Exception:
            logger.exception("Daily cycle setup failed (DB open/seed); daemon continues")
        sleep_fn(sleep_until_next_window() + WINDOW_GUARD_PAD_SECONDS)
        cycles += 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    initialize_background_daemon()
