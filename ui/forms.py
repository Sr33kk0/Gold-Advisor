"""Streamlit input surfaces: the trade ledger form and the settings panel.

These use real Streamlit widgets (so they're interactive and AppTest-driveable)
over the dark theme. All display formatting + the cash<->mass math comes from
the pure presenter; writes go through the Phase 1 DAO. The AI deps for
"Refresh sentiment now" are imported lazily so the dashboard never needs them.

The trade ledger is an append-only journal: a logged entry is confirmed before
it is written, and corrected by reversal (an exact offsetting entry) rather than
deletion — the audit trail always stays honest (capital protection, Rule 3).
State transitions go through on_click callbacks so a single natural rerun (not a
manual st.rerun) advances review -> confirm -> logged.
"""

import csv
import io
import os
from datetime import date, datetime, timedelta, timezone

import streamlit as st

from database.connection import (
    delete_daily_quote, fetch_daily_quotes, fetch_transactions,
    get_db_connection, log_transaction, set_setting, write_daily_quote,
    write_spot_prices,
)
from ui import presenter
from ui.theme import THEME
from utils.timeutil import now_utc


def _heading(eyebrow: str, title: str, blurb: str) -> None:
    st.markdown(
        f'<div class="audash-page-title">'
        f'<div class="audash-eyebrow">{eyebrow}</div>'
        f'<div role="heading" aria-level="1" style="font-family:{THEME["f_display"]};'
        f'font-weight:600;font-size:34px;color:{THEME["text"]};margin:2px 0 4px;">{title}</div>'
        f'</div>'
        f'<p style="font-family:{THEME["f_body"]};font-size:15px;'
        f'color:{THEME["sub"]};max-width:70ch;margin:0 0 22px;">{blurb}</p>',
        unsafe_allow_html=True,
    )


def _trade_timestamp(trade_date) -> str:
    """UTC ISO for a date-granular trade. Noon UTC keeps date[:10] == the
    picked date, so the spread engine's spot-on-trade-date join can't drift
    across the UTC offset (Rule 1; guards the Phase 3 date-slice caveat)."""
    return f"{trade_date.isoformat()}T12:00:00+00:00"


def _reversal_timestamp(original_ts: str) -> str:
    """Timestamp for a void's offsetting entry: now, but never before the row
    it reverses, so the chronological portfolio walk sees open-then-close."""
    now = now_utc()
    try:
        orig = datetime.fromisoformat(str(original_ts))
    except (TypeError, ValueError):
        return now.isoformat()
    if orig.tzinfo is None:
        orig = orig.replace(tzinfo=timezone.utc)
    return (now if now > orig else orig + timedelta(seconds=1)).isoformat()


# --- state-transition callbacks (run before the rerun) -----------------------

def _stage_trade(action: str, metal: str, rate: float,
                 amounts: dict, trade_date, quote: dict | None = None) -> None:
    if amounts["mass_grams"] <= 0 or amounts["fiat_total_myr"] <= 0:
        st.session_state["_trade_error"] = (
            "Enter an amount greater than zero — nothing was logged.")
        return
    if rate <= 0:
        st.session_state["_trade_error"] = (
            "Enter a platform rate greater than zero — nothing was logged.")
        return
    st.session_state.pop("_trade_error", None)
    st.session_state["pending_trade"] = {
        "action": action, "metal": metal, "rate": rate,
        "mass_grams": amounts["mass_grams"],
        "fiat_total_myr": amounts["fiat_total_myr"], "date": trade_date,
        "quote": quote,
    }


def _commit_trade() -> None:
    pending = st.session_state.get("pending_trade")
    if not pending:
        return
    try:
        with get_db_connection() as conn:
            log_transaction(
                conn, pending["action"], pending["metal"], pending["rate"],
                pending["mass_grams"], pending["fiat_total_myr"],
                timestamp=_trade_timestamp(pending["date"]))
            if pending.get("quote"):
                write_daily_quote(
                    conn, pending["date"].isoformat(), pending["metal"],
                    pending["quote"]["buy"], pending["quote"]["sell"])
    except Exception:
        st.session_state["_confirm_error"] = (
            "Couldn't write to the ledger — nothing was logged. The worker may "
            "be mid-write; try again in a moment.")
        return
    st.session_state.pop("pending_trade", None)
    quote_note = (f" · quote for {pending['date'].isoformat()} recorded"
                  if pending.get("quote") else "")
    st.session_state["_trade_flash"] = (
        f"Logged {pending['action']} · {pending['metal']} · "
        f"RM {presenter.fmt(pending['fiat_total_myr'])} → ledger{quote_note}")


