import logging

import pytest

from worker import main
from worker.main import initialize_background_daemon, run_daily_cycle


def test_run_daily_cycle_swallows_pipeline_errors(db_conn, monkeypatch, caplog):
    def boom(conn, api_key, **kwargs):
        raise RuntimeError("api down")
    monkeypatch.setattr(main, "execute_ingestion_pipeline", boom)
    caplog.set_level(logging.ERROR, logger="worker")
    run_daily_cycle(db_conn, "KEY", sleep_fn=lambda _s: None)  # must NOT raise; no real sleeping
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
    assert sleeps == [1.0, 1.0, 1.0]   # 0.0 stub + 1s window-crossing guard


def test_run_daily_cycle_retries_then_succeeds(db_conn, monkeypatch):
    calls = {"n": 0}

    def flaky(conn, api_key, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return {"gold_rate_per_oz": 1.0, "silver_rate_per_oz": 1.0}

    monkeypatch.setattr(main, "execute_ingestion_pipeline", flaky)
    sleeps = []
    result = main.run_daily_cycle(db_conn, "KEY", sleep_fn=sleeps.append)
    assert result is True
    assert calls["n"] == 3              # 2 failures then success
    assert sleeps == [30.0, 120.0]      # backoffs before retries 1 and 2


def test_run_daily_cycle_exhausts_retries_returns_false(db_conn, monkeypatch, caplog):
    def always_fail(conn, api_key, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(main, "execute_ingestion_pipeline", always_fail)
    caplog.set_level(logging.ERROR, logger="worker")
    sleeps = []
    result = main.run_daily_cycle(db_conn, "KEY", sleep_fn=sleeps.append)
    assert result is False
    assert sleeps == [30.0, 120.0, 480.0]   # 3 backoffs, 4 attempts
    assert "failed after" in caplog.text.lower()


def test_loop_survives_db_open_failure(monkeypatch):
    monkeypatch.setenv("COMMODITY_API_KEY", "KEY")

    def boom(*args, **kwargs):
        raise RuntimeError("db locked")

    monkeypatch.setattr(main, "get_db_connection", boom)
    monkeypatch.setattr(main, "sleep_until_next_window", lambda: 0.0)
    sleeps = []
    main.initialize_background_daemon(max_cycles=2, sleep_fn=sleeps.append)
    assert sleeps == [1.0, 1.0]   # survived 2 cycles; 0.0 stub + 1s guard


def test_daemon_pads_sleep_past_window_boundary(monkeypatch, tmp_path):
    # A bare time.sleep can return a hair early; landing exactly on the window
    # would let next_local_time_utc see it as "not yet passed" and fire the same
    # window twice. The daemon adds a fixed guard so the sleep always crosses it.
    monkeypatch.setenv("COMMODITY_API_KEY", "KEY")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(main, "run_daily_cycle", lambda conn, api_key: None)
    monkeypatch.setattr(main, "sleep_until_next_window", lambda: 3600.0)
    sleeps = []
    initialize_background_daemon(max_cycles=1, sleep_fn=sleeps.append)
    assert sleeps == [3601.0]   # 3600s until window + 1s crossing guard
