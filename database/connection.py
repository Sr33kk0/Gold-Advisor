"""SQLite connection management and Data Access Object (DAO) functions.

The connection context manager enables WAL + foreign keys and applies the
schema idempotently. DAO functions accept an open connection so the caller
owns the transaction scope.
"""

import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

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


def log_transaction(conn: sqlite3.Connection, action_type: str, metal: str,
                    execution_rate_myr: float, mass_grams: float,
                    fiat_total_myr: float, timestamp: str | None = None) -> str:
    """Insert one ledger row; return its generated UUID."""
    tx_id = str(uuid.uuid4())
    ts = timestamp or now_utc().isoformat()
    conn.execute(
        "INSERT INTO transactions "
        "(id, timestamp, action_type, metal, execution_rate_myr, "
        " mass_grams, fiat_total_myr) "
        "VALUES (?, ?, ?, ?, ?, ?, ?);",
        (tx_id, ts, action_type, metal,
         execution_rate_myr, mass_grams, fiat_total_myr),
    )
    return tx_id


_MATRIX_COLUMNS = ["date", "gold_rate_per_oz", "silver_rate_per_oz"]


def fetch_historical_matrix(conn: sqlite3.Connection,
                            limit_days: int | None = None) -> pd.DataFrame:
    """Return spot-price time series as a DataFrame, ascending by date.

    `limit_days` keeps the most recent N rows.
    """
    query = (
        "SELECT date, gold_rate_per_oz, silver_rate_per_oz "
        "FROM spot_prices ORDER BY date DESC"
    )
    params: tuple = ()
    if limit_days is not None:
        query += " LIMIT ?"
        params = (limit_days,)
    rows = conn.execute(query, params).fetchall()
    df = pd.DataFrame([dict(r) for r in rows], columns=_MATRIX_COLUMNS)
    return df.sort_values("date").reset_index(drop=True)
