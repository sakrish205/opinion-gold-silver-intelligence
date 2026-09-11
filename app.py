"""OPINION — Gold & Silver Intelligence Dashboard entry point."""
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
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
    title="OPINION",
)

# ── Sidebar nav groups ────────────────────────────────────────────────────────
NAV_GROUPS = [
    ("📊 Markets", [
        ("Overview",              "/"),
        ("Gold (XAU)",            "/gold"),
        ("Silver (XAG)",          "/silver"),
        ("International",         "/international"),
        ("FX / INR",              "/fx-inr"),
        ("Historical Prices",     "/historical"),
    ]),
    ("🔮 Forecasting", [
        ("Forecasts",             "/forecasts"),
        ("Forecast vs Actual",    "/forecast-vs-actual"),
        ("Verification Queue",    "/forecast-verification"),
        ("Backtesting",           "/backtesting"),
    ]),
    ("🧠 Intelligence", [
        ("News Intelligence",     "/news"),
        ("Decision History",      "/decisions"),
        ("Currency Influence",    "/currency-influence"),
    ]),
    ("🤖 Models", [
        ("Model Performance",     "/model-performance"),
        ("Model Registry",        "/model-registry"),
    ]),
    ("⚙️ System", [
        ("Data Sources",          "/data-sources"),
        ("System Health",         "/system-health"),
        ("Settings",              "/settings"),
    ]),
]


def _nav_group(title, items):
    return html.Div([
        html.Div(title, className="px-3 pt-3 pb-1",
                 style={"fontSize": "0.68rem", "fontWeight": "700",
                        "letterSpacing": "0.08em", "color": "#888", "textTransform": "uppercase"}),
        *[dbc.NavLink(label, href=href, active="exact",
                      className="py-1 px-3",
                      style={"fontSize": "0.83rem", "borderRadius": "4px",
                             "margin": "1px 6px"})
          for label, href in items],
    ])


sidebar = html.Div(
    [
        # ── Logo / header (sticky) ────────────────────────────────────────────
        html.Div(
            [
                html.Div("OPINION", style={"fontSize": "1.1rem", "fontWeight": "800",
                                            "color": "#FFC107", "letterSpacing": "0.05em"}),
                html.Div("Gold & Silver Intelligence",
                         style={"fontSize": "0.72rem", "color": "#888", "marginTop": "2px"}),
                html.Hr(style={"borderColor": "#333", "margin": "12px 0 4px"}),
            ],
            className="px-3 pt-3",
            style={"position": "sticky", "top": 0, "zIndex": 10,
                   "background": "#1a1a2e"},
        ),
        # ── Scrollable nav ────────────────────────────────────────────────────
        dbc.Nav(
            [_nav_group(title, items) for title, items in NAV_GROUPS],
            vertical=True,
            pills=True,
            className="flex-column pb-4",
        ),
    ],
    style={
        "height": "100vh",
        "overflowY": "auto",
        "overflowX": "hidden",
        "background": "#1a1a2e",
        "position": "sticky",
        "top": 0,
        # hide scrollbar on webkit while keeping scrollability
        "scrollbarWidth": "thin",
        "scrollbarColor": "#444 #1a1a2e",
    },
)

app.layout = dbc.Container(
    [
        dbc.Row(
            [
                dbc.Col(sidebar, width=2, className="p-0"),
                dbc.Col(
                    [dcc.Location(id="url"), page_container],
                    width=10,
                    className="p-4",
                    style={"minHeight": "100vh"},
                ),
            ],
            className="g-0",
        ),
    ],
    fluid=True,
    className="p-0",
)

server = app.server

if __name__ == "__main__":
    # Auto-open browser after a short delay so Dash is ready
    def _open():
        webbrowser.open("http://127.0.0.1:8050")
    threading.Timer(1.5, _open).start()

    app.run(debug=False, host="127.0.0.1", port=8050)
