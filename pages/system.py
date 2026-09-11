"""System page — Data Sources, System Health, Settings in tabs."""
import sqlite3
import os
from datetime import datetime, timezone

import dash
from dash import callback, dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd

from config import DB_PATH
from data.providers.base import ProviderSpec
from data.providers.metals_futures import MetalsFuturesProvider
from data.providers.metals_spot import SpotUnavailableProvider
from data.providers.forex import YFinanceFXProvider, OpenERAPIFXProvider
from data.providers.news import VERIFIED_SOURCES
from llm.ollama_client import is_online
from llm.llm_registry import LLM_MODELS, DEFAULT_MODEL_KEY, get_model

dash.register_page(__name__, path="/system", name="System")

_providers = [MetalsFuturesProvider(), SpotUnavailableProvider(),
              YFinanceFXProvider(), OpenERAPIFXProvider()]


def _spec_table():
    rows = [html.Tr([
        html.Td(p.spec.name), html.Td(p.spec.cost),
        html.Td("Yes" if p.spec.requires_key else "No"),
        html.Td(p.spec.rate_limit), html.Td(p.spec.resolution),
        html.Td(p.spec.reliability), html.Td(p.spec.storage_rights),
        html.Td(p.spec.license),
    ]) for p in _providers]
    return dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in
                             ["Provider", "Cost", "Key", "Rate Limit", "Resolution",
                              "Reliability", "Storage", "License"]]))]
        + [html.Tbody(rows)],
        bordered=True, size="sm", responsive=True,
    )


layout = html.Div([
    html.H4("System", className="mb-3"),
    dcc.Interval(id="sys-interval", interval=30_000, n_intervals=0),
    dbc.Tabs([
        dbc.Tab(label="🔌 Data Sources", tab_id="sources"),
        dbc.Tab(label="🏥 Health", tab_id="health"),
        dbc.Tab(label="⚙️ Settings", tab_id="settings"),
    ], id="sys-tabs", active_tab="sources", className="mb-3"),
    html.Div(id="sys-content"),
])


def _sources_tab():
    news_section = (
        dbc.Alert("No news sources configured. Add to data/providers/news.py.", color="warning")
        if not VERIFIED_SOURCES else dbc.Table(
            [html.Thead(html.Tr([html.Th(c) for c in ["Name", "ToS Status"]]))]
            + [html.Tbody([html.Tr([html.Td(s.get("name")), html.Td(s.get("tos_status", ""))])
                           for s in VERIFIED_SOURCES])],
            bordered=True, size="sm",
        )
    )
    return html.Div([
        html.H6("Provider Specs", className="mb-2"),
        _spec_table(),
        html.Div(id="sys-health-cards", className="my-3"),
        html.H6("News Sources", className="mb-2"),
        news_section,
    ])


def _health_tab():
    return html.Div([
        dbc.Row([
            dbc.Col(html.Div(id="sys-ollama-card"), md=3),
            dbc.Col(html.Div(id="sys-db-card"), md=3),
        ], className="g-2 mb-3"),
        html.H6("Table Row Counts", className="mb-2"),
        html.Div(id="sys-counts"),
        html.H6("Source Log", className="mt-3 mb-2"),
        html.Div(id="sys-log"),
    ])


def _settings_tab():
    return html.Div([
        html.H6("LLM Model"),
        html.P("Used for news analysis only. Scores always determined by market data.",
               className="text-muted small"),
        dbc.Row([
            dbc.Col(dcc.Dropdown(id="st-llm-model",
                options=[{"label": f"{k} ({v.ollama_name}, {v.size_gb}GB)", "value": k}
                         for k, v in LLM_MODELS.items()],
                value=DEFAULT_MODEL_KEY, clearable=False), md=5),
            dbc.Col(dbc.Button("Save", id="st-save-llm", color="warning", size="sm"), md=1),
        ], className="g-2 mb-2"),
        html.Div(id="st-llm-model-spec", className="mb-3"),
        html.Div(id="st-save-llm-result", className="text-muted small mb-4"),
        html.H6("Thresholds"),
        dbc.Row([
            dbc.Col([html.Label("XAU/INR Cross-Check (%)", className="form-label small"),
                     dcc.Input(id="st-xau-threshold", type="number", value=0.5,
                               className="form-control form-control-sm")], md=3),
            dbc.Col([html.Label("Price Refresh (s)", className="form-label small"),
                     dcc.Input(id="st-refresh-prices", type="number", value=60,
                               className="form-control form-control-sm")], md=3),
            dbc.Col([html.Label("FX Refresh (s)", className="form-label small"),
                     dcc.Input(id="st-refresh-fx", type="number", value=300,
                               className="form-control form-control-sm")], md=3),
            dbc.Col(dbc.Button("Save", id="st-save-thresholds", color="secondary",
                               size="sm", className="mt-4"), md=1),
        ], className="g-2"),
        html.Div(id="st-save-thresholds-result", className="text-muted small mt-2"),
    ])


@callback(Output("sys-content", "children"), Input("sys-tabs", "active_tab"))
def render_tab(tab):
    return {"sources": _sources_tab, "health": _health_tab, "settings": _settings_tab}[tab]()


# ── Sources ───────────────────────────────────────────────────────────────────
@callback(Output("sys-health-cards", "children"), Input("sys-interval", "n_intervals"),
          Input("sys-tabs", "active_tab"))
