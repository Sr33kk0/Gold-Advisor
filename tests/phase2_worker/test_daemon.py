import logging

import pytest

from worker import main
from worker.main import initialize_background_daemon, run_daily_cycle


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


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("COMMODITY_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        initialize_background_daemon(max_cycles=1)


def test_runs_bounded_cycles_with_injected_sleep(monkeypatch, tmp_path):
    monkeypatch.setenv("COMMODITY_API_KEY", "KEY")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    cycles = {"n": 0}
    sleeps = []
    monkeypatch.setattr(main, "run_daily_cycle",
                        lambda conn, api_key: cycles.__setitem__("n", cycles["n"] + 1))
    monkeypatch.setattr(main, "sleep_until_next_window", lambda: 0.0)
    initialize_background_daemon(max_cycles=3, sleep_fn=sleeps.append)
    assert cycles["n"] == 3
    assert sleeps == [0.0, 0.0, 0.0]
