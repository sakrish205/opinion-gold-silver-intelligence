"""Forecasts page — Run forecasts, Audit chart, Verification queue in tabs."""
import sqlite3
from datetime import datetime, timezone

import dash
from dash import callback, dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd

from config import (ASSETS, DB_PATH, DATASET_VERSION, FEATURE_VERSION,
                    FX_PAIRS, HORIZONS)
from data.providers.metals_futures import MetalsFuturesProvider
from data.providers.forex import get_all_fx_latest, get_fx_history
from db import ops

dash.register_page(__name__, path="/forecasts", name="Forecasts")

_futures = MetalsFuturesProvider()

# ── Layout ────────────────────────────────────────────────────────────────────
layout = html.Div([
    html.H4("Forecasts", className="mb-3"),
    dbc.Tabs([
        dbc.Tab(label="▶ Run", tab_id="run"),
        dbc.Tab(label="📈 Audit", tab_id="audit"),
        dbc.Tab(label="✅ Verify", tab_id="verify"),
    ], id="fc-tabs", active_tab="run", className="mb-3"),
    html.Div(id="fc-tab-content"),
])


# ── Tab content ───────────────────────────────────────────────────────────────
def _run_tab():
    return html.Div([
        html.P("5 horizons × 5 models (Naive, AutoARIMA, AutoETS, Theta, XGBoost+FX)",
               className="text-muted"),
        dbc.Row([
            dbc.Col(dcc.Dropdown(id="fc-asset",
                options=[{"label": "Gold (XAU)", "value": "XAU"},
                         {"label": "Silver (XAG)", "value": "XAG"}],
                value="XAU", clearable=False), md=3),
            dbc.Col(dcc.Dropdown(id="fc-currency",
                options=[{"label": c, "value": c} for c in ["INR", "USD"]],
                value="INR", clearable=False), md=2),
            dbc.Col(dbc.Button("Run Forecasts", id="fc-run-btn", color="warning"), md=3),
        ], className="mb-3 g-2"),
        dcc.Loading(html.Div(id="fc-output")),
        html.Div(id="fc-status", className="text-muted small mt-2"),
    ])


def _audit_tab():
    return html.Div([
        html.P("Historical predictions vs observed outcomes (read from immutable forecast_history).",
               className="text-muted"),
        dbc.Row([
            dbc.Col(dcc.Dropdown(id="fva-asset",
                options=[{"label": "Gold (XAU)", "value": "XAU"},
                         {"label": "Silver (XAG)", "value": "XAG"}],
                value="XAU", clearable=False), md=3),
            dbc.Col(dcc.Dropdown(id="fva-horizon",
                options=[{"label": h.label, "value": h.code} for h in HORIZONS],
                value=HORIZONS[0].code, clearable=False), md=3),
            dbc.Col(dcc.Dropdown(id="fva-model",
                options=[{"label": m, "value": m} for m in
                         ["sf_naive", "sf_autoarima", "sf_autoets", "sf_theta", "xgboost_fx"]],
                value="sf_autoarima", clearable=False), md=3),
        ], className="mb-3 g-2"),
        dcc.Loading(dcc.Graph(id="fva-chart", style={"height": "480px"})),
    ])


def _verify_tab():
    return html.Div([
        dcc.Interval(id="fv-interval", interval=60_000, n_intervals=0),
        dbc.Tabs([
            dbc.Tab(html.Div(id="fv-pending"), label="Pending", tab_id="pending"),
            dbc.Tab(html.Div(id="fv-verified"), label="Verified", tab_id="verified"),
            dbc.Tab(html.Div(id="fv-disputed"), label="Disputed", tab_id="disputed"),
        ], id="fv-sub-tabs", active_tab="pending", className="mb-3"),
        html.Hr(),
        html.H6("Human Review", className="mt-2"),
        dbc.Row([
            dbc.Col(dcc.Input(id="fv-fc-id", placeholder="forecast_id",
                              className="form-control form-control-sm"), md=4),
            dbc.Col(dcc.Dropdown(id="fv-status",
                options=[{"label": s, "value": s} for s in
                         ["VERIFIED", "DISPUTED", "NEEDS_REVIEW"]],
                placeholder="Status", clearable=False), md=3),
            dbc.Col(dcc.Input(id="fv-note", placeholder="Note",
                              className="form-control form-control-sm"), md=3),
            dbc.Col(dbc.Button("Submit", id="fv-submit-btn", color="warning",
                               size="sm"), md=1),
        ], className="g-2"),
        html.Div(id="fv-submit-result", className="text-muted small mt-2"),
    ])


@callback(Output("fc-tab-content", "children"), Input("fc-tabs", "active_tab"))
def render_tab(tab):
    return {"run": _run_tab, "audit": _audit_tab, "verify": _verify_tab}[tab]()


