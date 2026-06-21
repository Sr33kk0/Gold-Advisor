import pytest

from database.connection import get_db_connection


@pytest.fixture
def db_conn(tmp_path):
    """Yield a connection to a fresh temp-file SQLite DB (WAL needs a real file)."""
    db_file = tmp_path / "test.db"
    with get_db_connection(str(db_file)) as conn:
        yield conn