def provider_health(_n, tab):
    if tab != "sources":
        return dash.no_update
    cards = []
    for p in _providers:
        try:
            r = p.fetch_latest("XAU") if hasattr(p, "fetch_latest") else p.fetch()
            status, latency = r.status, r.latency_ms
        except Exception:
            status, latency = "ERROR", None
        color = {"LIVE": "success", "STALE": "warning", "UNAVAILABLE": "secondary"}.get(status, "danger")
        cards.append(dbc.Col(dbc.Card(dbc.CardBody([
            html.Small(p.spec.name, className="text-muted"),
            html.Br(), dbc.Badge(status, color=color),
            html.Small(f" {latency}ms" if latency else "", className="text-muted ms-1"),
        ]), className="shadow-sm"), md=2))
    return dbc.Row(cards, className="g-2")


# ── Health ────────────────────────────────────────────────────────────────────
@callback(Output("sys-ollama-card", "children"), Output("sys-db-card", "children"),
          Output("sys-counts", "children"), Output("sys-log", "children"),
          Input("sys-interval", "n_intervals"), Input("sys-tabs", "active_tab"))
def health_refresh(_n, tab):
    if tab != "health":
        return (dash.no_update,) * 4
    online = is_online()
    ollama_card = dbc.Card(dbc.CardBody([
        html.Small("Ollama", className="text-muted"), html.Br(),
        dbc.Badge("ONLINE" if online else "OFFLINE", color="success" if online else "danger"),
    ]), className="shadow-sm")
    try:
        sz = f"{os.path.getsize(DB_PATH) / 1024:.1f} KB"
    except Exception:
        sz = "—"
    db_card = dbc.Card(dbc.CardBody([
        html.Small("opinion.db", className="text-muted"), html.H5(sz, className="mb-0"),
    ]), className="shadow-sm")
    tables = ["feature_snapshots", "model_registry", "forecast_history", "forecast_outcomes",
              "human_verification", "backtest_runs", "backtest_results",
              "data_source_log", "decision_history", "news_events", "data_quality_alerts"]
    rows = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            for t in tables:
                try:
                    n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except Exception:
                    n = "—"
                rows.append(html.Tr([html.Td(t), html.Td(str(n))]))
    except Exception:
        pass
    counts = dbc.Table([html.Thead(html.Tr([html.Th("Table"), html.Th("Rows")]))]
                       + [html.Tbody(rows)], bordered=True, size="sm",
                       style={"maxWidth": "400px"})
    try:
        with sqlite3.connect(DB_PATH) as conn:
            log_rows = conn.execute(
                """SELECT logged_at, source, data_type, http_status, latency_ms, ok, quality
                   FROM data_source_log ORDER BY logged_at DESC LIMIT 40"""
            ).fetchall()
    except Exception:
        log_rows = []
    log = (html.P("No source log yet.", className="text-muted") if not log_rows else
           dbc.Table(
               [html.Thead(html.Tr([html.Th(c) for c in
                                    ["Logged", "Source", "Type", "HTTP", "ms", "OK", "Quality"]]))]
               + [html.Tbody([html.Tr([
                   html.Td(str(r[0] or "")[:16]), html.Td(str(r[1])[:20]),
                   html.Td(str(r[2])), html.Td(str(r[3] or "—")), html.Td(str(r[4] or "—")),
                   html.Td(dbc.Badge("✓", color="success") if r[5] else dbc.Badge("✗", color="danger")),
                   html.Td(str(r[6])),
               ]) for r in log_rows])],
               bordered=True, size="sm", responsive=True, hover=True,
           ))
    return ollama_card, db_card, counts, log


# ── Settings ──────────────────────────────────────────────────────────────────
@callback(Output("st-llm-model-spec", "children"), Input("st-llm-model", "value"))
def llm_spec(key):
    spec = get_model(key)
    if not spec:
        return ""
    return dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.Small("Size"), html.H6(f"{spec.size_gb}GB")])), md=2),
        dbc.Col(dbc.Card(dbc.CardBody([html.Small("Min RAM"), html.H6(f"{spec.min_ram_gb}GB")])), md=2),
        dbc.Col(dbc.Card(dbc.CardBody([html.Small("License"), html.H6(spec.license)])), md=2),
        dbc.Col(dbc.Card(dbc.CardBody([html.Small("CPU?"), html.H6("Yes" if spec.cpu_capable else "No")])), md=2),
    ], className="g-2")


@callback(Output("st-save-llm-result", "children"), Input("st-save-llm", "n_clicks"),
          State("st-llm-model", "value"), prevent_initial_call=True)
def save_llm(_, key):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT OR REPLACE INTO _settings (key,value) VALUES ('llm_model',?)", (key,))
        return f"Saved: {key}"
    except Exception as e:
        return f"Error: {e}"


@callback(Output("st-save-thresholds-result", "children"), Input("st-save-thresholds", "n_clicks"),
          State("st-xau-threshold", "value"), State("st-refresh-prices", "value"),
          State("st-refresh-fx", "value"), prevent_initial_call=True)
def save_thresholds(_, xau, prices, fx):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _settings (key TEXT PRIMARY KEY, value TEXT)")
            for k, v in [("xau_inr_cross_check_threshold", xau),
                          ("refresh_prices_seconds", prices), ("refresh_fx_seconds", fx)]:
                if v is not None:
                    conn.execute("INSERT OR REPLACE INTO _settings (key,value) VALUES (?,?)", (k, str(v)))
        return "Saved (take effect on restart)."
    except Exception as e:
        return f"Error: {e}"
