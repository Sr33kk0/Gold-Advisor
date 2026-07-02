"""Gold Advisor — Streamlit entry point (Phase 5).

Top chrome + nav, then the dashboard (verdict hero, consensus, instrument
readout, the "why" ledger, the GSR assay balance, and the analytical charts),
or the trade / settings surfaces. Read side comes from ui.data_access; every
value/colour decision is a pure presenter helper; the look is the approved
Direction A "Assayer's Terminal" design.
"""

import html
import sqlite3

import streamlit as st

from database.connection import get_db_connection, seed_default_settings
from ui import charts, data_access, forms, presenter
from ui.theme import IDENTITY_CSS, THEME
from utils.timeutil import to_local

st.set_page_config(page_title="Gold Advisor", page_icon="🜚", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown(IDENTITY_CSS, unsafe_allow_html=True)


# --- HTML builders (read-only display surfaces) ------------------------------

def _eyebrow(model: dict) -> str:
    tz = model["settings"]["TIMEZONE"]
    local = to_local(model["now"], tz)
    age = model["sentiment_age"]
    max_age = float(model["settings"]["sentiment_max_age_days"])
    if age is None:
        freshness = "no snapshot"
    elif age <= max_age:
        freshness = "live"
    else:
        freshness = f"snapshot {age:.1f} d old"
    return f"{local:%d %b %Y · %H:%M} · {freshness}"


def _briefing_html(lines: list[dict]) -> str:
    """The morning-note lines as a quiet <dl>: eyebrow label left, prose right."""
    t = THEME
    rows = ""
    for ln in lines:
        rows += (
            f'<div style="display:grid;grid-template-columns:96px 1fr;gap:14px;'
            f'padding:9px 0;border-bottom:1px solid {t["line"]};">'
            f'<dt class="goldadvisor-eyebrow" style="align-self:baseline;">{ln["label"]}</dt>'
            f'<dd style="margin:0;font-family:{t["f_body"]};font-size:14px;'
            f'line-height:1.55;color:{ln["color"]};">{ln["text"]}</dd></div>'
        )
    return f'<dl style="margin:0;" aria-label="Morning briefing">{rows}</dl>'


def _verdict_consensus_html(view: dict, reason: str, detail: str, eyebrow: str) -> str:
    """Condensed header: the verdict (shape + serif word) and the consensus +
    sentiment gate side by side, kept tight so the live rates sit high on the
    page. The two engines stay visibly distinct (Principle 1, never collapsed)."""
    t = THEME
    stale = '<span class="goldadvisor-stale">STALE</span>' if view["stale"] else ""
    metal = (f'<span class="goldadvisor-verdict-metal">{view["metal_word"]}</span>'
             if view["metal_word"] else "")
    overridden = view.get("is_overridden")
    # When the risk desk owns the call, mute the directional consensus so a
    # strong BUY meter never reads as contradicting the SELL banner.
    consensus_num_color = t["muted"] if overridden else t["text"]
    quant_color = t["muted"] if overridden else view["quant_color"]
    decoupled_note = (
        f'<div style="font-family:{t["f_data"]};font-size:11px;'
        f'letter-spacing:0.04em;color:{t["muted"]};margin-top:6px;">'
        f'Directional alpha decoupled by Risk Policy</div>'
        if overridden else "")
    return f"""
    <div class="goldadvisor-duo">
      <div class="goldadvisor-panel goldadvisor-panel-verdict">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">
          <span class="goldadvisor-eyebrow">{eyebrow}</span>{stale}
        </div>
        <div style="display:flex;align-items:baseline;gap:16px;">
          <span aria-hidden="true" class="goldadvisor-verdict-shape" style="color:{view['color']};">{view['shape']}</span>
          <div class="goldadvisor-verdict-word" role="heading" aria-level="1" style="color:{view['color']};">{view['word']}</div>{metal}
        </div>
        <p class="goldadvisor-verdict-reason" style="margin:10px 0 0;">{reason}</p>
      </div>
      <div class="goldadvisor-panel goldadvisor-panel-verdict" style="display:flex;flex-direction:column;">
        <div class="goldadvisor-eyebrow" role="heading" aria-level="2" style="margin-bottom:8px;">Consensus</div>
        <div style="display:flex;align-items:baseline;gap:8px;">
          <span class="goldadvisor-num" style="font-family:{t['f_data']};font-weight:600;font-size:30px;line-height:1;color:{consensus_num_color};">{view['net_signed']}</span>
          <span style="font-family:{t['f_data']};font-size:13px;color:{t['sub']};">net votes</span>
        </div>
        <div style="font-family:{t['f_data']};font-size:13px;color:{t['sub']};margin-top:3px;">threshold ±{view['threshold']} → quant <span style="color:{quant_color};">{view['quant_bias']}</span></div>{decoupled_note}
        <div style="height:1px;background:{t['line']};margin:13px 0;"></div>
        <div class="goldadvisor-eyebrow" role="heading" aria-level="3" style="margin-bottom:7px;">Sentiment gate</div>
        <div style="display:flex;align-items:center;gap:9px;margin-bottom:7px;">
          <span aria-hidden="true" style="width:9px;height:9px;border-radius:50%;background:{view['gate_color']};"></span>
          <span style="font-family:{t['f_ui']};font-size:14px;font-weight:500;color:{t['text']};">{view['gate_label']}</span>
        </div>
        <p style="margin:0;font-family:{t['f_data']};font-size:13px;line-height:1.5;color:{t['sub']};">{detail}</p>
      </div>
    </div>"""


def _readouts_html(readouts: list[dict], val_size: int) -> str:
    """Borderless label→value rows (a <dl>): label left, tabular value right."""
    rows = ""
    for i, r in enumerate(readouts):
        unit = (f'<span class="goldadvisor-read-unit">{r["unit"]}</span>' if r["unit"] else "")
        rows += (
            f'<div class="goldadvisor-read" style="--i:{i};">'
            f'<dt class="goldadvisor-read-label">{r["label"]}</dt>'
            f'<dd class="goldadvisor-read-val"><span class="goldadvisor-num" '
            f'style="font-size:{val_size}px;color:{r["color"]};">{r["value"]}</span>{unit}</dd>'
            f'</div>'
        )
    return rows


def _readout_zones_html(market: dict, theme: dict) -> str:
    """The 'quiet ledger': three borderless data zones in one ruled bench —
    Zone A the Market (live rates, prominent), Zone B the Portfolio (PnL made
    large/distinct), Zone C the Engine (raw readings, tighter + secondary)."""
    t = theme
    market_rows = _readouts_html(presenter.build_market_readouts(market, t), 22)
    port = presenter.build_portfolio_readouts(market, t)
    port_rows = _readouts_html(port["secondary"], 18)
    p = port["pnl"]
    engine = presenter.build_engine_readouts(market, t)
    eng_cells = ""
    for r in engine:
        unit = (f'<span class="goldadvisor-eng-unit">{r["unit"]}</span>' if r["unit"] else "")
        eng_cells += (
            f'<div class="goldadvisor-eng">'
            f'<dt class="goldadvisor-eng-label">{r["label"]}</dt>'
            f'<dd class="goldadvisor-eng-val"><span class="goldadvisor-num" '
            f'style="color:{r["color"]};">{r["value"]}</span>{unit}</dd></div>'
        )
    return f"""
    <section class="goldadvisor-bench">
      <div class="goldadvisor-bench-row">
        <div class="goldadvisor-zone">
          <div class="goldadvisor-eyebrow" role="heading" aria-level="2" style="margin-bottom:13px;">The Market · MYR/g · Asia/Kuala_Lumpur</div>
          <dl class="goldadvisor-readout">{market_rows}</dl>
        </div>
        <div class="goldadvisor-vrule" aria-hidden="true"></div>
        <div class="goldadvisor-zone goldadvisor-zone-portfolio">
          <div class="goldadvisor-eyebrow" role="heading" aria-level="2" style="margin-bottom:13px;">The Portfolio</div>
          <dl class="goldadvisor-readout goldadvisor-readout-stack">{port_rows}</dl>
          <div class="goldadvisor-pnl">
            <span class="goldadvisor-pnl-label">{p['label']}</span>
            <div class="goldadvisor-pnl-row">
              <span aria-hidden="true" class="goldadvisor-pnl-shape" style="color:{p['color']};">{p['shape']}</span>
              <span class="goldadvisor-num goldadvisor-pnl-val" style="color:{p['color']};">{p['value']}</span>
              <span class="goldadvisor-pnl-unit">{p['unit']}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="goldadvisor-hrule" aria-hidden="true"></div>
      <div class="goldadvisor-zone">
        <div class="goldadvisor-eyebrow" role="heading" aria-level="3" style="margin-bottom:11px;">The Engine</div>
        <dl class="goldadvisor-engine">{eng_cells}</dl>
      </div>
    </section>"""


def _breakdown_gsr_html(rows: list[dict], view: dict, gsr_band: dict,
                        pos: dict, svg: str) -> str:
    t = THEME
    row_html = ""
    for s in rows:
        row_html += (
            f'<div role="row" style="display:grid;grid-template-columns:1fr auto auto;'
            f'align-items:center;gap:14px;padding:11px 0;border-bottom:1px solid {t["line"]};">'
            f'<div role="rowheader"><div style="font-family:{t["f_ui"]};font-size:14px;font-weight:500;color:{t["text"]};">{s["label"]}</div>'
            f'<div style="font-family:{t["f_data"]};font-size:13px;color:{t["sub"]};">{s["detail"]}</div></div>'
            f'<span role="cell" aria-label="reading {s["value"]}" class="goldadvisor-num" style="font-family:{t["f_data"]};font-size:14px;color:{t["sub"]};">{s["value"]}</span>'
            f'<span role="cell" aria-label="vote {s["vote_text"]}" class="goldadvisor-num goldadvisor-vote" style="min-width:38px;text-align:center;'
            f'color:{s["vote_color"]};border:1px solid {s["vote_color"]};">{s["vote_text"]}</span></div>'
        )
    label_color = presenter.gsr_label_color(pos["side"], t)
    return f"""
    <div class="goldadvisor-duo">
      <div class="goldadvisor-panel">
        <div class="goldadvisor-eyebrow" role="heading" aria-level="2" style="margin-bottom:16px;">Why · ledger of reasons</div>
        <div role="table" aria-label="Signal ledger — each row gives a signal, its reading, and its vote">
        {row_html}
        <div role="row" style="display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:14px;padding:13px 0 4px;border-bottom:1px solid {t['line']};">
          <div role="rowheader" style="font-family:{t['f_ui']};font-size:14px;font-weight:600;color:{t['text']};">Net quant bias</div>
          <span role="cell" class="goldadvisor-num" style="font-family:{t['f_data']};font-size:13px;color:{t['muted']};">{view['net_signed']} vs ±{view['threshold']}</span>
          <span role="cell" class="goldadvisor-num" style="min-width:38px;text-align:center;font-family:{t['f_data']};font-weight:600;color:{view['quant_color']};">{view['quant_bias']}</span>
        </div>
        <div role="row" style="display:flex;align-items:center;justify-content:space-between;gap:14px;padding-top:13px;">
          <div role="rowheader" style="font-family:{t['f_ui']};font-size:14px;font-weight:600;color:{t['text']};">Sentiment gate → final</div>
          <span role="cell" style="font-family:{t['f_display']};font-weight:700;font-size:22px;color:{view['color']};">{view['word']}</span>
        </div>
        </div>
      </div>
      <div class="goldadvisor-panel" style="display:flex;flex-direction:column;">
        <div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:6px;">
          <span class="goldadvisor-eyebrow" role="heading" aria-level="2">Gold / Silver Ratio</span>
          <span class="goldadvisor-num" style="font-family:{t['f_data']};font-weight:600;font-size:22px;color:{t['text']};">{presenter.fmt(gsr_band['value'], 1)}</span>
        </div>
        <div style="font-family:{t['f_ui']};font-size:13px;color:{label_color};margin-bottom:8px;">{pos['label']}</div>
        <div style="flex:1;display:flex;align-items:center;justify-content:center;min-height:170px;">{svg}</div>
        <div style="display:flex;justify-content:space-between;font-family:{t['f_data']};font-size:12px;color:{t['muted']};">
          <span>lower {presenter.fmt(gsr_band['lower'], 1)}</span><span>band</span><span>upper {presenter.fmt(gsr_band['upper'], 1)}</span>
        </div>
      </div>
    </div>"""


# --- screens -----------------------------------------------------------------

def render_dashboard(model: dict) -> None:
    local = to_local(model["now"], model["settings"]["TIMEZONE"])
    briefing = presenter.build_morning_briefing(model, THEME)
    with st.expander(f"Morning Briefing — {local:%a %d %b %Y}", expanded=True):
        st.markdown(_briefing_html(briefing), unsafe_allow_html=True)

    sig = model["signal_result"]
    view = presenter.verdict_view(sig, model["threshold"], THEME)
    reason = presenter.verdict_reason(sig)
    detail = presenter.gate_detail(sig, model["sentiment_age"],
                                   float(model["settings"]["sentiment_max_age_days"]),
                                   model["threshold"])
    st.markdown(_verdict_consensus_html(view, reason, detail, _eyebrow(model)),
                unsafe_allow_html=True)

    st.markdown(_readout_zones_html(model["market"], THEME), unsafe_allow_html=True)

    rows = presenter.build_signal_rows(sig, model["signal_inputs"], THEME)
    band = model["gsr_band"]
    pos = presenter.gsr_position(band["value"], band["lower"], band["upper"])
    svg = charts.build_gsr_balance_svg(pos["degrees"], THEME)
    st.markdown(_breakdown_gsr_html(rows, view, band, pos, svg),
                unsafe_allow_html=True)

    hdr, toggle = st.columns([3, 2])
    with hdr:
        st.markdown('<div class="goldadvisor-eyebrow" role="heading" aria-level="2" style="margin:6px 0 8px;">'
                    'Gold spot · Bollinger channel · trade marks</div>',
                    unsafe_allow_html=True)
    with toggle:
        chart_range = st.radio(
            "Chart range", presenter.CHART_RANGE_OPTIONS, index=1,
            horizontal=True, key="chart_range", label_visibility="collapsed")
    chart = presenter.slice_chart_range(model["chart"], chart_range)
    if chart["dates"]:
        price_fig = charts.build_price_figure(
            chart["dates"], chart["price"], chart["bands"], chart["markers"], THEME)
        st.plotly_chart(price_fig, width="stretch",
                        config={"displayModeBar": False})
        st.markdown('<div class="goldadvisor-eyebrow" role="heading" aria-level="3" style="margin:6px 0 8px;">'
                    'RSI · 14</div>', unsafe_allow_html=True)
        rsi_fig = charts.build_rsi_figure(
            chart["dates"], chart["rsi"],
            float(model["settings"]["rsi_oversold"]),
            float(model["settings"]["rsi_overbought"]), THEME)
        st.plotly_chart(rsi_fig, width="stretch",
                        config={"displayModeBar": False})
    else:
        st.markdown(f'<p style="font-family:{THEME["f_body"]};color:{THEME["muted"]};">'
                    'No price history yet — the worker will populate spot prices '
                    'on its next cycle.</p>', unsafe_allow_html=True)


def render_chrome() -> str:
    st.markdown(
        f'<div role="banner" style="display:flex;align-items:baseline;gap:10px;">'
        f'<span style="font-family:{THEME["f_display"]};font-weight:700;font-size:24px;'
        f'letter-spacing:0.04em;color:{THEME["text"]};">Gold Advisor</span></div>',
        unsafe_allow_html=True,
    )
    return st.radio("Navigation",
                    ["Dashboard", "New Trade", "Daily Prices", "Settings"],
                    horizontal=True, key="nav", label_visibility="collapsed")


# --- Capital-protection fallback (read side unavailable) ---------------------

def _is_db_locked(exc: BaseException) -> bool:
    """True for SQLite write-contention — the worker holding the database
    mid-write — as opposed to a genuine fault. Drives the reassuring copy."""
    return isinstance(exc, sqlite3.OperationalError) and (
        "locked" in str(exc).lower() or "busy" in str(exc).lower())


def _unavailable_panel_html(locked: bool, detail: str) -> str:
    """The 'no reading' panel, in the capital-protection voice.

    Mirrors the verdict hero (eyebrow · serif word · reason) but renders a
    forced, visible HOLD in neutral silver — the instrument declining to judge
    on data it can't trust (Rule 3 / Design Principle 4). Never an alarm, never
    a raw traceback. Read survives without colour: the word, the NO READING
    chip, and the pause glyph each carry the state.
    """
    t = THEME
    hold = t["hold"]
    if locked:
        eyebrow = "Capital protection · instrument holding"
        reason = (
            "The background worker is committing a fresh reading, so the "
            "database is briefly locked. Gold Advisor is holding rather than show a "
            "half-written number — your capital is never judged on partial "
            "data. The reading clears on its own once the write completes.")
        note = "Database locked · worker mid-write"
    else:
        eyebrow = "Capital protection · no reading"
        reason = (
            "Gold Advisor can't reach its data store, so it is declining to show a "
            "verdict rather than guess — no trade should be made on an absent "
            "reading. Confirm the worker and its data volume are running, then "
            "retake the reading below.")
        note = "Data store unreachable"
    note_html = html.escape(f"{note} · {detail}" if detail else note)
    pause = (
        '<svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true" '
        'style="flex:none;">'
        f'<rect x="6" y="5" width="3.4" height="12" rx="1" fill="{hold}"></rect>'
        f'<rect x="12.6" y="5" width="3.4" height="12" rx="1" fill="{hold}"></rect>'
        '</svg>')
    return (
        f'<div class="goldadvisor-panel goldadvisor-hold-panel" role="status" aria-live="polite" '
        f'style="margin-bottom:20px;border-color:{hold}40;">'
        f'<span class="goldadvisor-eyebrow">{eyebrow}</span>'
        f'<div style="display:flex;align-items:center;gap:14px;margin-top:10px;">'
        f'{pause}'
        f'<span style="font-family:{t["f_display"]};font-weight:700;'
        f'font-size:60px;line-height:0.9;letter-spacing:0.01em;color:{hold};">'
        f'HOLD</span>'
        f'<span class="goldadvisor-num" style="font-family:{t["f_data"]};'
        f'font-size:10px;font-weight:600;letter-spacing:0.16em;color:{hold};'
        f'border:1px solid {hold};padding:3px 8px;border-radius:2px;">'
        f'NO READING</span></div>'
        f'<p class="goldadvisor-verdict-reason" style="margin:16px 0 0;">{reason}</p>'
        f'<div class="goldadvisor-num" style="font-family:{t["f_data"]};'
        f'font-size:11.5px;color:{t["muted"]};margin-top:14px;'
        f'letter-spacing:0.02em;">{note_html}</div></div>'
    )


def render_unavailable(exc: Exception) -> None:
    """Stand in for any screen when the read side can't be assembled: the
    on-brand HOLD panel plus a calm retry (a rerun re-attempts the read)."""
    locked = _is_db_locked(exc)
    detail = "" if locked else type(exc).__name__
    st.markdown(_unavailable_panel_html(locked, detail), unsafe_allow_html=True)
    st.button("↻ Retake the reading", key="retry_read", type="primary")


def main() -> None:
    section = render_chrome()
    try:
        with get_db_connection() as conn:
            seed_default_settings(conn)
            model = data_access.load_dashboard_model(conn)
    except Exception as exc:  # noqa: BLE001 — any read-side fault degrades to a calm HOLD, never a traceback
        render_unavailable(exc)
        return

    if section == "Dashboard":
        render_dashboard(model)
    elif section == "New Trade":
        forms.render_ledger_input_form(model)
    elif section == "Daily Prices":
        forms.render_daily_quotes_form(model)
    else:
        forms.render_settings_panel(model)


main()
