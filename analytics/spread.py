"""Pure platform-spread engine: median per-side spread from recorded quotes.

All spread values are absolute MYR-per-gram amounts. No I/O, no global state
(Rule 2). The displayed buy/sell rate is the day's quote when present, else
spot +/- the median spread of all recorded quotes.
"""

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
