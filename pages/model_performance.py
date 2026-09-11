"""Page 12: Model Performance — MAE/RMSE/sMAPE/coverage/score per model."""
import sqlite3
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd

from config import DB_PATH, HORIZONS

dash.register_page(__name__, path="/model-performance", name="Model Performance")

layout = html.Div([
    html.H4("Model Performance", className="mb-3"),
    dcc.Interval(id="mp-interval", interval=120_000, n_intervals=0),
    dbc.Row([
        dbc.Col(dcc.Dropdown(id="mp-asset",
            options=[{"label": "Gold (XAU)", "value": "XAU"}, {"label": "Silver (XAG)", "value": "XAG"}],
            value="XAU", clearable=False), md=3),
        dbc.Col(dcc.Dropdown(id="mp-metric",
            options=[{"label": m, "value": m} for m in
                     ["directional_accuracy", "smape", "mae", "rmse", "interval_coverage", "cumulative_score"]],
            value="directional_accuracy", clearable=False), md=3),
    ], className="mb-3"),
    dcc.Loading(dcc.Graph(id="mp-chart")),
    html.H5("Full Table", className="mt-3 mb-2"),
    html.Div(id="mp-table"),
])


@callback(
    Output("mp-chart", "figure"),
    Output("mp-table", "children"),
    Input("mp-interval", "n_intervals"),
    Input("mp-asset", "value"),
    Input("mp-metric", "value"),
)
def refresh(_, asset, metric):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query(
                """SELECT model_id, model_name, model_type, mae, rmse, smape,
                          directional_accuracy, interval_coverage, cumulative_score, status
                   FROM model_registry WHERE dataset_version LIKE ?
                   ORDER BY directional_accuracy DESC NULLS LAST""",
                conn, params=(f"%{asset}%",),
            )
    except Exception:
        df = pd.DataFrame()

    if df.empty:
        empty_fig = px.bar(title=f"No model data for {asset}").update_layout(template="plotly_dark")
        return empty_fig, html.P("No model registry entries yet. Run backtesting first.",
                                  className="text-muted")

    fig = px.bar(
        df, x="model_name", y=metric, color="status",
        title=f"{asset} — {metric}",
        template="plotly_dark",
        color_discrete_map={"production": "gold", "candidate": "steelblue",
                             "retired": "gray", "failed": "red"},
    )

    def status_badge(s):
        c = {"production": "warning", "candidate": "primary", "retired": "secondary", "failed": "danger"}
        return dbc.Badge(s, color=c.get(s, "secondary"))

    table = dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in
                             ["Model", "Type", "MAE", "RMSE", "sMAPE",
                              "Dir Acc", "Interval Cov", "Score", "Status"]]))]
        + [html.Tbody([
            html.Tr([
                html.Td(r["model_name"]),
                html.Td(r["model_type"]),
                html.Td(f"{r['mae']:.4f}" if r["mae"] else "—"),
                html.Td(f"{r['rmse']:.4f}" if r["rmse"] else "—"),
                html.Td(f"{r['smape']:.2f}%" if r["smape"] else "—"),
                html.Td(f"{r['directional_accuracy']:.1%}" if r["directional_accuracy"] else "—"),
                html.Td(f"{r['interval_coverage']:.1%}" if r["interval_coverage"] else "—"),
                html.Td(str(r["cumulative_score"])),
                html.Td(status_badge(r["status"])),
            ]) for _, r in df.iterrows()
        ])],
        bordered=True, size="sm", responsive=True,
    )
    return fig, table