def _cancel_trade() -> None:
    st.session_state.pop("pending_trade", None)


def _arm_void(tx_id: str) -> None:
    st.session_state["void_arm"] = tx_id


def _cancel_void() -> None:
    st.session_state.pop("void_arm", None)


def _commit_void(entry: dict, original_ts: str, original_id: str,
                 flash: str) -> None:
    try:
        with get_db_connection() as conn:
            log_transaction(
                conn, entry["action_type"], entry["metal"],
                entry["execution_rate_myr"], entry["mass_grams"],
                entry["fiat_total_myr"],
                timestamp=_reversal_timestamp(original_ts),
                reverses_id=original_id)
    except Exception:
        st.session_state["_void_error"] = (
            "Couldn't write the reversal — the ledger is unchanged. Retry in a "
            "moment.")
        return
    st.session_state.pop("void_arm", None)
    st.session_state["_trade_flash"] = flash


def _commit_quote(metal: str, quote_date, buy_rate: float,
                  sell_rate: float) -> None:
    if buy_rate <= 0 or sell_rate <= 0:
        st.session_state["_quote_error"] = (
            "Enter buy and sell rates greater than zero — nothing was recorded.")
        return
    st.session_state.pop("_quote_error", None)
    try:
        with get_db_connection() as conn:
            write_daily_quote(conn, quote_date.isoformat(), metal,
                              buy_rate, sell_rate)
    except Exception:
        st.session_state["_quote_error"] = (
            "Couldn't record the quote — the worker may be mid-write. Nothing "
            "was saved; retry in a moment.")
        return
    st.session_state["_trade_flash"] = (
        f"Recorded {metal} quote for {quote_date.isoformat()} · buy "
        f"{presenter.fmt(buy_rate)} / sell {presenter.fmt(sell_rate)} MYR/g")


def _delete_quote(date: str, metal: str) -> None:
    try:
        with get_db_connection() as conn:
            delete_daily_quote(conn, date, metal)
    except Exception:
        st.session_state["_quote_error"] = (
            "Couldn't delete the quote — the worker may be mid-write. Retry in "
            "a moment.")
        return
    st.session_state["_trade_flash"] = f"Deleted {metal} quote for {date}"


def _flash() -> None:
    """Surface a one-shot success message stashed by a callback across a rerun."""
    msg = st.session_state.pop("_trade_flash", None)
    if msg:
        st.success(msg)


# --- New Trade ---------------------------------------------------------------

def render_ledger_input_form(model: dict) -> None:
    """Two-step trade entry (review -> confirm) + the recent-trades ledger."""
    _heading("New Trade", "Log a transaction",
             "Confirmed before it joins the ledger. The derived value uses the "
             "live platform rate; the ledger is append-only and corrected by "
             "reversal, never erased.")
    _flash()

    pending = st.session_state.get("pending_trade")
    if pending:
        _render_trade_confirm(pending)
    else:
        _render_trade_entry(model)

    _render_recent_trades()


