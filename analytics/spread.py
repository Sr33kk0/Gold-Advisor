"""Pure platform-spread engine: asymmetric, recency-weighted, staleness-decaying.

All spread values are absolute MYR-per-gram amounts. No I/O, no global state
(Rule 2). The spread reflects broker pricing behavior, so it uses the entire
trade history (recency-decayed) and never resets on liquidation.
"""

import math
from datetime import datetime

import numpy as np
import pandas as pd

# Physical constant; mirrors worker.api_client.GRAMS_PER_TROY_OZ. Duplicated
# here to keep analytics free of any worker import (purity / no I/O coupling).
GRAMS_PER_TROY_OZ = 31.1034768


def per_gram(per_oz):
    """Convert a per-troy-ounce amount (scalar or Series) to per gram."""
    return per_oz / GRAMS_PER_TROY_OZ


def realized_spread(exec_rate: float, spot: float, side: str) -> float:
    """Per-trade realized spread vs spot (per gram). BUY markup / SELL haircut."""
    if side == "BUY":
        return exec_rate - spot
    if side == "SELL":
        return spot - exec_rate
    raise ValueError(f"side must be 'BUY' or 'SELL', got {side!r}")


def recency_weighted_mean(values, ages_days, alpha_days: float) -> float:
    """Exponentially recency-weighted mean: weight_i = exp(-age_i / alpha)."""
    v = np.asarray(values, dtype=float)
    a = np.asarray(ages_days, dtype=float)
    if v.size == 0:
        raise ValueError("recency_weighted_mean requires at least one value")
    if alpha_days <= 0:
        raise ValueError("alpha_days must be positive")
    weights = np.exp(-a / alpha_days)
    return float(np.sum(weights * v) / np.sum(weights))


def staleness_weight(latest_age_days: float, tau_days: float) -> float:
    """Decay weight for how stale the latest trade is: exp(-age / tau)."""
    if tau_days <= 0:
        raise ValueError("tau_days must be positive")
    return math.exp(-latest_age_days / tau_days)


def effective_spread(derived: float | None, fallback: float,
                     staleness_w: float) -> float:
    """Blend derived spread toward the configured fallback as trades go stale."""
    if derived is None:
        return fallback
    return staleness_w * derived + (1.0 - staleness_w) * fallback


def platform_rates(spot_today_per_gram: float, eff_buy_spread: float,
                   eff_sell_spread: float) -> dict[str, float]:
    """Current platform buy/sell rates from spot plus asymmetric spreads."""
    return {
        "buy": spot_today_per_gram + eff_buy_spread,
        "sell": spot_today_per_gram - eff_sell_spread,
    }


def spot_on_or_before(spot_per_gram: pd.Series, date: str) -> float | None:
    """Spot at `date`, else the nearest prior date; None if none exists.

    Expects an ascending ISO 'YYYY-MM-DD' string index (lexicographic == chronological).
    """
    prior = spot_per_gram[spot_per_gram.index <= date]
    if prior.empty:
        return None
    return float(prior.iloc[-1])


def compute_side_spread(trades: pd.DataFrame, spot_per_gram: pd.Series, side: str,
                        *, fallback: float, alpha_days: float, tau_days: float,
                        now: datetime) -> dict[str, float | int | None]:
    """Effective per-gram spread for one side from the full (decayed) history."""
    side_trades = trades[trades["action_type"] == side]

    realized: list[float] = []
    timestamps: list[datetime] = []
    for _, row in side_trades.iterrows():
        ts_str = str(row["timestamp"])
        spot = spot_on_or_before(spot_per_gram, ts_str[:10])
        if spot is None:  # no spot on/before trade date -> skip from derivation
            continue
        realized.append(realized_spread(float(row["execution_rate_myr"]), spot, side))
        timestamps.append(datetime.fromisoformat(ts_str))

    if not realized:
        return {"effective_spread": fallback, "derived_spread": None,
                "staleness_weight": 0.0, "n_trades": 0}

    t_latest = max(timestamps)
    ages = [(t_latest - t).total_seconds() / 86400.0 for t in timestamps]
    derived = recency_weighted_mean(realized, ages, alpha_days)
    latest_age = (now - t_latest).total_seconds() / 86400.0
    w = staleness_weight(latest_age, tau_days)
    return {
        "effective_spread": effective_spread(derived, fallback, w),
        "derived_spread": derived,
        "staleness_weight": w,
        "n_trades": len(realized),
    }


def derive_quote_spreads(quotes: pd.DataFrame, spot_per_gram: pd.Series, *,
                         fallback_buy: float,
                         fallback_sell: float) -> dict[str, float | int]:
    """Median per-side spread (MYR/g) from recorded daily quotes.

    For each quote row, join spot on/before its date and compute
    buy_spread = buy_rate - spot and sell_spread = spot - sell_rate. Returns the
    median of each side across quotes, or the configured fallback for a side
    with no usable quote (a quote whose date has no spot on/before it is
    skipped). Pure (Rule 2): DataFrame/Series in, values out.
    """
    buy_spreads: list[float] = []
    sell_spreads: list[float] = []
    for _, row in quotes.iterrows():
        spot = spot_on_or_before(spot_per_gram, str(row["date"])[:10])
        if spot is None:
            continue
        buy_spreads.append(realized_spread(float(row["buy_rate_myr"]), spot, "BUY"))
        sell_spreads.append(realized_spread(float(row["sell_rate_myr"]), spot, "SELL"))
    return {
        "buy_spread": float(np.median(buy_spreads)) if buy_spreads else fallback_buy,
        "sell_spread": float(np.median(sell_spreads)) if sell_spreads else fallback_sell,
        "n_quotes": len(buy_spreads),
    }
