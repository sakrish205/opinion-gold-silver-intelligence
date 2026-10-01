"""Dashboard — Gold & Silver Market Intelligence (primary view)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

from config import FX_PAIRS, REFRESH_PRICES_MS, DB_PATH
from data.providers.metals_futures import MetalsFuturesProvider
from data.providers.forex import get_all_fx_latest, get_fx_history
import data.cache as cache

dash.register_page(__name__, path="/", name="Dashboard")

_futures = MetalsFuturesProvider()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _status_dot(ok: bool) -> html.Span:
    return html.Span("●", style={"color": "#2ecc71" if ok else "#95a5a6"}, className="me-1")


def _filter_df(df: pd.DataFrame, range_val: str) -> pd.DataFrame:
    delta = {
        "1D": pd.Timedelta("1D"),
        "5D": pd.Timedelta("5D"),
        "1M": pd.Timedelta("30D"),
        "3M": pd.Timedelta("90D"),
        "6M": pd.Timedelta("180D"),
        "1Y": pd.Timedelta("365D"),
    }.get(range_val, pd.Timedelta("30D"))
    cutoff = df.index[-1] - delta
    return df[df.index >= cutoff]


def _fetch_history(asset: str) -> pd.DataFrame | None:
    key = f"dash_{asset}_hist"
    df = cache.get(key)
    if df is None:
        r = _futures.fetch(asset=asset)
        if r.status not in ("LIVE", "STALE") or r.value is None:
            return None
        df = r.value
        cache.set(key, df, ttl_seconds=300)
    return df


def _empty_fig(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, xref="paper", yref="paper",
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(size=14, color="#95a5a6"))
    fig.update_layout(template="plotly_white", margin=dict(t=20, b=20),
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


# ── Layout ────────────────────────────────────────────────────────────────────

_RANGE_OPTIONS = ["1D", "5D", "1M", "3M", "6M", "1Y"]
_ASSET_OPTIONS = [
    {"label": "Gold", "value": "XAU"},
    {"label": "Silver", "value": "XAG"},
    {"label": "G/S Ratio", "value": "ratio"},
    {"label": "USD/INR", "value": "fx"},
]
_FC_HORIZON_OPTIONS = [
    {"label": h, "value": h} for h in ["1H", "5H", "12H", "24H", "48H"]
]

layout = html.Div([
    dcc.Interval(id="dash-interval", interval=REFRESH_PRICES_MS, n_intervals=0),

    # ── Header ────────────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            html.H5("Gold & Silver Market Intelligence",
                    className="mb-0 fw-bold", style={"color": "#2C3E50"}),
            html.Small("GC=F / SI=F — COMEX Futures · NOT spot prices",
                       className="text-muted"),
        ], md=8),
        dbc.Col(html.Div(id="dash-header-status", className="text-end pt-1"), md=4),
    ], className="mb-3 align-items-center"),

    # ── Price cards ───────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col(dbc.Card(id="dash-gold-card", className="shadow-sm border-0"), md=6),
        dbc.Col(dbc.Card(id="dash-silver-card", className="shadow-sm border-0"), md=6),
    ], className="mb-4"),

    # ── Main market chart ─────────────────────────────────────────────────────
    dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col(html.Span("Market Chart", className="fw-semibold"), md="auto"),
                dbc.Col(
                    dbc.RadioItems(
                        id="dash-asset-radio",
                        options=_ASSET_OPTIONS,
                        value="XAU",
                        inline=True,
                        input_class_name="btn-check",
                        label_class_name="btn btn-sm btn-outline-secondary",
                        label_checked_class_name="active",
                    ), md="auto"),
                dbc.Col(
                    dbc.RadioItems(
                        id="dash-range-radio",
                        options=[{"label": r, "value": r} for r in _RANGE_OPTIONS],
                        value="1M",
                        inline=True,
                        input_class_name="btn-check",
                        label_class_name="btn btn-sm btn-outline-secondary",
                        label_checked_class_name="active",
                    ), md="auto"),
            ], className="g-2 mb-3 align-items-center flex-wrap"),
            dcc.Loading(dcc.Graph(id="dash-main-chart", style={"height": "420px"},
                                  config={"scrollZoom": True, "displayModeBar": True,
                                          "responsive": True})),
        ])
    ], className="shadow-sm border-0 mb-4"),

    # ── Indexed comparison ────────────────────────────────────────────────────
    dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col(html.Span("Gold vs Silver — Indexed Performance",
                                  className="fw-semibold"), md="auto"),
                dbc.Col(html.Small("Both indexed to 100 at period start. Relative movement only.",
                                   className="text-muted"), md="auto"),
            ], className="g-2 mb-3 align-items-center"),
            dcc.Loading(dcc.Graph(id="dash-comparison-chart", style={"height": "280px"},
                                  config={"scrollZoom": True, "responsive": True})),
        ])
    ], className="shadow-sm border-0 mb-4"),

    # ── Forecast ──────────────────────────────────────────────────────────────
    dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col(html.Span("Forecast", className="fw-semibold"), md="auto"),
                dbc.Col(dcc.Dropdown(
                    id="dash-fc-asset",
                    options=[{"label": "Gold (XAU)", "value": "XAU"},
                             {"label": "Silver (XAG)", "value": "XAG"}],
                    value="XAU", clearable=False,
                    style={"width": "160px", "fontSize": "0.85rem"},
                ), md="auto"),
                dbc.Col(
                    dbc.RadioItems(
                        id="dash-fc-horizon",
                        options=_FC_HORIZON_OPTIONS,
                        value="1H",
                        inline=True,
                        input_class_name="btn-check",
                        label_class_name="btn btn-sm btn-outline-secondary",
                        label_checked_class_name="active",
                    ), md="auto"),
            ], className="g-2 mb-3 align-items-center flex-wrap"),
            dbc.Row([
                dbc.Col(dcc.Loading(
                    dcc.Graph(id="dash-fc-chart", style={"height": "280px"},
                              config={"responsive": True})), md=8),
                dbc.Col(html.Div(id="dash-fc-metrics",
                                 className="small text-muted pt-3"), md=4),
            ]),
        ])
    ], className="shadow-sm border-0 mb-4"),

    # ── Market Drivers + Metrics ──────────────────────────────────────────────
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardBody([
                html.Span("Market Drivers", className="fw-semibold d-block mb-3"),
                html.Div(id="dash-drivers"),
            ])
        ], className="shadow-sm border-0"), md=6),
        dbc.Col(dbc.Card([
            dbc.CardBody([
                html.Span("Market Metrics", className="fw-semibold d-block mb-3"),
                html.Div(id="dash-metrics"),
            ])
        ], className="shadow-sm border-0"), md=6),
    ], className="mb-4"),

    # ── News + FinBERT ────────────────────────────────────────────────────────
    dbc.Card([
        dbc.CardBody([
            html.Span("News & Sentiment", className="fw-semibold d-block mb-3"),
            dbc.Row([
                dbc.Col(dcc.Loading(
                    dcc.Graph(id="dash-sentiment-chart", style={"height": "200px"},
                              config={"responsive": True})), md=5),
                dbc.Col(html.Div(id="dash-news-list"), md=7),
            ]),
        ])
    ], className="shadow-sm border-0 mb-4"),

    # ── System status strip ───────────────────────────────────────────────────
    dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col(html.Div(id="dash-sys-strip"), md=8),
                dbc.Col(html.Small(id="dash-sys-updated", className="text-muted text-end"), md=4),
            ], className="align-items-center"),
        ], className="py-2")
    ], className="border-0 bg-light mb-2"),

], style={"maxWidth": "1400px"})


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("dash-gold-card", "children"),
    Output("dash-silver-card", "children"),
    Output("dash-header-status", "children"),
    Input("dash-interval", "n_intervals"),
)
def refresh_price_cards(_n):
    xau_r = _futures.fetch_latest("XAU")
    xag_r = _futures.fetch_latest("XAG")
    fx_all = get_all_fx_latest()
    usd_inr_r = fx_all.get("USD/INR")
    usd_inr = usd_inr_r.value.get("rate") if usd_inr_r and usd_inr_r.value else None

    # Full history for change calc
    xau_hist = _fetch_history("XAU")
    xag_hist = _fetch_history("XAG")

    def _change(hist):
        if hist is None or len(hist) < 2:
            return None, None
        last = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2]
        return last - prev, (last - prev) / prev * 100

    xau_chg, xau_pct = _change(xau_hist)
    xag_chg, xag_pct = _change(xag_hist)

    def _card(label, ticker, asset_result, hist, chg, pct):
        price = asset_result.value.get("price") if asset_result.value else None
        ts = asset_result.value.get("timestamp", "")[:16] if asset_result.value else ""
        inr = price * usd_inr if (price and usd_inr) else None
        status = asset_result.status

        color_cls = "text-success" if (pct or 0) >= 0 else "text-danger"
        dot_color = {"LIVE": "#2ecc71", "STALE": "#f39c12"}.get(status, "#95a5a6")

        return dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Span(label, className="fw-bold me-2"),
                        dbc.Badge("FUTURES", color="warning", className="me-1 small"),
                        dbc.Badge(ticker, color="secondary", className="small"),
                    ], className="mb-1"),
                    html.Div([
                        html.Span("₹ " if inr else "",
                                  className="text-muted small"),
                        html.Span(
                            f"{inr:,.0f}" if inr else "UNAVAILABLE",
                            className="fs-3 fw-bold" + (" text-warning" if inr else " text-secondary"),
                        ),
                        html.Small(" INR · DERIVED" if inr else "",
                                   className="text-muted ms-2"),
                    ], className="mb-1"),
                    html.Div([
                        html.Small(
                            f"USD {price:,.2f}" if price else "—",
                            className="text-muted me-3",
                        ),
                        html.Span(
                            (f"{chg:+.2f} ({pct:+.2f}%)" if chg is not None else "—"),
                            className=f"small {color_cls}",
                        ),
                    ]),
                ], md=9),
                dbc.Col([
                    html.Span("●", style={"color": dot_color, "fontSize": "1.4rem"}),
                    html.Br(),
                    html.Small(status, className="text-muted"),
                    html.Br(),
                    html.Small(ts or "—", className="text-muted",
                               style={"fontSize": "0.7rem"}),
                ], md=3, className="text-end"),
            ], className="align-items-center"),
        ])

    gold_card = _card("Gold", "GC=F", xau_r, xau_hist, xau_chg, xau_pct)
    silver_card = _card("Silver", "SI=F", xag_r, xag_hist, xag_chg, xag_pct)

    fx_status = usd_inr_r.status if usd_inr_r else "UNAVAILABLE"
    header_status = html.Div([
        html.Small("FX: ", className="text-muted"),
        dbc.Badge(fx_status,
                  color={"LIVE": "success", "STALE": "warning"}.get(fx_status, "secondary"),
                  className="me-2 small"),
        html.Small(datetime.now(timezone.utc).strftime("%H:%M UTC"),
                   className="text-muted"),
    ])
    return gold_card, silver_card, header_status


@callback(
    Output("dash-main-chart", "figure"),
    Input("dash-asset-radio", "value"),
    Input("dash-range-radio", "value"),
    Input("dash-interval", "n_intervals"),
)
def update_main_chart(asset_sel, range_val, _n):
    if asset_sel == "fx":
        usd_inr_pair = next((p for p in FX_PAIRS if p.pair == "USD/INR"), None)
        if not usd_inr_pair:
            return _empty_fig("USD/INR data unavailable")
        r = get_fx_history(usd_inr_pair)
        if r.status not in ("LIVE", "STALE") or r.value is None:
            return _empty_fig(f"USD/INR — {r.status}")
        df_fx = r.value.reset_index()
        df_fx.columns = ["datetime", "rate"]
        df_fx["datetime"] = pd.to_datetime(df_fx["datetime"], utc=True)
        cutoff = df_fx["datetime"].iloc[-1] - _timedelta_for(range_val)
        df_fx = df_fx[df_fx["datetime"] >= cutoff]
        fig = go.Figure(go.Scatter(x=df_fx["datetime"], y=df_fx["rate"],
                                   mode="lines", line=dict(color="#3498db", width=1.5)))
        fig.update_layout(title="USD/INR · Hourly", yaxis_title="INR per USD",
                          template="plotly_white", hovermode="x unified",
                          xaxis_rangeslider_visible=False,
                          margin=dict(t=40, b=20, l=50, r=20))
        return fig

    if asset_sel == "ratio":
        xau_df = _fetch_history("XAU")
        xag_df = _fetch_history("XAG")
        if xau_df is None or xag_df is None:
            return _empty_fig("Gold or Silver data unavailable")
        both = pd.DataFrame({"gold": xau_df["Close"], "silver": xag_df["Close"]}).dropna()
        both = _filter_df(both, range_val)
        ratio = both["gold"] / both["silver"]
        fig = go.Figure(go.Scatter(x=ratio.index, y=ratio.values,
                                   mode="lines", line=dict(color="#9b59b6", width=1.5)))
        fig.update_layout(title="Gold/Silver Ratio", yaxis_title="Ratio",
                          template="plotly_white", hovermode="x unified",
                          xaxis_rangeslider_visible=False,
                          margin=dict(t=40, b=20, l=50, r=20))
        return fig

    # Gold or Silver candlestick
    df = _fetch_history(asset_sel)
    if df is None:
        label = "Gold" if asset_sel == "XAU" else "Silver"
        return _empty_fig(f"{label} data unavailable")
    df = _filter_df(df, range_val)
    ticker = "GC=F" if asset_sel == "XAU" else "SI=F"
    label = "Gold" if asset_sel == "XAU" else "Silver"
    fig = go.Figure(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        increasing_line_color="#2ecc71", decreasing_line_color="#e74c3c",
        name=ticker,
    ))
    fig.update_layout(
        title=f"{label} · {ticker} COMEX Futures · Hourly",
        yaxis_title="USD — FUTURES",
        xaxis_rangeslider_visible=False,
        template="plotly_white", hovermode="x unified",
        margin=dict(t=40, b=20, l=60, r=20),
    )
    return fig


def _timedelta_for(range_val: str) -> pd.Timedelta:
    return {
        "1D": pd.Timedelta("1D"),   "5D": pd.Timedelta("5D"),
        "1M": pd.Timedelta("30D"),  "3M": pd.Timedelta("90D"),
        "6M": pd.Timedelta("180D"), "1Y": pd.Timedelta("365D"),
    }.get(range_val, pd.Timedelta("30D"))


@callback(
    Output("dash-comparison-chart", "figure"),
    Input("dash-range-radio", "value"),
    Input("dash-interval", "n_intervals"),
)
def update_comparison(range_val, _n):
    xau_df = _fetch_history("XAU")
    xag_df = _fetch_history("XAG")
    if xau_df is None or xag_df is None:
        return _empty_fig("Gold or Silver data unavailable")

    both = pd.DataFrame({"Gold": xau_df["Close"], "Silver": xag_df["Close"]}).dropna()
    both = _filter_df(both, range_val)
    if len(both) < 2:
        return _empty_fig("Not enough data for comparison")

    # Index to 100 at first bar in the filtered range
    indexed = both / both.iloc[0] * 100
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=indexed.index, y=indexed["Gold"],
                             mode="lines", name="Gold",
                             line=dict(color="#F39C12", width=2)))
    fig.add_trace(go.Scatter(x=indexed.index, y=indexed["Silver"],
                             mode="lines", name="Silver",
                             line=dict(color="#95a5a6", width=2)))
    fig.add_hline(y=100, line_dash="dot", line_color="rgba(0,0,0,0.2)", line_width=1)
    fig.update_layout(
        yaxis_title="Indexed performance (start = 100)",
        template="plotly_white", hovermode="x unified",
        legend=dict(orientation="h", x=0, y=1.12),
        margin=dict(t=30, b=20, l=50, r=20),
        xaxis_rangeslider_visible=False,
    )
    return fig


@callback(
    Output("dash-fc-chart", "figure"),
    Output("dash-fc-metrics", "children"),
    Input("dash-fc-asset", "value"),
    Input("dash-fc-horizon", "value"),
    Input("dash-interval", "n_intervals"),
)
def update_forecast(asset, horizon, _n):
    # Check if any forecasts exist
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT COUNT(*) FROM forecast_history WHERE asset=? AND horizon_code=?",
                (asset, horizon.lower()),
            ).fetchone()
        has_data = rows[0] > 0 if rows else False
    except Exception:
        has_data = False

    if not has_data:
        df = _fetch_history(asset)
        fig = go.Figure()
        if df is not None and len(df) > 0:
            recent = df.tail(48)
            fig.add_trace(go.Scatter(
                x=recent.index, y=recent["Close"],
                mode="lines", name="Historical",
                line=dict(color="#2c3e50", width=1.5),
            ))
        fig.add_annotation(
            text="Forecast unavailable — model not trained yet",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(size=13, color="#95a5a6"),
        )
        fig.update_layout(
            template="plotly_white", xaxis_rangeslider_visible=False,
            margin=dict(t=20, b=20, l=50, r=20),
        )
        metrics = html.Div([
            _metric_row("Current Price", _current_price(asset)),
            _metric_row("Predicted Price", "—"),
            _metric_row("Expected Return", "—"),
            _metric_row("Model", "Pending"),
            html.Small("Signals available after model validation.",
                       className="text-muted mt-2 d-block"),
        ])
        return fig, metrics

    # If forecasts exist (post Prompt 5), pull and display last forecast
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df_fc = pd.read_sql_query(
                """SELECT forecast_origin, target_timestamp, predicted_price,
                          price_at_forecast, model_id
                   FROM forecast_history WHERE asset=? AND horizon_code=?
                   ORDER BY forecast_origin DESC LIMIT 48""",
                conn, params=(asset, horizon.lower()),
            )
    except Exception:
        df_fc = pd.DataFrame()

    if df_fc.empty:
        return _empty_fig("No forecast data"), html.Div()

    hist_df = _fetch_history(asset)
    fig = go.Figure()
    if hist_df is not None:
        recent = hist_df.tail(48 * 2)
        fig.add_trace(go.Scatter(x=recent.index, y=recent["Close"],
                                 mode="lines", name="Historical",
                                 line=dict(color="#2c3e50", width=1.5)))
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(df_fc["target_timestamp"]), y=df_fc["predicted_price"],
        mode="lines+markers", name="Forecast",
        line=dict(color="#e67e22", dash="dot", width=2),
    ))
    fig.update_layout(template="plotly_white", hovermode="x unified",
                      xaxis_rangeslider_visible=False,
                      margin=dict(t=20, b=20, l=50, r=20))

    last = df_fc.iloc[0]
    metrics = html.Div([
        _metric_row("Current Price", _current_price(asset)),
        _metric_row("Predicted", f"{last['predicted_price']:,.2f}" if last["predicted_price"] else "—"),
        _metric_row("Horizon", horizon),
        _metric_row("Model", str(last["model_id"])[:20]),
    ])
    return fig, metrics


def _current_price(asset: str) -> str:
    df = _fetch_history(asset)
    if df is None or df.empty:
        return "Unavailable"
    return f"USD {df['Close'].iloc[-1]:,.2f}"


def _metric_row(label: str, value: str) -> html.Div:
    return html.Div([
        html.Span(label + ": ", className="text-muted"),
        html.Span(value, className="fw-semibold"),
    ], className="mb-1")


@callback(
    Output("dash-drivers", "children"),
    Output("dash-metrics", "children"),
    Input("dash-interval", "n_intervals"),
)
def update_drivers_metrics(_n):
    fx_all = get_all_fx_latest()
    usd_inr_r = fx_all.get("USD/INR")
    usd_inr = usd_inr_r.value.get("rate") if usd_inr_r and usd_inr_r.value else None

    xau_df = _fetch_history("XAU")
    xag_df = _fetch_history("XAG")

    def _pct_change(df, window=24):
        if df is None or len(df) < window + 1:
            return None
        return (df["Close"].iloc[-1] / df["Close"].iloc[-window] - 1) * 100

    def _vol(df, window=24):
        if df is None or len(df) < window + 1:
            return None
        returns = df["Close"].pct_change().iloc[-window:]
        return returns.std() * 100

    def _ratio():
        if xau_df is None or xag_df is None or xag_df["Close"].iloc[-1] == 0:
            return None
        return xau_df["Close"].iloc[-1] / xag_df["Close"].iloc[-1]

    xau_chg = _pct_change(xau_df, 24)
    xag_chg = _pct_change(xag_df, 24)
    xau_vol = _vol(xau_df, 24)
    ratio = _ratio()

    def _chg_span(v):
        if v is None:
            return html.Span("—", className="text-muted")
        cls = "text-success" if v >= 0 else "text-danger"
        return html.Span(f"{v:+.2f}%", className=cls + " fw-semibold")

    def _fmt(v, fmt=".2f", suffix=""):
        return html.Span(f"{v:{fmt}}{suffix}", className="fw-semibold") if v is not None else html.Span("—", className="text-muted")

    drivers = html.Table([
        html.Tbody([
            html.Tr([html.Td("USD/INR", className="text-muted pe-3"),
                     html.Td(_fmt(usd_inr, ".4f"))]),
            html.Tr([html.Td("Gold 24h Return", className="text-muted pe-3"),
                     html.Td(_chg_span(xau_chg))]),
            html.Tr([html.Td("Silver 24h Return", className="text-muted pe-3"),
                     html.Td(_chg_span(xag_chg))]),
            html.Tr([html.Td("Gold Volatility (24h)", className="text-muted pe-3"),
                     html.Td(_fmt(xau_vol, ".3f", "%") if xau_vol else html.Span("—", className="text-muted"))]),
            html.Tr([html.Td("News Sentiment", className="text-muted pe-3"),
                     html.Td(html.Span("No data", className="text-muted"))]),
        ])
    ], className="table table-sm mb-0")

    metrics_items = [
        ("Gold/Silver Ratio", _fmt(ratio, ".1f") if ratio else html.Span("—", className="text-muted")),
        ("Silver Volatility (24h)", _fmt(_vol(xag_df, 24), ".3f", "%") if _vol(xag_df, 24) else html.Span("—", className="text-muted")),
        ("Gold (24h Return)", _chg_span(xau_chg)),
        ("Silver (24h Return)", _chg_span(xag_chg)),
    ]
    metrics = html.Table([
        html.Tbody([
            html.Tr([html.Td(lbl, className="text-muted pe-3"), html.Td(val)])
            for lbl, val in metrics_items
        ])
    ], className="table table-sm mb-0")

    return drivers, metrics


@callback(
    Output("dash-sentiment-chart", "figure"),
    Output("dash-news-list", "children"),
    Input("dash-interval", "n_intervals"),
)
def update_news(_n):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """SELECT published_at, source, headline, asset,
                          direction, sentiment_score, status
                   FROM news_events
                   ORDER BY published_at DESC LIMIT 20"""
            ).fetchall()
            sent_rows = conn.execute(
                """SELECT cached_at, positive_prob, negative_prob, neutral_prob
                   FROM finbert_cache
                   ORDER BY cached_at ASC LIMIT 200"""
            ).fetchall()
    except Exception:
        rows, sent_rows = [], []

    # Sentiment chart
    if sent_rows:
        df_sent = pd.DataFrame(sent_rows, columns=["dt", "pos", "neg", "neu"])
        df_sent["dt"] = pd.to_datetime(df_sent["dt"], utc=True)
        fig_sent = go.Figure()
        fig_sent.add_trace(go.Scatter(x=df_sent["dt"], y=df_sent["pos"],
                                      mode="lines", name="Positive",
                                      fill="tozeroy", line=dict(color="#2ecc71", width=1)))
        fig_sent.add_trace(go.Scatter(x=df_sent["dt"], y=df_sent["neg"],
                                      mode="lines", name="Negative",
                                      fill="tozeroy", line=dict(color="#e74c3c", width=1)))
        fig_sent.update_layout(template="plotly_white", hovermode="x unified",
                                yaxis_title="Probability", legend=dict(orientation="h"),
                                margin=dict(t=10, b=20, l=40, r=10))
    else:
        fig_sent = _empty_fig("No sentiment data yet")

    # News list
    if not rows:
        news_el = dbc.Alert("No news data available. Use the Intelligence page to fetch news.",
                            color="secondary", className="small mt-0")
    else:
        items = []
        for r in rows:
            pub = str(r[0] or "")[:16]
            src = str(r[1] or "")[:20]
            hl = str(r[2] or "")[:100]
            direction = r[4] or ""
            dir_color = {"UP": "success", "DOWN": "danger", "NEUTRAL": "secondary"}.get(direction, "secondary")
            items.append(html.Div([
                html.Div([
                    dbc.Badge(src, color="light", text_color="dark", className="me-1 small"),
                    html.Small(pub, className="text-muted me-2"),
                    dbc.Badge(direction, color=dir_color, className="small") if direction else None,
                ], className="mb-1"),
                html.Div(hl, className="small"),
            ], className="border-bottom pb-2 mb-2"))
        news_el = html.Div(items, style={"maxHeight": "180px", "overflowY": "auto"})

    return fig_sent, news_el


@callback(
    Output("dash-sys-strip", "children"),
    Output("dash-sys-updated", "children"),
    Input("dash-interval", "n_intervals"),
)
def update_system_status(_n):
    # Data: raw_market_data rows
    data_ok = False
    features_ok = False
    finbert_ok = False
    try:
        with sqlite3.connect(DB_PATH) as conn:
            n_raw = conn.execute("SELECT COUNT(*) FROM raw_market_data").fetchone()[0]
            data_ok = n_raw > 0
            n_fc = conn.execute("SELECT COUNT(*) FROM finbert_cache").fetchone()[0]
            finbert_ok = n_fc > 0
    except Exception:
        pass

    # Features: check parquet files exist
    proc_dir = Path(__file__).parent.parent / "data" / "processed"
    features_ok = (proc_dir / "gold_features.parquet").exists() or \
                  (proc_dir / "silver_features.parquet").exists()

    # FinBERT: also check if transformers is importable
    if not finbert_ok:
        try:
            import transformers  # noqa: F401
            finbert_ok = True  # library present even if cache empty
        except ImportError:
            finbert_ok = False

    def _item(label, ok, suffix=""):
        return html.Span([
            html.Span("●", style={"color": "#2ecc71" if ok else "#95a5a6"}, className="me-1"),
            html.Span(label + suffix, className="me-3 small"),
        ])

    strip = html.Div([
        _item("Data", data_ok),
        _item("Features", features_ok),
        _item("FinBERT", finbert_ok),
        _item("Models", False, " (pending)"),
    ])
    updated = f"Updated {datetime.now(timezone.utc).strftime('%H:%M')} UTC"
    return strip, updated
