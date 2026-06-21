"""SQLite connection management and Data Access Object (DAO) functions.

The connection context manager enables WAL + foreign keys and applies the
schema idempotently. DAO functions accept an open connection so the caller
owns the transaction scope.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from utils.timeutil import now_utc

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _resolve_db_path(db_path: str | None) -> str:
    if db_path is not None:
        return db_path
    data_dir = os.environ.get("DATA_DIR", "data")
    return os.path.join(data_dir, "audash.db")


@contextmanager
def get_db_connection(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a WAL-enabled SQLite connection with the schema applied.

    Commits on clean exit, rolls back on exception, always closes.
    """
    path = _resolve_db_path(db_path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.executescript(_SCHEMA_PATH.read_text())
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def write_spot_prices(conn: sqlite3.Connection, date: str,
                      gold: float, silver: float) -> None:
    """Upsert a daily spot-price row (keyed on date)."""
    conn.execute(
        "INSERT OR REPLACE INTO spot_prices "
        "(date, gold_rate_per_oz, silver_rate_per_oz, fetched_at) "
        "VALUES (?, ?, ?, ?);",
        (date, gold, silver, now_utc().isoformat()),
    )
