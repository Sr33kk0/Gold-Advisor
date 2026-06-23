import pytest

from database.connection import fetch_latest_sentiment
from worker import sentiment_pipeline
from worker.sentiment_pipeline import execute_sentiment_pipeline

_GOOD = ('{"sentiment_score": 2.0, "dominant_risk_factor": "Fed", '
         '"analytical_summary": "Dovish."}')


def _stub_headlines(monkeypatch, headlines):
    monkeypatch.setattr(sentiment_pipeline, "fetch_macroeconomic_headlines",
                        lambda *a, **k: headlines)


def test_success_persists_snapshot(db_conn, monkeypatch):
    _stub_headlines(monkeypatch, [{"title": "Fed dovish", "link": "u1"}])
    res = execute_sentiment_pipeline(
        db_conn, api_key="KEY", date="2026-06-23",
        generate_content_fn=lambda p: _GOOD)
    assert res["failed"] is False
    snap = fetch_latest_sentiment(db_conn)
    assert snap is not None
    assert snap["date"] == "2026-06-23"
    assert snap["sentiment_score"] == pytest.approx(2.0)
    assert snap["source_headlines"] == ["Fed dovish"]


def test_failed_inference_does_not_persist(db_conn, monkeypatch):
    _stub_headlines(monkeypatch, [{"title": "Fed dovish", "link": "u1"}])
    res = execute_sentiment_pipeline(
        db_conn, api_key="KEY", date="2026-06-23",
        generate_content_fn=lambda p: (_ for _ in ()).throw(RuntimeError("503")))
    assert res["failed"] is True
    assert fetch_latest_sentiment(db_conn) is None  # nothing written


def test_headline_collection_failure_is_tolerated(db_conn, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("all feeds down")
    monkeypatch.setattr(sentiment_pipeline, "fetch_macroeconomic_headlines", boom)
    # inference still succeeds on empty headlines -> persists with empty audit list
    res = execute_sentiment_pipeline(
        db_conn, api_key="KEY", date="2026-06-23",
        generate_content_fn=lambda p: _GOOD)
    assert res["failed"] is False
    snap = fetch_latest_sentiment(db_conn)
    assert snap["source_headlines"] == []


def test_pipeline_never_raises_on_total_failure(db_conn, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("feeds down")
    monkeypatch.setattr(sentiment_pipeline, "fetch_macroeconomic_headlines", boom)
    res = execute_sentiment_pipeline(  # inference also fails -> neutral, no raise
        db_conn, api_key="KEY", date="2026-06-23",
        generate_content_fn=lambda p: (_ for _ in ()).throw(RuntimeError("503")))
    assert res["failed"] is True
    assert fetch_latest_sentiment(db_conn) is None
