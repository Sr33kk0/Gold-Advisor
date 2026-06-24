"""DB -> dashboard view-model assembly (the UI's read side).

This is the impure seam: it reads spot prices, trades, settings, and the latest
sentiment snapshot, then drives the *pure* analytics + presenter helpers to
produce one model dict the Streamlit layer renders. It is where Phase 5 finally
wires fetch_latest_sentiment -> sentiment_age_days -> generate_trade_signal, so
stale/missing sentiment forces a conservative HOLD (Rule 3).
"""

import math
import sqlite3
from datetime import datetime

import pandas as pd

from analytics.portfolio import calculate_cost_basis, evaluate_unrealized_pnl
from analytics.quantitative import (
    compute_gold_silver_ratio, compute_relative_strength_index,
    compute_volatility_bands,
)
from analytics.signals import generate_trade_signal
from analytics.spread import derive_quote_spreads, per_gram, platform_rates
from database.connection import (
    DEFAULT_SETTINGS, fetch_daily_quotes, fetch_historical_matrix,
    fetch_latest_sentiment, fetch_transactions,
)
from ui.presenter import sentiment_age_days
from utils.timeutil import now_utc, to_local

# Re-export so the UI imports its read API from one module.
__all__ = ["fetch_transactions", "load_dashboard_model"]

_GSR_BAND_WINDOW = 20
_NEUTRAL_RSI = 50.0      # no-data placeholder that yields a 0 RSI vote
_NEUTRAL_PCT_B = 0.5     # mid-channel -> 0 volatility vote


def _load_settings(conn: sqlite3.Connection) -> dict[str, str]:
    """All system_settings, layered over the seeded defaults."""
    rows = conn.execute(
        "SELECT config_key, config_value FROM system_settings"
    ).fetchall()
    merged = dict(DEFAULT_SETTINGS)
    merged.update({r["config_key"]: r["config_value"] for r in rows})
    return merged


def _last_float(series: pd.Series | None) -> float | None:
    """Last non-NaN value of a series as a float, or None."""
    if series is None or series.empty:
        return None
    valid = series.dropna()
    return float(valid.iloc[-1]) if not valid.empty else None


def _resolve_rates(quotes: pd.DataFrame, spot_index: pd.Series,
                   spot_today: float, today: str,
                   fb_buy: float, fb_sell: float) -> dict:
    """Today's platform buy/sell + the standing median default spread.

    If a quote exists for `today`, show those exact quoted prices; otherwise
    derive from spot_today +/- the median spread of all recorded quotes (or the
    config fallback when none). `quotes` is already filtered to one metal.
    """
    sp = derive_quote_spreads(quotes, spot_index,
                              fallback_buy=fb_buy, fallback_sell=fb_sell)
    today_row = quotes[quotes["date"] == today]
    if not today_row.empty:
        last = today_row.iloc[-1]
        buy, sell, quoted_today = (
            float(last["buy_rate_myr"]), float(last["sell_rate_myr"]), True)
    else:
        rates = platform_rates(spot_today, sp["buy_spread"], sp["sell_spread"])
        buy, sell, quoted_today = rates["buy"], rates["sell"], False
    return {
        "buy": buy, "sell": sell,
        "buy_spread": sp["buy_spread"], "sell_spread": sp["sell_spread"],
        "n_quotes": sp["n_quotes"], "quoted_today": quoted_today,
    }


