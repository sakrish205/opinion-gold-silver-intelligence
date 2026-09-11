"""Page 1: Overview — INR-first prices, FX table, quality badges."""
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import pandas as pd

from config import FX_PAIRS, REFRESH_PRICES_MS
from data.providers.metals_futures import MetalsFuturesProvider
from data.providers.metals_spot import get_spot_price
from data.providers.forex import get_all_fx_latest

dash.register_page(__name__, path="/", name="Overview")

_futures = MetalsFuturesProvider()

BADGE = {
    "LIVE":        ("success", "LIVE"),
    "STALE":       ("warning", "STALE"),
    "UNAVAILABLE": ("secondary", "UNAVAILABLE"),
    "ERROR":       ("danger", "ERROR"),
}


def _quality_badge(status: str) -> dbc.Badge:
    color, label = BADGE.get(status, ("secondary", status))
    return dbc.Badge(label, color=color, className="ms-2")


def _type_badge(data_type: str) -> dbc.Badge:
    colors = {"FUTURES": "warning", "SPOT": "info", "DERIVED": "primary", "UNAVAILABLE": "secondary"}
    return dbc.Badge(data_type, color=colors.get(data_type, "secondary"), className="ms-1")


layout = html.Div([
    html.H4("Overview", className="mb-3"),
    dcc.Interval(id="overview-interval", interval=REFRESH_PRICES_MS, n_intervals=0),
    dbc.Row([
        dbc.Col(dbc.Card(id="xau-card", className="mb-3"), md=6),
        dbc.Col(dbc.Card(id="xag-card", className="mb-3"), md=6),
    ]),
    html.H5("FX Rates (→ INR)", className="mt-2 mb-2"),
    html.Div(id="fx-table"),
    html.Div(id="quality-note", className="text-muted small mt-3"),
])


def _price_card(asset: str, label: str, futures_result, fx_result) -> list:
    futures_price = None
    inr_price = None
    usd_inr = None

    if futures_result.status in ("LIVE", "STALE") and futures_result.value:
        v = futures_result.value
        futures_price = v.get("price") if isinstance(v, dict) else None

    fx_usd = fx_result.get("USD/INR") if fx_result else None
    if fx_usd and fx_usd.status in ("LIVE", "STALE") and fx_usd.value:
        usd_inr = fx_usd.value.get("rate")

    if futures_price and usd_inr:
        inr_price = futures_price * usd_inr

    return dbc.CardBody([
        html.H5([label, _type_badge("FUTURES"), _quality_badge(futures_result.status)]),
        html.Div([
            html.Span("₹ ", className="text-muted"),
            html.Span(
                f"{inr_price:,.2f}" if inr_price else "UNAVAILABLE",
                className="fs-3 fw-bold text-warning" if inr_price else "fs-3 text-secondary",
            ),
            _type_badge("DERIVED") if inr_price else html.Span(),
        ], className="mb-1"),
        html.Div([
            html.Span("USD ", className="text-muted small"),
            html.Span(
                f"{futures_price:,.2f}" if futures_price else "UNAVAILABLE",
                className="small",
            ),
            _type_badge("FUTURES") if futures_price else html.Span(),
        ]),
        html.Small(
            f"Source: {futures_result.source} | {futures_result.fetched_at[:19]} UTC",
            className="text-muted",
        ),
    ])


@callback(
    Output("xau-card", "children"),
    Output("xag-card", "children"),
    Output("fx-table", "children"),
    Output("quality-note", "children"),
    Input("overview-interval", "n_intervals"),
)
def refresh(_n):
    xau_r = _futures.fetch_latest(asset="XAU")
    xag_r = _futures.fetch_latest(asset="XAG")
    fx_all = get_all_fx_latest()

    xau_card = _price_card("XAU", "Gold (XAU)", xau_r, fx_all)
    xag_card = _price_card("XAG", "Silver (XAG)", xag_r, fx_all)

    # FX table
    rows = []
    for pair_obj in FX_PAIRS:
        r = fx_all.get(pair_obj.pair)
        if r and r.status in ("LIVE", "STALE") and r.value:
            rate = r.value.get("rate")
            res = r.value.get("resolution", "?")
            rows.append(html.Tr([
                html.Td(pair_obj.pair),
                html.Td(f"{rate:.4f}" if rate else "—"),
                html.Td(_quality_badge(r.status)),
                html.Td(html.Small(res, className="text-muted")),
                html.Td(html.Small(r.source, className="text-muted")),
            ]))
        else:
            status = r.status if r else "UNAVAILABLE"
            rows.append(html.Tr([
                html.Td(pair_obj.pair),
                html.Td("UNAVAILABLE"),
                html.Td(_quality_badge(status)),
                html.Td("—"), html.Td("—"),
            ]))

    fx_table = dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in ["Pair", "Rate", "Quality", "Resolution", "Source"]]))]
        + [html.Tbody(rows)],
        bordered=True, hover=True, size="sm", className="mt-2",
    )

    note = (
        "⚠ GC=F and SI=F are COMEX futures contracts — not spot prices. "
        "INR values are DERIVED (futures × USD/INR). "
        "XAU/USD Spot: UNAVAILABLE (no verified free source)."
    )
    return xau_card, xag_card, fx_table, note
