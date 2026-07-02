"""Unit tests for the pure presentation helpers (ui/presenter.py).

These encode the display contract from spec §5.3 and the Claude Design file
(AuDash.dc.html): number formatting, verdict/vote color mapping, the sentiment
gate, the GSR balance geometry, cash<->mass derivation, and the view-models the
Streamlit layer renders. All functions are pure (no DB, no Streamlit).
"""

from datetime import datetime, timezone

import pandas as pd
import pytest

from ui import presenter
from ui.theme import THEME


# --- number formatting -------------------------------------------------------

def test_fmt_groups_thousands_and_fixes_decimals():
    assert presenter.fmt(1234.5) == "1,234.50"
    assert presenter.fmt(520.0) == "520.00"
    assert presenter.fmt(73.4, 1) == "73.4"


def test_signed_prefixes_plus_for_non_negative():
    assert presenter.signed(1.2, 1) == "+1.2"
    assert presenter.signed(0.0, 2) == "+0.00"
    assert presenter.signed(-3.4, 1) == "-3.4"


def test_signed_int_prefixes_plus_for_non_negative():
    assert presenter.signed_int(2) == "+2"
    assert presenter.signed_int(0) == "+0"
    assert presenter.signed_int(-1) == "-1"


# --- verdict / vote colors ---------------------------------------------------

def test_verdict_color_maps_recommendation_to_palette():
    assert presenter.verdict_color("BUY", THEME) == THEME["buy"]
    assert presenter.verdict_color("SELL", THEME) == THEME["sell"]
    assert presenter.verdict_color("HOLD", THEME) == THEME["hold"]


def test_vote_text_renders_signed_single_digit():
    assert presenter.vote_text(1) == "+1"
    assert presenter.vote_text(0) == "0"
    assert presenter.vote_text(-1) == "-1"


def test_vote_color_follows_sign():
    assert presenter.vote_color(1, THEME) == THEME["buy"]
    assert presenter.vote_color(-1, THEME) == THEME["sell"]
    assert presenter.vote_color(0, THEME) == THEME["muted"]


# --- sentiment gate ----------------------------------------------------------

def test_sentiment_gate_stale_takes_priority():
    sig = {"sentiment_stale": True, "quant_bias": "SELL", "final_recommendation": "HOLD"}
    assert presenter.sentiment_gate(sig) == "stale"


def test_sentiment_gate_vetoed_when_final_drops_to_hold():
    sig = {"sentiment_stale": False, "quant_bias": "SELL", "final_recommendation": "HOLD"}
    assert presenter.sentiment_gate(sig) == "vetoed"


def test_sentiment_gate_passed_when_final_matches_quant():
    sig = {"sentiment_stale": False, "quant_bias": "BUY", "final_recommendation": "BUY"}
    assert presenter.sentiment_gate(sig) == "passed"


def test_sentiment_gate_neutral_when_no_quant_trade():
    sig = {"sentiment_stale": False, "quant_bias": "HOLD", "final_recommendation": "HOLD"}
    assert presenter.sentiment_gate(sig) == "neutral"


def test_gate_label_and_color():
    assert presenter.gate_label("neutral") == "No quant trade"
    assert presenter.gate_color("passed", THEME) == THEME["buy"]
    assert presenter.gate_color("vetoed", THEME) == THEME["sell"]
    assert presenter.gate_color("stale", THEME) == THEME["sell"]
    assert presenter.gate_color("neutral", THEME) == THEME["hold"]


# --- GSR balance geometry ----------------------------------------------------

def test_gsr_position_gold_rich_above_band_tilts_and_clamps():
    pos = presenter.gsr_position(88.8, 78.0, 86.5)
    assert pos["side"] == "gold"
    assert "Gold-rich" in pos["label"]
    # frac > 1 -> clamped to 1 -> +11 degrees
    assert pos["degrees"] == pytest.approx(11.0)


def test_gsr_position_silver_rich_below_band_tilts_negative():
    pos = presenter.gsr_position(75.2, 78.0, 86.5)
    assert pos["side"] == "silver"
    assert "Silver-rich" in pos["label"]
    assert pos["degrees"] == pytest.approx(-11.0)


def test_gsr_position_within_band_is_balanced_and_level():
    pos = presenter.gsr_position(82.25, 78.0, 86.5)
    assert pos["side"] == "neutral"
    assert "Within band" in pos["label"]
    assert pos["degrees"] == pytest.approx(0.0)


# --- sentiment age -----------------------------------------------------------

def test_sentiment_age_days_none_when_no_snapshot():
    assert presenter.sentiment_age_days(None, datetime.now(timezone.utc)) is None


def test_sentiment_age_days_measures_utc_delta_in_fractional_days():
    snap = {"fetched_at": "2026-06-21T00:00:00+00:00"}
    now = datetime(2026, 6, 23, 0, 0, 0, tzinfo=timezone.utc)
    assert presenter.sentiment_age_days(snap, now) == pytest.approx(2.0)


# --- cash <-> mass derivation ------------------------------------------------

