import numpy as np
import pandas as pd
import pytest

from analytics.quantitative import (
    compute_coefficient_of_variation,
    compute_gold_silver_ratio,
    compute_momentum_roc,
    compute_price_deviation,
    compute_relative_strength_index,
    compute_trend_strength,
    compute_up_day_ratio,
    compute_volatility_bands,
)



def test_gsr_elementwise_ratio():
    gold = pd.Series([2000.0, 2200.0])
    silver = pd.Series([25.0, 20.0])
    gsr = compute_gold_silver_ratio(gold, silver)
    assert gsr.iloc[0] == pytest.approx(80.0)
    assert gsr.iloc[1] == pytest.approx(110.0)


def test_gsr_preserves_length_and_index():
    gold = pd.Series([2000.0, 2100.0, 2200.0], index=[10, 11, 12])
    silver = pd.Series([25.0, 25.0, 25.0], index=[10, 11, 12])
    gsr = compute_gold_silver_ratio(gold, silver)
    assert len(gsr) == 3
    assert list(gsr.index) == [10, 11, 12]
    assert gsr.iloc[-1] == pytest.approx(88.0)


def test_rsi_all_gains_approaches_100():
    price = pd.Series([float(i) for i in range(1, 31)])  # strictly increasing
    rsi = compute_relative_strength_index(price, period=14)
    assert rsi.iloc[-1] == pytest.approx(100.0)


def test_rsi_all_losses_approaches_0():
    price = pd.Series([float(i) for i in range(30, 0, -1)])  # strictly decreasing
    rsi = compute_relative_strength_index(price, period=14)
    assert rsi.iloc[-1] == pytest.approx(0.0)


def test_rsi_bounded_and_length_preserved():
    rng = np.random.default_rng(42)
    price = pd.Series(100.0 + np.cumsum(rng.standard_normal(100)))
    rsi = compute_relative_strength_index(price, period=14)
    assert len(rsi) == len(price)
    valid = rsi.dropna()
    assert (valid >= 0.0).all()
    assert (valid <= 100.0).all()


def test_bands_constant_series_collapse():
    price = pd.Series([10.0] * 5)
    bands = compute_volatility_bands(price, window=3, deviations=2.0)
    assert bands["middle"].iloc[-1] == pytest.approx(10.0)
    assert bands["upper"].iloc[-1] == pytest.approx(10.0)
    assert bands["lower"].iloc[-1] == pytest.approx(10.0)


def test_percent_b_is_half_when_price_equals_mean():
    # window of [3, 1, 2]: mean == 2 == last price -> %B == 0.5
    price = pd.Series([3.0, 1.0, 2.0])
    bands = compute_volatility_bands(price, window=3, deviations=2.0)
    assert bands["percent_b"].iloc[-1] == pytest.approx(0.5)


def test_bands_widen_with_more_deviations():
    price = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    one = compute_volatility_bands(price, window=3, deviations=1.0)
    two = compute_volatility_bands(price, window=3, deviations=2.0)
    width_one = one["upper"].iloc[-1] - one["lower"].iloc[-1]
    width_two = two["upper"].iloc[-1] - two["lower"].iloc[-1]
    assert width_two > width_one

def test_roc_computes_percent_change_over_window():
    price = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    roc = compute_momentum_roc(price, window=2)
    assert roc.iloc[2] == pytest.approx(2.0)  # 30 / 10 - 1
    assert roc.iloc[:2].isna().all()


def test_roc_zero_prior_price_is_nan_not_inf():
    price = pd.Series([0.0, 5.0, 10.0])
    roc = compute_momentum_roc(price, window=1)
    assert pd.isna(roc.iloc[1])


def test_price_deviation_positive_when_above_mean():
    price = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    dev = compute_price_deviation(price, window=3)
    assert dev.iloc[-1] == pytest.approx(0.2)  # (5 - mean([3,4,5])) / 5


def test_trend_strength_is_one_for_perfect_linear_trend():
    price = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    strength = compute_trend_strength(price, window=4)
    assert strength.iloc[-1] == pytest.approx(1.0)


def test_trend_strength_is_nan_for_constant_price():
    price = pd.Series([5.0] * 6)
    strength = compute_trend_strength(price, window=3)
    assert pd.isna(strength.iloc[-1])


def test_coefficient_of_variation_zero_for_constant_price():
    price = pd.Series([10.0] * 5)
    cov = compute_coefficient_of_variation(price, window=3)
    assert cov.iloc[-1] == pytest.approx(0.0)


def test_coefficient_of_variation_matches_population_std_ratio():
    price = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    cov = compute_coefficient_of_variation(price, window=5)
    assert cov.iloc[-1] == pytest.approx(2.0**0.5 / 5.0)


def test_up_day_ratio_is_one_for_strictly_increasing_price():
    price = pd.Series([float(i) for i in range(1, 10)])
    ratio = compute_up_day_ratio(price, window=5)
    assert ratio.iloc[-1] == pytest.approx(1.0)


def test_up_day_ratio_is_zero_for_strictly_decreasing_price():
    price = pd.Series([float(i) for i in range(9, 0, -1)])
    ratio = compute_up_day_ratio(price, window=5)
    assert ratio.iloc[-1] == pytest.approx(0.0)