def _render_backdated_rates(metal: str, action: str, trade_date,
                            live_buy: float, live_sell: float,
                            buy_spread: float,
                            sell_spread: float) -> tuple[float, dict]:
    """One editable platform-rate input for a back-dated trade — the side that
    matches the action (BUY -> buy rate, SELL -> sell rate).

    Prefills from the recorded daily_quote's matching side for (trade_date,
    metal), or today's live rate for that side when none. Returns (rate, quote)
    where rate is the entered side the trade executes at and quote = {"buy",
    "sell"} is upserted as that date's quote on commit: the entered side exact,
    the other side kept from an existing recorded quote or, when none, estimated
    the median bid-ask width away (see presenter.backdated_quote). Widget key
    carries date+metal+action so a changed pick reseeds the prefill (Streamlit
    keeps a keyed widget's value).
    """
    quote_row = None
    # Degrade to the live-rate prefill if the read fails (e.g. worker
    # mid-write); the prefilled rate stays editable and is confirmed
    # before any write, so a stale prefill never reaches the ledger.
    try:
        with get_db_connection() as conn:
            quotes = fetch_daily_quotes(conn, metal)
    except Exception:
        quotes = None
    if quotes is not None and not quotes.empty:
        match = quotes[quotes["date"] == trade_date.isoformat()]
        if not match.empty:
            # daily_quotes is UNIQUE on (date, metal), so at most one row matches.
            quote_row = match.iloc[-1].to_dict()

    prefills = presenter.backdated_rate_prefills(quote_row, live_buy, live_sell)
    existing = ({"buy": float(quote_row["buy_rate_myr"]),
                 "sell": float(quote_row["sell_rate_myr"])}
                if quote_row is not None else None)
    side = "buy" if action == "BUY" else "sell"

    st.markdown(
        f'<div class="audash-eyebrow" style="margin-top:6px;">Editing historical '
        f'platform {action.lower()} rate · {trade_date.isoformat()}</div>',
        unsafe_allow_html=True)

    k = f"{trade_date.isoformat()}_{metal}_{action}"
    rate = st.number_input(
        f"Platform {action.lower()} rate · MYR/g", min_value=0.0,
        value=float(prefills[side]), step=1.0, format="%.2f",
        key=f"trade_rate_{k}",
        help=f"The platform's {action} price on this date — what this {action} "
             f"executes at and is recorded as the {trade_date.isoformat()} quote.")

    quote = presenter.backdated_quote(action, rate, buy_spread=buy_spread,
                                      sell_spread=sell_spread, existing=existing)
    other = "sell" if action == "BUY" else "buy"
    other_src = "recorded quote" if existing is not None else "median spread"
    st.markdown(
        f'<div class="audash-eyebrow">Used for this {action} · '
        f'<span style="color:{THEME["accent"]};">{presenter.fmt(rate)} MYR/g</span>'
        f' · {other} side {presenter.fmt(quote[other])} from {other_src}'
        f' · both recorded as the {trade_date.isoformat()} {metal} quote'
        f'</div>', unsafe_allow_html=True)
    if quote["buy"] > 0 and quote["sell"] > 0 and quote["buy"] < quote["sell"]:
        st.warning("Buy rate is below sell rate — did you swap them? The quote "
                   "will be recorded exactly as derived.")
    return rate, quote


def _render_trade_entry(model: dict) -> None:
    """Pick metal/action/date + a cash<->mass amount; stage a trade to review.

    Today's trade uses the read-only live platform rate; a back-dated trade
    (date before today) gets one editable rate input for the side matching the
    action (buy for BUY, sell for SELL); the other side is preserved from an
    existing recorded quote or estimated from the median spread, and both are
    recorded as that date's quote.
    """
    market = model["market"]
    today = date.fromisoformat(model["today"])

    metal = st.radio("Metal", ["GOLD", "SILVER"], horizontal=True, key="trade_metal")
    action = st.radio("Action", ["BUY", "SELL"], horizontal=True, key="trade_action")
    trade_date = st.date_input("Date", value=today, max_value=today, key="trade_date")

    live_buy = float(market[f"{metal.lower()}_buy"])
    live_sell = float(market[f"{metal.lower()}_sell"])

    if trade_date < today:
        spreads = model["quotes"][metal]
        rate, quote = _render_backdated_rates(
            metal, action, trade_date, live_buy, live_sell,
            spreads["buy_spread"], spreads["sell_spread"])
    else:
        rate = live_buy if action == "BUY" else live_sell
        quote = None
        st.markdown(
            f'<div class="audash-eyebrow" style="margin-top:6px;">'
            f'Platform {action.lower()} rate</div>'
            f'<div class="audash-num" style="font-family:{THEME["f_data"]};'
            f'font-size:18px;color:{THEME["text"]};margin-bottom:10px;">'
            f'{presenter.fmt(rate)} <span class="audash-cell-unit">MYR/g</span></div>',
            unsafe_allow_html=True,
        )

    mode = st.radio("Enter by", ["cash", "mass"], horizontal=True, key="trade_mode",
                    format_func=lambda m: "Cash · MYR" if m == "cash" else "Mass · grams")
    step, fmt_spec = (100.0, "%.2f") if mode == "cash" else (0.1, "%.3f")
    primary = st.number_input(
        "Cash · MYR" if mode == "cash" else "Mass · grams",
        min_value=0.0, value=0.0, step=step, format=fmt_spec, key="trade_primary",
        help="Positive amounts only; a non-positive value can't be logged.")

    amounts = presenter.resolve_trade_amounts(mode, primary, rate)
    if mode == "cash":
        derived = f"{presenter.fmt(amounts['mass_grams'], 3)} g"
    else:
        derived = f"RM {presenter.fmt(amounts['fiat_total_myr'])}"
    st.markdown(
        f'<div class="audash-eyebrow">Derived <span style="color:{THEME["accent"]};">'
        f'live</span></div><div class="audash-num" style="font-family:'
        f'{THEME["f_data"]};font-size:18px;font-weight:600;color:{THEME["accent"]};'
        f'margin-bottom:18px;">{derived}</div>',
        unsafe_allow_html=True,
    )

    st.button("Review trade →", key="trade_review", type="primary",
              on_click=_stage_trade,
              args=(action, metal, rate, amounts, trade_date, quote))

    error = st.session_state.pop("_trade_error", None)
    if error:
        st.error(error)