def test_resolve_trade_amounts_cash_mode_derives_mass():
    out = presenter.resolve_trade_amounts("cash", "5000", 520.0)
    assert out["fiat_total_myr"] == pytest.approx(5000.0)
    assert out["mass_grams"] == pytest.approx(9.615384, abs=1e-5)


def test_resolve_trade_amounts_mass_mode_derives_cash():
    out = presenter.resolve_trade_amounts("mass", "10", 520.0)
    assert out["mass_grams"] == pytest.approx(10.0)
    assert out["fiat_total_myr"] == pytest.approx(5200.0)


def test_resolve_trade_amounts_blank_input_is_zero():
    out = presenter.resolve_trade_amounts("cash", "", 520.0)
    assert out == {"mass_grams": 0.0, "fiat_total_myr": 0.0}


def test_resolve_trade_amounts_zero_rate_does_not_divide_by_zero():
    out = presenter.resolve_trade_amounts("cash", "5000", 0.0)
    assert out["mass_grams"] == 0.0


# --- view-models -------------------------------------------------------------

def _market():
    return {
        "gold_buy": 520.0, "gold_sell": 500.0,
        "silver_buy": 6.0, "silver_sell": 5.54,
        "buy_spread": 12.0, "sell_spread": 8.0,
        "holdings": 125.0, "cost_basis": 478.5,
        "pnl": 2687.5, "rsi": 73.4, "percent_b": 1.04, "sentiment": 1.2,
        "momentum_roc": 0.03, "trend_strength": 0.82, "up_day_ratio": 0.7,
        "price_deviation": 0.015, "coeff_variation": 0.012,
    }


# Zone A — the Market: four live rates, colored by metal (not boxed).
def test_build_market_readouts_four_rates_colored_by_metal():
    r = presenter.build_market_readouts(_market(), THEME)
    assert [x["label"] for x in r] == ["Gold buy", "Gold sell", "Silver buy", "Silver sell"]
    assert r[0]["value"] == "520.00" and r[0]["color"] == THEME["gold"]
    assert r[2]["color"] == THEME["silver"]
    assert all(x["unit"] == "MYR/g" for x in r)


# Zone B — the Portfolio: PnL is the emphasized readout (sign + shape + color).
def test_pnl_readout_signs_shape_and_color():
    pos = presenter.pnl_readout(2687.5, THEME)
    assert pos["value"] == "+2,687.50"
    assert pos["shape"] == "▲" and pos["color"] == THEME["buy"]
    neg = presenter.pnl_readout(-100.0, THEME)
    assert neg["shape"] == "▼" and neg["color"] == THEME["sell"]
    flat = presenter.pnl_readout(0.0, THEME)
    assert flat["shape"] == "○" and flat["color"] == THEME["muted"]


def test_build_portfolio_readouts_secondary_and_emphasized_pnl():
    port = presenter.build_portfolio_readouts(_market(), THEME)
    assert [x["label"] for x in port["secondary"]] == ["Holdings", "Cost basis"]
    assert port["secondary"][0]["value"] == "125.000" and port["secondary"][0]["unit"] == "g"
    assert port["pnl"]["label"] == "Unrealized PnL"
    assert port["pnl"]["value"] == "+2,687.50"


# Zone C — the Engine: secondary raw readings, sentiment colored by sign.
def test_build_engine_readouts_order_and_sentiment_sign_color():
    eng = presenter.build_engine_readouts(_market(), THEME)
    assert [x["label"] for x in eng] == [
        "RSI", "%B", "Trend R²", "Up-day ratio", "Price dev", "Volatility (CoV)",
        "Sentiment", "Eff. buy spread", "Eff. sell spread"]
    sent = next(x for x in eng if x["label"] == "Sentiment")
    assert sent["value"] == "+1.2" and sent["color"] == THEME["buy"]

    m = _market()
    m["sentiment"] = -2.0
    neg = presenter.build_engine_readouts(m, THEME)
    assert next(x for x in neg if x["label"] == "Sentiment")["color"] == THEME["sell"]


def test_verdict_shape_encodes_by_geometry_not_hue():
    assert presenter.verdict_shape("BUY") == "▲"
    assert presenter.verdict_shape("SELL") == "▼"
    assert presenter.verdict_shape("HOLD") == "○"


def _signal_result():
    return {
        "rsi_vote": -1, "vol_vote": -1, "gsr_vote": -1, "roc_vote": -1,
        "trend_strength": 0.82, "net_votes": -4,
        "quant_bias": "SELL", "sentiment_score": 1.2, "sentiment_stale": False,
        "final_recommendation": "HOLD",
    }


def test_build_signal_rows_maps_votes_to_four_rows():
    inputs = {"rsi": 73.4, "percent_b": 1.04, "gsr": 88.8, "roc": -0.03}
    rows = presenter.build_signal_rows(_signal_result(), inputs, THEME)
    assert [r["label"] for r in rows] == [
        "RSI (14)", "Volatility band (%B)", "Gold / Silver Ratio", "Momentum (ROC)"]
    assert rows[0]["vote_text"] == "-1"
    assert rows[0]["vote_color"] == THEME["sell"]
    assert rows[3]["vote_text"] == "-1"
    assert "downtrend" in rows[3]["detail"]


