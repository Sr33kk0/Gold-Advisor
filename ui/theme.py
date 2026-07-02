"""Direction A "Assayer's Terminal" palette + identity CSS.

Pure configuration (no Streamlit/Plotly import) so presenter helpers can take
the palette as a plain dict and stay unit-testable. Hex tokens are ported
verbatim from the approved Claude Design file (AuDash.dc.html, theme "A").
"""

# Bi-metallic instrument-panel palette. Keys are snake_case mirrors of the
# design's camelCase theme object so the mapping is auditable 1:1.
THEME: dict[str, object] = {
    "is_dark": True,
    "bg": "#0E0D0B",
    "chrome": "rgba(14,13,11,0.86)",
    "panel": "#1A1815",
    "line": "#2E2A24",
    "text": "#EDE7D9",
    "sub": "#B8AF9F",
    "muted": "#ABA493",
    "accent": "#C8A24C",
    "accent_bright": "#E8C877",
    "gold": "#C8A24C",
    "gold_edge": "#C8A24C",
    "silver": "#AEB6BD",
    "silver_edge": "#AEB6BD",
    "buy": "#6FAE7E",
    "sell": "#C56A5C",
    "hold": "#AEB6BD",
    "gold_tint": "rgba(200,162,76,0.06)",
    "silver_tint": "rgba(174,182,189,0.06)",
    "neutral_tint": "#1A1815",
    "on_accent": "#0E0D0B",
    "f_display": "'Cormorant Garamond', Georgia, serif",
    "f_data": "'IBM Plex Mono', monospace",
    "f_ui": "'IBM Plex Sans', system-ui, sans-serif",
    "f_body": "'IBM Plex Sans', system-ui, sans-serif",
}

# Google Fonts + the identity layer injected once via st.markdown(unsafe...).
# Re-skins Streamlit's default chrome into the dark warm-charcoal instrument
# panel and supplies the verdict/metric/badge primitives the views compose.
IDENTITY_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,500&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

:root {{ --focus: {THEME['accent']}; }}

.stApp {{ background: {THEME['bg']}; color: {THEME['text']}; font-family: {THEME['f_ui']}; }}
.block-container {{ max-width: 1240px; padding-top: 1.4rem; }}

.audash-num {{ font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1; }}

:focus-visible {{ outline: 2px solid var(--focus); outline-offset: 2px; }}

/* Panels --------------------------------------------------------------- */
.audash-panel {{
    background: {THEME['panel']};
    border: 1px solid {THEME['line']};
    border-radius: 6px;
    padding: 24px;
}}
/* Condensed header panels — tighter so the live rates sit higher on the page. */
.audash-panel-verdict {{ padding: 18px 22px; }}
.audash-eyebrow {{
    font-family: {THEME['f_data']};
    font-size: 12px;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: {THEME['sub']};
}}

/* Verdict hero --------------------------------------------------------- */
.audash-verdict-word {{
    font-family: {THEME['f_display']};
    font-weight: 700;
    font-size: 60px;
    line-height: 0.9;
    letter-spacing: 0.01em;
}}
/* The verdict glyph (▲ ▼ ○) — shape-encodes the call beside the word/color. */
.audash-verdict-shape {{
    font-family: {THEME['f_data']};
    font-size: 28px;
    line-height: 0.9;
}}
.audash-verdict-metal {{
    font-family: {THEME['f_display']};
    font-size: 24px;
    font-weight: 500;
    letter-spacing: 0.04em;
    color: {THEME['sub']};
}}
.audash-verdict-reason {{
    font-family: {THEME['f_body']};
    font-size: 16px;
    line-height: 1.55;
    color: {THEME['sub']};
    max-width: 46ch;
    text-wrap: pretty;
}}
.audash-stale {{
    font-family: {THEME['f_data']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.10em;
    color: {THEME['sell']};
    border: 1px solid {THEME['sell']};
    padding: 2px 7px;
    border-radius: 2px;
}}

/* Readout bench — three borderless zones (Market / Portfolio / Engine) -- */
/* One ruled "bench" surface instead of a dozen boxes: a hairline frame top and
   bottom, a vertical rule splitting the Market from the Portfolio, a horizontal
   rule above the secondary Engine strip. Every value is tabular so the digits
   stack like a mechanical scale. */
.audash-bench {{
    border-top: 1px solid {THEME['line']};
    border-bottom: 1px solid {THEME['line']};
    padding: 18px 0 16px;
    margin-bottom: 22px;
}}
.audash-bench-row {{
    display: grid;
    grid-template-columns: 1.55fr 1px 1fr;
    column-gap: 26px;
    align-items: stretch;
}}
.audash-vrule, .audash-hrule {{ background: {THEME['line']}; }}
.audash-hrule {{ height: 1px; margin: 16px 0; }}
.audash-zone-portfolio {{ display: flex; flex-direction: column; }}

/* Label -> value readout rows (Market grid + Portfolio secondary stack). */
.audash-readout {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 30px; }}
.audash-readout-stack {{ display: flex; flex-direction: column; }}
.audash-read {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    padding: 7px 0;
}}
.audash-read-label {{
    font-family: {THEME['f_ui']};
    font-size: 12.5px;
    font-weight: 500;
    letter-spacing: 0.02em;
    color: {THEME['sub']};
}}
.audash-read-val {{
    font-family: {THEME['f_data']};
    font-weight: 600;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}}
