import pandas as pd
import pytest

from analytics.spread import (
    GRAMS_PER_TROY_OZ,
    derive_quote_spreads,
    per_gram,
    platform_rates,
    realized_spread,
    spot_on_or_before,
)


def test_per_gram_constant_and_conversion():
    assert GRAMS_PER_TROY_OZ == 31.1034768
    assert per_gram(31.1034768) == pytest.approx(1.0)


def test_realized_spread_buy_is_markup():
    assert realized_spread(105.0, 100.0, "BUY") == pytest.approx(5.0)


def test_realized_spread_sell_is_haircut():
    assert realized_spread(95.0, 100.0, "SELL") == pytest.approx(5.0)


def test_realized_spread_rejects_bad_side():
    with pytest.raises(ValueError):
        realized_spread(100.0, 100.0, "HOLD")


def test_platform_rates_apply_asymmetric_spreads():
    rates = platform_rates(100.0, 3.0, 2.0)
    assert rates["buy"] == pytest.approx(103.0)
    assert rates["sell"] == pytest.approx(98.0)


def test_spot_on_or_before_uses_nearest_prior():
    spot = pd.Series({"2026-01-01": 10.0, "2026-01-03": 12.0})
    assert spot_on_or_before(spot, "2026-01-02") == pytest.approx(10.0)
    assert spot_on_or_before(spot, "2026-01-03") == pytest.approx(12.0)
    assert spot_on_or_before(spot, "2025-12-31") is None


def _spot():
    return pd.Series({"2026-06-22": 100.0})


def test_derive_quote_spreads_empty_is_fallback():
    quotes = pd.DataFrame(columns=["date", "buy_rate_myr", "sell_rate_myr"])
    res = derive_quote_spreads(quotes, _spot(),
                               fallback_buy=3.0, fallback_sell=2.0)
    assert res["n_quotes"] == 0
    assert res["buy_spread"] == pytest.approx(3.0)
    assert res["sell_spread"] == pytest.approx(2.0)


def test_derive_quote_spreads_single_quote_is_realized():
    quotes = pd.DataFrame([
        {"date": "2026-06-22", "buy_rate_myr": 104.0, "sell_rate_myr": 97.0},
    ])
    res = derive_quote_spreads(quotes, _spot(),
                               fallback_buy=3.0, fallback_sell=2.0)
    assert res["n_quotes"] == 1
    assert res["buy_spread"] == pytest.approx(4.0)   # 104 - 100
    assert res["sell_spread"] == pytest.approx(3.0)  # 100 - 97


def test_derive_quote_spreads_uses_median_over_quotes():
    spot = pd.Series({"2026-06-20": 100.0, "2026-06-21": 100.0,
                      "2026-06-22": 100.0})
    quotes = pd.DataFrame([
        {"date": "2026-06-20", "buy_rate_myr": 102.0, "sell_rate_myr": 99.0},
        {"date": "2026-06-21", "buy_rate_myr": 104.0, "sell_rate_myr": 98.0},
        {"date": "2026-06-22", "buy_rate_myr": 110.0, "sell_rate_myr": 90.0},  # outlier
    ])
    res = derive_quote_spreads(quotes, spot, fallback_buy=0.0, fallback_sell=0.0)
    assert res["n_quotes"] == 3
    assert res["buy_spread"] == pytest.approx(4.0)   # median(2, 4, 10)
    assert res["sell_spread"] == pytest.approx(2.0)  # median(1, 2, 10)


def test_derive_quote_spreads_skips_quote_with_no_prior_spot():
    quotes = pd.DataFrame([
        {"date": "2026-06-20", "buy_rate_myr": 104.0, "sell_rate_myr": 97.0},
    ])  # _spot() only has 2026-06-22, so no spot on/before 2026-06-20
    res = derive_quote_spreads(quotes, _spot(),
                               fallback_buy=3.0, fallback_sell=2.0)
    assert res["n_quotes"] == 0
    assert res["buy_spread"] == pytest.approx(3.0)
    assert res["sell_spread"] == pytest.approx(2.0)
