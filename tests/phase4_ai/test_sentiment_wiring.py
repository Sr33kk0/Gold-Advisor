import logging

from worker import main


def test_sentiment_cycle_skips_without_key(db_conn, monkeypatch, caplog):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    called = []
    monkeypatch.setattr(main, "execute_sentiment_pipeline",
                        lambda *a, **k: called.append(True))
    caplog.set_level(logging.INFO, logger="worker")
    main.run_sentiment_cycle(db_conn)
    assert called == []                      # pipeline never invoked
    assert "skipping sentiment" in caplog.text.lower()


def test_sentiment_cycle_invokes_pipeline_with_key(db_conn, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "GKEY")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    seen = {}
    def fake_pipeline(conn, **kwargs):
        seen.update(kwargs)
        return {"failed": False}
    monkeypatch.setattr(main, "execute_sentiment_pipeline", fake_pipeline)
    main.run_sentiment_cycle(db_conn)
    assert seen["api_key"] == "GKEY"
    assert seen["model_name"] == "gemini-test"
    assert "market_metrics" in seen


def test_sentiment_cycle_never_raises(db_conn, monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", "GKEY")
    def boom(conn, **kwargs):
        raise RuntimeError("unexpected")
    monkeypatch.setattr(main, "execute_sentiment_pipeline", boom)
    caplog.set_level(logging.ERROR, logger="worker")
    main.run_sentiment_cycle(db_conn)        # must NOT raise
    assert "sentiment cycle failed" in caplog.text.lower()


def test_latest_market_metrics_empty_without_spot(db_conn):
    assert main._latest_market_metrics(db_conn) == {}


def test_latest_market_metrics_from_spot(db_conn):
    from database.connection import write_spot_prices
    write_spot_prices(db_conn, "2026-06-23", 2400.0, 30.0)
    metrics = main._latest_market_metrics(db_conn)
    assert metrics["gold_rate_per_oz"] == 2400.0
    assert metrics["silver_rate_per_oz"] == 30.0
    assert metrics["gold_silver_ratio"] == 80.0
