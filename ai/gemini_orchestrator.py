"""Gemini sentiment inference: build a structured prompt, call the model under
an enforced JSON contract, parse + validate, and never raise.

The live Google SDK is imported lazily inside `_default_generate_content` so
this module imports cleanly even where `google-generativeai` is absent (e.g. the
test venv). All callers can inject `generate_content_fn` to stay hermetic.
On any failure the inference returns NEUTRAL_RESULT (failed=True); the caller
declines to persist it, preserving the Phase 3 staleness fail-safe (Rule 3).
"""

import json
import logging

logger = logging.getLogger("ai")

SENTIMENT_SCORE_MIN = -5.0
SENTIMENT_SCORE_MAX = 5.0

NEUTRAL_RESULT: dict = {
    "sentiment_score": 0.0,
    "dominant_risk_factor": "UNKNOWN",
    "analytical_summary": "Sentiment unavailable; defaulting to neutral.",
    "failed": True,
}


def build_sentiment_prompt(headlines: list[dict[str, str]],
                           market_metrics: dict[str, float]) -> str:
    """Assemble the JSON-contract prompt from headlines + market metrics."""
    if headlines:
        headline_block = "\n".join(f"- {h['title']}" for h in headlines)
    else:
        headline_block = "(no recent macroeconomic headlines)"
    if market_metrics:
        metrics_block = "\n".join(f"- {k}: {v}" for k, v in market_metrics.items())
    else:
        metrics_block = "(no market metrics provided)"
    return (
        "You are an unemotional macro analyst scoring gold-market sentiment.\n"
        "Rate how bullish recent macro news is for GOLD on a scale from -5 "
        "(strongly bearish) to 5 (strongly bullish).\n\n"
        f"Recent headlines:\n{headline_block}\n\n"
        f"Current market metrics:\n{metrics_block}\n\n"
        "Respond with ONLY a JSON object (no prose) with exactly these keys:\n"
        '  "sentiment_score": a number from -5 to 5,\n'
        '  "dominant_risk_factor": a short string naming the key risk,\n'
        '  "analytical_summary": a one or two sentence rationale.\n'
    )


def parse_sentiment_response(raw_text: str) -> dict:
    """Parse + validate the model's JSON; clamp score to [-5, 5].

    Raises ValueError on malformed JSON, missing keys, or a non-numeric score.
    """
    data = json.loads(raw_text)  # JSONDecodeError is a ValueError subclass
    if "dominant_risk_factor" not in data or "analytical_summary" not in data:
        raise ValueError("sentiment response missing required key(s)")
    try:
        score = float(data["sentiment_score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid sentiment_score: {exc}") from exc
    score = max(SENTIMENT_SCORE_MIN, min(SENTIMENT_SCORE_MAX, score))
    return {
        "sentiment_score": score,
        "dominant_risk_factor": str(data["dominant_risk_factor"]),
        "analytical_summary": str(data["analytical_summary"]),
        "failed": False,
    }
