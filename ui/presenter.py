"""Pure presentation helpers — the testable core of the Streamlit UI.

No Streamlit, no DB, no network (mirrors the analytics purity rule). Everything
that decides *what text/color/shape* a value renders as lives here, so the
Streamlit shells in app.py/forms.py stay thin and the display contract from
spec §5.3 + AuDash.dc.html is unit-tested directly.

The verdict word, votes, and gate are derived from the structured dict returned
by analytics.signals.generate_trade_signal — the UI never re-implements fusion.
"""

import re
from datetime import datetime


# --- number formatting -------------------------------------------------------

def fmt(n: float, d: int = 2) -> str:
    """Thousands-grouped fixed-decimal number (matches the design's en-US style)."""
    return f"{n:,.{d}f}"


def signed(n: float, d: int = 2) -> str:
    """Like fmt, but force a leading '+' on non-negative values."""
    return ("+" if n >= 0 else "") + fmt(n, d)


def signed_int(n: int) -> str:
    """Signed integer with an explicit '+' on non-negative values (e.g. '+2')."""
    return f"+{n}" if n >= 0 else str(n)


# --- verdict / vote colors ---------------------------------------------------

def verdict_color(recommendation: str, theme: dict) -> str:
    """Palette color for a BUY/SELL/HOLD recommendation."""
    return {"BUY": theme["buy"], "SELL": theme["sell"]}.get(recommendation, theme["hold"])


def verdict_shape(recommendation: str) -> str:
    """Geometric glyph for the verdict, encoding direction by *shape* not hue —
    BUY ▲, SELL ▼, HOLD ○ — so the call reads under colorblindness (Principle:
    BUY/HOLD/SELL must never rely on green/red alone)."""
    return {"BUY": "▲", "SELL": "▼"}.get(recommendation, "○")


def vote_text(vote: int) -> str:
    """Render a single signal vote as '+1' / '0' / '-1'."""
    if vote > 0:
        return "+1"
    if vote < 0:
        return "-1"
    return "0"


def vote_color(vote: int, theme: dict) -> str:
    """Color a vote by its sign: buy / sell / muted-for-neutral."""
    if vote > 0:
        return theme["buy"]
    if vote < 0:
        return theme["sell"]
    return theme["muted"]


# --- sentiment gate ----------------------------------------------------------

def sentiment_gate(signal_result: dict) -> str:
    """Classify the gate outcome: 'stale' | 'neutral' | 'passed' | 'vetoed'.

    Derived from the signal breakdown: stale wins outright; with no quant trade
    the gate is moot ('neutral'); otherwise it passed iff the final call still
    matches the quant bias, else sentiment vetoed it toward HOLD.
    """
    if signal_result["sentiment_stale"]:
        return "stale"
    if signal_result["quant_bias"] == "HOLD":
        return "neutral"
    if signal_result["final_recommendation"] == signal_result["quant_bias"]:
        return "passed"
    return "vetoed"


_GATE_LABELS = {"passed": "Passed", "vetoed": "Vetoed",
                "stale": "Stale", "neutral": "No quant trade"}


def gate_label(gate: str) -> str:
    """Human label for a gate outcome."""
    return _GATE_LABELS[gate]


def gate_color(gate: str, theme: dict) -> str:
    """Color a gate outcome: passed=buy, vetoed/stale=sell, neutral=hold."""
    if gate == "passed":
        return theme["buy"]
    if gate in ("vetoed", "stale"):
        return theme["sell"]
    return theme["hold"]


# --- GSR balance geometry ----------------------------------------------------

# The assay-balance beam tilts at most this many degrees at the band edge.
_GSR_MAX_TILT_DEG = 11.0


def gsr_position(gsr: float, lower: float, upper: float) -> dict[str, object]:
    """Where the GSR sits in its band, plus the assay-balance tilt.

    Returns side ('gold'|'silver'|'neutral'), a human label, the clamped
    in-band fraction (-1..1), and the beam tilt in degrees (+ = gold pan down).
    """
    mid = (upper + lower) / 2.0
    half = (upper - lower) / 2.0
    frac = 0.0 if half == 0 else (gsr - mid) / half
    frac = max(-1.0, min(1.0, frac))
    degrees = frac * _GSR_MAX_TILT_DEG

    if gsr > upper:
        side, label = "gold", "Gold-rich · silver cheap"
    elif gsr < lower:
        side, label = "silver", "Silver-rich · gold cheap"
    else:
        side, label = "neutral", "Within band · balanced"

    return {"side": side, "label": label, "fraction": frac, "degrees": degrees}


