"""Page 17: System Health — source log, Ollama ping, DB table sizes."""
import sqlite3
import os
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import pandas as pd

from config import DB_PATH
from llm.ollama_client import is_online

dash.register_page(__name__, path="/system-health", name="System Health")

layout = html.Div([
    html.H4("System Health", className="mb-3"),
    dcc.Interval(id="sh-interval", interval=30_000, n_intervals=0),
    dbc.Row([
        dbc.Col(html.Div(id="sh-ollama-card"), md=3),
        dbc.Col(html.Div(id="sh-db-size-card"), md=3),
    ], className="mb-4"),
    html.H5("Table Row Counts", className="mb-2"),
    html.Div(id="sh-table-counts"),
    html.H5("Recent Data Source Log", className="mt-4 mb-2"),
    html.Div(id="sh-source-log"),
])


@callback(
    Output("sh-ollama-card", "children"),
    Output("sh-db-size-card", "children"),
    Output("sh-table-counts", "children"),
    Output("sh-source-log", "children"),
    Input("sh-interval", "n_intervals"),
)
def refresh(_n):
    # Ollama card
    online = is_online()
    ollama_card = dbc.Card(dbc.CardBody([
        html.Small("Ollama LLM", className="text-muted"),
        html.Br(),
        dbc.Badge("ONLINE" if online else "OFFLINE", color="success" if online else "danger"),
        html.Small(" http://localhost:11434", className="text-muted ms-1"),
    ]))

    # DB size card
    try:
        db_size_kb = os.path.getsize(DB_PATH) / 1024
        size_str = f"{db_size_kb:.1f} KB"
    except Exception:
        size_str = "unavailable"
    db_card = dbc.Card(dbc.CardBody([
        html.Small("opinion.db", className="text-muted"),
        html.Br(),
        html.H5(size_str),
    ]))

    # Table counts
    tables = [
        "feature_snapshots", "model_registry", "forecast_history", "forecast_outcomes",
        "human_verification", "backtest_runs", "backtest_results",
        "data_source_log", "decision_history", "news_events", "data_quality_alerts",
    ]
    count_rows = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            for t in tables:
                try:
                    n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except Exception:
                    n = "—"
                count_rows.append(html.Tr([html.Td(t), html.Td(str(n))]))
    except Exception:
        count_rows = [html.Tr([html.Td("DB error"), html.Td("")])]

    counts_table = dbc.Table(
        [html.Thead(html.Tr([html.Th("Table"), html.Th("Rows")]))]
        + [html.Tbody(count_rows)],
        bordered=True, size="sm", style={"maxWidth": "400px"},
    )

    # Source log
    try:
        with sqlite3.connect(DB_PATH) as conn:
            log_rows = conn.execute(
                """SELECT logged_at, source, data_type, http_status, latency_ms, ok, quality, error_message
                   FROM data_source_log ORDER BY logged_at DESC LIMIT 50"""
            ).fetchall()
    except Exception:
        log_rows = []

    if not log_rows:
        log_table = html.P("No source log entries yet.", className="text-muted")
    else:
        log_table = dbc.Table(
            [html.Thead(html.Tr([html.Th(c) for c in
                                 ["Logged At", "Source", "Type", "HTTP", "Latency ms",
                                  "OK", "Quality", "Error"]]))]
            + [html.Tbody([
                html.Tr([
                    html.Td(str(r[0] or "")[:16]),
                    html.Td(str(r[1])),
                    html.Td(str(r[2])),
                    html.Td(str(r[3] or "—")),
                    html.Td(str(r[4] or "—")),
                    html.Td(dbc.Badge("✓", color="success") if r[5] else dbc.Badge("✗", color="danger")),
                    html.Td(str(r[6])),
                    html.Td(str(r[7] or "")[:60]),
                ]) for r in log_rows
            ])],
            bordered=True, size="sm", responsive=True,
        )

    return ollama_card, db_card, counts_table, log_table
