import numpy as np
import pandas as pd
import pytest

from analytics.quantitative import compute_gold_silver_ratio
from analytics.quantitative import compute_relative_strength_index


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
