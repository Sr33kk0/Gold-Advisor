from analytics.signals import generate_trade_signal


def _signal(**overrides):
    base = dict(
        rsi=50.0, percent_b=0.5, gsr=80.0, gsr_upper=90.0, gsr_lower=70.0,
        sentiment_score=0.0, sentiment_age_days=0.0,
        rsi_oversold=30.0, rsi_overbought=70.0,
        quant_vote_threshold=2, sentiment_max_age_days=2.0,
    )
    base.update(overrides)
    return generate_trade_signal(**base)


def test_momentum_uptrend_adds_buy_vote_when_trend_is_clean():
    res = _signal(momentum_roc=0.05, trend_strength=0.9, momentum_r2_min=0.5)
    assert res["roc_vote"] == 1


def test_momentum_downtrend_adds_sell_vote_when_trend_is_clean():
    res = _signal(momentum_roc=-0.05, trend_strength=0.9, momentum_r2_min=0.5)
    assert res["roc_vote"] == -1


def test_momentum_muted_when_trend_too_weak():
    # Clear positive ROC, but a choppy market (R^2 below the gate) -> no vote.
    res = _signal(momentum_roc=0.05, trend_strength=0.2, momentum_r2_min=0.5)
    assert res["roc_vote"] == 0


def test_momentum_muted_when_data_missing():
    res = _signal(momentum_roc=None, trend_strength=None, momentum_r2_min=0.5)
    assert res["roc_vote"] == 0


def test_momentum_counts_toward_net_and_can_reach_threshold():
    # RSI oversold (+1) plus a clean uptrend ROC (+1) clears the ±2 threshold.
    res = _signal(rsi=20.0, momentum_roc=0.05, trend_strength=0.9,
                  momentum_r2_min=0.5, sentiment_score=1.0)
    assert res["net_votes"] == 2
    assert res["quant_bias"] == "BUY"
    assert res["final_recommendation"] == "BUY"


def test_momentum_brakes_falling_knife_buy():
    # RSI oversold says "buy the dip" (+1), but a clean strong downtrend ROC
    # (-1) offsets it -> net 0 -> HOLD (capital protection).
    res = _signal(rsi=20.0, momentum_roc=-0.05, trend_strength=0.9,
                  momentum_r2_min=0.5, sentiment_score=1.0)
    assert res["rsi_vote"] == 1
    assert res["roc_vote"] == -1
    assert res["net_votes"] == 0
    assert res["quant_bias"] == "HOLD"


def test_strong_buy_quant_with_positive_sentiment_buys():
    res = _signal(rsi=20.0, percent_b=-0.1, gsr=60.0, sentiment_score=1.0)
    assert res["rsi_vote"] == 1
    assert res["vol_vote"] == 1
    assert res["gsr_vote"] == 1
    assert res["net_votes"] == 3
    assert res["quant_bias"] == "BUY"
    assert res["final_recommendation"] == "BUY"


def test_buy_quant_vetoed_by_negative_sentiment_holds():
    res = _signal(rsi=20.0, percent_b=-0.1, gsr=60.0, sentiment_score=-1.0)
    assert res["quant_bias"] == "BUY"
    assert res["final_recommendation"] == "HOLD"


def test_strong_sell_quant_with_negative_sentiment_sells():
    res = _signal(rsi=80.0, percent_b=1.1, gsr=100.0, sentiment_score=-1.0)
    assert res["net_votes"] == -3
    assert res["quant_bias"] == "SELL"
    assert res["final_recommendation"] == "SELL"


def test_sell_quant_vetoed_by_positive_sentiment_holds():
    res = _signal(rsi=80.0, percent_b=1.1, gsr=100.0, sentiment_score=1.0)
    assert res["quant_bias"] == "SELL"
    assert res["final_recommendation"] == "HOLD"


def test_below_threshold_net_is_quant_hold():
    res = _signal(rsi=20.0, percent_b=0.5, gsr=80.0, sentiment_score=1.0)
    assert res["net_votes"] == 1  # only the RSI vote fires
    assert res["quant_bias"] == "HOLD"
    assert res["final_recommendation"] == "HOLD"


def test_stale_sentiment_forces_hold():
    res = _signal(rsi=20.0, percent_b=-0.1, gsr=60.0,
                  sentiment_score=1.0, sentiment_age_days=5.0)  # > max_age 2
    assert res["quant_bias"] == "BUY"
    assert res["sentiment_stale"] is True
    assert res["final_recommendation"] == "HOLD"


def test_missing_sentiment_forces_hold():
    res = _signal(rsi=20.0, percent_b=-0.1, gsr=60.0,
                  sentiment_score=None, sentiment_age_days=None)
    assert res["sentiment_stale"] is True
    assert res["final_recommendation"] == "HOLD"


def test_breakdown_contains_all_keys():
    res = _signal()
    for key in ("rsi_vote", "vol_vote", "gsr_vote", "roc_vote", "trend_strength",
                "net_votes", "quant_bias", "sentiment_score", "sentiment_stale",
                "final_recommendation", "reasons"):
        assert key in res
