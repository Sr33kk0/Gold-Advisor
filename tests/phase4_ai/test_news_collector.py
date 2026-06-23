from types import SimpleNamespace

import pytest

from ai import news_collector
from ai.news_collector import fetch_macroeconomic_headlines


def _feed(*entries):
    """Build a fake feedparser result: an object exposing `.entries`."""
    return SimpleNamespace(entries=[dict(e) for e in entries])


def _patch_parse(monkeypatch, mapping):
    """Map each feed URL to a fake parsed result (or an Exception to raise)."""
    def fake_parse(url):
        result = mapping[url]
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(news_collector.feedparser, "parse", fake_parse)


def test_keeps_only_keyword_matches(monkeypatch):
    _patch_parse(monkeypatch, {
        "f1": _feed(
            {"title": "Fed signals rate hold", "link": "u1"},
            {"title": "Celebrity buys a yacht", "link": "u2"},
            {"title": "Inflation cools in May", "link": "u3"},
        ),
    })
    out = fetch_macroeconomic_headlines(["f1"], ["fed", "inflation"])
    titles = [h["title"] for h in out]
    assert titles == ["Fed signals rate hold", "Inflation cools in May"]
    assert out[0]["link"] == "u1"


def test_dedupes_by_title_across_feeds(monkeypatch):
    _patch_parse(monkeypatch, {
        "f1": _feed({"title": "Fed holds rates", "link": "u1"}),
        "f2": _feed({"title": "Fed holds rates", "link": "u2"}),  # dup title
    })
    out = fetch_macroeconomic_headlines(["f1", "f2"], ["fed"])
    assert len(out) == 1
    assert out[0]["link"] == "u1"  # first occurrence wins


def test_bad_feed_is_skipped_not_fatal(monkeypatch):
    _patch_parse(monkeypatch, {
        "bad": RuntimeError("feed 500"),
        "good": _feed({"title": "Inflation rises", "link": "u9"}),
    })
    out = fetch_macroeconomic_headlines(["bad", "good"], ["inflation"])
    assert [h["title"] for h in out] == ["Inflation rises"]


def test_respects_max_headlines(monkeypatch):
    _patch_parse(monkeypatch, {
        "f1": _feed(*[{"title": f"Fed note {i}", "link": f"u{i}"} for i in range(10)]),
    })
    out = fetch_macroeconomic_headlines(["f1"], ["fed"], max_headlines=3)
    assert len(out) == 3


def test_no_matches_returns_empty(monkeypatch):
    _patch_parse(monkeypatch, {"f1": _feed({"title": "Sports recap", "link": "u1"})})
    assert fetch_macroeconomic_headlines(["f1"], ["fed"]) == []


def test_defaults_are_nonempty_lists():
    assert news_collector.DEFAULT_FEED_URLS
    assert news_collector.DEFAULT_KEYWORDS
    assert all(k == k.lower() for k in news_collector.DEFAULT_KEYWORDS)
