"""OPINION — Gold & Silver Intelligence Dashboard."""
import threading
import webbrowser

import dash
import dash_bootstrap_components as dbc
from dash import Dash, html, dcc, page_container

from db.schema import init_db

init_db()

app = Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.FLATLY],
    suppress_callback_exceptions=True,
    title="OPINION",
)

# ── 8-page nav (grouped) ──────────────────────────────────────────────────────
NAV_GROUPS = [
    ("MARKETS", [
        ("🏠 Overview",    "/"),
        ("🥇 Metals",      "/metals"),
        ("🌐 Markets",     "/markets"),
    ]),
    ("FORECASTING", [
        ("🔮 Forecasts",   "/forecasts"),
        ("📊 Analytics",   "/analytics"),
    ]),
    ("INTELLIGENCE", [
        ("🧠 Intelligence", "/intelligence"),
    ]),
    ("MODELS & SYSTEM", [
        ("🤖 Models",      "/models"),
        ("⚙️ System",      "/system"),
    ]),
]

_ACCENT = "#2C3E50"   # FLATLY's dark sidebar color


def _group(title, items):
    return html.Div([
        html.Div(title,
                 style={"fontSize": "0.65rem", "fontWeight": "700", "letterSpacing": "0.1em",
                        "color": "rgba(255,255,255,0.45)", "padding": "14px 16px 4px"}),
        *[dbc.NavLink(
            label, href=href, active="exact",
            style={"color": "rgba(255,255,255,0.85)", "fontSize": "0.88rem",
                   "padding": "7px 16px", "borderRadius": "6px", "margin": "1px 8px",
                   "fontWeight": "500"},
            class_name="opinion-nav-link",
        ) for label, href in items],
    ])


sidebar = html.Div(
    [
        # Logo
        html.Div([
            html.Div("OPINION",
                     style={"fontSize": "1.3rem", "fontWeight": "800",
                            "color": "#F39C12", "letterSpacing": "0.06em"}),
            html.Div("Gold & Silver Intelligence",
                     style={"fontSize": "0.7rem", "color": "rgba(255,255,255,0.5)",
                            "marginTop": "2px"}),
            html.Hr(style={"borderColor": "rgba(255,255,255,0.15)", "margin": "14px 0 6px"}),
        ], style={"padding": "20px 16px 0"}),
        # Nav
        dbc.Nav(
            [_group(t, items) for t, items in NAV_GROUPS],
            vertical=True, pills=True, className="flex-column pb-4",
        ),
    ],
    style={
        "background": _ACCENT,
        "height": "100vh",
        "position": "sticky",
        "top": 0,
        "overflowY": "auto",
        "overflowX": "hidden",
        "scrollbarWidth": "thin",
        "scrollbarColor": "rgba(255,255,255,0.2) transparent",
    },
)

app.layout = html.Div([
    # Global active-link styling (light indicator on dark sidebar)
    html.Style("""
        .opinion-nav-link.active {
            background: rgba(255,255,255,0.15) !important;
            color: #fff !important;
            border-left: 3px solid #F39C12;
        }
        .opinion-nav-link:hover:not(.active) {
            background: rgba(255,255,255,0.08) !important;
            color: #fff !important;
        }
    """),
    dbc.Row([
        dbc.Col(sidebar, width=2, className="p-0"),
        dbc.Col([
            dcc.Location(id="url"),
            page_container,
        ], width=10, style={"padding": "28px 32px", "minHeight": "100vh",
                            "background": "#f8f9fa"}),
    ], className="g-0"),
], style={"fontFamily": "system-ui, -apple-system, sans-serif"})

server = app.server

if __name__ == "__main__":
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8050")).start()
    app.run(debug=False, host="127.0.0.1", port=8050)
