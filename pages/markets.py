"""Markets page — International prices, FX/INR rates, Historical OHLCV in tabs."""
import sqlite3
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from config import DB_PATH, FX_PAIRS, REFRESH_FX_MS, REFRESH_PRICES_MS
from data.providers.metals_futures import MetalsFuturesProvider
from data.providers.forex import get_all_fx_latest, get_fx_history
import data.cache as cache

dash.register_page(__name__, path="/markets", name="Markets")

_futures = MetalsFuturesProvider()

layout = html.Div([
    html.H4("Markets", className="mb-3"),
    dcc.Interval(id="mkt-interval", interval=REFRESH_FX_MS, n_intervals=0),
    dbc.Tabs([
        dbc.Tab(label="🌐 International", tab_id="intl"),
        dbc.Tab(label="💱 FX / INR", tab_id="fx"),
        dbc.Tab(label="📉 History", tab_id="hist"),
    ], id="mkt-tabs", active_tab="intl", className="mb-3"),
    html.Div(id="mkt-content"),
])


# ── International ─────────────────────────────────────────────────────────────
def _intl():
    return html.Div([
        html.Div(id="mkt-intl-table"),
        html.P(
            "FUTURES = COMEX contract (GC=F/SI=F). DERIVED = computed via FX conversion. "
            "XAU/USD Spot: UNAVAILABLE.",
            className="text-muted small mt-3",
        ),
    ])


# ── FX / INR ─────────────────────────────────────────────────────────────────
def _fx():
    return html.Div([
        html.Div(id="mkt-fx-cards", className="mb-3"),
        dcc.Dropdown(id="mkt-fx-pair",
                     options=[{"label": p.pair, "value": p.pair} for p in FX_PAIRS],
                     value="USD/INR", clearable=False,
                     style={"maxWidth": "200px", "marginBottom": "12px"}),
        dcc.Loading(dcc.Graph(id="mkt-fx-chart")),
    ])


# ── History ───────────────────────────────────────────────────────────────────
def _hist():
    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Dropdown(id="mkt-hist-asset",
                options=[{"label": "Gold (XAU)", "value": "XAU"},
                         {"label": "Silver (XAG)", "value": "XAG"}],
                value="XAU", clearable=False), md=3),
            dbc.Col(dcc.Dropdown(id="mkt-hist-type",
                options=[{"label": "Candlestick", "value": "candle"},
                         {"label": "Line", "value": "line"}],
                value="candle", clearable=False), md=3),
        ], className="g-2 mb-3"),
        dcc.Loading(dcc.Graph(id="mkt-hist-chart", style={"height": "500px"})),
        html.P("Hourly COMEX futures (GC=F / SI=F). NOT spot prices.",
               className="text-muted small"),
    ])


@callback(Output("mkt-content", "children"), Input("mkt-tabs", "active_tab"))
def render_tab(tab):
    return {"intl": _intl, "fx": _fx, "hist": _hist}[tab]()


# ── International callbacks ───────────────────────────────────────────────────
@callback(Output("mkt-intl-table", "children"), Input("mkt-interval", "n_intervals"),
          Input("mkt-tabs", "active_tab"))
def refresh_intl(_n, tab):
    if tab != "intl":
        return dash.no_update
    xau_r = _futures.fetch_latest("XAU")
    xag_r = _futures.fetch_latest("XAG")
    fx = get_all_fx_latest()
    xau_usd = xau_r.value.get("price") if xau_r.value else None
    xag_usd = xag_r.value.get("price") if xag_r.value else None

    def rate(pair):
        r = fx.get(pair)
        return r.value.get("rate") if r and r.value else None

    usd_inr = rate("USD/INR"); eur_inr = rate("EUR/INR"); cny_inr = rate("CNY/INR")

    def badge(t):
        return dbc.Badge(t, color={"FUTURES": "warning", "DERIVED": "primary",
                                    "UNAVAILABLE": "secondary"}.get(t, "secondary"))
    def fmt(v, d=2): return f"{v:,.{d}f}" if v else "UNAVAILABLE"

    rows_data = [
        ("XAU/USD", fmt(xau_usd), "FUTURES" if xau_usd else "UNAVAILABLE"),
        ("XAU/EUR", fmt(xau_usd / eur_inr * usd_inr if xau_usd and eur_inr and usd_inr else None),
         "DERIVED" if xau_usd and eur_inr and usd_inr else "UNAVAILABLE"),
        ("XAU/CNY", fmt(xau_usd / cny_inr * usd_inr if xau_usd and cny_inr and usd_inr else None),
         "DERIVED" if xau_usd and cny_inr and usd_inr else "UNAVAILABLE"),
        ("XAU/INR", fmt(xau_usd * usd_inr if xau_usd and usd_inr else None),
         "DERIVED" if xau_usd and usd_inr else "UNAVAILABLE"),
        ("XAG/USD", fmt(xag_usd, 3), "FUTURES" if xag_usd else "UNAVAILABLE"),
        ("XAG/EUR", fmt(xag_usd / eur_inr * usd_inr if xag_usd and eur_inr and usd_inr else None, 3),
         "DERIVED" if xag_usd and eur_inr and usd_inr else "UNAVAILABLE"),
        ("XAG/CNY", fmt(xag_usd / cny_inr * usd_inr if xag_usd and cny_inr and usd_inr else None, 3),
         "DERIVED" if xag_usd and cny_inr and usd_inr else "UNAVAILABLE"),
        ("XAG/INR", fmt(xag_usd * usd_inr if xag_usd and usd_inr else None, 3),
         "DERIVED" if xag_usd and usd_inr else "UNAVAILABLE"),
    ]
    return dbc.Table(
        [html.Thead(html.Tr([html.Th("Pair"), html.Th("Price"), html.Th("Type")]))]
        + [html.Tbody([html.Tr([html.Td(p), html.Td(v), html.Td(badge(t))]) for p, v, t in rows_data])],
        bordered=True, hover=True, size="sm",
    )


