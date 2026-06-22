import pandas as pd
import pytest

from analytics.portfolio import calculate_cost_basis


def _trades(rows):
    return pd.DataFrame(
        rows,
        columns=["timestamp", "action_type", "execution_rate_myr", "mass_grams"],
    )


def test_cost_basis_weighted_average_of_buys():
    trades = _trades([
        ["2026-01-01", "BUY", 100.0, 10.0],
        ["2026-01-02", "BUY", 200.0, 10.0],
    ])
    res = calculate_cost_basis(trades)
    assert res["holding_grams"] == pytest.approx(20.0)
    assert res["cost_basis"] == pytest.approx(150.0)  # (1000 + 2000) / 20
    assert res["oversell_flagged"] is False


def test_partial_sell_preserves_average_cost():
    trades = _trades([
        ["2026-01-01", "BUY", 100.0, 10.0],
        ["2026-01-02", "BUY", 200.0, 10.0],
        ["2026-01-03", "SELL", 180.0, 5.0],
    ])
    res = calculate_cost_basis(trades)
    assert res["holding_grams"] == pytest.approx(15.0)
    assert res["cost_basis"] == pytest.approx(150.0)  # unchanged by the sell


def test_liquidation_resets_basis_for_new_lot():
    trades = _trades([
        ["2026-01-01", "BUY", 100.0, 10.0],
        ["2026-01-02", "SELL", 120.0, 10.0],   # liquidate -> reset
        ["2026-01-03", "BUY", 300.0, 5.0],     # fresh lot, uncontaminated
    ])
    res = calculate_cost_basis(trades)
    assert res["holding_grams"] == pytest.approx(5.0)
    assert res["cost_basis"] == pytest.approx(300.0)


def test_oversell_is_clamped_and_flagged():
    trades = _trades([
        ["2026-01-01", "BUY", 100.0, 5.0],
        ["2026-01-02", "SELL", 110.0, 8.0],    # only 5 held
    ])
    res = calculate_cost_basis(trades)
    assert res["holding_grams"] == pytest.approx(0.0)
    assert res["oversell_flagged"] is True


def test_empty_history_is_flat():
    res = calculate_cost_basis(_trades([]))
    assert res["holding_grams"] == pytest.approx(0.0)
    assert res["cost_basis"] == pytest.approx(0.0)
    assert res["oversell_flagged"] is False


def test_unsorted_input_is_processed_chronologically():
    trades = _trades([
        ["2026-01-03", "BUY", 300.0, 5.0],
        ["2026-01-01", "BUY", 100.0, 10.0],
        ["2026-01-02", "SELL", 120.0, 10.0],
    ])
    # chronological: BUY10@100 -> SELL10 (liquidate/reset) -> BUY5@300
    res = calculate_cost_basis(trades)
    assert res["holding_grams"] == pytest.approx(5.0)
    assert res["cost_basis"] == pytest.approx(300.0)
