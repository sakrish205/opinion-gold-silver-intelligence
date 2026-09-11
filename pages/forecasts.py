"""Page 7: Forecasts — 5 horizons × 5 models × 2 assets."""
import sqlite3
import uuid
from datetime import datetime, timezone

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from dash import Input, Output, State, callback, dcc, html

from config import ASSETS, DB_PATH, DATASET_VERSION, FEATURE_VERSION, FX_PAIRS, HORIZONS
from data.providers.metals_futures import MetalsFuturesProvider
from data.providers.forex import get_all_fx_latest, get_fx_history
from db import ops
from db.schema import init_db
from models.forecaster import run_forecast

dash.register_page(__name__, path="/forecasts", name="Forecasts")

_futures = MetalsFuturesProvider()

layout = html.Div([
    html.H4("Forecasts", className="mb-3"),
    html.P("5 horizons × 5 models (Naive, AutoARIMA, AutoETS, Theta, XGBoost+FX) × 2 assets",
           className="text-muted"),
    dbc.Row([
        dbc.Col(dcc.Dropdown(id="fc-asset",
            options=[{"label": "Gold (XAU)", "value": "XAU"}, {"label": "Silver (XAG)", "value": "XAG"}],
            value="XAU", clearable=False), md=3),
        dbc.Col(dcc.Dropdown(id="fc-currency",
            options=[{"label": c, "value": c} for c in ["INR", "USD"]],
            value="INR", clearable=False), md=2),
        dbc.Col(dbc.Button("Run Forecasts", id="fc-run-btn", color="warning"), md=3),
    ], className="mb-3"),
    dcc.Loading(html.Div(id="fc-output")),
    html.Div(id="fc-status", className="text-muted small mt-2"),
])


@callback(
    Output("fc-output", "children"),
    Output("fc-status", "children"),
    Input("fc-run-btn", "n_clicks"),
    State("fc-asset", "value"),
    State("fc-currency", "value"),
    prevent_initial_call=True,
)
def run_forecasts(n_clicks, asset, currency):
    result = _futures.fetch(asset=asset)
    if result.status not in ("LIVE", "STALE") or result.value is None:
        return html.P(f"Data {result.status}: {result.error}", className="text-warning"), ""

    df = result.value
    series = df["Close"]

    # FX history for XGBoost features
    fx_history = {}
    for p in FX_PAIRS:
        r = get_fx_history(p)
        if r.status in ("LIVE", "STALE") and r.value is not None:
            fx_history[p.pair] = r.value["rate"].reindex(series.index, method="ffill")

    fx_latest = get_all_fx_latest()
    usd_inr_r = fx_latest.get("USD/INR")
    usd_inr = usd_inr_r.value.get("rate") if usd_inr_r and usd_inr_r.value else None

    price_type = "FUTURES"
    price_at_forecast = float(series.iloc[-1])

    # Build feature snapshot
    snap = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "xau_usd_futures": price_at_forecast if asset == "XAU" else None,
        "xag_usd_futures": price_at_forecast if asset == "XAG" else None,
        "dataset_version": DATASET_VERSION,
        "feature_version": FEATURE_VERSION,
    }
    for p in FX_PAIRS:
        col = p.pair.lower().replace("/", "_")
        r = fx_latest.get(p.pair)
        rate = r.value.get("rate") if r and r.value else None
        res = r.value.get("resolution", "?") if r and r.value else "?"
        qual = r.status if r else "UNAVAILABLE"
        src = r.source if r else "none"
        ts = r.fetched_at if r else None
        snap.update({col: rate, f"{col}_source": src, f"{col}_resolution": res,
                     f"{col}_quality": qual, f"{col}_fetched_at": ts})

    snap_id = ops.insert_feature_snapshot(snap)

    # Run all 5 models
    records = run_forecast(
        asset=asset, series=series, currency=currency,
        price_type=price_type, feature_snapshot_id=snap_id,
        fx_history=fx_history if fx_history else None,
    )

    for rec in records:
        ops.insert_forecast(rec)

    # Build display table
    rows_by_horizon = {}
    for rec in records:
        h = rec["horizon_code"]
        if h not in rows_by_horizon:
            rows_by_horizon[h] = []
        p = rec.get("predicted_price")
        if currency == "INR" and usd_inr and p:
            p_disp = p * usd_inr
            p_fmt = f"₹{p_disp:,.2f} (DERIVED)"
        else:
            p_fmt = f"{p:,.4f}" if p else "—"
        dir_badge = dbc.Badge(
            rec.get("predicted_direction", "—"),
            color={"UP": "success", "DOWN": "danger", "FLAT": "secondary"}.get(
                rec.get("predicted_direction", ""), "secondary"),
        )
        rows_by_horizon[h].append(
            html.Tr([html.Td(rec["model_id"]), html.Td(p_fmt), html.Td(dir_badge)])
        )

    tabs = []
    for hdef in HORIZONS:
        h = hdef.code
        if h not in rows_by_horizon:
            continue
        table = dbc.Table(
            [html.Thead(html.Tr([html.Th("Model"), html.Th(f"Predicted ({currency})"), html.Th("Direction")]))]
            + [html.Tbody(rows_by_horizon[h])],
            bordered=True, size="sm",
        )
        tabs.append(dbc.Tab(table, label=hdef.label, tab_id=h))

    output = dbc.Tabs(tabs, active_tab=HORIZONS[0].code) if tabs else html.P("No forecasts produced.")
    status = f"Ran {len(records)} forecasts for {asset} | feature_snapshot_id={snap_id} | {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
    return output, status
