"""Page 5: FX / INR — 5 pairs, hourly history, cross-check anomaly log."""
import sqlite3
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd

from config import DB_PATH, FX_PAIRS, REFRESH_FX_MS
from data.providers.forex import get_fx_history, get_all_fx_latest

dash.register_page(__name__, path="/fx-inr", name="FX / INR")

layout = html.Div([
    html.H4("FX / INR", className="mb-3"),
    dcc.Interval(id="fx-interval", interval=REFRESH_FX_MS, n_intervals=0),
    dbc.Row([
        dbc.Col(html.Div(id="fx-latest-cards")),
    ]),
    html.H5("Historical Rate", className="mt-4 mb-2"),
    dcc.Dropdown(
        id="fx-pair-select",
        options=[{"label": p.pair, "value": p.pair} for p in FX_PAIRS],
        value="USD/INR",
        clearable=False,
        style={"width": "200px"},
    ),
    dcc.Loading(dcc.Graph(id="fx-history-chart")),
    html.H5("Cross-Check Anomalies", className="mt-4 mb-2"),
    html.Div(id="fx-anomaly-log"),
])


@callback(Output("fx-latest-cards", "children"), Input("fx-interval", "n_intervals"))
def refresh_latest(_n):
    fx = get_all_fx_latest()
    cards = []
    for p in FX_PAIRS:
        r = fx.get(p.pair)
        rate = r.value.get("rate") if r and r.value else None
        res = r.value.get("resolution", "?") if r and r.value else "?"
        status = r.status if r else "UNAVAILABLE"
        color = {"LIVE": "success", "STALE": "warning"}.get(status, "secondary")
        cards.append(dbc.Col(dbc.Card(dbc.CardBody([
            html.Small(p.pair, className="text-muted"),
            html.H5(f"{rate:.4f}" if rate else "—"),
            dbc.Badge(status, color=color),
            html.Small(f" {res}", className="text-muted ms-1"),
        ])), md=2))
    return dbc.Row(cards)


@callback(
    Output("fx-history-chart", "figure"),
    Input("fx-pair-select", "value"),
    Input("fx-interval", "n_intervals"),
)
def refresh_history(pair_name, _n):
    pair_obj = next((p for p in FX_PAIRS if p.pair == pair_name), None)
    if not pair_obj:
        return {}
    result = get_fx_history(pair_obj)
    if result.status not in ("LIVE", "STALE") or result.value is None:
        fig = px.line(title=f"{pair_name} — {result.status}")
        return fig
    df = result.value.reset_index()
    df.columns = ["datetime", "rate"]
    fig = px.line(df, x="datetime", y="rate",
                  title=f"{pair_name} | Hourly (resolution: {result.value.attrs.get('resolution','1h')})",
                  template="plotly_dark")
    return fig


@callback(Output("fx-anomaly-log", "children"), Input("fx-interval", "n_intervals"))
def refresh_anomalies(_n):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """SELECT detected_at, pair, description, delta_pct, severity
                   FROM data_quality_alerts
                   WHERE alert_type='CROSS_CHECK_ANOMALY'
                   ORDER BY detected_at DESC LIMIT 50"""
            ).fetchall()
    except Exception:
        rows = []
    if not rows:
        return html.P("No cross-check anomalies recorded.", className="text-muted")
    table = dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in ["Detected", "Pair", "Description", "Delta %", "Severity"]]))]
        + [html.Tbody([html.Tr([html.Td(str(v)) for v in r]) for r in rows])],
        bordered=True, size="sm",
    )
    return table
