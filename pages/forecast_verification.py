"""Page 9: Forecast Verification — pending/verified/disputed queue + human review form."""
import sqlite3
from datetime import datetime, timezone

import dash
from dash import callback, dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

from config import DB_PATH
from db import ops

dash.register_page(__name__, path="/forecast-verification", name="Forecast Verification")

layout = html.Div([
    html.H4("Forecast Verification", className="mb-3"),
    dcc.Interval(id="fv-interval", interval=60_000, n_intervals=0),
    dbc.Tabs([
        dbc.Tab(html.Div(id="fv-pending"), label="Pending", tab_id="pending"),
        dbc.Tab(html.Div(id="fv-verified"), label="Verified", tab_id="verified"),
        dbc.Tab(html.Div(id="fv-disputed"), label="Disputed", tab_id="disputed"),
    ], id="fv-tabs", active_tab="pending", className="mb-3"),
    html.Hr(),
    html.H5("Human Review", className="mt-3"),
    dbc.Row([
        dbc.Col(dcc.Input(id="fv-fc-id", placeholder="forecast_id", className="form-control"), md=4),
        dbc.Col(dcc.Dropdown(id="fv-status",
            options=[{"label": s, "value": s} for s in ["VERIFIED", "DISPUTED", "NEEDS_REVIEW"]],
            placeholder="Status", clearable=False), md=3),
        dbc.Col(dcc.Input(id="fv-note", placeholder="Reviewer note", className="form-control"), md=4),
    ], className="mb-2"),
    dbc.Button("Submit Review", id="fv-submit-btn", color="warning", className="me-2"),
    html.Div(id="fv-submit-result", className="mt-2 text-muted small"),
])


def _fetch_queue(status_filter):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            if status_filter == "pending":
                rows = conn.execute(
                    """SELECT fh.forecast_id, fh.asset, fh.horizon_code, fh.model_id,
                              fh.predicted_price, fh.predicted_direction, fh.target_timestamp
                       FROM forecast_history fh
                       WHERE NOT EXISTS (
                           SELECT 1 FROM forecast_outcomes fo WHERE fo.forecast_id = fh.forecast_id
                       ) ORDER BY fh.target_timestamp ASC LIMIT 50"""
                ).fetchall()
                cols = ["forecast_id", "asset", "horizon", "model", "predicted_price", "direction", "target_ts"]
            else:
                hv_status = {"verified": "VERIFIED", "disputed": "DISPUTED"}[status_filter]
                rows = conn.execute(
                    """SELECT hv.forecast_id, hv.status, hv.human_score, hv.machine_score,
                              hv.reviewer_note, hv.reviewed_at, hv.revision
                       FROM human_verification hv
                       WHERE hv.status=? AND hv.revision=(
                           SELECT MAX(revision) FROM human_verification hv2
                           WHERE hv2.forecast_id=hv.forecast_id
                       ) ORDER BY hv.reviewed_at DESC LIMIT 50""",
                    (hv_status,),
                ).fetchall()
                cols = ["forecast_id", "status", "human_score", "machine_score", "note", "reviewed_at", "revision"]
    except Exception:
        return html.P("DB read error.", className="text-danger")

    if not rows:
        return html.P(f"No {status_filter} forecasts.", className="text-muted")
    table = dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in cols]))]
        + [html.Tbody([html.Tr([html.Td(str(v)) for v in r]) for r in rows])],
        bordered=True, size="sm", responsive=True,
    )
    return table


@callback(Output("fv-pending", "children"), Input("fv-interval", "n_intervals"))
def refresh_pending(_n):
    return _fetch_queue("pending")


@callback(Output("fv-verified", "children"), Input("fv-tabs", "active_tab"),
          Input("fv-interval", "n_intervals"))
def refresh_verified(tab, _n):
    return _fetch_queue("verified") if tab == "verified" else dash.no_update


@callback(Output("fv-disputed", "children"), Input("fv-tabs", "active_tab"),
          Input("fv-interval", "n_intervals"))
def refresh_disputed(tab, _n):
    return _fetch_queue("disputed") if tab == "disputed" else dash.no_update


@callback(
    Output("fv-submit-result", "children"),
    Input("fv-submit-btn", "n_clicks"),
    State("fv-fc-id", "value"),
    State("fv-status", "value"),
    State("fv-note", "value"),
    prevent_initial_call=True,
)
def submit_review(n_clicks, forecast_id, status, note):
    if not forecast_id or not status:
        return "Enter forecast_id and status."
    try:
        row_id = ops.insert_human_verification({
            "forecast_id": forecast_id.strip(),
            "status": status,
            "reviewer_note": note or "",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "reviewed_by": "human",
        })
        return f"Saved revision row id={row_id}."
    except Exception as e:
        return f"Error: {e}"
