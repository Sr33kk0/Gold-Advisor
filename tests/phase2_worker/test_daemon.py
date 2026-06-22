import logging

from worker import main
from worker.main import run_daily_cycle


def test_run_daily_cycle_swallows_pipeline_errors(db_conn, monkeypatch, caplog):
    def boom(conn, api_key, **kwargs):
        raise RuntimeError("api down")
    monkeypatch.setattr(main, "execute_ingestion_pipeline", boom)
    caplog.set_level(logging.ERROR, logger="worker")
    run_daily_cycle(db_conn, "KEY")  # must NOT raise
    assert "failed" in caplog.text.lower()


def test_run_daily_cycle_success_invokes_pipeline(db_conn, monkeypatch):
    calls = []
    def ok(conn, api_key, **kwargs):
        calls.append(api_key)
        return {"gold_rate_per_oz": 1.0, "silver_rate_per_oz": 1.0}
    monkeypatch.setattr(main, "execute_ingestion_pipeline", ok)
    run_daily_cycle(db_conn, "KEY")
    assert calls == ["KEY"]