def _render_trade_confirm(pending: dict) -> None:
    """Show the exact entry and require a deliberate confirm before writing."""
    line = presenter.trade_confirm_line(
        pending["action"], pending["metal"], pending["mass_grams"],
        pending["fiat_total_myr"], pending["rate"])
    st.markdown(
        f'<div class="audash-panel" style="margin-bottom:16px;">'
        f'<div class="audash-eyebrow" role="heading" aria-level="2" style="margin-bottom:10px;">'
        f'Confirm entry · review before it joins the ledger</div>'
        f'<div class="audash-num" style="font-family:{THEME["f_data"]};'
        f'font-size:18px;font-weight:600;color:{THEME["accent"]};">{line}</div>'
        f'<p style="font-family:{THEME["f_body"]};font-size:13px;color:{THEME["muted"]};'
        f'margin:12px 0 0;">Append-only: once logged, this can be reversed but '
        f'not erased.</p></div>',
        unsafe_allow_html=True,
    )

    confirm, cancel = st.columns([1, 1])
    confirm.button(f"Confirm · log {pending['action']} {pending['metal']}",
                   key="trade_submit", type="primary", on_click=_commit_trade)
    cancel.button("Cancel · edit", key="trade_cancel", on_click=_cancel_trade)

    error = st.session_state.pop("_confirm_error", None)
    if error:
        st.error(error)


# --- Recent trades + void ----------------------------------------------------

def _render_recent_trades() -> None:
    """The append-only ledger tail, each row reversible via an offsetting void."""
    st.markdown(
        '<div class="audash-eyebrow" role="heading" aria-level="2" style="margin:26px 0 12px;">'
        'Recent trades · ledger</div>', unsafe_allow_html=True)
    try:
        with get_db_connection() as conn:
            trades = fetch_transactions(conn)
    except Exception:
        st.error("Couldn't read the ledger right now — the worker may be "
                 "mid-write. Retry in a moment.")
        return

    rows = presenter.build_recent_trades(trades, THEME, limit=8)
    if not rows:
        st.markdown(
            f'<p style="font-family:{THEME["f_body"]};color:{THEME["muted"]};'
            f'margin:0;">No trades logged yet — your first entry will appear '
            f'here.</p>', unsafe_allow_html=True)
        return

    armed = st.session_state.get("void_arm")
    for row in rows:
        _render_trade_row(row, armed=(armed == row["id"]))

    error = st.session_state.pop("_void_error", None)
    if error:
        st.error(error)


