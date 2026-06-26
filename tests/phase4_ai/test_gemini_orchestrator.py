import pytest

from ai.gemini_orchestrator import build_sentiment_prompt


def test_prompt_includes_headlines_and_metrics():
    prompt = build_sentiment_prompt(
        [{"title": "Fed holds rates", "link": "u1"},
         {"title": "Inflation cools", "link": "u2"}],
        {"gold_silver_ratio": 80.5},
    )
    assert "Fed holds rates" in prompt
    assert "Inflation cools" in prompt
    assert "gold_silver_ratio" in prompt
    assert "80.5" in prompt


def test_prompt_states_scale_and_json_keys():
    prompt = build_sentiment_prompt([], {})
    assert "-5" in prompt and "5" in prompt
    assert "sentiment_score" in prompt
    assert "dominant_risk_factor" in prompt
    assert "analytical_summary" in prompt
    assert "JSON" in prompt


def test_prompt_handles_empty_inputs():
    prompt = build_sentiment_prompt([], {})
    assert "no recent macroeconomic headlines" in prompt
    assert "no market metrics provided" in prompt


from ai.gemini_orchestrator import parse_sentiment_response


def test_parses_valid_response():
    raw = ('{"sentiment_score": 2.5, "dominant_risk_factor": "Fed policy", '
           '"analytical_summary": "Dovish tilt supports gold."}')
    out = parse_sentiment_response(raw)
    assert out["sentiment_score"] == pytest.approx(2.5)
    assert out["dominant_risk_factor"] == "Fed policy"
    assert out["analytical_summary"] == "Dovish tilt supports gold."
    assert out["failed"] is False


def test_clamps_score_into_range():
    high = parse_sentiment_response(
        '{"sentiment_score": 99, "dominant_risk_factor": "x", "analytical_summary": "y"}')
    low = parse_sentiment_response(
        '{"sentiment_score": -99, "dominant_risk_factor": "x", "analytical_summary": "y"}')
    assert high["sentiment_score"] == pytest.approx(5.0)
    assert low["sentiment_score"] == pytest.approx(-5.0)


def test_missing_key_raises():
    with pytest.raises(ValueError):
        parse_sentiment_response('{"sentiment_score": 1.0, "dominant_risk_factor": "x"}')


def test_non_numeric_score_raises():
    with pytest.raises(ValueError):
        parse_sentiment_response(
            '{"sentiment_score": "bullish", "dominant_risk_factor": "x", "analytical_summary": "y"}')


def test_bad_json_raises():
    with pytest.raises(ValueError):
        parse_sentiment_response("not json at all")


from ai.gemini_orchestrator import generate_sentiment_inference


def test_inference_success_returns_parsed():
    captured = {}

    def fake_fn(prompt):
        captured["prompt"] = prompt
        return ('{"sentiment_score": 3, "dominant_risk_factor": "CPI", '
                '"analytical_summary": "Hot CPI lifts safe-haven demand."}')

    out = generate_sentiment_inference(
        [{"title": "CPI surprises high", "link": "u1"}], {"rsi": 28.0},
        api_key="KEY", generate_content_fn=fake_fn)
    assert out["failed"] is False
    assert out["sentiment_score"] == pytest.approx(3.0)
    assert "CPI surprises high" in captured["prompt"]   # prompt actually built + passed


def test_inference_api_error_returns_neutral():
    def boom(prompt):
        raise RuntimeError("gemini 503")

    out = generate_sentiment_inference([], None, api_key="KEY", generate_content_fn=boom)
    assert out["failed"] is True
    assert out["sentiment_score"] == pytest.approx(0.0)
    assert out["dominant_risk_factor"] == "UNKNOWN"


def test_inference_bad_payload_returns_neutral():
    out = generate_sentiment_inference(
        [], None, api_key="KEY", generate_content_fn=lambda p: "<<not json>>")
    assert out["failed"] is True


