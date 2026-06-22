"""Gated-consensus signal fusion: math proposes, sentiment vetoes (Rule 3).

Pure function (Rule 2). Quant votes are summed into a bias; the sentiment gate
can only veto toward HOLD, never strengthen a trade. Stale/missing sentiment
forces a conservative HOLD to protect capital. Gold-centric orientation.
"""


def generate_trade_signal(*, rsi: float, percent_b: float, gsr: float,
                          gsr_upper: float, gsr_lower: float,
                          sentiment_score: float | None,
                          sentiment_age_days: float | None,
                          rsi_oversold: float, rsi_overbought: float,
                          quant_vote_threshold: int,
                          sentiment_max_age_days: float) -> dict[str, object]:
    """Fuse quant indicators + sentiment into BUY/SELL/HOLD with a breakdown."""
    reasons: list[str] = []

    if rsi < rsi_oversold:
        rsi_vote = 1
        reasons.append(f"RSI {rsi:.1f} < oversold {rsi_oversold} (buy bias)")
    elif rsi > rsi_overbought:
        rsi_vote = -1
        reasons.append(f"RSI {rsi:.1f} > overbought {rsi_overbought} (sell bias)")
    else:
        rsi_vote = 0

    if percent_b <= 0.0:
        vol_vote = 1
        reasons.append("Price at/below lower band (buy bias)")
    elif percent_b >= 1.0:
        vol_vote = -1
        reasons.append("Price at/above upper band (sell bias)")
    else:
        vol_vote = 0

    if gsr > gsr_upper:
        gsr_vote = -1
        reasons.append("GSR above band: gold rich vs silver (sell-gold bias)")
    elif gsr < gsr_lower:
        gsr_vote = 1
        reasons.append("GSR below band: gold cheap vs silver (buy-gold bias)")
    else:
        gsr_vote = 0

    net = rsi_vote + vol_vote + gsr_vote
    if net >= quant_vote_threshold:
        quant_bias = "BUY"
    elif net <= -quant_vote_threshold:
        quant_bias = "SELL"
    else:
        quant_bias = "HOLD"

    stale = (sentiment_score is None or sentiment_age_days is None
             or sentiment_age_days > sentiment_max_age_days)
    if stale:
        final = "HOLD"
        reasons.append("Sentiment missing/stale -> forced HOLD (capital protection)")
    elif quant_bias == "BUY":
        final = "BUY" if sentiment_score >= 0 else "HOLD"
        if final == "HOLD":
            reasons.append(f"Sentiment {sentiment_score} < 0 vetoes BUY -> HOLD")
    elif quant_bias == "SELL":
        final = "SELL" if sentiment_score <= 0 else "HOLD"
        if final == "HOLD":
            reasons.append(f"Sentiment {sentiment_score} > 0 vetoes SELL -> HOLD")
    else:
        final = "HOLD"

    return {
        "rsi_vote": rsi_vote,
        "vol_vote": vol_vote,
        "gsr_vote": gsr_vote,
        "net_votes": net,
        "quant_bias": quant_bias,
        "sentiment_score": sentiment_score,
        "sentiment_stale": stale,
        "final_recommendation": final,
        "reasons": reasons,
    }
