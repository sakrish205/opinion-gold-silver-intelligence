"""Page 6: Historical Prices — OHLCV explorer."""
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from data.providers.metals_futures import MetalsFuturesProvider
import data.cache as cache

dash.register_page(__name__, path="/historical", name="Historical Prices")

_futures = MetalsFuturesProvider()

layout = html.Div([
    html.H4("Historical Prices", className="mb-3"),
    dbc.Row([
        dbc.Col(dcc.Dropdown(
            id="hist-asset", options=[{"label": "Gold (XAU)", "value": "XAU"},
                                       {"label": "Silver (XAG)", "value": "XAG"}],
            value="XAU", clearable=False), md=3),
        dbc.Col(dcc.Dropdown(
            id="hist-chart-type",
            options=[{"label": "Candlestick", "value": "candle"},
                     {"label": "Line (Close)", "value": "line"}],
            value="candle", clearable=False), md=3),
    ], className="mb-3"),
    dcc.Loading(dcc.Graph(id="hist-chart", style={"height": "600px"})),
    html.P(
        "Data: COMEX futures (GC=F / SI=F) via yfinance. "
        "All prices are FUTURES contracts, not spot. Hourly bars.",
        className="text-muted small mt-2",
    ),
])


@callback(
    Output("hist-chart", "figure"),
    Input("hist-asset", "value"),
    Input("hist-chart-type", "value"),
)
def update_chart(asset, chart_type):
    cache_key = f"hist_{asset}"
    df = cache.get(cache_key)
    if df is None:
        result = _futures.fetch(asset=asset)
        if result.status not in ("LIVE", "STALE") or result.value is None:
            return go.Figure().update_layout(title=f"{asset} — {result.status}", template="plotly_dark")
        df = result.value
        cache.set(cache_key, df, ttl_seconds=300)

    label = "XAU/USD Gold Futures (GC=F)" if asset == "XAU" else "XAG/USD Silver Futures (SI=F)"
    if chart_type == "candle":
        fig = go.Figure(go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"],
        ))
    else:
        fig = go.Figure(go.Scatter(x=df.index, y=df["Close"], mode="lines", name="Close"))

    fig.update_layout(
        title=f"{label} | Hourly | FUTURES",
        yaxis_title="USD — FUTURES",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
    )
    return fig
