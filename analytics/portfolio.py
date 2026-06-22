"""Pure per-metal portfolio math: cost basis and unrealized PnL.

Chronological walk-forward, average-cost method, with position reset on
liquidation. No I/O, no global state (Rule 2). Caller filters `trades` to a
single metal before calling.
"""

import pandas as pd


def calculate_cost_basis(trades: pd.DataFrame, epsilon: float = 1e-9) -> dict:
    """Walk trades chronologically; return the current open position's basis.

    Returns {"holding_grams", "cost_basis", "oversell_flagged"}. Average-cost:
    partial sells leave per-gram cost unchanged. Liquidation (~0 grams) resets
    both accumulators. Oversell is clamped to the holding and flagged.
    """
    open_grams = 0.0
    open_cost = 0.0  # sum of buy_rate * grams for the CURRENT open lot
    oversell = False

    if not trades.empty:
        for _, row in trades.sort_values("timestamp").iterrows():
            grams = float(row["mass_grams"])
            rate = float(row["execution_rate_myr"])
            if row["action_type"] == "BUY":
                open_grams += grams
                open_cost += rate * grams
            else:  # SELL
                if grams > open_grams + epsilon:
                    oversell = True
                    grams = open_grams
                avg = open_cost / open_grams if open_grams > epsilon else 0.0
                open_grams -= grams
                open_cost -= avg * grams  # average-cost: per-gram avg unchanged
                if open_grams <= epsilon:  # liquidation -> reset the lot
                    open_grams = 0.0
                    open_cost = 0.0

    cost_basis = open_cost / open_grams if open_grams > epsilon else 0.0
    return {
        "holding_grams": open_grams,
        "cost_basis": cost_basis,
        "oversell_flagged": oversell,
    }
