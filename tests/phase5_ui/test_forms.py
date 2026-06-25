"""Headless AppTest coverage for the form side-effects.

Drives the real widgets and asserts the DB write actually happened (the trade
ledger row, the persisted setting) and that "Refresh sentiment now" degrades
safely with no API key.
"""

from datetime import timedelta

from streamlit.testing.v1 import AppTest

from database.connection import (
    delete_daily_quote, fetch_daily_quotes, fetch_transactions,
    get_db_connection, get_setting, log_transaction, write_daily_quote,
    write_spot_prices,
)
from utils.timeutil import now_utc

APP = "ui/app.py"


def _seed(db_file) -> None:
    with get_db_connection(str(db_file)) as conn:
        base = now_utc().date()
        for i in range(30):
            d = (base - timedelta(days=29 - i)).isoformat()
            write_spot_prices(conn, d, 16000.0 - i * 60.0, 190.0 - i * 0.2)


def _run(tmp_path, monkeypatch) -> AppTest:
    _seed(tmp_path / "audash.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return AppTest.from_file(APP, default_timeout=60).run()


def _widget(widgets, key):
    return next(w for w in widgets if w.key == key)


def test_submitting_trade_form_writes_a_ledger_row(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    at.radio[0].set_value("New Trade").run()
    _widget(at.number_input, "trade_primary").set_value(5000.0).run()
    _widget(at.button, "trade_review").click().run()      # step 1: review
    _widget(at.button, "trade_submit").click().run()       # step 2: confirm

    assert not at.exception
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        df = fetch_transactions(conn)
    assert len(df) == 1
    assert df.iloc[0]["action_type"] == "BUY"
    assert df.iloc[0]["metal"] == "GOLD"


def test_non_positive_amount_is_blocked_and_logs_nothing(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    at.radio[0].set_value("New Trade").run()
    # leave the amount at its 0.0 default and try to review
    _widget(at.button, "trade_review").click().run()

    assert not at.exception
    assert any("greater than zero" in e.value for e in at.error)
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        assert len(fetch_transactions(conn)) == 0


def test_voiding_a_trade_writes_an_offsetting_reversal(tmp_path, monkeypatch):
    _seed(tmp_path / "audash.db")
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        tx_id = log_transaction(conn, "BUY", "GOLD", 400.0, 2.0, 800.0)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()

    at.radio[0].set_value("New Trade").run()
    _widget(at.button, f"void_{tx_id}").click().run()      # arm the void
    _widget(at.button, f"voidok_{tx_id}").click().run()    # confirm the void

    assert not at.exception
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        df = fetch_transactions(conn)
    assert len(df) == 2
    sells = df[df["action_type"] == "SELL"]
    assert len(sells) == 1
    rev = sells.iloc[0]
    assert rev["metal"] == "GOLD"
    assert rev["mass_grams"] == 2.0
    assert rev["execution_rate_myr"] == 400.0


def test_recent_trades_render_as_description_list(tmp_path, monkeypatch):
    """Each ledger row is a semantic <dl> with screen-reader-only datum labels,
    while the per-row Void button stays a live widget."""
    _seed(tmp_path / "audash.db")
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        tx_id = log_transaction(conn, "BUY", "GOLD", 400.0, 2.0, 800.0)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.radio[0].set_value("New Trade").run()

    assert not at.exception
    blob = " ".join(m.value for m in at.markdown)
    assert 'class="audash-trade"' in blob
    assert 'class="audash-sr-only">Mass' in blob
    assert any(w.key == f"void_{tx_id}" for w in at.button)  # still interactive


def test_void_controls_are_trade_specific(tmp_path, monkeypatch):
    """The Void / confirm / cancel controls name the exact trade, so their
    accessible names aren't the ambiguous repeated 'Void' / 'Cancel'."""
    _seed(tmp_path / "audash.db")
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        tx_id = log_transaction(conn, "BUY", "GOLD", 400.0, 2.0, 800.0)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.radio[0].set_value("New Trade").run()

    void = _widget(at.button, f"void_{tx_id}")
    assert void.label == "Void BUY GOLD…"
    assert void.help and "BUY GOLD" in void.help and "2026-" in void.help

    void.click().run()                                     # arm the confirmation
    assert _widget(at.button, f"voidok_{tx_id}").label == "Void BUY GOLD"
    assert _widget(at.button, f"voidcancel_{tx_id}").label == "Keep BUY GOLD"
    assert not at.exception


def test_saving_settings_persists_change(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    at.radio[0].set_value("Settings").run()
    _widget(at.text_input, "set_rsi_oversold").set_value("35").run()
    _widget(at.button, "save_settings").click().run()

    assert not at.exception
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        assert get_setting(conn, "rsi_oversold") == "35"


def test_refresh_sentiment_without_key_warns(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    at.radio[0].set_value("Settings").run()
    _widget(at.button, "refresh_sentiment").click().run()

    assert not at.exception
    assert any("Gemini API key" in w.value for w in at.warning)


def test_recording_a_quote_writes_a_daily_quote_row(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    at.radio[0].set_value("Daily Prices").run()
    _widget(at.number_input, "quote_buy").set_value(520.0).run()
    _widget(at.number_input, "quote_sell").set_value(510.0).run()
    _widget(at.button, "quote_submit").click().run()

    assert not at.exception
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        df = fetch_daily_quotes(conn)
    assert len(df) == 1
    assert df.iloc[0]["metal"] == "GOLD"
    assert df.iloc[0]["buy_rate_myr"] == 520.0
    assert df.iloc[0]["sell_rate_myr"] == 510.0


def test_recording_quote_with_zero_rate_is_blocked(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    at.radio[0].set_value("Daily Prices").run()
    _widget(at.number_input, "quote_buy").set_value(520.0).run()
    # leave quote_sell at its 0.0 default
    _widget(at.button, "quote_submit").click().run()

    assert not at.exception
    assert any("greater than zero" in e.value for e in at.error)
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        assert len(fetch_daily_quotes(conn)) == 0


def test_inverted_quote_warns_but_still_records(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    at.radio[0].set_value("Daily Prices").run()
    _widget(at.number_input, "quote_buy").set_value(500.0).run()
    _widget(at.number_input, "quote_sell").set_value(510.0).run()  # buy < sell

    assert any("swap" in w.value.lower() for w in at.warning)
    _widget(at.button, "quote_submit").click().run()
    assert not at.exception
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        assert len(fetch_daily_quotes(conn)) == 1


def test_deleting_a_quote_removes_it(tmp_path, monkeypatch):
    _seed(tmp_path / "audash.db")
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        write_daily_quote(conn, "2026-06-20", "GOLD", 500.0, 490.0)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()

    at.radio[0].set_value("Daily Prices").run()
    _widget(at.button, "delq_2026-06-20_GOLD").click().run()

    assert not at.exception
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        assert len(fetch_daily_quotes(conn)) == 0


def test_voiding_collapses_to_a_single_voided_line(tmp_path, monkeypatch):
    _seed(tmp_path / "audash.db")
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        tx_id = log_transaction(conn, "BUY", "GOLD", 400.0, 2.0, 800.0)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()

    at.radio[0].set_value("New Trade").run()
    _widget(at.button, f"void_{tx_id}").click().run()      # arm
    _widget(at.button, f"voidok_{tx_id}").click().run()    # confirm

    assert not at.exception
    # the offsetting reversal is persisted AND linked back to the original
    with get_db_connection(str(tmp_path / "audash.db")) as conn:
        df = fetch_transactions(conn)
    assert (df["reverses_id"] == tx_id).sum() == 1
    # the original now renders as VOIDED with no void button; reversal not listed
    blob = " ".join(m.value for m in at.markdown)
    assert "VOIDED" in blob
    assert not any(w.key and w.key.startswith("void_") for w in at.button)
