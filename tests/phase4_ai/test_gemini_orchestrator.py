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