def test_verdict_view_blanks_metal_word_on_hold_and_signs_net():
    view = presenter.verdict_view(_signal_result(), threshold=2, theme=THEME)
    assert view["word"] == "HOLD"
    assert view["metal_word"] == ""
    assert view["net_signed"] == "-4"
    assert view["threshold"] == 2
    assert view["stale"] is False
    assert view["shape"] == "○"   # HOLD encodes by shape too, not just hue


def test_verdict_view_sets_metal_word_when_trading():
    sig = _signal_result()
    sig["final_recommendation"] = "SELL"
    view = presenter.verdict_view(sig, threshold=2, theme=THEME)
    assert view["metal_word"] == "GOLD"
    assert view["word"] == "SELL"


# --- settings grouping -------------------------------------------------------

def test_verdict_reason_stale_protects_capital():
    sig = {"sentiment_stale": True, "quant_bias": "SELL", "final_recommendation": "HOLD"}
    reason = presenter.verdict_reason(sig).lower()
    assert "stale" in reason and "capital" in reason


def test_verdict_reason_vetoed_mentions_block():
    sig = {"sentiment_stale": False, "quant_bias": "SELL", "final_recommendation": "HOLD"}
    assert "block" in presenter.verdict_reason(sig).lower()


def test_verdict_reason_passed_is_clean_trade():
    sig = {"sentiment_stale": False, "quant_bias": "BUY", "final_recommendation": "BUY"}
    assert "clean buy" in presenter.verdict_reason(sig).lower()


def test_verdict_reason_neutral_is_mixed():
    sig = {"sentiment_stale": False, "quant_bias": "HOLD", "final_recommendation": "HOLD"}
    assert "mixed" in presenter.verdict_reason(sig).lower()


def test_gate_detail_stale_without_snapshot():
    sig = {"sentiment_stale": True, "quant_bias": "HOLD",
           "final_recommendation": "HOLD", "sentiment_score": None, "net_votes": 0}
    detail = presenter.gate_detail(sig, age=None, max_age=2.0, threshold=2)
    assert "no sentiment" in detail.lower()


def test_gate_detail_stale_reports_age_and_limit():
    sig = {"sentiment_stale": True, "quant_bias": "BUY",
           "final_recommendation": "HOLD", "sentiment_score": 0.5, "net_votes": 2}
    detail = presenter.gate_detail(sig, age=4.1, max_age=2.0, threshold=2)
    assert "4.1" in detail and "beyond" in detail.lower()


def test_gate_detail_passed_mentions_clears():
    sig = {"sentiment_stale": False, "quant_bias": "BUY",
           "final_recommendation": "BUY", "sentiment_score": 0.8, "net_votes": 2}
    detail = presenter.gate_detail(sig, age=0.6, max_age=2.0, threshold=2)
    assert "clear" in detail.lower()


def test_gate_detail_neutral_surfaces_live_sentiment_and_age():
    # Quant is neutral, but a fresh sentiment reading exists. The panel must
    # still show the live score + freshness (show-the-why) so a refresh that
    # can't move a neutral verdict still visibly registers, while explaining
    # there is no quant trade for sentiment to gate.
    sig = {"sentiment_stale": False, "quant_bias": "HOLD",
           "final_recommendation": "HOLD", "sentiment_score": 0.8, "net_votes": 0}
    detail = presenter.gate_detail(sig, age=0.0, max_age=2.0, threshold=2)
    assert "+0.8" in detail                       # live score is surfaced
    assert "0.0 d" in detail                       # freshness is surfaced
    assert "no quant trade" in detail.lower()      # still explains the non-gate
    assert "+0 within ±2" in detail                # net-vote context retained


def test_sentiment_refresh_note_reports_score_and_neutral_verdict():
    # A successful refresh against a neutral quant engine: report the new score
    # and make clear the verdict is unaffected (not a broken button).
    note = presenter.sentiment_refresh_note(0.8, "HOLD")
    assert "+0.8" in note
    assert "HOLD" in note
    assert "neutral" in note.lower()


def test_sentiment_refresh_note_active_gate_names_the_bias():
    note = presenter.sentiment_refresh_note(-1.5, "SELL")
    assert "-1.5" in note
    assert "SELL" in note


