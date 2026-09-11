"""OPINION — Gold & Silver Intelligence Dashboard entry point."""
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

NAV_ITEMS = [
    ("Overview",              "/"),
    ("Gold",                  "/gold"),
    ("Silver",                "/silver"),
    ("International Markets", "/international"),
    ("FX / INR",              "/fx-inr"),
    ("Historical Prices",     "/historical"),
    ("Forecasts",             "/forecasts"),
    ("Forecast vs Actual",    "/forecast-vs-actual"),
    ("Forecast Verification", "/forecast-verification"),
    ("News Intelligence",     "/news"),
    ("Decision History",      "/decisions"),
    ("Model Performance",     "/model-performance"),
    ("Backtesting",           "/backtesting"),
    ("Currency Influence",    "/currency-influence"),
    ("Data Sources",          "/data-sources"),
    ("Model Registry",        "/model-registry"),
    ("System Health",         "/system-health"),
    ("Settings",              "/settings"),
]

sidebar = dbc.Nav(
    [
        html.Div(
            [
                html.Span("OPINION", className="fs-5 fw-bold text-warning"),
                html.Div("Gold & Silver Intelligence", className="text-muted small"),
            ],
            className="p-3",
        ),
        html.Hr(className="my-1"),
    ]
    + [
        dbc.NavLink(label, href=href, active="exact", className="nav-item-sm")
        for label, href in NAV_ITEMS
    ],
    vertical=True,
    pills=True,
    className="flex-column",
    style={"fontSize": "0.82rem"},
)

app.layout = dbc.Container(
    [
        dbc.Row(
            [
                dbc.Col(sidebar, width=2, className="bg-dark min-vh-100 p-0"),
                dbc.Col(
                    [dcc.Location(id="url"), page_container],
                    width=10,
                    className="p-3",
                ),
            ],
            className="g-0",
        )
    ],
    fluid=True,
    className="p-0",
)

server = app.server

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8050)
