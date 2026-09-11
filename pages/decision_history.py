"""Page 11: Decision History — user decisions and system signals."""
import sqlite3
from datetime import datetime, timezone

import dash
from dash import callback, dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

from config import DB_PATH
from db import ops

dash.register_page(__name__, path="/decisions", name="Decision History")

layout = html.Div([
    html.H4("Decision History", className="mb-3"),
    html.P(
        "Record your own decisions. System signals come from forecasts. "
        "This system does not execute trades.",
        className="text-muted",
    ),
    dbc.Card(dbc.CardBody([
        html.H6("Log a Decision"),
        dbc.Row([
            dbc.Col(dcc.Dropdown(id="dec-metal",
                options=[{"label": "Gold (XAU)", "value": "XAU"},
                         {"label": "Silver (XAG)", "value": "XAG"}],
                value="XAU", clearable=False), md=2),
            dbc.Col(dcc.Dropdown(id="dec-decision",
                options=[{"label": v, "value": v} for v in ["BUY", "SELL", "HOLD", "WATCH"]],
                placeholder="Your decision", clearable=False), md=2),
            dbc.Col(dcc.Input(id="dec-rationale", placeholder="Rationale",
                              className="form-control"), md=5),
            dbc.Col(dbc.Button("Save", id="dec-save-btn", color="warning"), md=2),
        ], className="g-2"),
        html.Div(id="dec-save-result", className="text-muted small mt-2"),
    ]), className="mb-4"),
    dcc.Interval(id="dec-interval", interval=60_000, n_intervals=0),
    html.H5("History", className="mb-2"),
    html.Div(id="dec-table"),
])


@callback(
    Output("dec-save-result", "children"),
    Input("dec-save-btn", "n_clicks"),
    State("dec-metal", "value"),
    State("dec-decision", "value"),
    State("dec-rationale", "value"),
    prevent_initial_call=True,
)
def save_decision(n_clicks, metal, decision, rationale):
    if not decision:
        return "Select a decision."
    ops.insert_decision({
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metal": metal,
        "user_decision": decision,
        "user_rationale": rationale or "",
    })
    return f"Saved: {metal} {decision}"


@callback(Output("dec-table", "children"), Input("dec-interval", "n_intervals"),
          Input("dec-save-btn", "n_clicks"))
def refresh_table(_n, _btn):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """SELECT created_at, metal, system_signal, user_decision, user_rationale,
                          price_inr_at_decision, price_type_at_decision
                   FROM decision_history
                   ORDER BY created_at DESC LIMIT 100"""
            ).fetchall()
    except Exception:
        rows = []

    if not rows:
        return html.P("No decisions logged yet.", className="text-muted")

    def sig_badge(s):
        c = {"UP": "success", "DOWN": "danger", "FLAT": "secondary"}
        return dbc.Badge(s or "—", color=c.get(s, "secondary"))

    def dec_badge(d):
        c = {"BUY": "success", "SELL": "danger", "HOLD": "warning", "WATCH": "secondary"}
        return dbc.Badge(d or "—", color=c.get(d, "secondary"))

    return dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in
                             ["Created", "Metal", "System Signal", "Your Decision",
                              "Rationale", "Price INR", "Price Type"]]))]
        + [html.Tbody([
            html.Tr([
                html.Td(str(r[0] or "")[:16]),
                html.Td(str(r[1])),
                html.Td(sig_badge(r[2])),
                html.Td(dec_badge(r[3])),
                html.Td(str(r[4] or "")[:60]),
                html.Td(f"₹{r[5]:,.2f}" if r[5] else "—"),
                html.Td(str(r[6] or "—")),
            ]) for r in rows
        ])],
        bordered=True, size="sm", responsive=True,
    )
