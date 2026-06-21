def test_wal_mode_enabled(db_conn):
    mode = db_conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert mode.lower() == "wal"


def test_foreign_keys_enabled(db_conn):
    fk = db_conn.execute("PRAGMA foreign_keys;").fetchone()[0]
    assert fk == 1


def test_busy_timeout_set(db_conn):
    timeout = db_conn.execute("PRAGMA busy_timeout;").fetchone()[0]
    assert timeout == 5000


def test_all_tables_created(db_conn):
    rows = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table';"
    ).fetchall()
    names = {r[0] for r in rows}
    assert {"spot_prices", "transactions",
            "sentiment_snapshots", "system_settings"} <= names


def test_schema_bootstrap_is_idempotent(tmp_path):
    from database.connection import get_db_connection
    path = str(tmp_path / "idem.db")
    with get_db_connection(path):
        pass
    # Connecting again must not raise (CREATE TABLE IF NOT EXISTS).
    with get_db_connection(path) as conn:
        count = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table';"
        ).fetchone()[0]
        assert count >= 4