def test_settings_groups_cover_keys_and_mask_api_keys():
    settings = {
        "rsi_period": "14", "rsi_oversold": "30", "rsi_overbought": "70",
        "vol_band_deviations": "2", "gsr_band_deviations": "2",
        "quant_vote_threshold": "2", "sentiment_max_age_days": "2",
        "default_buy_spread": "12.0", "default_sell_spread": "8.0",
        "BASE_CURRENCY": "MYR", "TIMEZONE": "Asia/Kuala_Lumpur",
        "GEMINI_API_KEY": "secret", "COMMODITY_API_KEY": "secret2",
    }
    groups = presenter.settings_groups(settings)
    titles = [g["title"] for g in groups]
    assert "Indicators" in titles
    all_fields = [f for g in groups for f in g["fields"]]
    by_key = {f["key"]: f for f in all_fields}
    assert "spread_recency_alpha" not in by_key
    assert "spread_staleness_tau" not in by_key
    assert "default_buy_spread" in by_key
    assert "momentum_r2_min" in by_key   # the new R²-gate knob is editable
    assert by_key["rsi_period"]["value"] == "14"
    assert by_key["GEMINI_API_KEY"]["type"] == "password"


def test_settings_groups_includes_editable_gemini_model():
    settings = {"GEMINI_MODEL": "gemini-3-flash-preview"}
    groups = presenter.settings_groups(settings)
    by_key = {f["key"]: f for g in groups for f in g["fields"]}
    assert "GEMINI_MODEL" in by_key
    assert by_key["GEMINI_MODEL"]["value"] == "gemini-3-flash-preview"
    assert by_key["GEMINI_MODEL"]["type"] != "password"  # model id isn't a secret


# --- amount parsing (thousands separators / pasted values) -------------------

def test_resolve_trade_amounts_strips_thousands_separators():
    out = presenter.resolve_trade_amounts("cash", "1,234.56", 1.0)
    assert out["fiat_total_myr"] == pytest.approx(1234.56)


def test_resolve_trade_amounts_strips_currency_prefix():
    out = presenter.resolve_trade_amounts("cash", "RM 5,000.00", 1.0)
    assert out["fiat_total_myr"] == pytest.approx(5000.0)


def test_resolve_trade_amounts_accepts_native_float():
    out = presenter.resolve_trade_amounts("mass", 2.45, 100.0)
    assert out["mass_grams"] == pytest.approx(2.45)
    assert out["fiat_total_myr"] == pytest.approx(245.0)


def test_resolve_trade_amounts_garbage_is_zero():
    out = presenter.resolve_trade_amounts("cash", "abc", 520.0)
    assert out == {"mass_grams": 0.0, "fiat_total_myr": 0.0}


# --- trade confirm line ------------------------------------------------------

def test_trade_confirm_line_carries_all_fields():
    line = presenter.trade_confirm_line("BUY", "GOLD", 2.45, 1012.4, 413.22)
    assert "BUY" in line and "GOLD" in line
    assert "2.450" in line
    assert "413.22" in line
    assert "1,012.40" in line


# --- recent trades + reversal ------------------------------------------------

def _trades_df():
    return pd.DataFrame([
        {"id": "a", "timestamp": "2026-06-20T12:00:00+00:00", "action_type": "BUY",
         "metal": "GOLD", "execution_rate_myr": 400.0, "mass_grams": 2.0,
         "fiat_total_myr": 800.0},
        {"id": "b", "timestamp": "2026-06-22T12:00:00+00:00", "action_type": "SELL",
         "metal": "SILVER", "execution_rate_myr": 5.0, "mass_grams": 10.0,
         "fiat_total_myr": 50.0},
    ])


def _trades_with_void_df():
    return pd.DataFrame([
        {"id": "a", "timestamp": "2026-06-20T12:00:00+00:00", "action_type": "BUY",
         "metal": "GOLD", "execution_rate_myr": 400.0, "mass_grams": 2.0,
         "fiat_total_myr": 800.0, "reverses_id": None},
        {"id": "rev-a", "timestamp": "2026-06-21T12:00:00+00:00",
         "action_type": "SELL", "metal": "GOLD", "execution_rate_myr": 400.0,
         "mass_grams": 2.0, "fiat_total_myr": 800.0, "reverses_id": "a"},
        {"id": "b", "timestamp": "2026-06-22T12:00:00+00:00", "action_type": "BUY",
         "metal": "SILVER", "execution_rate_myr": 5.0, "mass_grams": 10.0,
         "fiat_total_myr": 50.0, "reverses_id": None},
    ])


def test_build_recent_trades_empty_returns_empty_list():
    empty = pd.DataFrame(columns=["id", "timestamp", "action_type", "metal",
                                  "execution_rate_myr", "mass_grams", "fiat_total_myr"])
    assert presenter.build_recent_trades(empty, THEME) == []


def test_build_recent_trades_orders_newest_first():
    rows = presenter.build_recent_trades(_trades_df(), THEME)
    assert [r["id"] for r in rows] == ["b", "a"]
    assert rows[0]["date"] == "2026-06-22"


def test_build_recent_trades_limit_caps_rows():
    rows = presenter.build_recent_trades(_trades_df(), THEME, limit=1)
    assert len(rows) == 1
    assert rows[0]["id"] == "b"


def test_build_recent_trades_maps_color_and_opposite():
    rows = presenter.build_recent_trades(_trades_df(), THEME)
    buy_row = next(r for r in rows if r["id"] == "a")
    assert buy_row["action"] == "BUY"
    assert buy_row["color"] == THEME["buy"]
    assert buy_row["opposite"] == "SELL"
    assert buy_row["mass"] == "2.000"
    assert buy_row["mass_grams"] == pytest.approx(2.0)


