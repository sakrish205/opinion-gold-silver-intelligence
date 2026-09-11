"""Page 13: Backtesting — walk-forward CV results and trigger."""
import sqlite3
import dash
from dash import callback, dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd

from config import DB_PATH, FX_PAIRS, HORIZONS
from data.providers.metals_futures import MetalsFuturesProvider
from data.providers.forex import get_fx_history
from models.backtest import run_backtest

dash.register_page(__name__, path="/backtesting", name="Backtesting")

_futures = MetalsFuturesProvider()

layout = html.Div([
    html.H4("Backtesting", className="mb-3"),
    html.P("Walk-forward cross-validation only. No random splits. No future leakage.",
           className="text-muted"),
    dbc.Card(dbc.CardBody([
        html.H6("Run Backtest"),
        dbc.Row([
            dbc.Col(dcc.Dropdown(id="bt-asset",
                options=[{"label": "Gold (XAU)", "value": "XAU"}, {"label": "Silver (XAG)", "value": "XAG"}],
                value="XAU", clearable=False), md=3),
            dbc.Col(dcc.Input(id="bt-windows", type="number", value=10,
                              placeholder="Windows", className="form-control"), md=2),
            dbc.Col(dcc.Input(id="bt-step", type="number", value=24,
                              placeholder="Step hours", className="form-control"), md=2),
            dbc.Col(dbc.Button("Run Walk-Forward", id="bt-run-btn", color="warning"), md=3),
        ], className="g-2"),
        dcc.Loading(html.Div(id="bt-run-result", className="text-muted small mt-2")),
    ]), className="mb-4"),
    dbc.Row([
        dbc.Col(dcc.Dropdown(id="bt-run-select", placeholder="Select run", clearable=False), md=6),
    ], className="mb-3"),
    dcc.Loading(dcc.Graph(id="bt-chart")),
    html.Div(id="bt-window-table"),
])


@callback(
    Output("bt-run-result", "children"),
    Output("bt-run-select", "options"),
    Input("bt-run-btn", "n_clicks"),
    State("bt-asset", "value"),
    State("bt-windows", "value"),
    State("bt-step", "value"),
    prevent_initial_call=True,
)
def run_backtest_cb(n_clicks, asset, n_windows, step_size):
    result = _futures.fetch(asset=asset)
    if result.status not in ("LIVE", "STALE") or result.value is None:
        return f"Data {result.status}", []

    series = result.value["Close"]
    fx_history = {}
    for p in FX_PAIRS:
        r = get_fx_history(p)
        if r.status in ("LIVE", "STALE") and r.value is not None:
            fx_history[p.pair] = r.value["rate"].reindex(series.index, method="ffill")

    run_backtest(
        asset=asset, series=series, fx_history=fx_history,
        n_windows=int(n_windows or 10), step_size_hours=int(step_size or 24),
        currency="USD", method="walk_forward",
    )
    # Query run IDs for this asset just written
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT run_id FROM backtest_runs WHERE asset=? ORDER BY started_at DESC LIMIT 50",
            (asset,),
        ).fetchall()
    opts = [{"label": r[0][:16] + "…", "value": r[0]} for r in rows]
    return f"Backtest complete. {len(opts)} run(s) in DB.", opts


@callback(
    Output("bt-chart", "figure"),
    Output("bt-window-table", "children"),
    Input("bt-run-select", "value"),
)
def show_run(run_id):
    if not run_id:
        return {}, html.Div()

    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query(
                """SELECT window_index, train_end, test_start, actual_price, predicted_price,
                          direction_correct, score, interval_covered
                   FROM backtest_results WHERE run_id=? ORDER BY window_index""",
                conn, params=(run_id,),
            )
    except Exception:
        return {}, html.P("DB error", className="text-danger")

    if df.empty:
        return {}, html.P("No results for this run.", className="text-muted")

    fig = px.line(df, x="window_index", y=["actual_price", "predicted_price"],
                  title=f"Run {run_id[:16]}… — Actual vs Predicted per Window",
                  template="plotly_dark")

    table = dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in
                             ["Window", "Train End", "Test Start", "Actual", "Predicted",
                              "Dir Correct", "Score", "Interval"]]))]
        + [html.Tbody([
            html.Tr([
                html.Td(r["window_index"]),
                html.Td(str(r["train_end"] or "")[:10]),
                html.Td(str(r["test_start"] or "")[:10]),
                html.Td(f"{r['actual_price']:,.4f}" if r["actual_price"] else "—"),
                html.Td(f"{r['predicted_price']:,.4f}" if r["predicted_price"] else "—"),
                html.Td(dbc.Badge("✓", color="success") if r["direction_correct"] else dbc.Badge("✗", color="danger")),
                html.Td(str(r["score"])),
                html.Td(dbc.Badge("✓", color="success") if r["interval_covered"] else dbc.Badge("✗", color="secondary")),
            ]) for _, r in df.iterrows()
        ])],
        bordered=True, size="sm", responsive=True,
    )
    return fig, table