def _trade_row_dl(row: dict, voided: bool = False) -> str:
    """One ledger row as a horizontal description list.

    Each datum is a <dt>/<dd> pair (the <dt> labels are screen-reader-only), so
    assistive tech hears "Trade BUY · GOLD, Mass 2.0000 g, Value RM 800.00 …"
    instead of an unlabeled value stream. Flex ratios mirror the old 3 : 1.6 : 2
    columns so the figures still line up down the ledger. A `voided` row is dimmed
    and struck through, with a non-color "VOIDED" tag (colorblind-safe)."""
    t = THEME
    label_color = t["muted"] if voided else row["color"]
    text_color = t["muted"] if voided else t["text"]
    strike = "text-decoration:line-through;" if voided else ""
    tag = (
        f'<span style="font-family:{t["f_ui"]};font-size:10px;font-weight:600;'
        f'letter-spacing:0.08em;color:{t["muted"]};border:1px solid {t["line"]};'
        f'border-radius:3px;padding:1px 5px;margin-left:8px;">VOIDED</span>'
        if voided else "")
    return (
        '<dl class="audash-trade" style="display:flex;align-items:center;gap:14px;">'
        '<div style="flex:3 1 0;min-width:0;">'
        '<dt class="audash-sr-only">Trade</dt>'
        f'<dd><span style="font-family:{t["f_ui"]};font-size:14px;font-weight:600;'
        f'color:{label_color};{strike}">{row["action"]} · {row["metal"]}</span>{tag}'
        f'<span style="display:block;font-family:{t["f_data"]};font-size:11px;'
        f'color:{t["muted"]};">{row["date"]}</span></dd></div>'
        '<div style="flex:1.6 1 0;min-width:0;">'
        '<dt class="audash-sr-only">Mass (grams)</dt>'
        f'<dd class="audash-num" style="font-family:{t["f_data"]};font-size:14px;'
        f'color:{text_color};{strike}">{row["mass"]} '
        f'<span style="color:{t["muted"]};font-size:11px;">g</span></dd></div>'
        '<div style="flex:2 1 0;min-width:0;">'
        '<dt class="audash-sr-only">Value</dt>'
        f'<dd class="audash-num" style="font-family:{t["f_data"]};font-size:14px;'
        f'color:{text_color};{strike}">RM {row["fiat"]}'
        f'<span style="display:block;font-size:11px;color:{t["muted"]};">'
        f'@ {row["rate"]}</span></dd></div>'
        '</dl>'
    )


def _render_trade_row(row: dict, armed: bool) -> None:
    if row.get("voided"):
        st.markdown(_trade_row_dl(row, voided=True), unsafe_allow_html=True)
        return

    data, action = st.columns([6.6, 1.4])
    with data:
        st.markdown(_trade_row_dl(row), unsafe_allow_html=True)
    with action:
        if not armed:
            st.button(
                "Void…", key=f"void_{row['id']}",
                help=f"Reverse the {row['action']} {row['metal']} trade from "
                     f"{row['date']}.",
                on_click=_arm_void, args=(row["id"],))

    if armed:
        _render_void_confirm(row)


def _render_void_confirm(row: dict) -> None:
    opp_color = THEME["sell"] if row["opposite"] == "SELL" else THEME["buy"]
    st.markdown(
        f'<div style="font-family:{THEME["f_body"]};font-size:13px;'
        f'color:{THEME["sub"]};margin:2px 0 8px;">Void writes an offsetting '
        f'<b style="color:{opp_color};">{row["opposite"]}</b> of {row["mass"]} g '
        f'to reverse this {row["action"]}. The original stays on the ledger.</div>',
        unsafe_allow_html=True)

    entry = presenter.reversal_entry(
        row["action"], row["metal"], row["execution_rate_myr"],
        row["mass_grams"], row["fiat_total_myr"])
    flash = (f"Voided {row['date']} {row['action']} · {row['metal']} — net "
             f"position unchanged, ledger preserved")

    confirm, cancel = st.columns([1, 1])
    confirm.button("Void trade", key=f"voidok_{row['id']}",
                   type="primary", on_click=_commit_void,
                   args=(entry, row["ts"], row["id"], flash))
    cancel.button("Keep trade", key=f"voidcancel_{row['id']}",
                  on_click=_cancel_void)


# --- Daily Prices ------------------------------------------------------------

def render_daily_quotes_form(model: dict) -> None:
    """Record the platform's quoted buy/sell prices for a day (not a trade)."""
    _heading("Daily Prices", "Record today's quote",
             "The platform's quoted buy/sell prices for a day — no trade "
             "required. Recorded quotes set the median default spread used on "
             "days you don't enter one.")
    _flash()

    metal = st.radio("Metal", ["GOLD", "SILVER"], horizontal=True,
                     key="quote_metal")
    quote_date = st.date_input("Date", value=date.fromisoformat(model["today"]),
                              key="quote_date")
    buy_rate = st.number_input(
        "Buy rate · MYR/g", min_value=0.0, value=0.0, step=1.0, format="%.2f",
        key="quote_buy", help="Price you pay to buy (≈ spot + spread).")
    sell_rate = st.number_input(
        "Sell rate · MYR/g", min_value=0.0, value=0.0, step=1.0, format="%.2f",
        key="quote_sell", help="Price you receive to sell (≈ spot − spread).")

    _render_quote_preview(model, metal, buy_rate, sell_rate)

    st.button("Record quote", key="quote_submit", type="primary",
              on_click=_commit_quote, args=(metal, quote_date, buy_rate, sell_rate))

    error = st.session_state.pop("_quote_error", None)
    if error:
        st.error(error)

    _render_recent_quotes()