.audash-read-unit {{ font-family: {THEME['f_data']}; font-size: 11px; color: {THEME['muted']}; margin-left: 5px; }}

/* Portfolio PnL — the emphasized readout: large, sign-shaped, sign-colored. */
.audash-pnl {{ margin-top: auto; padding-top: 14px; }}
.audash-pnl-label {{
    font-family: {THEME['f_ui']};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: {THEME['sub']};
}}
.audash-pnl-row {{ display: flex; align-items: baseline; gap: 10px; margin-top: 7px; }}
.audash-pnl-shape {{ font-family: {THEME['f_data']}; font-size: 22px; line-height: 1; }}
.audash-pnl-val {{
    font-family: {THEME['f_data']};
    font-weight: 600;
    font-size: 30px;
    line-height: 1;
    font-variant-numeric: tabular-nums;
}}
.audash-pnl-unit {{ font-family: {THEME['f_data']}; font-size: 12px; color: {THEME['sub']}; }}

/* Engine strip — secondary raw readings, tight and small. */
.audash-engine {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }}
.audash-eng {{ display: flex; flex-direction: column; gap: 6px; }}
.audash-eng-label {{
    font-family: {THEME['f_ui']};
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: {THEME['muted']};
}}
.audash-eng-val {{
    font-family: {THEME['f_data']};
    font-weight: 600;
    font-size: 15px;
    line-height: 1;
    font-variant-numeric: tabular-nums;
}}
.audash-eng-unit {{ font-family: {THEME['f_data']}; font-size: 10px; color: {THEME['muted']}; margin-left: 4px; }}

/* Kept for forms.py quote/confirm rows. */
.audash-cell-unit {{ font-family: {THEME['f_data']}; font-size: 12px; color: {THEME['sub']}; }}

/* Ledger / breakdown --------------------------------------------------- */
.audash-vote {{
    font-family: {THEME['f_data']};
    font-weight: 600;
    font-size: 14px;
    border-radius: 3px;
    padding: 3px 10px;
}}

/* Accessible structure ------------------------------------------------- */
/* Screen-reader-only: present to AT, removed from the visual layout. */
.audash-sr-only {{
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
}}
/* Native <dl> readouts + trade rows: strip the UA margins/indent Streamlit
   may re-assert at runtime, so the description lists lay out as designed. */
.audash-readout, .audash-readout dt, .audash-readout dd,
.audash-engine, .audash-engine dt, .audash-engine dd,
.audash-trade, .audash-trade dt, .audash-trade dd {{ margin: 0 !important; }}

/* Motion — "a reading is taken, then it settles" ---------------------- */
/* Three entrance gestures, each deliberately distinct so the page never fades
   in as one uniform reflex: the balance weighs (rotates to equilibrium), the
   verdict resolves (rises), the readout comes online (a quick scan). The
   feedback layer is always on; the capital-protection panel breathes to show
   an *active* hold. Stillness is the brand — most of the page never moves. */

/* Resting pose (also the reduced-motion pose): the signature balance is drawn
   level, then settled into its GSR tilt. The transform carries the final pose,
   so a motionless render is identical to the animated end state. */
.audash-beam {{
    transform-box: view-box;
    transform-origin: 150px 60px;
    transform: rotate(var(--tilt, 0deg));
}}
.audash-pan {{
    transform-box: view-box;
    transform: translate(var(--dx, 0), var(--dy, 0));
}}

/* Interaction feedback — standard affordances, eased; tactile, never a nudge. */
.stButton > button,
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"] {{
    transition: background-color 140ms cubic-bezier(0.22, 1, 0.36, 1),
                border-color 140ms cubic-bezier(0.22, 1, 0.36, 1),
                color 140ms cubic-bezier(0.22, 1, 0.36, 1),
                transform 90ms cubic-bezier(0.22, 1, 0.36, 1);
}}
/* The brand's hover lift to Struck Gold, forced past Streamlit's own runtime
   hover style (which it generates for primaryColor). Focus rings stay instant
   — keyboard users get immediate feedback, never an eased-in outline. */
[data-testid="stBaseButton-primary"]:hover {{
    background-color: {THEME['accent_bright']} !important;
    border-color: {THEME['accent_bright']} !important;
    color: {THEME['on_accent']} !important;
}}
.stButton > button:active {{ transform: scale(0.985); }}
.stRadio label {{ transition: color 140ms cubic-bezier(0.22, 1, 0.36, 1); }}

