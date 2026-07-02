"""Pure, stateless quantitative indicators over price series.

No I/O, no Streamlit, no global state (Rule 2): every function takes pandas
Series / primitives and returns values, so each is unit-testable in isolation.
Spot inputs are per troy ounce; the Gold/Silver Ratio is unit-invariant.
"""

import pandas as pd


def compute_gold_silver_ratio(gold: pd.Series, silver: pd.Series) -> pd.Series:
    """Return the elementwise Gold/Silver Ratio (gold_per_oz / silver_per_oz)."""
    return gold / silver


def compute_relative_strength_index(price: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (0-100). Uses exponential smoothing with alpha = 1/period.

    avg_loss == 0 (only gains) -> RSI 100; avg_gain == 0 (only losses) -> RSI 0.
    The leading `period` observations are NaN (insufficient history).
    """
    delta = price.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    # Algebraically identical to 100 - 100/(1 + avg_gain/avg_loss), but this
    # form has no 0/0: avg_loss == 0 (only gains) -> 100; avg_gain == 0 -> 0.
    # Keeps test output pristine (no divide-by-zero RuntimeWarning).
    return 100.0 * avg_gain / (avg_gain + avg_loss)


def compute_volatility_bands(price: pd.Series, window: int = 20,
                             deviations: float = 2.0) -> pd.DataFrame:
    """Bollinger bands + %B position.

    `window` defaults to 20 (standard Bollinger length); `deviations` comes
    from `vol_band_deviations`. Population std (ddof=0). %B = (price - lower) /
    (upper - lower); a flat window (std 0) yields NaN %B (0/0), which is
    expected and handled by the caller.
    """
    middle = price.rolling(window).mean()
    std = price.rolling(window).std(ddof=0)
    upper = middle + deviations * std
    lower = middle - deviations * std
    width = upper - lower
    # Guard the flat-window case (std 0 -> width 0): yield NaN %B, not a 0/0
    # RuntimeWarning. Dividing by NaN is silent.
    percent_b = (price - lower) / width.where(width != 0)
    return pd.DataFrame({
        "middle": middle,
        "upper": upper,
        "lower": lower,
        "percent_b": percent_b,
    })


# The five functions below port formulas from Microsoft Qlib's Alpha158 zoo
# (github.com/microsoft/qlib, Apache-2.0), as adapted to pure-pandas single-
# instrument scripts by github.com/HKUDS/Vibe-Trading
# (agent/src/factors/zoo/qlib158/). Qlib's originals run cross-sectionally
# over a wide DataFrame of many instruments; these operate on the one price
# Series a metal's spot history is (Rule 2: no I/O, no global state).


def compute_momentum_roc(price: pd.Series, window: int = 10) -> pd.Series:
    """Rate of change: price_t / price_{t-window} - 1 (qlib158 ROC).

    Positive -> up over the window, negative -> down. The leading `window`
    observations are NaN (no prior price to compare against). A zero prior
    price (never expected for spot gold/silver) yields NaN, not inf.
    """
    prior = price.shift(window)
    return (price / prior.where(prior != 0)) - 1.0


def compute_price_deviation(price: pd.Series, window: int = 20) -> pd.Series:
    """Price deviation from its own rolling mean, normalized (qlib158 RESI).

    (price - ts_mean(price, window)) / price. Positive -> trading above its
    recent average, negative -> below; magnitude is a mean-reversion signal.
    A zero price yields NaN, not inf.
    """
    mean = price.rolling(window).mean()
    return (price - mean) / price.where(price != 0)


def compute_trend_strength(price: pd.Series, window: int = 20) -> pd.Series:
    """R^2 of price against a linear time trend over the window (qlib158 RSQR).

    Squared rolling Pearson correlation between price and an increasing time
    index, bounded [0, 1]. Near 1 -> price is moving in a clean, near-linear
    trend (momentum signals are trustworthy); near 0 -> choppy/range-bound
    (momentum signals are noisier). A constant-price window has undefined
    correlation and yields NaN, not a false 0.
    """
    t = pd.Series(range(len(price)), index=price.index, dtype="float64")
    corr = price.rolling(window).corr(t)
    return corr * corr


def compute_coefficient_of_variation(price: pd.Series, window: int = 20) -> pd.Series:
    """Rolling price volatility relative to price level (qlib158 STD).

    ts_std(price, window) / price, population std (ddof=0, matching
    `compute_volatility_bands`). Unit-free, so it is comparable across metals
    or across time even as the price level drifts. A zero price yields NaN.
    """
    std = price.rolling(window).std(ddof=0)
    return std / price.where(price != 0)


def compute_up_day_ratio(price: pd.Series, window: int = 10) -> pd.Series:
    """Fraction of up days within the window (qlib158 CNTP).

    rolling_mean(1[price > price_{t-1}], window), bounded [0, 1]. High ->
    persistent upward days (trend consistency); low -> persistent downward
    days. 0.5 -> no directional bias.
    """
    up = (price > price.shift(1)).astype("float64")
    return up.rolling(window).mean()