def _render_quote_preview(model: dict, metal: str,
                          buy_rate: float, sell_rate: float) -> None:
    info = model["quotes"][metal]
    spot = model["spot_today"][metal]
    prev = presenter.quote_preview(buy_rate, sell_rate, spot)

    st.markdown(
        f'<div class="audash-eyebrow" style="margin-top:6px;">Current default '
        f'spread · {metal.lower()} · median of {info["n_quotes"]} quote(s)</div>'
        f'<div class="audash-num" style="font-family:{THEME["f_data"]};'
        f'font-size:15px;color:{THEME["sub"]};margin-bottom:10px;">buy +'
        f'{presenter.fmt(info["buy_spread"])} / sell −'
        f'{presenter.fmt(info["sell_spread"])} MYR/g</div>',
        unsafe_allow_html=True)

    if prev["inverted"] and buy_rate > 0 and sell_rate > 0:
        st.warning("Buy rate is below sell rate — did you swap them? It will "
                   "be recorded exactly as entered.")
    if spot > 0 and (buy_rate > 0 or sell_rate > 0):
        st.markdown(
            f'<div class="audash-eyebrow">Implied spread · vs latest spot '
            f'{presenter.fmt(spot)}</div>'
            f'<div class="audash-num" style="font-family:{THEME["f_data"]};'
            f'font-size:15px;color:{THEME["accent"]};margin-bottom:12px;">buy '
            f'{presenter.signed(prev["buy_spread"])} / sell '
            f'{presenter.signed(prev["sell_spread"])} MYR/g</div>',
            unsafe_allow_html=True)


def _quote_row_dl(row: dict) -> str:
    t = THEME
    color = t["gold"] if row["metal"] == "GOLD" else t["silver"]
    return (
        '<dl class="audash-trade" style="display:flex;align-items:center;gap:14px;">'
        '<div style="flex:3 1 0;min-width:0;">'
        '<dt class="audash-sr-only">Quote</dt>'
        f'<dd><span style="font-family:{t["f_ui"]};font-size:14px;font-weight:600;'
        f'color:{color};">{row["metal"]}</span>'
        f'<span style="display:block;font-family:{t["f_data"]};font-size:11px;'
        f'color:{t["muted"]};">{row["date"]}</span></dd></div>'
        '<div style="flex:2 1 0;min-width:0;">'
        '<dt class="audash-sr-only">Buy rate</dt>'
        f'<dd class="audash-num" style="font-family:{t["f_data"]};font-size:14px;'
        f'color:{t["text"]};">{row["buy"]} '
        f'<span style="color:{t["muted"]};font-size:11px;">buy</span></dd></div>'
        '<div style="flex:2 1 0;min-width:0;">'
        '<dt class="audash-sr-only">Sell rate</dt>'
        f'<dd class="audash-num" style="font-family:{t["f_data"]};font-size:14px;'
        f'color:{t["text"]};">{row["sell"]} '
        f'<span style="color:{t["muted"]};font-size:11px;">sell</span></dd></div>'
        '</dl>'
    )


def _render_recent_quotes() -> None:
    st.markdown(
        '<div class="audash-eyebrow" role="heading" aria-level="2" '
        'style="margin:26px 0 12px;">Recent quotes</div>', unsafe_allow_html=True)
    try:
        with get_db_connection() as conn:
            quotes = fetch_daily_quotes(conn)
    except Exception:
        st.error("Couldn't read recorded quotes right now — the worker may be "
                 "mid-write. Retry in a moment.")
        return

    rows = presenter.build_recent_quotes(quotes, limit=10)
    if not rows:
        st.markdown(
            f'<p style="font-family:{THEME["f_body"]};color:{THEME["muted"]};'
            f'margin:0;">No quotes recorded yet — your first entry sets the '
            f'default spread.</p>', unsafe_allow_html=True)
        return
    for row in rows:
        _render_quote_row(row)


def _render_quote_row(row: dict) -> None:
    data, action = st.columns([6.6, 1.4])
    with data:
        st.markdown(_quote_row_dl(row), unsafe_allow_html=True)
    with action:
        st.button(
            "Delete",
            key=f"delq_{row['date']}_{row['metal']}",
            help=f"Remove the {row['metal']} quote for {row['date']}.",
            on_click=_delete_quote, args=(row["date"], row["metal"]))


