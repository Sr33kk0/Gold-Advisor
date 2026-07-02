"""Themed Plotly figures for the analytical charts (spec §5.3).

Data in, figure out — no DB or Streamlit. Styling carries the Direction A
palette + mono font so the charts read as part of the instrument panel. The
verdict/legend chrome is drawn in HTML by app.py; these figures stay quiet
(no built-in legend, hairline gridlines, no chart junk).
"""

import math

import pandas as pd
import plotly.graph_objects as go


def _base_layout(theme: dict, height: int) -> dict:
    """Shared transparent-background, mono-font, hairline-grid layout."""
    return {
        "height": height,
        "margin": {"l": 8, "r": 8, "t": 14, "b": 22},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "showlegend": False,
        "font": {"family": theme["f_data"], "size": 11, "color": theme["muted"]},
        "xaxis": {"gridcolor": theme["line"], "linecolor": theme["line"],
                  "showgrid": False, "zeroline": False},
        "yaxis": {"gridcolor": theme["line"], "linecolor": theme["line"],
                  "zeroline": False},
        "hovermode": "x unified",
    }


def build_price_figure(dates: list[str], price_per_gram: list[float],
                       bands: pd.DataFrame, markers: list[dict],
                       theme: dict) -> go.Figure:
    """Spot price line + Bollinger channel + BUY/SELL trade markers."""
    fig = go.Figure()

    # Bollinger channel: upper line, then lower with a fill back up to it.
    fig.add_trace(go.Scatter(
        x=dates, y=list(bands["upper"]), name="Upper", mode="lines",
        line={"color": theme["line"], "width": 1, "dash": "dot"},
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=list(bands["lower"]), name="Lower", mode="lines",
        line={"color": theme["line"], "width": 1, "dash": "dot"},
        fill="tonexty", fillcolor=theme["gold_tint"], hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=list(bands["middle"]), name="Mid", mode="lines",
        line={"color": theme["muted"], "width": 1, "dash": "dash"},
        hoverinfo="skip",
    ))

    # Spot line.
    fig.add_trace(go.Scatter(
        x=dates, y=price_per_gram, name="Spot", mode="lines",
        line={"color": theme["accent"], "width": 2},
    ))

    # Trade markers, always present (possibly empty) so the legend chrome is stable.
    for side, name, color, symbol in (
        ("BUY", "Buy", theme["buy"], "triangle-up"),
        ("SELL", "Sell", theme["sell"], "triangle-down"),
    ):
        pts = [m for m in markers if m["side"] == side]
        fig.add_trace(go.Scatter(
            x=[m["date"] for m in pts], y=[m["price"] for m in pts],
            name=name, mode="markers",
            marker={"color": color, "size": 11, "symbol": symbol,
                    "line": {"color": theme["panel"], "width": 2}},
        ))

    fig.update_layout(**_base_layout(theme, height=300))
    return fig


