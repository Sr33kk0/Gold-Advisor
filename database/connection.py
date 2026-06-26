"""SQLite connection management and Data Access Object (DAO) functions.

The connection context manager enables WAL + foreign keys and applies the
schema idempotently. DAO functions accept an open connection so the caller
owns the transaction scope.
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

from utils.timeutil import now_utc

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
# Read the (static) schema once at import; re-applied per connection for the
# multi-container boot race, but without re-hitting disk every time.
_SCHEMA_SQL = _SCHEMA_PATH.read_text()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str,
                   decl: str) -> None:
    """Add `column` to `table` if absent. Idempotent and multi-container safe:
    a concurrent boot that already added it raises 'duplicate column', ignored."""
    existing = [r["name"] for r in
                conn.execute(f"PRAGMA table_info({table});").fetchall()]
    if column in existing:
        return
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl};")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def _resolve_db_path(db_path: str | None) -> str:
    if db_path is not None:
        return db_path
    data_dir = os.environ.get("DATA_DIR", "data")
    return os.path.join(data_dir, "audash.db")


@contextmanager
def get_db_connection(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a WAL-enabled SQLite connection with the schema applied.

    Commits on clean exit, rolls back on exception, always closes.

    Note: executescript() issues an implicit COMMIT, so the schema is committed
    before the caller's transaction scope begins.
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
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.executescript(_SCHEMA_SQL)
        _ensure_column(conn, "transactions", "reverses_id", "TEXT")
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
                    fiat_total_myr: float, timestamp: str | None = None,
                    reverses_id: str | None = None) -> str:
    """Insert one ledger row; return its generated UUID.

    `reverses_id` links a void's offsetting entry back to the trade it reverses
    (None for an original trade).
    """
    tx_id = str(uuid.uuid4())
    ts = timestamp or now_utc().isoformat()
    conn.execute(
        "INSERT INTO transactions "
        "(id, timestamp, action_type, metal, execution_rate_myr, "
        " mass_grams, fiat_total_myr, reverses_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
        (tx_id, ts, action_type, metal,
         execution_rate_myr, mass_grams, fiat_total_myr, reverses_id),
    )
    return tx_id


_TRANSACTION_COLUMNS = ["id", "timestamp", "action_type", "metal",
                        "execution_rate_myr", "mass_grams", "fiat_total_myr",
                        "reverses_id"]


def fetch_transactions(conn: sqlite3.Connection,
                       metal: str | None = None) -> pd.DataFrame:
    """Return the trade ledger as a DataFrame, ascending by timestamp.

    `metal` ('GOLD'/'SILVER') filters to one metal; None returns all rows.
    """
    query = (
        "SELECT id, timestamp, action_type, metal, execution_rate_myr, "
        "mass_grams, fiat_total_myr, reverses_id FROM transactions"
    )
    params: tuple = ()
    if metal is not None:
        query += " WHERE metal=?"
        params = (metal,)
    query += " ORDER BY timestamp"
    rows = conn.execute(query, params).fetchall()
    return pd.DataFrame([dict(r) for r in rows], columns=_TRANSACTION_COLUMNS)


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


_QUOTE_COLUMNS = ["date", "metal", "buy_rate_myr", "sell_rate_myr", "recorded_at"]


def write_daily_quote(conn: sqlite3.Connection, date: str, metal: str,
                      buy_rate_myr: float, sell_rate_myr: float) -> None:
    """Upsert one daily platform price quote (keyed on date+metal)."""
    conn.execute(
        "INSERT OR REPLACE INTO daily_quotes "
        "(date, metal, buy_rate_myr, sell_rate_myr, recorded_at) "
        "VALUES (?, ?, ?, ?, ?);",
        (date, metal, buy_rate_myr, sell_rate_myr, now_utc().isoformat()),
    )


def fetch_daily_quotes(conn: sqlite3.Connection,
                       metal: str | None = None) -> pd.DataFrame:
    """Return recorded daily quotes as a DataFrame, ascending by date.

    `metal` ('GOLD'/'SILVER') filters to one metal; None returns all rows.
    """
    query = (
        "SELECT date, metal, buy_rate_myr, sell_rate_myr, recorded_at "
        "FROM daily_quotes"
    )
    params: tuple = ()
    if metal is not None:
        query += " WHERE metal=?"
        params = (metal,)
    query += " ORDER BY date"
    rows = conn.execute(query, params).fetchall()
    return pd.DataFrame([dict(r) for r in rows], columns=_QUOTE_COLUMNS)


def delete_daily_quote(conn: sqlite3.Connection, date: str, metal: str) -> None:
    """Remove one recorded daily quote (fat-finger correction)."""
    conn.execute(
        "DELETE FROM daily_quotes WHERE date=? AND metal=?;",
        (date, metal),
    )


DEFAULT_SETTINGS: dict[str, str] = {
    # Spread engine (absolute MYR-per-gram fallbacks)
    "default_buy_spread": "0.0",
    "default_sell_spread": "0.0",
    # Indicators
    "rsi_period": "14",
    "rsi_oversold": "30",
    "rsi_overbought": "70",
    "vol_band_deviations": "2",
    "gsr_band_deviations": "2",
    # Signal fusion
    "quant_vote_threshold": "2",
    # Risk policy (position-aware overrides)
    "stop_loss_pct": "5.0",
    "take_profit_pct": "10.0",
    "max_position_grams": "100.0",
    # Sentiment
    "sentiment_max_age_days": "2",
    "GEMINI_MODEL": "gemini-3-flash-preview",
    # Locale
    "BASE_CURRENCY": "MYR",
    "TIMEZONE": "Asia/Kuala_Lumpur",
}


def set_setting(conn: sqlite3.Connection, key: str, value) -> None:
    """Upsert a single config key (value stored as text)."""
    conn.execute(
        "INSERT OR REPLACE INTO system_settings (config_key, config_value) "
        "VALUES (?, ?);",
        (key, str(value)),
    )


def get_setting(conn: sqlite3.Connection, key: str,
                default: str | None = None) -> str | None:
    """Return a config value, or `default` if the key is absent."""
    row = conn.execute(
        "SELECT config_value FROM system_settings WHERE config_key=?;",
        (key,),
    ).fetchone()
    return row["config_value"] if row is not None else default


def seed_default_settings(conn: sqlite3.Connection) -> None:
    """Insert each default only if its key is absent (never overwrites).

    INSERT OR IGNORE skips rows whose config_key (PRIMARY KEY) already exists,
    so this is a single batch write rather than a per-key SELECT + INSERT.
    """
    conn.executemany(
        "INSERT OR IGNORE INTO system_settings (config_key, config_value) "
        "VALUES (?, ?);",
        DEFAULT_SETTINGS.items(),
    )


def write_sentiment_snapshot(conn: sqlite3.Connection, date: str,
                             sentiment_score: float, dominant_risk_factor: str,
                             analytical_summary: str,
                             source_headlines: list[str]) -> None:
    """Upsert a daily sentiment snapshot (headlines stored as JSON)."""
    conn.execute(
        "INSERT OR REPLACE INTO sentiment_snapshots "
        "(date, sentiment_score, dominant_risk_factor, analytical_summary, "
        " source_headlines, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        (date, sentiment_score, dominant_risk_factor, analytical_summary,
         json.dumps(source_headlines), now_utc().isoformat()),
    )


def fetch_latest_sentiment(conn: sqlite3.Connection) -> dict | None:
    """Return the most recent sentiment snapshot as a dict, or None."""
    row = conn.execute(
        "SELECT * FROM sentiment_snapshots ORDER BY date DESC LIMIT 1;"
    ).fetchone()
    if row is None:
        return None
    snap = dict(row)
    snap["source_headlines"] = (
        json.loads(snap["source_headlines"]) if snap["source_headlines"] else []
    )
    return snap