def test_inference_does_not_mutate_neutral_constant():
    from ai import gemini_orchestrator
    out = generate_sentiment_inference([], None, api_key="KEY",
                                       generate_content_fn=lambda p: "bad")
    out["sentiment_score"] = 4.0  # mutate the returned copy
    assert gemini_orchestrator.NEUTRAL_RESULT["sentiment_score"] == 0.0  # constant intact


# --- _default_generate_content: live call over the REST endpoint (no SDK) -----

from ai import gemini_orchestrator
from ai.gemini_orchestrator import _default_generate_content

_GEMINI_TEXT = ('{"sentiment_score": 1.5, "dominant_risk_factor": "Fed", '
                '"analytical_summary": "Dovish."}')
_GEMINI_OK_PAYLOAD = {
    "candidates": [{"content": {"parts": [{"text": _GEMINI_TEXT}]}}]
}


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise gemini_orchestrator.requests.HTTPError(f"status {self.status_code}")


def test_default_generate_content_returns_model_text(monkeypatch):
    captured = {}

    def fake_post(url, params=None, json=None, timeout=None):
        captured.update(url=url, params=params, json=json)
        return _FakeResp(_GEMINI_OK_PAYLOAD)

    monkeypatch.setattr(gemini_orchestrator.requests, "post", fake_post)
    text = _default_generate_content(
        "MY PROMPT", api_key="KEY", model_name="gemini-3-flash-preview")
    assert text == _GEMINI_TEXT


def test_default_generate_content_targets_model_key_and_prompt(monkeypatch):
    captured = {}

    def fake_post(url, params=None, json=None, timeout=None):
        captured.update(url=url, params=params, json=json)
        return _FakeResp(_GEMINI_OK_PAYLOAD)

    monkeypatch.setattr(gemini_orchestrator.requests, "post", fake_post)
    _default_generate_content("MY PROMPT", api_key="SECRET",
                              model_name="gemini-3-flash-preview")
    assert "gemini-3-flash-preview:generateContent" in captured["url"]
    assert captured["params"]["key"] == "SECRET"   # key in query, not URL path
    assert "MY PROMPT" in str(captured["json"])     # prompt in request body


def test_default_generate_content_requests_json_mime(monkeypatch):
    captured = {}

    def fake_post(url, params=None, json=None, timeout=None):
        captured.update(json=json)
        return _FakeResp(_GEMINI_OK_PAYLOAD)

    monkeypatch.setattr(gemini_orchestrator.requests, "post", fake_post)
    _default_generate_content("P", api_key="K", model_name="m")
    assert captured["json"]["generationConfig"]["responseMimeType"] == "application/json"


def test_default_generate_content_uses_generous_timeout(monkeypatch):
    captured = {}

    def fake_post(url, params=None, json=None, timeout=None):
        captured["timeout"] = timeout
        return _FakeResp(_GEMINI_OK_PAYLOAD)

    monkeypatch.setattr(gemini_orchestrator.requests, "post", fake_post)
    _default_generate_content("P", api_key="K", model_name="gemini-3-flash-preview")
    # gemini-3 reasoning models routinely take ~25-30s; the timeout must clear that
    # comfortably or real sentiment refreshes spuriously fail (read timeout).
    assert captured["timeout"] >= 60


def test_default_generate_content_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(gemini_orchestrator.requests, "post",
                        lambda *a, **k: _FakeResp({}, status=429))
    with pytest.raises(gemini_orchestrator.requests.HTTPError):
        _default_generate_content("P", api_key="K", model_name="m")


def test_inference_uses_rest_path_when_no_fn_injected(monkeypatch):
    """The real app path (no injected fn) now flows through requests, not the SDK."""
    monkeypatch.setattr(gemini_orchestrator.requests, "post",
                        lambda *a, **k: _FakeResp(_GEMINI_OK_PAYLOAD))
    out = generate_sentiment_inference(
        [{"title": "h", "link": "u"}], {"rsi": 30.0}, api_key="KEY",
        model_name="gemini-3-flash-preview")
    assert out["failed"] is False
    assert out["sentiment_score"] == pytest.approx(1.5)