def test_reversal_entry_flips_action_and_preserves_amounts():
    rev = presenter.reversal_entry("BUY", "GOLD", 400.0, 2.0, 800.0)
    assert rev == {"action_type": "SELL", "metal": "GOLD",
                   "execution_rate_myr": 400.0, "mass_grams": 2.0,
                   "fiat_total_myr": 800.0}
    back = presenter.reversal_entry("SELL", "SILVER", 5.0, 10.0, 50.0)
    assert back["action_type"] == "BUY"


def test_build_trade_markers_excludes_voided_and_reversal():
    markers = presenter.build_trade_markers(_trades_with_void_df())
    # only the live trade 'b' survives; voided 'a' and its reversal 'rev-a' hidden
    assert len(markers) == 1
    assert markers[0] == {"date": "2026-06-22", "side": "BUY", "price": 5.0}


def test_build_trade_markers_legacy_frame_shows_all():
    markers = presenter.build_trade_markers(_trades_df())
    assert len(markers) == 2
    assert {m["side"] for m in markers} == {"BUY", "SELL"}


def test_build_trade_markers_empty_is_empty_list():
    empty = pd.DataFrame(columns=["id", "timestamp", "action_type", "metal",
                                  "execution_rate_myr", "mass_grams",
                                  "fiat_total_myr", "reverses_id"])
    assert presenter.build_trade_markers(empty) == []


def test_build_recent_trades_marks_voided_and_drops_reversal():
    rows = presenter.build_recent_trades(_trades_with_void_df(), THEME)
    ids = [r["id"] for r in rows]
    assert "rev-a" not in ids               # reversal folded away
    assert ids == ["b", "a"]                # order unchanged, voided stays in place
    assert next(r for r in rows if r["id"] == "a")["voided"] is True
    assert next(r for r in rows if r["id"] == "b")["voided"] is False


def test_build_recent_trades_limit_counts_only_visible_trades():
    df = pd.DataFrame([
        {"id": "t1", "timestamp": "2026-06-01T12:00:00+00:00", "action_type": "BUY",
         "metal": "GOLD", "execution_rate_myr": 400.0, "mass_grams": 1.0,
         "fiat_total_myr": 400.0, "reverses_id": None},
        {"id": "t2", "timestamp": "2026-06-02T12:00:00+00:00", "action_type": "BUY",
         "metal": "GOLD", "execution_rate_myr": 400.0, "mass_grams": 1.0,
         "fiat_total_myr": 400.0, "reverses_id": None},
        {"id": "rev", "timestamp": "2026-06-09T12:00:00+00:00", "action_type": "SELL",
         "metal": "GOLD", "execution_rate_myr": 400.0, "mass_grams": 1.0,
         "fiat_total_myr": 400.0, "reverses_id": "t2"},
    ])
    rows = presenter.build_recent_trades(df, THEME, limit=2)
    # reversal dropped first, so its recent timestamp never evicts t1
    assert [r["id"] for r in rows] == ["t2", "t1"]
    assert next(r for r in rows if r["id"] == "t2")["voided"] is True


def test_build_recent_trades_legacy_frame_without_link_column():
    rows = presenter.build_recent_trades(_trades_df(), THEME)
    assert {r["id"] for r in rows} == {"a", "b"}
    assert all(r["voided"] is False for r in rows)


# --- quote preview + recent quotes -------------------------------------------

def test_quote_preview_computes_per_side_spread_vs_spot():
    prev = presenter.quote_preview(104.0, 97.0, 100.0)
    assert prev["buy_spread"] == pytest.approx(4.0)   # 104 - 100
    assert prev["sell_spread"] == pytest.approx(3.0)  # 100 - 97
    assert prev["inverted"] is False


def test_quote_preview_flags_inverted_when_buy_below_sell():
    prev = presenter.quote_preview(500.0, 510.0, 505.0)
    assert prev["inverted"] is True


def test_build_recent_quotes_newest_first_with_raw_keys():
    quotes = pd.DataFrame([
        {"date": "2026-06-20", "metal": "GOLD", "buy_rate_myr": 500.0,
         "sell_rate_myr": 490.0, "recorded_at": "x"},
        {"date": "2026-06-24", "metal": "SILVER", "buy_rate_myr": 7.0,
         "sell_rate_myr": 6.5, "recorded_at": "y"},
    ])
    rows = presenter.build_recent_quotes(quotes)
    assert rows[0]["date"] == "2026-06-24"   # newest first
    assert rows[0]["metal"] == "SILVER"
    assert rows[0]["buy"] == "7.00"
    assert rows[1]["sell"] == "490.00"


def test_build_recent_quotes_empty_is_empty_list():
    assert presenter.build_recent_quotes(pd.DataFrame()) == []


# --- back-dated trade rate prefill -------------------------------------------