# --- Settings ----------------------------------------------------------------

def render_settings_panel(model: dict) -> None:
    """Edit every system_settings key; save, or re-run sentiment on demand."""
    settings = model["settings"]
    _heading("Settings", "System settings",
             "Runtime configuration stored in system_settings.")

    edited: dict[str, str] = {}
    for group in presenter.settings_groups(settings):
        st.markdown(
            f'<div class="audash-eyebrow" role="heading" aria-level="2" '
            f'style="color:{THEME["accent"]};margin:14px 0 6px;">{group["title"]}</div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(2)
        for i, field in enumerate(group["fields"]):
            with cols[i % 2]:
                kwargs = {"type": "password"} if field["type"] == "password" else {}
                edited[field["key"]] = st.text_input(
                    field["label"], value=str(field["value"]),
                    key=f"set_{field['key']}", **kwargs)

    save, refresh = st.columns([1, 1])
    with save:
        if st.button("Save settings", key="save_settings", type="primary"):
            try:
                with get_db_connection() as conn:
                    for key, value in edited.items():
                        set_setting(conn, key, value)
            except Exception:
                st.error("Couldn't save settings — the worker may be mid-write. "
                         "Nothing was changed; retry in a moment.")
            else:
                st.success("Settings saved to system_settings")
    with refresh:
        if st.button("↻ Refresh sentiment now", key="refresh_sentiment"):
            _refresh_sentiment(model, edited)

    _render_price_import()


def _render_price_import() -> None:
    """Bulk-backfill spot_prices from a user-supplied CSV of past prices.

    Lets a fresh install start with real history instead of only the daily
    reads collected from install day forward.
    """
    st.markdown(
        f'<div class="audash-eyebrow" role="heading" aria-level="2" '
        f'style="color:{THEME["accent"]};margin:14px 0 6px;">'
        f'Historical price import</div>',
        unsafe_allow_html=True,
    )
    st.caption("CSV with columns date, gold_per_gram, silver_per_gram (MYR). "
              "Backfills spot_prices so analytics have history from day one.")
    uploaded = st.file_uploader("Import historical prices", type="csv",
                                key="price_import_file")
    if uploaded is None:
        return

    reader = csv.DictReader(io.StringIO(uploaded.getvalue().decode("utf-8")))
    result = presenter.validate_price_import(list(reader))
    rows, errors = result["rows"], result["errors"]
    if errors:
        st.warning(f"{len(errors)} row(s) skipped:\n" +
                  "\n".join(f"- {e}" for e in errors[:10]))
    if not rows:
        st.error("No valid rows to import.")
        return

    st.write(f"{len(rows)} valid row(s) · {rows[0]['date']} → {rows[-1]['date']}")
    if st.button(f"Import {len(rows)} row(s)", key="confirm_price_import",
                type="primary"):
        try:
            with get_db_connection() as conn:
                for row in rows:
                    write_spot_prices(conn, row["date"], row["gold_oz"],
                                      row["silver_oz"])
        except Exception:
            st.error("Couldn't import — the worker may be mid-write. Nothing "
                     "was saved; retry in a moment.")
        else:
            st.success(f"Imported {len(rows)} day(s) of historical spot prices.")


def _refresh_sentiment(model: dict, edited: dict) -> None:
    """Re-run the AI sentiment pipeline and write a fresh snapshot."""
    api_key = edited.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        st.warning("No Gemini API key configured — add one above, save, then retry.")
        return
    # Lazy import: keeps feedparser off the dashboard's import path.
    from worker.sentiment_pipeline import execute_sentiment_pipeline

    market = model["market"]
    metrics = {"rsi": market["rsi"], "gsr": model["gsr_band"]["value"]}
    with st.spinner("Re-running sentiment pipeline…"):
        try:
            with get_db_connection() as conn:
                result = execute_sentiment_pipeline(
                    conn, api_key=api_key,
                    model_name=edited.get("GEMINI_MODEL") or "gemini-3-flash-preview",
                    market_metrics=metrics)
        except Exception:
            st.error("Couldn't reach the database to refresh sentiment — the "
                     "worker may be mid-write. The prior snapshot is unchanged; "
                     "retry in a moment.")
            return
    if result.get("failed"):
        st.error("Sentiment refresh failed — prior snapshot kept (capital protection).")
    else:
        st.success(presenter.sentiment_refresh_note(
            result["sentiment_score"], model["signal_result"]["quant_bias"]))