# ── Run Forecasts callbacks ───────────────────────────────────────────────────
@callback(
    Output("fc-output", "children"),
    Output("fc-status", "children"),
    Input("fc-run-btn", "n_clicks"),
    State("fc-asset", "value"),
    State("fc-currency", "value"),
    prevent_initial_call=True,
)
def run_forecasts(n_clicks, asset, currency):
    from models.forecaster import run_forecast
    result = _futures.fetch(asset=asset)
    if result.status not in ("LIVE", "STALE") or result.value is None:
        return html.P(f"Data {result.status}", className="text-warning"), ""

    series = result.value["Close"]
    fx_history = {}
    for p in FX_PAIRS:
        r = get_fx_history(p)
        if r.status in ("LIVE", "STALE") and r.value is not None:
            fx_history[p.pair] = r.value["rate"].reindex(series.index, method="ffill")

    fx_latest = get_all_fx_latest()
    usd_inr_r = fx_latest.get("USD/INR")
    usd_inr = usd_inr_r.value.get("rate") if usd_inr_r and usd_inr_r.value else None

    snap = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "xau_usd_futures": float(series.iloc[-1]) if asset == "XAU" else None,
        "xag_usd_futures": float(series.iloc[-1]) if asset == "XAG" else None,
        "dataset_version": DATASET_VERSION, "feature_version": FEATURE_VERSION,
    }
    for p in FX_PAIRS:
        col = p.pair.lower().replace("/", "_")
        r = fx_latest.get(p.pair)
        snap.update({
            col: r.value.get("rate") if r and r.value else None,
            f"{col}_source": r.source if r else "none",
            f"{col}_resolution": r.value.get("resolution", "?") if r and r.value else "?",
            f"{col}_quality": r.status if r else "UNAVAILABLE",
            f"{col}_fetched_at": r.fetched_at if r else None,
        })
    snap_id = ops.insert_feature_snapshot(snap)

    records = run_forecast(asset=asset, series=series, currency=currency,
                           price_type="FUTURES", feature_snapshot_id=snap_id,
                           fx_history=fx_history or None)
    for rec in records:
        ops.insert_forecast(rec)

    rows_by_horizon = {}
    for rec in records:
        h = rec["horizon_code"]
        rows_by_horizon.setdefault(h, [])
        p = rec.get("predicted_price")
        if currency == "INR" and usd_inr and p:
            p_fmt = f"₹{p * usd_inr:,.2f} (DERIVED)"
        else:
            p_fmt = f"{p:,.4f}" if p else "—"
        dir_badge = dbc.Badge(
            rec.get("predicted_direction", "—"),
            color={"UP": "success", "DOWN": "danger", "FLAT": "secondary"}.get(
                rec.get("predicted_direction", ""), "secondary"),
        )
        rows_by_horizon[h].append(html.Tr([
            html.Td(rec["model_id"]), html.Td(p_fmt), html.Td(dir_badge),
        ]))

    tabs = [dbc.Tab(
        dbc.Table(
            [html.Thead(html.Tr([html.Th("Model"), html.Th(f"Predicted ({currency})"), html.Th("Direction")]))]
            + [html.Tbody(rows_by_horizon.get(h.code, []))],
            bordered=True, size="sm", hover=True,
        ), label=h.label, tab_id=h.code,
    ) for h in HORIZONS if h.code in rows_by_horizon]

    out = dbc.Tabs(tabs, active_tab=HORIZONS[0].code) if tabs else html.P("No forecasts.")
    status = f"{len(records)} forecasts for {asset} | snapshot {snap_id} | {datetime.now(timezone.utc).strftime('%H:%M')} UTC"
    return out, status


