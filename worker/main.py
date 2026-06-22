"""Background worker daemon: schedule, ingest, persist, repeat.

The daemon wakes at WINDOW_HOUR:WINDOW_MINUTE local time each day, runs the
price-ingestion pipeline with failure tolerance, then sleeps until the next
window. Scheduling and cycle functions accept injected `now`/`sleep_fn`/
`max_cycles` so they are deterministic under test.
"""

import logging
import os
import time
from datetime import datetime

from database.connection import get_db_connection, seed_default_settings
from utils.timeutil import next_local_time_utc, now_utc
from worker.api_client import execute_ingestion_pipeline

logger = logging.getLogger("worker")

WINDOW_HOUR = 17
WINDOW_MINUTE = 0
_DEFAULT_TZ = "Asia/Kuala_Lumpur"


def sleep_until_next_window(now: datetime | None = None,
                            tz_name: str | None = None) -> float:
    """Return seconds until the next WINDOW_HOUR:WINDOW_MINUTE local instant."""
    now = now or now_utc()
    tz_name = tz_name or os.environ.get("TIMEZONE", _DEFAULT_TZ)
    target = next_local_time_utc(WINDOW_HOUR, WINDOW_MINUTE, tz_name, now=now)
    return (target - now).total_seconds()


def run_daily_cycle(conn, api_key: str) -> None:
    """Run the price-ingestion pipeline, tolerating any single failure."""
    try:
        rates = execute_ingestion_pipeline(conn, api_key)
        logger.info("Price ingestion succeeded: %s", rates)
    except Exception:
        logger.exception("Price ingestion failed; daemon continues")
