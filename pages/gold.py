"""Page 2: Gold — XAU hourly OHLCV, FUTURES label, technicals."""
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from config import REFRESH_PRICES_MS
from data.providers.metals_futures import MetalsFuturesProvider
import data.cache as cache

dash.register_page(__name__, path="/gold", name="Gold")

_futures = MetalsFuturesProvider()

layout = html.Div([
    html.H4([
        "Gold (XAU) ",
        dbc.Badge("FUTURES — GC=F (COMEX)", color="warning", className="ms-2 fs-6"),
        dbc.Badge("NOT SPOT", color="danger", className="ms-1 fs-6"),
    ], className="mb-3"),
    dcc.Interval(id="gold-interval", interval=REFRESH_PRICES_MS * 5, n_intervals=0),
    dcc.Loading(html.Div(id="gold-chart")),
    html.Div(id="gold-technicals", className="mt-3"),
])


@callback(
    Output("gold-chart", "children"),
    Output("gold-technicals", "children"),
    Input("gold-interval", "n_intervals"),
)
def refresh(_n):
    cached = cache.get("gold_history")
    if cached is None:
        result = _futures.fetch(asset="XAU")
        if result.status not in ("LIVE", "STALE") or result.value is None:
            return html.P(f"Gold data: {result.status} — {result.error}", className="text-warning"), html.Div()
        df = result.value
        cache.set("gold_history", df, ttl_seconds=300)
    else:
        df = cached

    fig = go.Figure(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        name="XAU/USD Futures",
    ))
    fig.update_layout(
        title="XAU/USD — Gold Futures (GC=F) | Hourly",
        yaxis_title="Price (USD) — FUTURES",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=500,
    )
    fig.add_annotation(
        text="⚠ FUTURES price (GC=F). Not spot. INR value is DERIVED.",
        xref="paper", yref="paper", x=0, y=1.08,
        showarrow=False, font=dict(color="orange", size=11),
    )

    last = df["Close"].iloc[-1]
    prev = df["Close"].iloc[-2] if len(df) > 1 else last
    chg = (last - prev) / prev * 100
    ma20 = df["Close"].rolling(20).mean().iloc[-1]
    ma50 = df["Close"].rolling(50).mean().iloc[-1]

    technicals = dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.Small("Last (USD, FUTURES)"), html.H5(f"{last:,.2f}")])), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.Small("Change (1h)"), html.H5(f"{chg:+.2f}%",
            className="text-success" if chg >= 0 else "text-danger")])), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.Small("MA-20h"), html.H5(f"{ma20:,.2f}")])), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.Small("MA-50h"), html.H5(f"{ma50:,.2f}")])), md=3),
    ])

    return dcc.Graph(figure=fig, config={"scrollZoom": True}), technicals