def build_rsi_figure(dates: list[str], rsi: list[float],
                     oversold: float, overbought: float,
                     theme: dict) -> go.Figure:
    """RSI line with oversold/overbought guide lines, fixed 0-100 axis."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=rsi, name="RSI", mode="lines",
        line={"color": theme["accent"], "width": 1.6},
    ))
    fig.add_hline(y=overbought, line={"color": theme["sell"], "width": 1, "dash": "dash"},
                  opacity=0.6, annotation_text=str(int(overbought)),
                  annotation_position="top right",
                  annotation_font={"color": theme["muted"], "size": 10})
    fig.add_hline(y=oversold, line={"color": theme["buy"], "width": 1, "dash": "dash"},
                  opacity=0.6, annotation_text=str(int(oversold)),
                  annotation_position="bottom right",
                  annotation_font={"color": theme["muted"], "size": 10})

    layout = _base_layout(theme, height=120)
    layout["yaxis"]["range"] = (0, 100)
    fig.update_layout(**layout)
    return fig


def _balance_pan(px: float, py: float, color: str, label: str, theme: dict) -> str:
    """One side of the assay balance: hangers, bowl, knot, metal label."""
    return (
        f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{px - 18:.1f}" y2="{py + 26:.1f}" '
        f'stroke="{theme["muted"]}" stroke-width="1"/>'
        f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{px + 18:.1f}" y2="{py + 26:.1f}" '
        f'stroke="{theme["muted"]}" stroke-width="1"/>'
        f'<path d="M {px - 22:.1f} {py + 26:.1f} A 22 10 0 0 0 {px + 22:.1f} {py + 26:.1f}" '
        f'fill="none" stroke="{color}" stroke-width="2.5"/>'
        f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="{color}"/>'
        f'<text x="{px:.1f}" y="{py + 50:.1f}" fill="{color}" font-size="11" '
        f'font-family="{theme["f_data"]}" text-anchor="middle" '
        f'letter-spacing="0.1em">{label}</text>'
    )


def build_gsr_balance_svg(degrees: float, theme: dict) -> str:
    """The signature Gold/Silver assay balance as a tilting-beam SVG.

    `degrees` is the beam tilt (+ = gold pan down / gold-rich), from
    presenter.gsr_position. Silver (AG) hangs left, gold (AU) hangs right.

    The beam is emitted *level* and settled into `degrees` by CSS: `.goldadvisor-beam`
    rotates about the fulcrum while each `.goldadvisor-pan` glides to its settled
    height, still hanging upright (gravity). The resting transforms (per-element
    inline custom props) carry the final pose, so a motionless / reduced-motion
    render is identical to the animated end state.
    """
    cx, cy, arm = 150.0, 60.0, 110.0
    rad = math.radians(degrees)
    # Level beam ends (where the pans start) and the settled, tilted ends.
    l0x, l0y, r0x, r0y = cx - arm, cy, cx + arm, cy
    lx, ly = cx - math.cos(rad) * arm, cy - math.sin(rad) * arm
    rx, ry = cx + math.cos(rad) * arm, cy + math.sin(rad) * arm
    # Decorative: the same reading is carried in text beside it (the GSR value,
    # the side label, and the band bounds), so it's hidden from assistive tech
    # rather than read out of context as bare "AG"/"AU" glyphs.
    return (
        '<svg viewBox="0 0 300 175" style="width:100%;max-width:300px;height:auto;" '
        'aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg">'
        # Static stand + base — the pivot never moves.
        f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx:.1f}" y2="150" '
        f'stroke="{theme["line"]}" stroke-width="3"/>'
        f'<path d="M {cx - 26:.1f} 150 L {cx + 26:.1f} 150 L {cx + 16:.1f} 160 '
        f'L {cx - 16:.1f} 160 Z" fill="{theme["line"]}"/>'
        # Beam: drawn level, rotated to `degrees` about the fulcrum by CSS.
        f'<g class="goldadvisor-beam" style="--tilt:{degrees:.2f}deg;">'
        f'<line x1="{l0x:.1f}" y1="{l0y:.1f}" x2="{r0x:.1f}" y2="{r0y:.1f}" '
        f'stroke="{theme["text"]}" stroke-width="3" stroke-linecap="round"/>'
        '</g>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{theme["accent"]}"/>'
        # Pans: drawn at the level ends, each glides to its settled height.
        f'<g class="goldadvisor-pan" style="--dx:{lx - l0x:.2f}px;--dy:{ly - l0y:.2f}px;">'
        f'{_balance_pan(l0x, l0y, theme["silver"], "AG", theme)}</g>'
        f'<g class="goldadvisor-pan" style="--dx:{rx - r0x:.2f}px;--dy:{ry - r0y:.2f}px;">'
        f'{_balance_pan(r0x, r0y, theme["gold"], "AU", theme)}</g>'
        '</svg>'
    )
