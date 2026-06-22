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