def gsr_label_color(side: str, theme: dict) -> str:
    """Color the GSR band label by which metal is rich."""
    if side == "gold":
        return theme["gold"]
    if side == "silver":
        return theme["silver"]
    return theme["muted"]


# --- sentiment age -----------------------------------------------------------

def sentiment_age_days(snapshot: dict | None, now: datetime) -> float | None:
    """Age (fractional days) of the latest sentiment snapshot, or None.

    `now` must be timezone-aware UTC; the snapshot's fetched_at is stored as a
    UTC ISO-8601 string (Rule 1). Returns None when there is no snapshot.
    """
    if snapshot is None:
        return None
    fetched = datetime.fromisoformat(snapshot["fetched_at"])
    return (now - fetched).total_seconds() / 86400.0


# --- cash <-> mass derivation ------------------------------------------------

def _to_float(value: object) -> float:
    """Parse a form value to float; blank/garbage -> 0.0 (never raises).

    Accepts native numbers as-is and tolerates typed/pasted strings carrying
    thousands separators, currency symbols, or stray whitespace
    ("RM 1,234.56" -> 1234.56). Assumes en-US decimals (matches `fmt`).
    """
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
    if value is None:
        return 0.0
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return 0.0


def resolve_trade_amounts(mode: str, primary_value: object,
                          rate: float) -> dict[str, float]:
    """Resolve {mass_grams, fiat_total_myr} from one entered value + the rate.

    In 'cash' mode the entered MYR is the fiat total and mass is derived; in
    'mass' mode the entered grams is the mass and fiat is derived. This keeps
    fiat_total and rate*grams consistent for log_transaction.
    """
    p = _to_float(primary_value)
    if mode == "cash":
        mass = p / rate if rate else 0.0
        return {"mass_grams": mass, "fiat_total_myr": p}
    if mode == "mass":
        return {"mass_grams": p, "fiat_total_myr": p * rate}
    raise ValueError(f"mode must be 'cash' or 'mass', got {mode!r}")


# --- trade ledger: confirm line, recent rows, reversal -----------------------

def trade_confirm_line(action: str, metal: str, mass_grams: float,
                       fiat_total_myr: float, rate: float) -> str:
    """One-line, exact restatement of what a confirm will write to the ledger."""
    return (f"{action} · {metal} · {fmt(mass_grams, 4)} g "
            f"@ {fmt(rate)} MYR/g · RM {fmt(fiat_total_myr)}")


def build_recent_trades(trades, theme: dict, limit: int = 8) -> list[dict]:
    """View-model for the recent-trades ledger panel, newest first.

    Carries both display strings (for the row) and the raw numeric fields
    (so the void action can build an exact offsetting entry). `trades` is the
    fetch_transactions DataFrame; an empty/None frame yields an empty list.
    """
    if trades is None or len(trades) == 0:
        return []
    recent = trades.sort_values("timestamp", ascending=False).head(limit)
    rows = []
    for _, r in recent.iterrows():
        action = str(r["action_type"])
        rows.append({
            "id": str(r["id"]),
            "ts": str(r["timestamp"]),
            "date": str(r["timestamp"])[:10],
            "action": action,
            "metal": str(r["metal"]),
            "color": theme["buy"] if action == "BUY" else theme["sell"],
            "opposite": "SELL" if action == "BUY" else "BUY",
            "mass": fmt(float(r["mass_grams"]), 4),
            "rate": fmt(float(r["execution_rate_myr"])),
            "fiat": fmt(float(r["fiat_total_myr"])),
            "execution_rate_myr": float(r["execution_rate_myr"]),
            "mass_grams": float(r["mass_grams"]),
            "fiat_total_myr": float(r["fiat_total_myr"]),
        })
    return rows


def reversal_entry(action_type: str, metal: str, execution_rate_myr: float,
                   mass_grams: float, fiat_total_myr: float) -> dict:
    """The exact offsetting entry that reverses a trade (append-only void).

    Flips the side, keeps metal/mass/rate/fiat identical, so the portfolio walk
    nets the position back out without ever erasing the original row.
    """
    return {
        "action_type": "SELL" if action_type == "BUY" else "BUY",
        "metal": metal,
        "execution_rate_myr": float(execution_rate_myr),
        "mass_grams": float(mass_grams),
        "fiat_total_myr": float(fiat_total_myr),
    }


# --- daily quotes ------------------------------------------------------------

def quote_preview(buy_rate: float, sell_rate: float,
                  spot: float) -> dict[str, object]:
    """Implied per-side spread of a prospective quote vs the latest spot.

    `inverted` flags buy < sell (a likely swapped entry); the quote is still
    recorded as entered.
    """
    return {
        "buy_spread": buy_rate - spot,
        "sell_spread": spot - sell_rate,
        "inverted": buy_rate < sell_rate,
    }


