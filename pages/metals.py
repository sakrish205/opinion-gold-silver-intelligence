"""Metals page — Gold and Silver in one tabbed view."""
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from config import REFRESH_PRICES_MS
from data.providers.metals_futures import MetalsFuturesProvider
import data.cache as cache

dash.register_page(__name__, path="/metals", name="Metals")

_futures = MetalsFuturesProvider()


def _make_chart(asset):
    key = f"{asset}_history"
    df = cache.get(key)
    if df is None:
        result = _futures.fetch(asset=asset)
        if result.status not in ("LIVE", "STALE") or result.value is None:
            return go.Figure().update_layout(
                title=f"{asset} — {result.status}", template="plotly_white")
        df = result.value
        cache.set(key, df, ttl_seconds=300)

    ticker = "GC=F" if asset == "XAU" else "SI=F"
    name = "Gold" if asset == "XAU" else "Silver"
    fig = go.Figure(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        name=f"{asset}/USD Futures",
        increasing_line_color="#2ecc71",
        decreasing_line_color="#e74c3c",
    ))
    fig.update_layout(
        title=f"{name} ({asset}/USD) — {ticker} COMEX Futures | Hourly",
        yaxis_title="Price (USD) — FUTURES",
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        height=420,
        margin=dict(t=50, b=20),
    )
    fig.add_annotation(
        text=f"⚠ {ticker} is a FUTURES contract — not spot. INR price is DERIVED.",
        xref="paper", yref="paper", x=0, y=1.06,
        showarrow=False, font=dict(color="#e67e22", size=11),
    )
    return fig


def _technicals(df, decimals=2):
    if df is None or df.empty:
        return dbc.Row([])
    last = df["Close"].iloc[-1]
    prev = df["Close"].iloc[-2] if len(df) > 1 else last
    chg = (last - prev) / prev * 100
    ma20 = df["Close"].rolling(20).mean().iloc[-1]
    ma50 = df["Close"].rolling(50).mean().iloc[-1]
    fmt = lambda v: f"{v:,.{decimals}f}"
    return dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Small("Last (USD · FUTURES)", className="text-muted"),
            html.H5(fmt(last), className="mb-0"),
        ]), className="shadow-sm"), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Small("1h Change", className="text-muted"),
            html.H5(f"{chg:+.2f}%", className="mb-0 " + ("text-success" if chg >= 0 else "text-danger")),
        ]), className="shadow-sm"), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Small("MA-20h", className="text-muted"),
            html.H5(fmt(ma20), className="mb-0"),
        ]), className="shadow-sm"), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Small("MA-50h", className="text-muted"),
            html.H5(fmt(ma50), className="mb-0"),
        ]), className="shadow-sm"), md=3),
    ], className="g-2 mt-2")


layout = html.Div([
    html.H4("Metals", className="mb-1"),
    dbc.Stack([
        dbc.Badge("FUTURES — GC=F / SI=F", color="warning", className="me-1"),
        dbc.Badge("NOT SPOT", color="danger"),
    ], direction="horizontal", className="mb-3"),
    dcc.Interval(id="metals-interval", interval=REFRESH_PRICES_MS * 5, n_intervals=0),
    dbc.Tabs([
        dbc.Tab(label="Gold (XAU)", tab_id="XAU"),
        dbc.Tab(label="Silver (XAG)", tab_id="XAG"),
    ], id="metals-tab", active_tab="XAU", className="mb-3"),
    dcc.Loading(html.Div(id="metals-content")),
])


@callback(
    Output("metals-content", "children"),
    Input("metals-tab", "active_tab"),
    Input("metals-interval", "n_intervals"),
)
def refresh(asset, _n):
    decimals = 2 if asset == "XAU" else 3
    key = f"{asset}_history"
    df = cache.get(key)
    if df is None:
        result = _futures.fetch(asset=asset)
        df = result.value if result.status in ("LIVE", "STALE") and result.value is not None else None
        if df is not None:
            cache.set(key, df, ttl_seconds=300)
    return html.Div([
        dcc.Graph(figure=_make_chart(asset), config={"scrollZoom": True}),
        _technicals(df, decimals),
    ])
