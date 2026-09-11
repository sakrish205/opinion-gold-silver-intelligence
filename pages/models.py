"""Models page — Model Performance and Model Registry in tabs."""
import sqlite3
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd

from config import DB_PATH

dash.register_page(__name__, path="/models", name="Models")

layout = html.Div([
    html.H4("Models", className="mb-3"),
    dbc.Tabs([
        dbc.Tab(label="📈 Performance", tab_id="perf"),
        dbc.Tab(label="🗂 Registry", tab_id="registry"),
    ], id="model-tabs", active_tab="perf", className="mb-3"),
    dcc.Interval(id="model-interval", interval=120_000, n_intervals=0),
    html.Div(id="model-content"),
])


def _perf_controls():
    return dbc.Row([
        dbc.Col(dcc.Dropdown(id="mp-asset",
            options=[{"label": "Gold (XAU)", "value": "XAU"},
                     {"label": "Silver (XAG)", "value": "XAG"}],
            value="XAU", clearable=False), md=3),
        dbc.Col(dcc.Dropdown(id="mp-metric",
            options=[{"label": m, "value": m} for m in
                     ["directional_accuracy", "smape", "mae", "rmse",
                      "interval_coverage", "cumulative_score"]],
            value="directional_accuracy", clearable=False), md=3),
    ], className="g-2 mb-3")


def _reg_controls():
    return dbc.Row([
        dbc.Col(dcc.Dropdown(id="mr-status-filter",
            options=[{"label": "All", "value": "all"}]
            + [{"label": s, "value": s} for s in
               ["production", "candidate", "benchmark", "retired", "failed"]],
            value="all", clearable=False), md=3),
    ], className="g-2 mb-3")


@callback(Output("model-content", "children"), Input("model-tabs", "active_tab"))
def render_tab(tab):
    if tab == "perf":
        return html.Div([_perf_controls(), dcc.Loading(dcc.Graph(id="mp-chart")),
                         html.Div(id="mp-table")])
    return html.Div([
        html.P("model_id, parameters, training_cutoff, created_at are immutable after insert.",
               className="text-muted small"),
        _reg_controls(),
        html.Div(id="mr-table"),
    ])


@callback(Output("mp-chart", "figure"), Output("mp-table", "children"),
          Input("model-interval", "n_intervals"), Input("mp-asset", "value"),
          Input("mp-metric", "value"), Input("model-tabs", "active_tab"))
def perf_refresh(_n, asset, metric, tab):
    if tab != "perf":
        return dash.no_update, dash.no_update
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query(
                """SELECT model_id, model_name, model_type, mae, rmse, smape,
                          directional_accuracy, interval_coverage, cumulative_score, status
                   FROM model_registry ORDER BY directional_accuracy DESC""",
                conn,
            )
    except Exception:
        df = pd.DataFrame()
    if df.empty:
        fig = px.bar(title="No model data — run backtesting first").update_layout(template="plotly_white")
        return fig, html.P("No data.", className="text-muted")

    fig = px.bar(df, x="model_name", y=metric, color="status",
                 title=f"{asset} — {metric}", template="plotly_white",
                 color_discrete_map={"production": "#f39c12", "candidate": "#3498db",
                                     "retired": "#95a5a6", "failed": "#e74c3c"})

    def sbadge(s):
        return dbc.Badge(s, color={"production": "warning", "candidate": "primary",
                                    "retired": "secondary", "failed": "danger"}.get(s, "secondary"))
    table = dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in
                             ["Model", "Type", "MAE", "RMSE", "sMAPE",
                              "Dir Acc", "Interval", "Score", "Status"]]))]
        + [html.Tbody([html.Tr([
            html.Td(r["model_name"]),
            html.Td(r["model_type"]),
            html.Td(f"{r['mae']:.4f}" if r["mae"] else "—"),
            html.Td(f"{r['rmse']:.4f}" if r["rmse"] else "—"),
            html.Td(f"{r['smape']:.2f}%" if r["smape"] else "—"),
            html.Td(f"{r['directional_accuracy']:.1%}" if r["directional_accuracy"] else "—"),
            html.Td(f"{r['interval_coverage']:.1%}" if r["interval_coverage"] else "—"),
            html.Td(str(r["cumulative_score"])),
            html.Td(sbadge(r["status"])),
        ]) for _, r in df.iterrows()])],
        bordered=True, size="sm", responsive=True, hover=True,
    )
    return fig, table


@callback(Output("mr-table", "children"),
          Input("model-interval", "n_intervals"), Input("mr-status-filter", "value"),
          Input("model-tabs", "active_tab"))
def reg_refresh(_n, status_filter, tab):
    if tab != "registry":
        return dash.no_update
    try:
        with sqlite3.connect(DB_PATH) as conn:
            q = "SELECT * FROM model_registry"
            params = ()
            if status_filter != "all":
                q += " WHERE status=?"
                params = (status_filter,)
            df = pd.read_sql_query(q + " ORDER BY created_at DESC LIMIT 200", conn, params=params)
    except Exception:
        df = pd.DataFrame()
    if df.empty:
        return html.P("No models yet. Run backtesting first.", className="text-muted")

    def sbadge(s):
        return dbc.Badge(s, color={"production": "warning", "candidate": "primary",
                                    "benchmark": "info", "retired": "secondary",
                                    "failed": "danger"}.get(s, "secondary"))
    return dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in
                             ["Model ID", "Name", "Type", "Training Cutoff",
                              "Dir Acc", "sMAPE", "Score", "Status", "Created"]]))]
        + [html.Tbody([html.Tr([
            html.Td(str(r.get("model_id", ""))[:18]),
            html.Td(str(r.get("model_name", ""))),
            html.Td(str(r.get("model_type", ""))),
            html.Td(str(r.get("training_cutoff", ""))[:10]),
            html.Td(f"{r['directional_accuracy']:.1%}" if r.get("directional_accuracy") else "—"),
            html.Td(f"{r['smape']:.2f}%" if r.get("smape") else "—"),
            html.Td(str(r.get("cumulative_score", 0))),
            html.Td(sbadge(r.get("status", ""))),
            html.Td(str(r.get("created_at", ""))[:10]),
        ]) for _, r in df.iterrows()])],
        bordered=True, size="sm", responsive=True, hover=True,
    )
