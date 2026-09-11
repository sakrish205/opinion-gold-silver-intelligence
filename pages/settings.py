"""Page 18: Settings — LLM model selector, refresh intervals, thresholds."""
import sqlite3
import dash
from dash import callback, dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

from config import DB_PATH
from llm.llm_registry import LLM_MODELS, DEFAULT_MODEL_KEY, get_model

dash.register_page(__name__, path="/settings", name="Settings")

layout = html.Div([
    html.H4("Settings", className="mb-3"),
    dbc.Card(dbc.CardBody([
        html.H6("LLM Model"),
        html.P("Active model used for news analysis. Scores are always determined by market data, not LLM.",
               className="text-muted small"),
        dbc.Row([
            dbc.Col(dcc.Dropdown(
                id="st-llm-model",
                options=[{"label": f"{k} ({v.ollama_name}, {v.size_gb}GB, {v.license})", "value": k}
                         for k, v in LLM_MODELS.items()],
                value=DEFAULT_MODEL_KEY, clearable=False), md=6),
            dbc.Col(dbc.Button("Save LLM Model", id="st-save-llm", color="warning"), md=2),
        ], className="g-2 mb-3"),
        html.Div(id="st-llm-model-spec"),
        html.Div(id="st-save-llm-result", className="text-muted small mt-2"),
    ]), className="mb-4"),

    dbc.Card(dbc.CardBody([
        html.H6("Thresholds"),
        dbc.Row([
            dbc.Col([
                html.Label("XAU/INR Cross-Check Threshold (%)", className="form-label small"),
                dcc.Input(id="st-xau-threshold", type="number", value=0.5, step=0.1,
                          className="form-control"),
            ], md=4),
            dbc.Col([
                html.Label("Price Refresh Interval (seconds)", className="form-label small"),
                dcc.Input(id="st-refresh-prices", type="number", value=60, step=5,
                          className="form-control"),
            ], md=4),
            dbc.Col([
                html.Label("FX Refresh Interval (seconds)", className="form-label small"),
                dcc.Input(id="st-refresh-fx", type="number", value=300, step=30,
                          className="form-control"),
            ], md=4),
        ], className="g-2 mb-3"),
        dbc.Button("Save Thresholds", id="st-save-thresholds", color="secondary"),
        html.Div(id="st-save-thresholds-result", className="text-muted small mt-2"),
        html.P("Note: saved values take effect on next app restart.", className="text-muted small mt-1"),
    ]), className="mb-4"),

    dbc.Card(dbc.CardBody([
        html.H6("Active LLM Model (from DB)", className="mb-2"),
        html.Div(id="st-active-model-display"),
        dcc.Interval(id="st-interval", interval=10_000, n_intervals=0),
    ])),
])


@callback(Output("st-llm-model-spec", "children"), Input("st-llm-model", "value"))
def show_spec(model_key):
    spec = get_model(model_key)
    if not spec:
        return html.P("Unknown model.", className="text-warning")
    return dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.Small("Size"), html.H6(f"{spec.size_gb} GB")])), md=2),
        dbc.Col(dbc.Card(dbc.CardBody([html.Small("Min RAM"), html.H6(f"{spec.min_ram_gb} GB")])), md=2),
        dbc.Col(dbc.Card(dbc.CardBody([html.Small("License"), html.H6(spec.license)])), md=2),
        dbc.Col(dbc.Card(dbc.CardBody([html.Small("CPU Capable"), html.H6("Yes" if spec.cpu_capable else "No")])), md=2),
        dbc.Col(dbc.Card(dbc.CardBody([html.Small("Finance Reasoning"), html.H6(spec.finance_reasoning)])), md=2),
    ])


@callback(
    Output("st-save-llm-result", "children"),
    Input("st-save-llm", "n_clicks"),
    State("st-llm-model", "value"),
    prevent_initial_call=True,
)
def save_llm_model(n_clicks, model_key):
    if not model_key:
        return "Select a model."
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT OR REPLACE INTO _settings (key, value) VALUES ('llm_model', ?)", (model_key,))
        return f"Active LLM model saved: {model_key}"
    except Exception as e:
        return f"Error: {e}"


@callback(
    Output("st-save-thresholds-result", "children"),
    Input("st-save-thresholds", "n_clicks"),
    State("st-xau-threshold", "value"),
    State("st-refresh-prices", "value"),
    State("st-refresh-fx", "value"),
    prevent_initial_call=True,
)
def save_thresholds(n_clicks, xau_threshold, refresh_prices, refresh_fx):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _settings (key TEXT PRIMARY KEY, value TEXT)")
            for k, v in [("xau_inr_cross_check_threshold", xau_threshold),
                          ("refresh_prices_seconds", refresh_prices),
                          ("refresh_fx_seconds", refresh_fx)]:
                if v is not None:
                    conn.execute("INSERT OR REPLACE INTO _settings (key, value) VALUES (?, ?)",
                                 (k, str(v)))
        return "Thresholds saved (take effect on restart)."
    except Exception as e:
        return f"Error: {e}"


@callback(Output("st-active-model-display", "children"), Input("st-interval", "n_intervals"))
def refresh_active_model(_n):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _settings (key TEXT PRIMARY KEY, value TEXT)")
            row = conn.execute("SELECT value FROM _settings WHERE key='llm_model'").fetchone()
            active = row[0] if row else DEFAULT_MODEL_KEY
    except Exception:
        active = DEFAULT_MODEL_KEY
    spec = get_model(active)
    ollama_name = spec.ollama_name if spec else "unknown"
    return html.P(f"Active: {active} ({ollama_name})")