def load_dashboard_model(conn: sqlite3.Connection, *,
                         now: datetime | None = None) -> dict:
    """Assemble everything the dashboard renders from the shared DB."""
    now = now or now_utc()
    s = _load_settings(conn)

    rsi_period = int(s["rsi_period"])
    vol_dev = float(s["vol_band_deviations"])
    gsr_dev = float(s["gsr_band_deviations"])
    threshold = int(s["quant_vote_threshold"])
    fb_buy = float(s["default_buy_spread"])
    fb_sell = float(s["default_sell_spread"])

    matrix = fetch_historical_matrix(conn)
    has_data = not matrix.empty

    if has_data:
        dates = list(matrix["date"])
        gold_g = per_gram(matrix["gold_rate_per_oz"]).reset_index(drop=True)
        silver_g = per_gram(matrix["silver_rate_per_oz"]).reset_index(drop=True)
        gsr_series = compute_gold_silver_ratio(
            matrix["gold_rate_per_oz"], matrix["silver_rate_per_oz"])
        rsi_series = compute_relative_strength_index(gold_g, rsi_period)
        bands = compute_volatility_bands(gold_g, deviations=vol_dev)
        gsr_mid = gsr_series.rolling(_GSR_BAND_WINDOW).mean()
        gsr_sd = gsr_series.rolling(_GSR_BAND_WINDOW).std(ddof=0)
        gsr_upper_series = gsr_mid + gsr_dev * gsr_sd
        gsr_lower_series = gsr_mid - gsr_dev * gsr_sd
        spot_g_today = float(gold_g.iloc[-1])
        silver_g_today = float(silver_g.iloc[-1])
        spot_index = pd.Series(gold_g.values, index=dates)
        silver_index = pd.Series(silver_g.values, index=dates)
    else:
        dates = []
        gold_g = rsi_series = gsr_series = None
        silver_g = gsr_upper_series = gsr_lower_series = None
        bands = pd.DataFrame(columns=["middle", "upper", "lower", "percent_b"])
        spot_g_today = silver_g_today = 0.0
        spot_index = silver_index = pd.Series(dtype=float)

    # Latest indicator readings (neutralized when history is too short).
    rsi_val = _last_float(rsi_series)
    rsi_val = rsi_val if rsi_val is not None else _NEUTRAL_RSI
    pct_b = _last_float(bands["percent_b"]) if not bands.empty else None
    pct_b = pct_b if pct_b is not None else _NEUTRAL_PCT_B
    gsr_val = _last_float(gsr_series) or 0.0
    gsr_up = _last_float(gsr_upper_series)
    gsr_lo = _last_float(gsr_lower_series)

    # Trades drive the portfolio; quotes drive the displayed rates + spread.
    gold_trades = fetch_transactions(conn, metal="GOLD")

    all_quotes = fetch_daily_quotes(conn)
    gold_quotes = all_quotes[all_quotes["metal"] == "GOLD"]
    silver_quotes = all_quotes[all_quotes["metal"] == "SILVER"]
    today = to_local(now, s["TIMEZONE"]).date().isoformat()

    gold_res = _resolve_rates(gold_quotes, spot_index, spot_g_today, today,
                              fb_buy, fb_sell)
    silver_res = _resolve_rates(silver_quotes, silver_index, silver_g_today,
                                today, fb_buy, fb_sell)

    gold_rates = {"buy": gold_res["buy"], "sell": gold_res["sell"]}
    silver_rates = {"buy": silver_res["buy"], "sell": silver_res["sell"]}

    # Portfolio (gold).
    pf = calculate_cost_basis(gold_trades)
    pnl = evaluate_unrealized_pnl(pf["holding_grams"], pf["cost_basis"],
                                  gold_rates["sell"])

    # Sentiment.
    snapshot = fetch_latest_sentiment(conn)
    age = sentiment_age_days(snapshot, now)
    sentiment_score = snapshot["sentiment_score"] if snapshot else None

    # Fuse (math proposes, sentiment vetoes).
    signal_result = generate_trade_signal(
        rsi=rsi_val, percent_b=pct_b, gsr=gsr_val,
        gsr_upper=gsr_up if gsr_up is not None else math.inf,
        gsr_lower=gsr_lo if gsr_lo is not None else -math.inf,
        sentiment_score=sentiment_score, sentiment_age_days=age,
        rsi_oversold=float(s["rsi_oversold"]),
        rsi_overbought=float(s["rsi_overbought"]),
        quant_vote_threshold=threshold,
        sentiment_max_age_days=float(s["sentiment_max_age_days"]),
    )

    market = {
        "gold_buy": gold_rates["buy"], "gold_sell": gold_rates["sell"],
        "silver_buy": silver_rates["buy"], "silver_sell": silver_rates["sell"],
        "buy_spread": gold_res["buy_spread"], "sell_spread": gold_res["sell_spread"],
        "holdings": pf["holding_grams"], "cost_basis": pf["cost_basis"],
        "pnl": pnl, "rsi": rsi_val, "percent_b": pct_b,
        "sentiment": sentiment_score if sentiment_score is not None else 0.0,
    }

    markers = [
        {"date": str(r["timestamp"])[:10], "side": r["action_type"],
         "price": float(r["execution_rate_myr"])}
        for _, r in gold_trades.iterrows()
    ]

    chart = {
        "dates": dates,
        "price": list(gold_g) if has_data else [],
        "bands": bands[["middle", "upper", "lower"]] if has_data
        else pd.DataFrame(columns=["middle", "upper", "lower"]),
        "rsi": list(rsi_series) if has_data else [],
        "markers": markers,
    }

    return {
        "settings": s,
        "threshold": threshold,
        "market": market,
        "signal_inputs": {"rsi": rsi_val, "percent_b": pct_b, "gsr": gsr_val},
        "signal_result": signal_result,
        "gsr_band": {
            "value": gsr_val,
            "lower": gsr_lo if gsr_lo is not None else gsr_val,
            "upper": gsr_up if gsr_up is not None else gsr_val,
        },
        "chart": chart,
        "sentiment": snapshot,
        "sentiment_age": age,
        "now": now,
        "quotes": {
            "GOLD": {k: gold_res[k] for k in
                     ("buy_spread", "sell_spread", "n_quotes", "quoted_today")},
            "SILVER": {k: silver_res[k] for k in
                       ("buy_spread", "sell_spread", "n_quotes", "quoted_today")},
        },
        "spot_today": {"GOLD": spot_g_today, "SILVER": silver_g_today},
        "today": today,
    }
