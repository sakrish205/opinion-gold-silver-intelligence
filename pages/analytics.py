"""Analytics page — Currency Influence and Backtesting in tabs."""
import sqlite3
import dash
from dash import callback, dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from config import DB_PATH, FX_PAIRS
from data.providers.metals_futures import MetalsFuturesProvider
from data.providers.forex import get_fx_history
from models.backtest import run_backtest

dash.register_page(__name__, path="/analytics", name="Analytics")

_futures = MetalsFuturesProvider()

layout = html.Div([
    html.H4("Analytics", className="mb-3"),
    dbc.Tabs([
        dbc.Tab(label="📊 Currency Influence", tab_id="currency"),
        dbc.Tab(label="🔄 Backtesting", tab_id="backtest"),
    ], id="an-tabs", active_tab="currency", className="mb-3"),
    html.Div(id="an-content"),
])


def _currency_tab():
    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Dropdown(id="ci-asset",
                options=[{"label": "Gold (XAU)", "value": "XAU"},
                         {"label": "Silver (XAG)", "value": "XAG"}],
                value="XAU", clearable=False), md=3),
            dbc.Col(dcc.Dropdown(id="ci-window",
                options=[{"label": f"{h}h", "value": h} for h in [24, 48, 168, 720]],
                value=168, clearable=False), md=2),
        ], className="g-2 mb-3"),
        dcc.Loading(dcc.Graph(id="ci-heatmap")),
        html.P("Pearson correlation between metal futures price and FX pairs.",
               className="text-muted small mt-2"),
    ])


def _backtest_tab():
    return html.Div([
        html.P("Walk-forward only. No random splits. No future leakage.", className="text-muted small"),
        dbc.Row([
            dbc.Col(dcc.Dropdown(id="bt-asset",
                options=[{"label": "Gold (XAU)", "value": "XAU"},
                         {"label": "Silver (XAG)", "value": "XAG"}],
                value="XAU", clearable=False), md=3),
            dbc.Col(dcc.Input(id="bt-windows", type="number", value=10,
                              className="form-control form-control-sm"), md=2),
            dbc.Col(dcc.Input(id="bt-step", type="number", value=24,
                              className="form-control form-control-sm"), md=2),
            dbc.Col(dbc.Button("Run Walk-Forward", id="bt-run-btn",
                               color="warning", size="sm"), md=3),
        ], className="g-2 mb-2"),
        dcc.Loading(html.Div(id="bt-run-result", className="text-muted small mb-3")),
        dcc.Dropdown(id="bt-run-select", placeholder="Select run", clearable=False,
                     style={"maxWidth": "420px", "marginBottom": "12px"}),
        dcc.Loading(dcc.Graph(id="bt-chart")),
        html.Div(id="bt-window-table"),
    ])


@callback(Output("an-content", "children"), Input("an-tabs", "active_tab"))
def render_tab(tab):
    return _currency_tab() if tab == "currency" else _backtest_tab()


# ── Currency influence ────────────────────────────────────────────────────────
@callback(Output("ci-heatmap", "figure"), Input("ci-asset", "value"),
          Input("ci-window", "value"), Input("an-tabs", "active_tab"))
def heatmap(asset, window, tab):
    if tab != "currency":
        return dash.no_update
    metal_result = _futures.fetch(asset=asset)
    if metal_result.status not in ("LIVE", "STALE") or metal_result.value is None:
        return go.Figure().update_layout(title=f"{asset} — {metal_result.status}",
                                         template="plotly_white")
    frames = [metal_result.value["Close"].rename(f"{asset}/USD")]
    for p in FX_PAIRS:
        r = get_fx_history(p)
        if r.status in ("LIVE", "STALE") and r.value is not None:
            frames.append(r.value["rate"].rename(p.pair))
    if len(frames) < 2:
        return go.Figure().update_layout(title="Insufficient FX data", template="plotly_white")
    combined = pd.concat(frames, axis=1).dropna().iloc[-window:]
    fig = px.imshow(combined.corr(), text_auto=".2f",
                    title=f"{asset} FX Correlation | Last {window}h",
                    color_continuous_scale="RdBu", zmin=-1, zmax=1,
                    template="plotly_white")
    return fig


# ── Backtesting ───────────────────────────────────────────────────────────────
@callback(Output("bt-run-result", "children"), Output("bt-run-select", "options"),
          Input("bt-run-btn", "n_clicks"), State("bt-asset", "value"),
          State("bt-windows", "value"), State("bt-step", "value"),
          prevent_initial_call=True)
def run_bt(_, asset, n_windows, step):
    result = _futures.fetch(asset=asset)
    if result.status not in ("LIVE", "STALE") or result.value is None:
        return f"Data {result.status}", []
    series = result.value["Close"]
    fx_history = {}
    for p in FX_PAIRS:
        r = get_fx_history(p)
        if r.status in ("LIVE", "STALE") and r.value is not None:
            fx_history[p.pair] = r.value["rate"].reindex(series.index, method="ffill")
    run_backtest(asset=asset, series=series, fx_history=fx_history,
                 n_windows=int(n_windows or 10), step_size_hours=int(step or 24),
                 currency="USD", method="walk_forward")
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT run_id FROM backtest_runs WHERE asset=? ORDER BY started_at DESC LIMIT 50",
            (asset,),
        ).fetchall()
    opts = [{"label": r[0][:20] + "…", "value": r[0]} for r in rows]
    return f"Done. {len(opts)} run(s) in DB.", opts


@callback(Output("bt-chart", "figure"), Output("bt-window-table", "children"),
          Input("bt-run-select", "value"))
def show_run(run_id):
    if not run_id:
        return {}, html.Div()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query(
                """SELECT window_index, actual_price, predicted_price, direction_correct, score
                   FROM backtest_results WHERE run_id=? ORDER BY window_index""",
                conn, params=(run_id,),
            )
    except Exception:
        return {}, html.P("DB error", className="text-danger")
    if df.empty:
        return {}, html.P("No results.", className="text-muted")
    fig = px.line(df, x="window_index", y=["actual_price", "predicted_price"],
                  title="Actual vs Predicted per Window", template="plotly_white")
    table = dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in
                             ["Window", "Actual", "Predicted", "Dir Correct", "Score"]]))]
        + [html.Tbody([html.Tr([
            html.Td(r["window_index"]),
            html.Td(f"{r['actual_price']:,.4f}" if r["actual_price"] else "—"),
            html.Td(f"{r['predicted_price']:,.4f}" if r["predicted_price"] else "—"),
            html.Td(dbc.Badge("✓", color="success") if r["direction_correct"]
                    else dbc.Badge("✗", color="danger")),
            html.Td(str(r["score"])),
        ]) for _, r in df.iterrows()])],
        bordered=True, size="sm", responsive=True, hover=True,
    )
    return fig, table
