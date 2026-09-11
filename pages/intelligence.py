"""Intelligence page — News and Decision History in tabs."""
import sqlite3
from datetime import datetime, timezone

import dash
from dash import callback, dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

from config import DB_PATH
from data.providers.news import get_news
from llm.ollama_client import analyse_news, is_online
from db import ops

dash.register_page(__name__, path="/intelligence", name="Intelligence")

layout = html.Div([
    html.H4("Intelligence", className="mb-3"),
    dbc.Tabs([
        dbc.Tab(label="📰 News", tab_id="news"),
        dbc.Tab(label="📋 Decisions", tab_id="decisions"),
    ], id="intel-tabs", active_tab="news", className="mb-3"),
    html.Div(id="intel-content"),
])


def _news_tab():
    return html.Div([
        dcc.Interval(id="news-interval", interval=300_000, n_intervals=0),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Small("Ollama LLM", className="text-muted"),
                html.Div(id="intel-ollama-status"),
            ]), className="shadow-sm"), md=3),
            dbc.Col(dbc.Button("Fetch & Analyse", id="news-run-btn", color="warning",
                               size="sm"), md=2),
        ], className="mb-3 g-2"),
        html.Div(id="news-run-result", className="text-muted small mb-3"),
        html.Div(id="news-event-log"),
    ])


def _decisions_tab():
    return html.Div([
        html.P("Log your own decisions. System signals come from forecasts. "
               "This system does not execute trades.", className="text-muted small"),
        dbc.Row([
            dbc.Col(dcc.Dropdown(id="dec-metal",
                options=[{"label": "Gold (XAU)", "value": "XAU"},
                         {"label": "Silver (XAG)", "value": "XAG"}],
                value="XAU", clearable=False), md=2),
            dbc.Col(dcc.Dropdown(id="dec-decision",
                options=[{"label": v, "value": v} for v in ["BUY", "SELL", "HOLD", "WATCH"]],
                placeholder="Decision", clearable=False), md=2),
            dbc.Col(dcc.Input(id="dec-rationale", placeholder="Rationale",
                              className="form-control form-control-sm"), md=5),
            dbc.Col(dbc.Button("Save", id="dec-save-btn", color="warning", size="sm"), md=1),
        ], className="g-2 mb-2"),
        html.Div(id="dec-save-result", className="text-muted small mb-3"),
        html.Div(id="dec-table"),
    ])


@callback(Output("intel-content", "children"), Input("intel-tabs", "active_tab"))
def render_tab(tab):
    return _news_tab() if tab == "news" else _decisions_tab()


# ── News callbacks ────────────────────────────────────────────────────────────
@callback(Output("intel-ollama-status", "children"), Input("news-interval", "n_intervals"))
def ollama_status(_n):
    online = is_online()
    return dbc.Badge("ONLINE" if online else "OFFLINE",
                     color="success" if online else "danger")


@callback(Output("news-run-result", "children"), Input("news-run-btn", "n_clicks"),
          prevent_initial_call=True)
def fetch_news(_):
    items = get_news()
    if not items:
        return "No news. Add verified sources in data/providers/news.py."
    analysis = analyse_news([i.get("headline", "") for i in items[:20]])
    saved = 0
    for item in items:
        if ops.news_hash_exists(item.get("content_hash", "")):
            continue
        ops.insert_news_event({
            "news_id": item.get("news_id"), "published_at": item.get("published_at"),
            "fetched_at": item.get("fetched_at"), "source": item.get("source"),
            "source_url": item.get("source_url"), "headline": item.get("headline"),
            "content_hash": item.get("content_hash"),
            "status": "ANALYSED" if isinstance(analysis, dict) else "RAW",
            **({"event": analysis.get("event"), "direction": analysis.get("direction"),
                "impact": analysis.get("impact"), "confidence": analysis.get("confidence"),
                "asset": analysis.get("asset")} if isinstance(analysis, dict) else {}),
        })
        saved += 1
    return f"Fetched {len(items)} items, saved {saved} new."


@callback(Output("news-event-log", "children"),
          Input("news-interval", "n_intervals"), Input("news-run-btn", "n_clicks"))
def news_log(_n, _b):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """SELECT published_at, source, headline, asset, direction, impact, status
                   FROM news_events ORDER BY fetched_at DESC LIMIT 80"""
            ).fetchall()
    except Exception:
        rows = []
    if not rows:
        return html.P("No news events yet.", className="text-muted")

    def dbadge(d, mapping):
        return dbc.Badge(d or "—", color=mapping.get(d or "", "secondary"), className="me-1")

    return dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in
                             ["Published", "Source", "Headline", "Asset", "Direction", "Impact", "Status"]]))]
        + [html.Tbody([html.Tr([
            html.Td(str(r[0] or "")[:16]),
            html.Td(str(r[1])[:20]),
            html.Td(str(r[2])[:80]),
            html.Td(str(r[3] or "—")),
            html.Td(dbadge(r[4], {"UP": "success", "DOWN": "danger", "NEUTRAL": "secondary"})),
            html.Td(dbadge(r[5], {"HIGH": "danger", "MEDIUM": "warning", "LOW": "secondary"})),
            html.Td(str(r[6])),
        ]) for r in rows])],
        bordered=True, size="sm", responsive=True, hover=True,
    )


# ── Decisions callbacks ───────────────────────────────────────────────────────
@callback(Output("dec-save-result", "children"), Input("dec-save-btn", "n_clicks"),
          State("dec-metal", "value"), State("dec-decision", "value"),
          State("dec-rationale", "value"), prevent_initial_call=True)
def save_decision(_, metal, decision, rationale):
    if not decision:
        return "Select a decision."
    ops.insert_decision({"created_at": datetime.now(timezone.utc).isoformat(),
                          "metal": metal, "user_decision": decision,
                          "user_rationale": rationale or ""})
    return f"Saved: {metal} {decision}"


@callback(Output("dec-table", "children"),
          Input("dec-save-btn", "n_clicks"), Input("intel-tabs", "active_tab"))
def dec_table(_btn, tab):
    if tab != "decisions":
        return dash.no_update
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """SELECT created_at, metal, system_signal, user_decision, user_rationale
                   FROM decision_history ORDER BY created_at DESC LIMIT 80"""
            ).fetchall()
    except Exception:
        rows = []
    if not rows:
        return html.P("No decisions logged yet.", className="text-muted")
    return dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in
                             ["Date", "Metal", "Signal", "Your Decision", "Rationale"]]))]
        + [html.Tbody([html.Tr([
            html.Td(str(r[0] or "")[:16]),
            html.Td(str(r[1])),
            html.Td(dbc.Badge(r[2] or "—", color={"UP": "success", "DOWN": "danger"}.get(r[2] or "", "secondary"))),
            html.Td(dbc.Badge(r[3] or "—", color={"BUY": "success", "SELL": "danger",
                                                    "HOLD": "warning", "WATCH": "secondary"}.get(r[3] or "", "secondary"))),
            html.Td(str(r[4] or "")[:60]),
        ]) for r in rows])],
        bordered=True, size="sm", responsive=True, hover=True,
    )