def test_backdated_rate_prefills_uses_quote_when_present():
    row = {"buy_rate_myr": 433.0, "sell_rate_myr": 428.0}
    assert presenter.backdated_rate_prefills(row, 999.0, 888.0) == {
        "buy": 433.0, "sell": 428.0}


def test_backdated_rate_prefills_falls_back_to_live_when_no_quote():
    assert presenter.backdated_rate_prefills(None, 999.0, 888.0) == {
        "buy": 999.0, "sell": 888.0}


# --- back-dated single-sided quote (entered side exact, other side derived) --

def test_backdated_quote_buy_estimates_sell_from_median_width():
    # No existing quote: the un-entered SELL side sits the median bid-ask width
    # (buy_spread + sell_spread) below the entered BUY rate.
    q = presenter.backdated_quote("BUY", 425.0, buy_spread=12.0, sell_spread=8.0)
    assert q == {"buy": 425.0, "sell": 405.0}


def test_backdated_quote_sell_estimates_buy_from_median_width():
    q = presenter.backdated_quote("SELL", 421.0, buy_spread=12.0, sell_spread=8.0)
    assert q == {"buy": 441.0, "sell": 421.0}


def test_backdated_quote_preserves_recorded_other_side():
    # A real recorded quote exists for the date: the entered side overwrites its
    # side, the other side is kept verbatim (not re-estimated).
    existing = {"buy": 433.0, "sell": 428.0}
    sell_trade = presenter.backdated_quote("SELL", 430.0, buy_spread=12.0,
                                           sell_spread=8.0, existing=existing)
    assert sell_trade == {"buy": 433.0, "sell": 430.0}
    buy_trade = presenter.backdated_quote("BUY", 435.0, buy_spread=12.0,
                                          sell_spread=8.0, existing=existing)
    assert buy_trade == {"buy": 435.0, "sell": 428.0}


def test_backdated_quote_floors_estimated_side_at_zero():
    # Width wider than the entered rate would push the estimate negative; floor it.
    q = presenter.backdated_quote("BUY", 5.0, buy_spread=12.0, sell_spread=8.0)
    assert q == {"buy": 5.0, "sell": 0.0}


# --- position-aware presentation (Task 4) ------------------------------------

def _overridden(action, final="SELL"):
    return {
        "final_recommendation": final, "quant_bias": "BUY",
        "sentiment_stale": False, "sentiment_score": 1.0, "net_votes": 3,
        "position_action": action, "directional_recommendation": "BUY",
        "pnl_pct": -8.0, "reasons": [],
    }


def test_is_overridden_true_for_each_action():
    for a in ("EMERGENCY_LIQUIDATION", "TAKE_PROFIT", "AT_CAP",
              "NOTHING_TO_LIQUIDATE"):
        assert presenter.is_overridden({"position_action": a}) is True


def test_is_overridden_false_when_no_action():
    assert presenter.is_overridden({"position_action": None}) is False
    assert presenter.is_overridden({}) is False


def test_verdict_reason_describes_emergency_liquidation():
    msg = presenter.verdict_reason(_overridden("EMERGENCY_LIQUIDATION"))
    assert "liquidat" in msg.lower() or "stop-loss" in msg.lower()


def test_verdict_reason_override_not_mislabeled_as_sentiment():
    # A stop-loss flips a directional BUY to SELL; it must NOT read as a
    # sentiment veto (that would look like a concurrency bug).
    msg = presenter.verdict_reason(_overridden("EMERGENCY_LIQUIDATION"))
    assert "sentiment" not in msg.lower()


def test_gate_detail_decoupled_when_overridden():
    msg = presenter.gate_detail(_overridden("EMERGENCY_LIQUIDATION"), 0.5, 2.0, 2)
    assert "decoupled" in msg.lower() or "risk policy" in msg.lower()


def test_verdict_view_exposes_is_overridden():
    view = presenter.verdict_view(_overridden("EMERGENCY_LIQUIDATION"), 2, THEME)
    assert view["is_overridden"] is True
    assert view["position_action"] == "EMERGENCY_LIQUIDATION"


def test_verdict_view_not_overridden_for_plain_signal():
    plain = {
        "final_recommendation": "HOLD", "quant_bias": "HOLD",
        "sentiment_stale": False, "sentiment_score": 0.0, "net_votes": 0,
        "reasons": [],
    }
    view = presenter.verdict_view(plain, 2, THEME)
    assert view["is_overridden"] is False


def test_verdict_view_neutralizes_gate_badge_on_override():
    # EMERGENCY_LIQUIDATION: quant_bias=BUY, fresh sentiment, final=SELL.
    # sentiment_gate() returns "vetoed" but the risk desk owns the call —
    # the badge must show "Decoupled"/muted, NOT "Vetoed"/sell.
    view = presenter.verdict_view(_overridden("EMERGENCY_LIQUIDATION"), 2, THEME)
    assert view["gate_label"] == "Decoupled"
    assert view["gate_color"] == THEME["muted"]
    assert view["gate_color"] != THEME["sell"]  # explicitly NOT the red mislabel


