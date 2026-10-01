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

_ACCENT = "#2C3E50"

sidebar = html.Div(
    [
        html.Div([
            html.Div("OPINION",
                     style={"fontSize": "1.3rem", "fontWeight": "800",
                            "color": "#F39C12", "letterSpacing": "0.06em"}),
            html.Div("Gold & Silver Intelligence",
                     style={"fontSize": "0.7rem", "color": "rgba(255,255,255,0.5)",
                            "marginTop": "2px"}),
            html.Hr(style={"borderColor": "rgba(255,255,255,0.15)", "margin": "14px 0 6px"}),
        ], style={"padding": "20px 16px 0"}),

        # Primary: Dashboard
        dbc.NavLink(
            "Dashboard", href="/", active="exact",
            className="opinion-nav-link fw-semibold",
            style={"color": "rgba(255,255,255,0.9)", "fontSize": "0.9rem",
                   "padding": "8px 16px", "borderRadius": "6px", "margin": "1px 8px"},
        ),

        # Secondary
        html.Div("DETAILS",
                 style={"fontSize": "0.65rem", "fontWeight": "700",
                        "letterSpacing": "0.1em",
                        "color": "rgba(255,255,255,0.45)",
                        "padding": "18px 16px 4px"}),
        *[dbc.NavLink(
            label, href=href, active="exact",
            className="opinion-nav-link",
            style={"color": "rgba(255,255,255,0.75)", "fontSize": "0.85rem",
                   "padding": "6px 16px", "borderRadius": "6px", "margin": "1px 8px"},
        ) for label, href in [
            ("Forecasts",    "/forecasts"),
            ("Intelligence", "/intelligence"),
            ("System",       "/system"),
        ]],
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

app.index_string = """
<!DOCTYPE html>
<html>
<head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
.opinion-nav-link.active {
    background: rgba(255,255,255,0.15) !important;
    color: #fff !important;
    border-left: 3px solid #F39C12;
}
.opinion-nav-link:hover:not(.active) {
    background: rgba(255,255,255,0.08) !important;
    color: #fff !important;
}
</style>
</head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>
"""

app.layout = html.Div([
    dbc.Row([
        dbc.Col(sidebar, width=2, className="p-0"),
        dbc.Col([
            dcc.Location(id="url"),
            page_container,
        ], width=10, style={"padding": "24px 28px", "minHeight": "100vh",
                            "background": "#f8f9fa"}),
    ], className="g-0"),
], style={"fontFamily": "system-ui, -apple-system, sans-serif"})

server = app.server

if __name__ == "__main__":
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8050")).start()
    app.run(debug=False, host="127.0.0.1", port=8050)