def build_recent_quotes(quotes, limit: int = 10) -> list[dict]:
    """View-model for the recent-quotes list, newest first.

    `quotes` is the fetch_daily_quotes DataFrame; an empty/None frame yields an
    empty list. Carries display strings plus the raw date/metal a delete needs.
    """
    if quotes is None or len(quotes) == 0:
        return []
    recent = quotes.sort_values("date", ascending=False).head(limit)
    rows = []
    for _, r in recent.iterrows():
        rows.append({
            "date": str(r["date"]),
            "metal": str(r["metal"]),
            "buy": fmt(float(r["buy_rate_myr"])),
            "sell": fmt(float(r["sell_rate_myr"])),
        })
    return rows


# --- readout zones: Market / Portfolio / Engine ------------------------------
# Three borderless "quiet ledger" zones replace the old 12-box grid. Each helper
# returns plain readout dicts {label, value, unit, color}; the Streamlit layer
# lays them out with dividers + whitespace, not a card apiece.

def _readout(label: str, value: str, unit: str, color: str) -> dict[str, str]:
    return {"label": label, "value": value, "unit": unit, "color": color}


def _sign_color(n: float, theme: dict) -> str:
    """Buy for positive, sell for negative, muted at exactly zero."""
    return theme["buy"] if n > 0 else theme["sell"] if n < 0 else theme["muted"]


def build_market_readouts(market: dict, theme: dict) -> list[dict[str, str]]:
    """Zone A — the four live platform rates, gold then silver (metal-colored)."""
    g, s = theme["gold"], theme["silver"]
    return [
        _readout("Gold buy", fmt(market["gold_buy"]), "MYR/g", g),
        _readout("Gold sell", fmt(market["gold_sell"]), "MYR/g", g),
        _readout("Silver buy", fmt(market["silver_buy"]), "MYR/g", s),
        _readout("Silver sell", fmt(market["silver_sell"]), "MYR/g", s),
    ]


def pnl_readout(pnl: float, theme: dict) -> dict[str, str]:
    """The emphasized portfolio PnL — encoded three ways (sign + shape + color)
    so gain/loss survives colorblindness: ▲ gain, ▼ loss, ○ flat."""
    shape = "▲" if pnl > 0 else "▼" if pnl < 0 else "○"
    return {"label": "Unrealized PnL", "value": signed(pnl), "unit": "MYR",
            "color": _sign_color(pnl, theme), "shape": shape}


def build_portfolio_readouts(market: dict, theme: dict) -> dict[str, object]:
    """Zone B — secondary holdings/cost basis plus the emphasized PnL."""
    return {
        "secondary": [
            _readout("Holdings", fmt(market["holdings"], 1), "g", theme["text"]),
            _readout("Cost basis", fmt(market["cost_basis"]), "MYR/g", theme["text"]),
        ],
        "pnl": pnl_readout(market["pnl"], theme),
    }


def build_engine_readouts(market: dict, theme: dict) -> list[dict[str, str]]:
    """Zone C — secondary raw engine readings (pre-vote), shown tight + small."""
    return [
        _readout("RSI", fmt(market["rsi"], 1), "", theme["text"]),
        _readout("%B", fmt(market["percent_b"], 2), "", theme["text"]),
        _readout("Sentiment", signed(market["sentiment"], 1), "/ ±5",
                 _sign_color(market["sentiment"], theme)),
        _readout("Eff. buy spread", fmt(market["buy_spread"]), "MYR/g", theme["muted"]),
        _readout("Eff. sell spread", fmt(market["sell_spread"]), "MYR/g", theme["muted"]),
    ]


# --- per-signal breakdown view-model -----------------------------------------

def _signal_detail(kind: str, vote: int) -> str:
    table = {
        "rsi": ("below oversold → buy bias", "above overbought → sell bias", "within neutral band"),
        "vol": ("at/below lower band → buy", "at/above upper band → sell", "mid-channel"),
        "gsr": ("below band → gold cheap (buy)", "above band → gold rich (sell)", "within band"),
    }
    pos, neg, neutral = table[kind]
    return pos if vote > 0 else neg if vote < 0 else neutral