def test_verdict_view_keeps_real_gate_badge_when_not_overridden():
    # A genuine sentiment veto (no override): quant=BUY, final=HOLD, fresh
    # negative sentiment.  The real badge must survive unchanged.
    sig = {
        "quant_bias": "BUY", "final_recommendation": "HOLD",
        "sentiment_stale": False, "sentiment_score": -1.0, "net_votes": 3,
        "position_action": None, "reasons": [],
    }
    view = presenter.verdict_view(sig, 2, THEME)
    assert view["gate_label"] == "Vetoed"
    assert view["gate_color"] == THEME["sell"]


# --- morning briefing ---------------------------------------------------------

def _briefing_model(**overrides) -> dict:
    """Minimal dashboard-model stub for build_morning_briefing."""
    model = {
        "signal_result": {
            "final_recommendation": "BUY", "quant_bias": "BUY",
            "sentiment_stale": False, "sentiment_score": 1.5,
            "net_votes": 2, "position_action": None,
        },
        "sentiment": {"sentiment_score": 1.5,
                      "analytical_summary": "Risk appetite firm.",
                      "fetched_at": "2026-07-02T00:00:00+00:00"},
        "sentiment_age": 0.5,
        "settings": {"sentiment_max_age_days": "2"},
        "spot_today": {"GOLD": 500.0, "SILVER": 6.0},
        "spot_prev": {"GOLD": 495.0, "SILVER": 6.1},
        "gsr_band": {"value": 83.3, "lower": 80.0, "upper": 90.0},
        "market": {"holdings": 0.0, "pnl": 0.0},
    }
    model.update(overrides)
    return model


def test_briefing_top_call_carries_verdict_shape_and_reason():
    lines = presenter.build_morning_briefing(_briefing_model(), THEME)
    top = lines[0]
    assert top["label"] == "Top call"
    assert top["text"].startswith("▲ BUY")
    assert "sentiment confirms" in top["text"]
    assert top["color"] == THEME["buy"]
    assert top["warn"] is False


def test_briefing_overnight_reports_both_metals_and_gsr():
    lines = presenter.build_morning_briefing(_briefing_model(), THEME)
    overnight = lines[1]
    assert overnight["label"] == "Overnight"
    assert "Gold +5.00 MYR/g (+1.0%)" in overnight["text"]
    assert "Silver -0.10 MYR/g (-1.6%)" in overnight["text"]
    assert "GSR 83.3" in overnight["text"]
    assert "Within band" in overnight["text"]


def test_briefing_overnight_degrades_without_previous_spot():
    model = _briefing_model(spot_prev={"GOLD": None, "SILVER": None})
    overnight = presenter.build_morning_briefing(model, THEME)[1]
    assert overnight["text"] == "No new spot reading since the previous session."
    assert overnight["warn"] is False


def test_briefing_sentiment_line_shows_summary_and_age():
    lines = presenter.build_morning_briefing(_briefing_model(), THEME)
    senti = lines[2]
    assert senti["label"] == "Sentiment"
    assert "Risk appetite firm." in senti["text"]
    assert "12 h ago" in senti["text"]
    assert senti["warn"] is False


def test_briefing_sentiment_stale_warns():
    model = _briefing_model(sentiment_age=3.2)
    model["signal_result"]["sentiment_stale"] = True
    model["signal_result"]["final_recommendation"] = "HOLD"
    senti = presenter.build_morning_briefing(model, THEME)[2]
    assert senti["warn"] is True
    assert "3.2 d old" in senti["text"]
    assert "HOLD" in senti["text"]


def test_briefing_sentiment_stale_age_unknown_warns():
    model = _briefing_model(sentiment_age=None)
    model["signal_result"]["sentiment_stale"] = True
    model["signal_result"]["final_recommendation"] = "HOLD"
    senti = presenter.build_morning_briefing(model, THEME)[2]
    assert senti["warn"] is True
    assert "d old" not in senti["text"]
    assert "beyond the" in senti["text"]
    assert "HOLD" in senti["text"]


def test_briefing_sentiment_missing_warns():
    model = _briefing_model(sentiment=None, sentiment_age=None)
    model["signal_result"]["sentiment_stale"] = True
    senti = presenter.build_morning_briefing(model, THEME)[2]
    assert senti["warn"] is True
    assert "No sentiment snapshot" in senti["text"]


def test_briefing_watch_omitted_when_flat_and_unoverridden():
    lines = presenter.build_morning_briefing(_briefing_model(), THEME)
    assert len(lines) == 3


def test_briefing_watch_reports_open_position():
    model = _briefing_model(market={"holdings": 12.5, "pnl": 62.5})
    watch = presenter.build_morning_briefing(model, THEME)[3]
    assert watch["label"] == "Watch"
    assert "12.500 g" in watch["text"]
    assert "+62.50 MYR" in watch["text"]


def test_briefing_watch_reports_risk_override_first():
    model = _briefing_model(market={"holdings": 12.5, "pnl": -900.0})
    model["signal_result"]["position_action"] = "EMERGENCY_LIQUIDATION"
    watch = presenter.build_morning_briefing(model, THEME)[3]
    assert "emergency liquidation" in watch["text"].lower()
    assert watch["warn"] is True
    assert watch["color"] == THEME["sell"]


