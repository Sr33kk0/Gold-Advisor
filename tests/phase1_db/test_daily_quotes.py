"""DAO tests for the manual daily price-quote table."""

from database.connection import (
    delete_daily_quote, fetch_daily_quotes, write_daily_quote,
)


def test_write_and_fetch_daily_quote(db_conn):
    write_daily_quote(db_conn, "2026-06-24", "GOLD", 520.0, 510.0)
    df = fetch_daily_quotes(db_conn)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["metal"] == "GOLD"
    assert row["buy_rate_myr"] == 520.0
    assert row["sell_rate_myr"] == 510.0
    assert row["recorded_at"]  # stamped, non-empty


def test_write_daily_quote_upserts_on_date_metal(db_conn):
    write_daily_quote(db_conn, "2026-06-24", "GOLD", 520.0, 510.0)
    write_daily_quote(db_conn, "2026-06-24", "GOLD", 525.0, 515.0)  # overwrite
    df = fetch_daily_quotes(db_conn)
    assert len(df) == 1
    assert df.iloc[0]["buy_rate_myr"] == 525.0


def test_fetch_daily_quotes_filters_by_metal_and_orders_ascending(db_conn):
    write_daily_quote(db_conn, "2026-06-24", "GOLD", 520.0, 510.0)
    write_daily_quote(db_conn, "2026-06-22", "GOLD", 500.0, 490.0)
    write_daily_quote(db_conn, "2026-06-24", "SILVER", 7.0, 6.5)
    gold = fetch_daily_quotes(db_conn, metal="GOLD")
    assert list(gold["date"]) == ["2026-06-22", "2026-06-24"]
    assert len(fetch_daily_quotes(db_conn, metal="SILVER")) == 1


def test_fetch_daily_quotes_empty_has_columns(db_conn):
    df = fetch_daily_quotes(db_conn)
    assert len(df) == 0
    assert {"date", "metal", "buy_rate_myr", "sell_rate_myr",
            "recorded_at"} <= set(df.columns)


def test_delete_daily_quote_removes_one_row(db_conn):
    write_daily_quote(db_conn, "2026-06-24", "GOLD", 520.0, 510.0)
    write_daily_quote(db_conn, "2026-06-24", "SILVER", 7.0, 6.5)
    delete_daily_quote(db_conn, "2026-06-24", "GOLD")
    df = fetch_daily_quotes(db_conn)
    assert len(df) == 1
    assert df.iloc[0]["metal"] == "SILVER"