@media (prefers-reduced-motion: no-preference) {{
    .audash-verdict-word,
    .audash-verdict-metal {{
        animation: audash-resolve 440ms cubic-bezier(0.22, 1, 0.36, 1) both;
    }}
    .audash-verdict-reason {{
        animation: audash-resolve 440ms cubic-bezier(0.22, 1, 0.36, 1) both;
        animation-delay: 90ms;
    }}
    .audash-read {{
        animation: audash-online 300ms cubic-bezier(0.22, 1, 0.36, 1) both;
        animation-delay: calc(var(--i, 0) * 30ms);
    }}
    .audash-beam {{ animation: audash-settle 760ms cubic-bezier(0.22, 1, 0.36, 1) both; }}
    .audash-pan {{ animation: audash-pan-settle 760ms cubic-bezier(0.22, 1, 0.36, 1) both; }}
    .audash-hold-panel {{ animation: audash-hold-breath 3.6s ease-in-out infinite; }}
}}

@keyframes audash-resolve {{
    from {{ opacity: 0; transform: translateY(7px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes audash-online {{
    from {{ opacity: 0; transform: translateY(3px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes audash-settle {{
    from {{ transform: rotate(0deg); }}
    to   {{ transform: rotate(var(--tilt, 0deg)); }}
}}
@keyframes audash-pan-settle {{
    from {{ transform: translate(0, 0); }}
    to   {{ transform: translate(var(--dx, 0), var(--dy, 0)); }}
}}
/* A slow, low-amplitude breath on the silver border — the instrument is
   holding, not alarming. Calm by design (Design Principle 2 + 4). */
@keyframes audash-hold-breath {{
    0%, 100% {{ border-color: {THEME['hold']}33; }}
    50%      {{ border-color: {THEME['hold']}66; }}
}}

/* Honour an explicit reduced-motion request, belt-and-suspenders, even if a
   future rule forgets to gate itself. The resting poses above already carry
   every final state, so nothing is lost — only the travel. */
@media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }}
}}

/* Responsive layout ---------------------------------------------------- */
/* Desktop-first (a self-hosted instrument), but the readout and paired panels
   degrade gracefully if the window is narrowed — 4→2 columns, side-by-side→
   stacked — instead of overflowing. Owned here as classes, not inline styles,
   so the breakpoint is real (inline grids can't carry a media query). */
.audash-duo {{ display: grid; grid-template-columns: 1.5fr 1fr; gap: 20px; margin-bottom: 20px; }}
@media (max-width: 760px) {{
    .audash-duo {{ grid-template-columns: 1fr; }}
    .audash-bench-row {{ grid-template-columns: 1fr; row-gap: 18px; }}
    .audash-vrule {{ display: none; }}
    .audash-readout {{ grid-template-columns: 1fr; }}
    .audash-engine {{ grid-template-columns: repeat(2, 1fr); row-gap: 14px; }}
}}

/* Navigation + radio groups -------------------------------------------- */
/* One segmented-control vocabulary for every radio (nav, metal, action,
   enter-by): readable inactive labels (not disabled-looking), a clear
   selected state, breathing room between segments. */
.stRadio [role="radiogroup"] {{ gap: 4px 18px; }}
.stRadio label p {{
    font-family: {THEME['f_ui']};
    font-size: 14px;
    color: {THEME['sub']};
}}
.stRadio label:has(input:checked) p {{
    color: {THEME['text']};
    font-weight: 600;
}}
.stRadio label:hover p {{ color: {THEME['text']}; }}
/* The top nav gets a gold underline on the active section so "where am I"
   never depends on dimming alone. */
[data-testid="stRadio"]:has(> div > [aria-label="Navigation"]) {{ margin: 6px 0 14px; }}
.stRadio label:has(input:checked) div[data-testid="stMarkdownContainer"] {{
    box-shadow: inset 0 -2px 0 {THEME['accent']};
    padding-bottom: 2px;
}}

/* Inputs ---------------------------------------------------------------- */
/* Legible labels over the fields (not microscopic slivers), mono digits
   inside, and left breathing room so typed values don't hug the border. */
.stTextInput label p, .stNumberInput label p, .stDateInput label p {{
    font-family: {THEME['f_ui']};
    font-size: 13px;
    color: {THEME['sub']};
}}
.stTextInput input, .stNumberInput input, .stDateInput input {{
    font-family: {THEME['f_data']};
    font-variant-numeric: tabular-nums;
    padding-left: 12px;
}}

/* Page entrance --------------------------------------------------------- */
/* Every section's title block shares the verdict's "resolve" gesture, so a
   nav switch reads as one deliberate transition instead of a hard swap. */
@media (prefers-reduced-motion: no-preference) {{
    .audash-page-title {{
        animation: audash-resolve 320ms cubic-bezier(0.22, 1, 0.36, 1) both;
    }}
}}

/* Streamlit chrome tidy ------------------------------------------------ */
#MainMenu, footer, header {{ visibility: hidden; }}
.stApp [data-testid="stToolbar"] {{ display: none; }}
</style>
"""
