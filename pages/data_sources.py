"""Page 15: Data Sources — provider spec table and health cards."""
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc

from data.providers.base import ProviderSpec
from data.providers.metals_futures import MetalsFuturesProvider
from data.providers.metals_spot import SpotUnavailableProvider
from data.providers.forex import YFinanceFXProvider, OpenERAPIFXProvider
from data.providers.news import RSSNewsProvider, VERIFIED_SOURCES

dash.register_page(__name__, path="/data-sources", name="Data Sources")

_providers = [
    MetalsFuturesProvider(),
    SpotUnavailableProvider(),
    YFinanceFXProvider(),
    OpenERAPIFXProvider(),
]


def _build_spec_table():
    rows = []
    for p in _providers:
        spec: ProviderSpec = p.spec
        rows.append(html.Tr([
            html.Td(spec.name),
            html.Td(spec.cost),
            html.Td("Yes" if spec.requires_key else "No"),
            html.Td(spec.rate_limit),
            html.Td(spec.resolution),
            html.Td(spec.reliability),
            html.Td(spec.storage_rights),
            html.Td(spec.redistribution),
            html.Td(spec.commercial_use),
            html.Td(spec.license),
        ]))
    return dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in
                             ["Provider", "Cost", "API Key", "Rate Limit", "Resolution",
                              "Reliability", "Storage", "Redistribution", "Commercial", "License"]]))]
        + [html.Tbody(rows)],
        bordered=True, size="sm", responsive=True,
    )


def _build_news_section():
    if not VERIFIED_SOURCES:
        return dbc.Alert(
            "No news sources configured. Verify ToS then add sources to "
            "data/providers/news.py::VERIFIED_SOURCES.",
            color="warning",
        )
    rows = [html.Tr([html.Td(s.get("name")), html.Td(s.get("url")), html.Td(s.get("tos_status"))])
            for s in VERIFIED_SOURCES]
    return dbc.Table(
        [html.Thead(html.Tr([html.Th(c) for c in ["Name", "URL", "ToS Status"]]))]
        + [html.Tbody(rows)],
        bordered=True, size="sm",
    )


layout = html.Div([
    html.H4("Data Sources", className="mb-3"),
    dcc.Interval(id="ds-interval", interval=120_000, n_intervals=0),
    html.Div(id="ds-health-cards", className="mb-4"),
    html.H5("Provider Specifications", className="mb-2"),
    _build_spec_table(),
    html.H5("News Sources", className="mt-4 mb-2"),
    _build_news_section(),
])


@callback(Output("ds-health-cards", "children"), Input("ds-interval", "n_intervals"))
def refresh_health(_n):
    cards = []
    for p in _providers:
        try:
            if hasattr(p, "fetch_latest"):
                r = p.fetch_latest("XAU")
            else:
                r = p.fetch()
            status = r.status
            latency = r.latency_ms
        except Exception:
            status, latency = "ERROR", None

        color = {"LIVE": "success", "STALE": "warning", "UNAVAILABLE": "secondary"}.get(status, "danger")
        cards.append(dbc.Col(dbc.Card(dbc.CardBody([
            html.Small(p.spec.name, className="text-muted"),
            html.Br(),
            dbc.Badge(status, color=color),
            html.Small(f" {latency}ms" if latency else "", className="text-muted ms-1"),
        ])), md=2))
    return dbc.Row(cards)
