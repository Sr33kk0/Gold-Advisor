"""Integration tests for the DB -> dashboard view-model assembly.

Uses the real temp-file SQLite fixture (db_conn). Covers the new
fetch_transactions DAO and ui.data_access.load_dashboard_model, with emphasis
on the Rule 3 wiring: sentiment age -> generate_trade_signal -> forced HOLD.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from database.connection import (
    log_transaction, write_daily_quote, write_sentiment_snapshot,
    write_spot_prices,
)
from ui import data_access
from utils.timeutil import now_utc, to_local


def _seed_spot(conn, days: int = 30, start_gold: float = 16000.0,
               start_silver: float = 190.0) -> list[str]:
    """Seed a descending gold series (drives RSI oversold) over `days` days."""
    dates = []
    base = now_utc().date()
    for i in range(days):
        d = (base - timedelta(days=days - 1 - i)).isoformat()
        dates.append(d)
        gold = start_gold - i * 60.0           # steady decline
        silver = start_silver - i * 0.2
        write_spot_prices(conn, d, gold, silver)
    return dates


def test_fetch_transactions_returns_dataframe_with_ledger_columns(db_conn):
    log_transaction(db_conn, "BUY", "GOLD", 500.0, 10.0, 5000.0)
    log_transaction(db_conn, "SELL", "GOLD", 510.0, 4.0, 2040.0)
    df = data_access.fetch_transactions(db_conn)
    assert len(df) == 2
    assert {"action_type", "timestamp", "execution_rate_myr",
            "mass_grams", "metal"} <= set(df.columns)


def test_fetch_transactions_filters_by_metal(db_conn):
    log_transaction(db_conn, "BUY", "GOLD", 500.0, 10.0, 5000.0)
    log_transaction(db_conn, "BUY", "SILVER", 6.0, 100.0, 600.0)
    gold = data_access.fetch_transactions(db_conn, metal="GOLD")
    assert len(gold) == 1
    assert gold.iloc[0]["metal"] == "GOLD"


def test_load_dashboard_model_populates_market_and_signal(db_conn):
    _seed_spot(db_conn)
    log_transaction(db_conn, "BUY", "GOLD", 500.0, 20.0, 10000.0)
    write_sentiment_snapshot(db_conn, now_utc().date().isoformat(),
                             1.5, "Risk-on", "Fresh positive read", ["h1"])

    model = data_access.load_dashboard_model(db_conn, now=now_utc())

    assert {"settings", "market", "signal_inputs", "signal_result",
            "gsr_band", "chart", "sentiment_age", "threshold"} <= set(model)
    assert isinstance(model["market"]["gold_buy"], float)
    assert model["market"]["gold_buy"] > 0
    assert model["signal_result"]["final_recommendation"] in {"BUY", "SELL", "HOLD"}
    assert len(model["chart"]["dates"]) == 30
    # fresh sentiment -> not stale
    assert model["signal_result"]["sentiment_stale"] is False


def test_load_dashboard_model_populates_momentum_context(db_conn):
    _seed_spot(db_conn)
    model = data_access.load_dashboard_model(db_conn, now=now_utc())

    # The four context indicators land on `market`; ROC lands on signal_inputs.
    for key in ("momentum_roc", "trend_strength", "up_day_ratio",
                "price_deviation", "coeff_variation"):
        assert isinstance(model["market"][key], float)
    assert isinstance(model["signal_inputs"]["roc"], float)


def test_clean_downtrend_produces_negative_momentum_vote(db_conn):
    # _seed_spot lays down a steady linear decline -> clean trend (high R^2),
    # negative ROC -> the R^2 gate opens and momentum votes SELL.
    _seed_spot(db_conn)
    model = data_access.load_dashboard_model(db_conn, now=now_utc())
    sig = model["signal_result"]

    assert sig["trend_strength"] > 0.5
    assert model["market"]["momentum_roc"] < 0
    assert sig["roc_vote"] == -1


def test_chart_markers_exclude_voided_trades(db_conn):
    _seed_spot(db_conn)
    tx = log_transaction(db_conn, "BUY", "GOLD", 500.0, 10.0, 5000.0)
    # void it: an offsetting SELL linked back to the original
    log_transaction(db_conn, "SELL", "GOLD", 500.0, 10.0, 5000.0, reverses_id=tx)
    # a separate, live BUY stays visible on the chart
    log_transaction(db_conn, "BUY", "GOLD", 520.0, 4.0, 2080.0)

    model = data_access.load_dashboard_model(db_conn, now=now_utc())
    markers = model["chart"]["markers"]

    assert [m["side"] for m in markers] == ["BUY"]   # voided pair hidden
    assert markers[0]["price"] == 520.0


def test_load_dashboard_model_forces_hold_when_sentiment_stale(db_conn):
    _seed_spot(db_conn)
    write_sentiment_snapshot(db_conn, now_utc().date().isoformat(),
                             1.5, "Risk-on", "Old read", ["h1"])

    # Look at the model 5 days later: the snapshot is now beyond max age.
    model = data_access.load_dashboard_model(
        db_conn, now=now_utc() + timedelta(days=5))

    assert model["signal_result"]["sentiment_stale"] is True
    assert model["signal_result"]["final_recommendation"] == "HOLD"


def test_load_dashboard_model_empty_db_is_safe_hold(db_conn):
    model = data_access.load_dashboard_model(db_conn, now=now_utc())
    assert model["signal_result"]["final_recommendation"] == "HOLD"
    assert model["signal_result"]["sentiment_stale"] is True
    assert model["chart"]["dates"] == []


def test_load_dashboard_model_uses_quote_for_today_directly(db_conn):
    _seed_spot(db_conn)
    now = now_utc()
    today_local = to_local(now, "Asia/Kuala_Lumpur").date().isoformat()
    write_daily_quote(db_conn, today_local, "GOLD", 9999.0, 9000.0)

    model = data_access.load_dashboard_model(db_conn, now=now)

    assert model["quotes"]["GOLD"]["quoted_today"] is True
    assert model["market"]["gold_buy"] == pytest.approx(9999.0)
    assert model["market"]["gold_sell"] == pytest.approx(9000.0)


def test_load_dashboard_model_derives_rates_from_median_when_unquoted(db_conn):
    # Two spot days (per-gram 100 then 110 gold; 10 then 11 silver).
    g = 31.1034768
    write_spot_prices(db_conn, "2026-06-20", 100.0 * g, 10.0 * g)
    write_spot_prices(db_conn, "2026-06-22", 110.0 * g, 11.0 * g)
    # Quotes only on 06-20 (today, 06-23, is unquoted).
    write_daily_quote(db_conn, "2026-06-20", "GOLD", 103.0, 98.0)    # +3 / +2 vs 100
    write_daily_quote(db_conn, "2026-06-20", "SILVER", 10.5, 9.5)    # +0.5 / +0.5 vs 10
    now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)

    model = data_access.load_dashboard_model(db_conn, now=now)

    assert model["quotes"]["GOLD"]["quoted_today"] is False
    assert model["market"]["buy_spread"] == pytest.approx(3.0)   # gold median
    assert model["market"]["sell_spread"] == pytest.approx(2.0)
    assert model["market"]["gold_buy"] == pytest.approx(113.0)   # 110 + 3
    assert model["market"]["gold_sell"] == pytest.approx(108.0)  # 110 - 2
    assert model["market"]["silver_buy"] == pytest.approx(11.5)  # 11 + 0.5
    assert model["market"]["silver_sell"] == pytest.approx(10.5)  # 11 - 0.5


def test_load_dashboard_model_no_quotes_uses_config_fallback(db_conn):
    _seed_spot(db_conn)
    model = data_access.load_dashboard_model(db_conn, now=now_utc())
    # Default spreads are 0.0 -> buy/sell collapse onto spot; n_quotes is 0.
    assert model["quotes"]["GOLD"]["n_quotes"] == 0
    assert model["market"]["gold_buy"] == pytest.approx(model["spot_today"]["GOLD"])


def test_position_policy_stop_loss_surfaces_in_model(db_conn):
    _seed_spot(db_conn)
    # Buy 10 g of gold at a far-above-market rate -> deep unrealized loss at the
    # current sell rate -> stop-loss must trip.
    log_transaction(db_conn, "BUY", "GOLD", 900.0, 10.0, 9000.0)
    write_sentiment_snapshot(db_conn, now_utc().date().isoformat(),
                             1.5, "Risk-on", "Fresh positive read", ["h1"])

    model = data_access.load_dashboard_model(db_conn, now=now_utc())
    sig = model["signal_result"]

    assert sig["position_action"] == "EMERGENCY_LIQUIDATION"
    assert sig["final_recommendation"] == "SELL"
    assert "directional_recommendation" in sig
    assert sig["pnl_pct"] is not None and sig["pnl_pct"] < 0