# ── FX callbacks ──────────────────────────────────────────────────────────────
@callback(Output("mkt-fx-cards", "children"), Input("mkt-interval", "n_intervals"),
          Input("mkt-tabs", "active_tab"))
def fx_cards(_n, tab):
    if tab != "fx":
        return dash.no_update
    fx = get_all_fx_latest()
    cards = []
    for p in FX_PAIRS:
        r = fx.get(p.pair)
        rate_val = r.value.get("rate") if r and r.value else None
        status = r.status if r else "UNAVAILABLE"
        color = {"LIVE": "success", "STALE": "warning"}.get(status, "secondary")
        cards.append(dbc.Col(dbc.Card(dbc.CardBody([
            html.Small(p.pair, className="text-muted"),
            html.H5(f"{rate_val:.4f}" if rate_val else "—", className="mb-1"),
            dbc.Badge(status, color=color),
        ]), className="shadow-sm"), md=2))
    return dbc.Row(cards, className="g-2")


@callback(Output("mkt-fx-chart", "figure"), Input("mkt-fx-pair", "value"),
          Input("mkt-interval", "n_intervals"), Input("mkt-tabs", "active_tab"))
def fx_chart(pair_name, _n, tab):
    if tab != "fx":
        return dash.no_update
    pair_obj = next((p for p in FX_PAIRS if p.pair == pair_name), None)
    if not pair_obj:
        return {}
    result = get_fx_history(pair_obj)
    if result.status not in ("LIVE", "STALE") or result.value is None:
        return px.line(title=f"{pair_name} — {result.status}").update_layout(template="plotly_white")
    df = result.value.reset_index()
    df.columns = ["datetime", "rate"]
    return px.line(df, x="datetime", y="rate", title=f"{pair_name} | Hourly",
                   template="plotly_white")


# ── History callbacks ─────────────────────────────────────────────────────────
@callback(Output("mkt-hist-chart", "figure"), Input("mkt-hist-asset", "value"),
          Input("mkt-hist-type", "value"), Input("mkt-tabs", "active_tab"))
def hist_chart(asset, chart_type, tab):
    if tab != "hist":
        return dash.no_update
    key = f"hist_{asset}"
    df = cache.get(key)
    if df is None:
        result = _futures.fetch(asset=asset)
        if result.status not in ("LIVE", "STALE") or result.value is None:
            return go.Figure().update_layout(title=f"{asset} — {result.status}",
                                             template="plotly_white")
        df = result.value
        cache.set(key, df, ttl_seconds=300)
    label = "XAU/USD Gold Futures (GC=F)" if asset == "XAU" else "XAG/USD Silver Futures (SI=F)"
    if chart_type == "candle":
        fig = go.Figure(go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"],
            increasing_line_color="#2ecc71", decreasing_line_color="#e74c3c",
        ))
    else:
        fig = go.Figure(go.Scatter(x=df.index, y=df["Close"], mode="lines",
                                   line=dict(color="#2c3e50")))
    fig.update_layout(title=f"{label} | Hourly | FUTURES",
                      yaxis_title="USD — FUTURES",
                      xaxis_rangeslider_visible=False, template="plotly_white")
    return fig
