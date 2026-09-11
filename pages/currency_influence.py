"""Page 14: Currency Influence — FX correlation heatmap and feature importance."""
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from data.providers.metals_futures import MetalsFuturesProvider
from data.providers.forex import get_fx_history
from config import FX_PAIRS

dash.register_page(__name__, path="/currency-influence", name="Currency Influence")

_futures = MetalsFuturesProvider()

layout = html.Div([
    html.H4("Currency Influence", className="mb-3"),
    dbc.Row([
        dbc.Col(dcc.Dropdown(id="ci-asset",
            options=[{"label": "Gold (XAU)", "value": "XAU"}, {"label": "Silver (XAG)", "value": "XAG"}],
            value="XAU", clearable=False), md=3),
        dbc.Col(dcc.Dropdown(id="ci-window",
            options=[{"label": f"{h}h", "value": h} for h in [24, 48, 168, 720]],
            value=168, clearable=False), md=2),
    ], className="mb-3"),
    dcc.Loading(dcc.Graph(id="ci-heatmap")),
    html.P(
        "Pearson correlation between metal futures price and FX pairs over selected window. "
        "FX data: yfinance hourly (LIVE) or open.er-api.com daily (STALE).",
        className="text-muted small mt-2",
    ),
])


@callback(
    Output("ci-heatmap", "figure"),
    Input("ci-asset", "value"),
    Input("ci-window", "value"),
)
def update_heatmap(asset, window):
    metal_result = _futures.fetch(asset=asset)
    if metal_result.status not in ("LIVE", "STALE") or metal_result.value is None:
        return go.Figure().update_layout(title=f"{asset} data {metal_result.status}", template="plotly_dark")

    metal_series = metal_result.value["Close"].rename(f"{asset}/USD_FUTURES")

    frames = [metal_series]
    for p in FX_PAIRS:
        r = get_fx_history(p)
        if r.status in ("LIVE", "STALE") and r.value is not None:
            frames.append(r.value["rate"].rename(p.pair))

    if len(frames) < 2:
        return go.Figure().update_layout(title="Insufficient FX data", template="plotly_dark")

    combined = pd.concat(frames, axis=1).dropna()
    if len(combined) > window:
        combined = combined.iloc[-window:]

    corr = combined.corr()
    fig = px.imshow(
        corr,
        text_auto=".2f",
        title=f"{asset} FX Correlation | Last {window}h",
        color_continuous_scale="RdBu",
        zmin=-1, zmax=1,
        template="plotly_dark",
    )
    return fig
