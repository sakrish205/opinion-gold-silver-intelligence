"""Page 4: International Markets — XAU/XAG in USD, EUR, CNY with type labels."""
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc

from config import REFRESH_PRICES_MS, FX_PAIRS
from data.providers.metals_futures import MetalsFuturesProvider
from data.providers.forex import get_all_fx_latest

dash.register_page(__name__, path="/international", name="International Markets")

_futures = MetalsFuturesProvider()

layout = html.Div([
    html.H4("International Markets", className="mb-3"),
    dcc.Interval(id="intl-interval", interval=REFRESH_PRICES_MS, n_intervals=0),
    html.Div(id="intl-table"),
    html.P(
        "All prices derived from COMEX futures (GC=F/SI=F) converted via FX rates. "
        "Type labels: FUTURES = source contract | DERIVED = computed cross price. "
        "XAU/USD Spot: UNAVAILABLE.",
        className="text-muted small mt-3",
    ),
])


@callback(Output("intl-table", "children"), Input("intl-interval", "n_intervals"))
def refresh(_n):
    xau_r = _futures.fetch_latest("XAU")
    xag_r = _futures.fetch_latest("XAG")
    fx = get_all_fx_latest()

    xau_usd = xau_r.value.get("price") if xau_r.value else None
    xag_usd = xag_r.value.get("price") if xag_r.value else None

    # Build FX lookup: base → INR rate
    def fx_rate(pair: str):
        r = fx.get(pair)
        return r.value.get("rate") if r and r.value else None

    usd_inr = fx_rate("USD/INR")
    eur_inr = fx_rate("EUR/INR")
    cny_inr = fx_rate("CNY/INR")

    def derived(usd_price, fx_r):
        return usd_price / fx_r * usd_inr if usd_price and fx_r and usd_inr else None

    def fmt(v, decimals=2):
        return f"{v:,.{decimals}f}" if v is not None else "UNAVAILABLE"

    def type_badge(t):
        c = {"FUTURES": "warning", "DERIVED": "primary", "UNAVAILABLE": "secondary"}
        return dbc.Badge(t, color=c.get(t, "secondary"), className="ms-1 small")

    xau_eur = xau_usd / eur_inr * usd_inr if xau_usd and eur_inr and usd_inr else None
    xau_cny = xau_usd / cny_inr * usd_inr if xau_usd and cny_inr and usd_inr else None
    xau_inr = xau_usd * usd_inr if xau_usd and usd_inr else None
    xag_eur = xag_usd / eur_inr * usd_inr if xag_usd and eur_inr and usd_inr else None
    xag_cny = xag_usd / cny_inr * usd_inr if xag_usd and cny_inr and usd_inr else None
    xag_inr = xag_usd * usd_inr if xag_usd and usd_inr else None

    rows = [
        ("XAU/USD", fmt(xau_usd), "FUTURES" if xau_usd else "UNAVAILABLE"),
        ("XAU/EUR", fmt(xau_eur), "DERIVED" if xau_eur else "UNAVAILABLE"),
        ("XAU/CNY", fmt(xau_cny), "DERIVED" if xau_cny else "UNAVAILABLE"),
        ("XAU/INR", fmt(xau_inr), "DERIVED" if xau_inr else "UNAVAILABLE"),
        ("XAG/USD", fmt(xag_usd, 3), "FUTURES" if xag_usd else "UNAVAILABLE"),
        ("XAG/EUR", fmt(xag_eur, 3), "DERIVED" if xag_eur else "UNAVAILABLE"),
        ("XAG/CNY", fmt(xag_cny, 3), "DERIVED" if xag_cny else "UNAVAILABLE"),
        ("XAG/INR", fmt(xag_inr, 3), "DERIVED" if xag_inr else "UNAVAILABLE"),
    ]

    table = dbc.Table(
        [html.Thead(html.Tr([html.Th("Pair"), html.Th("Price"), html.Th("Type")]))]
        + [html.Tbody([
            html.Tr([html.Td(pair), html.Td(price), html.Td(type_badge(t))])
            for pair, price, t in rows
        ])],
        bordered=True, hover=True, size="sm",
    )
    return table
