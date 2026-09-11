"""Page 16: Model Registry — status lifecycle, parameters, evaluation periods."""
import sqlite3
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import pandas as pd

from config import DB_PATH

dash.register_page(__name__, path="/model-registry", name="Model Registry")

layout = html.Div([
    html.H4("Model Registry", className="mb-3"),
    html.P(
        "model_id, parameters, library_version, training_cutoff, created_at are immutable after insert. "
        "Only status and aggregate metrics may be updated.",
        className="text-muted",
    ),
    dcc.Interval(id="mr-interval", interval=120_000, n_intervals=0),
    dbc.Row([
        dbc.Col(dcc.Dropdown(id="mr-status-filter",
            options=[{"label": "All", "value": "all"}]
            + [{"label": s, "value": s} for s in
               ["production", "candidate", "benchmark", "retired", "failed"]],
            value="all", clearable=False), md=3),
    ], className="mb-3"),
    html.Div(id="mr-table"),
])


@callback(Output("mr-table", "children"), Input("mr-interval", "n_intervals"),
          Input("mr-status-filter", "value"))
def refresh_table(_n, status_filter):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            query = "SELECT * FROM model_registry"
            params = ()
            if status_filter != "all":
                query += " WHERE status=?"
                params = (status_filter,)
            query += " ORDER BY created_at DESC LIMIT 200"
            df = pd.read_sql_query(query, conn, params=params)
    except Exception:
        df = pd.DataFrame()

    if df.empty:
        return html.P("No models registered yet. Run backtesting to populate.", className="text-muted")

    def status_badge(s):
        c = {"production": "warning", "candidate": "primary", "benchmark": "info",
             "retired": "secondary", "failed": "danger"}
        return dbc.Badge(s, color=c.get(s, "secondary"))

    rows = []
    for _, r in df.iterrows():
        rows.append(html.Tr([
            html.Td(str(r.get("model_id", ""))[:20]),
            html.Td(str(r.get("model_name", ""))),
            html.Td(str(r.get("model_type", ""))),
            html.Td(str(r.get("library", ""))),
            html.Td(str(r.get("library_version", ""))),
            html.Td(str(r.get("training_cutoff", ""))[:10]),
            html.Td(f"{r['directional_accuracy']:.1%}" if r.get("directional_accuracy") else "—"),
            html.Td(f"{r['smape']:.2f}%" if r.get("smape") else "—"),
            html.Td(str(r.get("cumulative_score", 0))),
            html.Td(status_badge(r.get("status", ""))),
            html.Td(str(r.get("created_at", ""))[:10]),
        ]))

    return dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in
                             ["Model ID", "Name", "Type", "Library", "Version",
                              "Training Cutoff", "Dir Acc", "sMAPE", "Score", "Status", "Created"]]))]
        + [html.Tbody(rows)],
        bordered=True, size="sm", responsive=True,
    )
