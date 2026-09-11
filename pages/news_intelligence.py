"""Page 10: News Intelligence — LLM pipeline output, event log."""
import sqlite3
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc

from config import DB_PATH
from data.providers.news import get_news
from llm.ollama_client import analyse_news, is_online
from db import ops

dash.register_page(__name__, path="/news", name="News Intelligence")

layout = html.Div([
    html.H4("News Intelligence", className="mb-3"),
    dcc.Interval(id="news-interval", interval=300_000, n_intervals=0),
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Small("Ollama LLM", className="text-muted"),
            html.Div(id="news-ollama-status"),
        ])), md=3),
        dbc.Col(dbc.Button("Fetch & Analyse", id="news-run-btn", color="warning"), md=2),
    ], className="mb-3"),
    html.Div(id="news-run-result", className="text-muted small mb-3"),
    html.H5("Event Log", className="mb-2"),
    html.Div(id="news-event-log"),
])


@callback(Output("news-ollama-status", "children"), Input("news-interval", "n_intervals"))
def refresh_ollama_status(_n):
    online = is_online()
    return dbc.Badge("ONLINE" if online else "OFFLINE",
                     color="success" if online else "danger")


@callback(
    Output("news-run-result", "children"),
    Input("news-run-btn", "n_clicks"),
    prevent_initial_call=True,
)
def fetch_and_analyse(n_clicks):
    items = get_news()
    if not items:
        return "No news from verified sources. Add sources to data/providers/news.py::VERIFIED_SOURCES."

    headlines = [i.get("headline", "") for i in items[:20]]
    analysis = analyse_news(headlines)

    saved = 0
    for item in items:
        if ops.news_hash_exists(item.get("content_hash", "")):
            continue
        ops.insert_news_event({
            "news_id": item.get("news_id"),
            "published_at": item.get("published_at"),
            "fetched_at": item.get("fetched_at"),
            "source": item.get("source"),
            "source_url": item.get("source_url"),
            "headline": item.get("headline"),
            "content_hash": item.get("content_hash"),
            "status": "ANALYSED" if isinstance(analysis, dict) else "RAW",
            "event": analysis.get("event") if isinstance(analysis, dict) else None,
            "direction": analysis.get("direction") if isinstance(analysis, dict) else None,
            "impact": analysis.get("impact") if isinstance(analysis, dict) else None,
            "confidence": analysis.get("confidence") if isinstance(analysis, dict) else None,
            "asset": analysis.get("asset") if isinstance(analysis, dict) else None,
        })
        saved += 1

    return f"Fetched {len(items)} items, saved {saved} new. LLM analysis: {analysis}"


@callback(Output("news-event-log", "children"), Input("news-interval", "n_intervals"),
          Input("news-run-btn", "n_clicks"))
def refresh_event_log(_n, _btn):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """SELECT published_at, source, headline, asset, direction,
                          impact, confidence, status
                   FROM news_events
                   ORDER BY fetched_at DESC LIMIT 100"""
            ).fetchall()
    except Exception:
        rows = []

    if not rows:
        return html.P("No news events recorded. Add verified sources and click Fetch & Analyse.",
                      className="text-muted")

    def dir_badge(d):
        colors = {"UP": "success", "DOWN": "danger", "NEUTRAL": "secondary", "UNCLEAR": "secondary"}
        return dbc.Badge(d or "—", color=colors.get(d, "secondary"))

    table = dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in
                             ["Published", "Source", "Headline", "Asset", "Direction", "Impact", "Conf", "Status"]]))]
        + [html.Tbody([
            html.Tr([
                html.Td(str(r[0] or "—")[:16]),
                html.Td(str(r[1])),
                html.Td(str(r[2])[:80]),
                html.Td(str(r[3] or "—")),
                html.Td(dir_badge(r[4])),
                html.Td(str(r[5] or "—")),
                html.Td(f"{r[6]:.2f}" if r[6] else "—"),
                html.Td(str(r[7])),
            ]) for r in rows
        ])],
        bordered=True, size="sm", responsive=True,
    )
    return table
