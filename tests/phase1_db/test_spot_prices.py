from database.connection import write_spot_prices


def test_write_then_read_back(db_conn):
    write_spot_prices(db_conn, "2026-06-21", 12000.0, 150.0)
    row = db_conn.execute(
        "SELECT gold_rate_per_oz, silver_rate_per_oz, fetched_at "
        "FROM spot_prices WHERE date=?;", ("2026-06-21",)
    ).fetchone()
    assert row["gold_rate_per_oz"] == 12000.0
    assert row["silver_rate_per_oz"] == 150.0
    assert row["fetched_at"] is not None


def test_insert_or_replace_overwrites_same_date(db_conn):
    write_spot_prices(db_conn, "2026-06-21", 12000.0, 150.0)
    write_spot_prices(db_conn, "2026-06-21", 12500.0, 155.0)
    rows = db_conn.execute(
        "SELECT gold_rate_per_oz FROM spot_prices WHERE date=?;", ("2026-06-21",)
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["gold_rate_per_oz"] == 12500.0