def test_briefing_watch_benign_override_does_not_warn():
    model = _briefing_model(market={"holdings": 12.5, "pnl": -900.0})
    model["signal_result"]["position_action"] = "AT_CAP"
    watch = presenter.build_morning_briefing(model, THEME)[3]
    assert "at position cap" in watch["text"].lower()
    assert watch["warn"] is False
    assert watch["color"] == THEME["text"]


def test_sentiment_text_fallback_uses_score_when_no_summary():
    text, warn = presenter._sentiment_text(
        {"sentiment_score": 1.5, "analytical_summary": None},
        age=0.5, stale=False, max_age=2.0)
    assert text.startswith("Score +1.5 on record.")
    assert warn is False


# --- historical price import -------------------------------------------------

def test_validate_price_import_converts_grams_to_oz():
    result = presenter.validate_price_import([
        {"date": "2025-07-01", "gold_per_gram": "488.00", "silver_per_gram": "6.10"},
    ])
    assert result["errors"] == []
    row = result["rows"][0]
    assert row["date"] == "2025-07-01"
    assert row["gold_oz"] == pytest.approx(488.00 * 31.1034768)
    assert row["silver_oz"] == pytest.approx(6.10 * 31.1034768)


def test_validate_price_import_flags_missing_columns():
    result = presenter.validate_price_import([{"date": "2025-07-01", "gold_per_gram": "488"}])
    assert result["rows"] == []
    assert "row 1" in result["errors"][0]


def test_validate_price_import_flags_unparseable_date():
    result = presenter.validate_price_import([
        {"date": "not-a-date", "gold_per_gram": "488", "silver_per_gram": "6.1"},
    ])
    assert result["rows"] == []
    assert "row 1" in result["errors"][0]


def test_validate_price_import_flags_non_positive_price():
    result = presenter.validate_price_import([
        {"date": "2025-07-01", "gold_per_gram": "0", "silver_per_gram": "6.1"},
    ])
    assert result["rows"] == []
    assert "row 1" in result["errors"][0]


def test_validate_price_import_skips_bad_rows_keeps_good_ones():
    result = presenter.validate_price_import([
        {"date": "2025-07-01", "gold_per_gram": "488", "silver_per_gram": "6.1"},
        {"date": "bogus", "gold_per_gram": "488", "silver_per_gram": "6.1"},
    ])
    assert len(result["rows"]) == 1
    assert len(result["errors"]) == 1


def test_validate_price_import_normalizes_date_formats():
    result = presenter.validate_price_import([
        {"date": "1/7/2025", "gold_per_gram": "488", "silver_per_gram": "6.1"},
    ])
    assert result["errors"] == []
    assert result["rows"][0]["date"] == "2025-07-01"


# --- chart range slicing ------------------------------------------------------

def _chart_over(n_days: int) -> dict:
    """A chart dict of n_days consecutive daily points ending 2026-01-01."""
    end = datetime(2026, 1, 1).date()
    dates = [(end - pd.Timedelta(days=n_days - 1 - i)).isoformat()
            for i in range(n_days)]
    return {
        "dates": dates,
        "price": [float(i) for i in range(n_days)],
        "bands": pd.DataFrame({
            "middle": [float(i) for i in range(n_days)],
            "upper": [float(i) + 1 for i in range(n_days)],
            "lower": [float(i) - 1 for i in range(n_days)],
        }),
        "rsi": [50.0] * n_days,
        "markers": [{"date": dates[0], "side": "BUY", "price": 0.0},
                    {"date": dates[-1], "side": "SELL", "price": float(n_days - 1)}]
        if n_days else [],
    }


def test_slice_chart_range_all_returns_full_chart_unchanged():
    chart = _chart_over(400)
    sliced = presenter.slice_chart_range(chart, "All")
    assert sliced is chart


def test_slice_chart_range_30d_keeps_only_last_30_days():
    chart = _chart_over(400)
    sliced = presenter.slice_chart_range(chart, "30d")
    assert len(sliced["dates"]) == 30
    assert sliced["dates"][-1] == chart["dates"][-1]
    assert len(sliced["price"]) == 30
    assert len(sliced["bands"]) == 30
    assert len(sliced["rsi"]) == 30


def test_slice_chart_range_drops_out_of_range_markers():
    chart = _chart_over(400)
    sliced = presenter.slice_chart_range(chart, "30d")
    assert len(sliced["markers"]) == 1
    assert sliced["markers"][0]["side"] == "SELL"


def test_slice_chart_range_handles_short_history_gracefully():
    chart = _chart_over(10)
    sliced = presenter.slice_chart_range(chart, "1y")
    assert len(sliced["dates"]) == 10


def test_slice_chart_range_empty_chart_returns_empty():
    chart = _chart_over(0)
    sliced = presenter.slice_chart_range(chart, "6m")
    assert sliced["dates"] == []