def build_signal_rows(signal_result: dict, inputs: dict,
                      theme: dict) -> list[dict[str, str]]:
    """RSI / Volatility / GSR ledger rows — order matters (it's a sequence)."""
    spec = [
        ("RSI (14)", "rsi", signal_result["rsi_vote"], fmt(inputs["rsi"], 1)),
        ("Volatility band (%B)", "vol", signal_result["vol_vote"], fmt(inputs["percent_b"], 2)),
        ("Gold / Silver Ratio", "gsr", signal_result["gsr_vote"], fmt(inputs["gsr"], 1)),
    ]
    return [
        {
            "label": label,
            "detail": _signal_detail(kind, vote),
            "value": value,
            "vote_text": vote_text(vote),
            "vote_color": vote_color(vote, theme),
        }
        for label, kind, vote, value in spec
    ]


# --- verdict hero view-model -------------------------------------------------

def verdict_view(signal_result: dict, threshold: int, theme: dict) -> dict[str, object]:
    """Assemble the verdict-hero + consensus view-model."""
    final = signal_result["final_recommendation"]
    quant = signal_result["quant_bias"]
    gate = sentiment_gate(signal_result)
    return {
        "word": final,
        "shape": verdict_shape(final),
        "metal_word": "" if final == "HOLD" else "GOLD",
        "color": verdict_color(final, theme),
        "stale": signal_result["sentiment_stale"],
        "net_signed": signed_int(signal_result["net_votes"]),
        "threshold": threshold,
        "quant_bias": quant,
        "quant_color": verdict_color(quant, theme),
        "gate": gate,
        "gate_label": gate_label(gate),
        "gate_color": gate_color(gate, theme),
    }


# --- verdict prose -----------------------------------------------------------

def verdict_reason(signal_result: dict) -> str:
    """One plain-language sentence explaining the final call."""
    gate = sentiment_gate(signal_result)
    quant = signal_result["quant_bias"]
    if gate == "stale":
        return "Sentiment is stale — the call is held to protect capital."
    if gate == "neutral":
        return "No quant consensus — signals are mixed, so the call is hold."
    if gate == "passed":
        return f"Quant reads {quant} and sentiment confirms — a clean {quant.lower()}."
    return (f"Quant reads {quant}, but sentiment blocks it — "
            "capital stays where it is.")


def gate_detail(signal_result: dict, age: float | None,
                max_age: float, threshold: int) -> str:
    """The consensus panel's explanation of the sentiment gate."""
    gate = sentiment_gate(signal_result)
    quant = signal_result["quant_bias"]
    score = signal_result["sentiment_score"]
    if gate == "stale":
        if age is None:
            return "No sentiment snapshot on record — a fresh read is needed."
        return (f"Last sentiment is {age:.1f} d old, beyond the {max_age:g} d max. "
                "Stale sentiment forces a conservative HOLD.")
    if gate == "neutral":
        net = signal_result["net_votes"]
        return f"No quant trade to gate — net {signed_int(net)} within ±{threshold}."
    age_txt = f" ({age:.1f} d old)" if age is not None else ""
    if gate == "passed":
        return (f"Sentiment {signed(score, 1)}{age_txt} is aligned and "
                f"clears the {quant}.")
    return (f"Sentiment {signed(score, 1)}{age_txt} opposes the {quant} and "
            "vetoes it toward HOLD.")


# --- settings grouping -------------------------------------------------------

def _field(label: str, key: str, settings: dict, field_type: str = "default") -> dict[str, str]:
    return {"label": label, "key": key, "value": settings.get(key, ""), "type": field_type}


def settings_groups(settings: dict) -> list[dict[str, object]]:
    """Grouped, labeled inputs for every system_settings key (API keys masked)."""
    return [
        {"title": "Indicators", "fields": [
            _field("RSI period", "rsi_period", settings, "number"),
            _field("RSI oversold", "rsi_oversold", settings, "number"),
            _field("RSI overbought", "rsi_overbought", settings, "number"),
            _field("Vol band σ", "vol_band_deviations", settings, "number"),
        ]},
        {"title": "Ratio & fusion", "fields": [
            _field("GSR band σ", "gsr_band_deviations", settings, "number"),
            _field("Quant vote threshold", "quant_vote_threshold", settings, "number"),
            _field("Sentiment max age (days)", "sentiment_max_age_days", settings, "number"),
        ]},
        {"title": "Spread engine", "fields": [
            _field("Default buy spread (MYR/g)", "default_buy_spread", settings),
            _field("Default sell spread (MYR/g)", "default_sell_spread", settings),
        ]},
        {"title": "Locale & keys", "fields": [
            _field("Base currency", "BASE_CURRENCY", settings),
            _field("Timezone", "TIMEZONE", settings),
            _field("Gemini API key", "GEMINI_API_KEY", settings, "password"),
            _field("Commodity API key", "COMMODITY_API_KEY", settings, "password"),
        ]},
    ]