# ── Audit chart callback ──────────────────────────────────────────────────────
@callback(
    Output("fva-chart", "figure"),
    Input("fva-asset", "value"),
    Input("fva-horizon", "value"),
    Input("fva-model", "value"),
)
def update_audit(asset, horizon_code, model_id):
    fig = go.Figure()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query(
                """SELECT fh.forecast_origin, fh.target_timestamp, fh.predicted_price,
                          fh.lower_bound, fh.upper_bound, fh.price_at_forecast,
                          fo.actual_price, fo.outcome_verified_at
                   FROM forecast_history fh
                   LEFT JOIN forecast_outcomes fo ON fo.forecast_id = fh.forecast_id
                   WHERE fh.asset=? AND fh.horizon_code=? AND fh.model_id=?
                   ORDER BY fh.forecast_origin ASC LIMIT 200""",
                conn, params=(asset, horizon_code, model_id),
            )
    except Exception:
        df = pd.DataFrame()

    if df.empty:
        return fig.update_layout(title="No data yet — run forecasts first", template="plotly_white")

    observed = df.dropna(subset=["actual_price"])
    if not observed.empty:
        fig.add_trace(go.Scatter(x=pd.to_datetime(observed["target_timestamp"]),
                                 y=observed["actual_price"], mode="markers",
                                 name="Observed", marker=dict(symbol="circle", size=8, color="#2c3e50")))
    fig.add_trace(go.Scatter(x=pd.to_datetime(df["target_timestamp"]),
                             y=df["predicted_price"], mode="lines+markers",
                             name="Predicted", line=dict(color="#e67e22", dash="dot")))
    has_bounds = df["lower_bound"].notna() & df["upper_bound"].notna()
    if has_bounds.any():
        b = df[has_bounds]
        fig.add_trace(go.Scatter(
            x=pd.concat([pd.to_datetime(b["target_timestamp"]),
                         pd.to_datetime(b["target_timestamp"]).iloc[::-1]]),
            y=pd.concat([b["upper_bound"], b["lower_bound"].iloc[::-1]]),
            fill="toself", fillcolor="rgba(230,126,34,0.1)",
            line=dict(color="rgba(0,0,0,0)"), name="90% Range",
        ))
    fig.add_trace(go.Scatter(x=pd.to_datetime(df["forecast_origin"]),
                             y=df["price_at_forecast"], mode="markers",
                             name="Forecast Origin",
                             marker=dict(symbol="triangle-right", size=8, color="#3498db")))
    verified = df.dropna(subset=["outcome_verified_at"])
    if not verified.empty:
        fig.add_trace(go.Scatter(x=pd.to_datetime(verified["outcome_verified_at"]),
                                 y=verified["actual_price"], mode="markers",
                                 name="Verified", marker=dict(symbol="diamond", size=10, color="#27ae60")))
    fig.update_layout(title=f"{asset} {horizon_code} | {model_id}",
                      yaxis_title="Price (USD — FUTURES)",
                      template="plotly_white", hovermode="x unified")
    return fig


# ── Verification queue callbacks ──────────────────────────────────────────────
def _queue(status_filter):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            if status_filter == "pending":
                rows = conn.execute(
                    """SELECT fh.forecast_id, fh.asset, fh.horizon_code, fh.model_id,
                              fh.predicted_direction, fh.target_timestamp
                       FROM forecast_history fh
                       WHERE NOT EXISTS (
                           SELECT 1 FROM forecast_outcomes fo WHERE fo.forecast_id=fh.forecast_id
                       ) ORDER BY fh.target_timestamp ASC LIMIT 50"""
                ).fetchall()
                cols = ["ID", "Asset", "Horizon", "Model", "Direction", "Target"]
            else:
                s = {"verified": "VERIFIED", "disputed": "DISPUTED"}[status_filter]
                rows = conn.execute(
                    """SELECT hv.forecast_id, hv.status, hv.human_score, hv.reviewer_note, hv.reviewed_at
                       FROM human_verification hv WHERE hv.status=?
                       AND hv.revision=(SELECT MAX(revision) FROM human_verification h2
                                        WHERE h2.forecast_id=hv.forecast_id)
                       ORDER BY hv.reviewed_at DESC LIMIT 50""", (s,),
                ).fetchall()
                cols = ["ID", "Status", "Score", "Note", "Reviewed At"]
    except Exception:
        rows, cols = [], []
    if not rows:
        return html.P(f"No {status_filter} forecasts.", className="text-muted")
    return dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in cols]))]
        + [html.Tbody([html.Tr([html.Td(str(v)[:30]) for v in r]) for r in rows])],
        bordered=True, size="sm", responsive=True, hover=True,
    )


@callback(Output("fv-pending", "children"), Input("fv-interval", "n_intervals"))
def q_pending(_n): return _queue("pending")

@callback(Output("fv-verified", "children"), Input("fv-sub-tabs", "active_tab"),
          Input("fv-interval", "n_intervals"))
def q_verified(tab, _n): return _queue("verified") if tab == "verified" else dash.no_update

@callback(Output("fv-disputed", "children"), Input("fv-sub-tabs", "active_tab"),
          Input("fv-interval", "n_intervals"))
def q_disputed(tab, _n): return _queue("disputed") if tab == "disputed" else dash.no_update

@callback(Output("fv-submit-result", "children"), Input("fv-submit-btn", "n_clicks"),
          State("fv-fc-id", "value"), State("fv-status", "value"), State("fv-note", "value"),
          prevent_initial_call=True)
def submit_review(_, fid, status, note):
    if not fid or not status:
        return "Enter forecast_id and status."
    try:
        ops.insert_human_verification({"forecast_id": fid.strip(), "status": status,
                                       "reviewer_note": note or "",
                                       "reviewed_at": datetime.now(timezone.utc).isoformat(),
                                       "reviewed_by": "human"})
        return f"Saved review for {fid[:16]}…"
    except Exception as e:
        return f"Error: {e}"
