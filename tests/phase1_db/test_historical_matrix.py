from database.connection import fetch_historical_matrix, write_spot_prices


def test_returns_rows_ascending_by_date(db_conn):
    write_spot_prices(db_conn, "2026-06-19", 100.0, 10.0)
    write_spot_prices(db_conn, "2026-06-21", 120.0, 12.0)
    write_spot_prices(db_conn, "2026-06-20", 110.0, 11.0)
    df = fetch_historical_matrix(db_conn)
    assert list(df["date"]) == ["2026-06-19", "2026-06-20", "2026-06-21"]
    assert list(df["gold_rate_per_oz"]) == [100.0, 110.0, 120.0]


def test_limit_days_keeps_most_recent(db_conn):
    for d, g in [("2026-06-19", 100.0), ("2026-06-20", 110.0),
                 ("2026-06-21", 120.0)]:
        write_spot_prices(db_conn, d, g, g / 10)
    df = fetch_historical_matrix(db_conn, limit_days=2)
    assert list(df["date"]) == ["2026-06-20", "2026-06-21"]


def test_empty_table_returns_empty_dataframe(db_conn):
    df = fetch_historical_matrix(db_conn)
    assert len(df) == 0
    assert list(df.columns) == ["date", "gold_rate_per_oz", "silver_rate_per_oz"]
