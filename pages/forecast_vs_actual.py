"""Page 8: Forecast vs Actual — audit graph with 6 required elements."""
import sqlite3
import dash
from dash import callback, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd

from config import DB_PATH, HORIZONS

dash.register_page(__name__, path="/forecast-vs-actual", name="Forecast vs Actual")

layout = html.Div([
    html.H4("Forecast vs Actual", className="mb-3"),
    html.P("Historical predictions vs observed outcomes. Predictions read from immutable forecast_history.",
           className="text-muted"),
    dbc.Row([
        dbc.Col(dcc.Dropdown(id="fva-asset",
            options=[{"label": "Gold (XAU)", "value": "XAU"}, {"label": "Silver (XAG)", "value": "XAG"}],
            value="XAU", clearable=False), md=3),
        dbc.Col(dcc.Dropdown(id="fva-horizon",
            options=[{"label": h.label, "value": h.code} for h in HORIZONS],
            value=HORIZONS[0].code, clearable=False), md=3),
        dbc.Col(dcc.Dropdown(id="fva-model",
            options=[{"label": m, "value": m} for m in
                     ["Naive", "AutoARIMA", "AutoETS", "Theta", "XGBoost"]],
            value="AutoARIMA", clearable=False), md=3),
    ], className="mb-3"),
    dcc.Loading(dcc.Graph(id="fva-chart", style={"height": "550px"})),
    html.P(
        "Elements: observed price | historical predicted price | forecast range | "
        "current forecast | forecast origin marker | verification point",
        className="text-muted small mt-2",
    ),
])


@callback(
    Output("fva-chart", "figure"),
    Input("fva-asset", "value"),
    Input("fva-horizon", "value"),
    Input("fva-model", "value"),
)
def update_chart(asset, horizon_code, model_id):
    fig = go.Figure()

    try:
        with sqlite3.connect(DB_PATH) as conn:
            forecasts = pd.read_sql_query(
                """SELECT fh.forecast_id, fh.forecast_origin, fh.target_timestamp,
                          fh.predicted_price, fh.lower_bound, fh.upper_bound, fh.price_at_forecast,
                          fo.actual_price, fo.direction_correct, fo.outcome_verified_at
                   FROM forecast_history fh
                   LEFT JOIN forecast_outcomes fo ON fo.forecast_id = fh.forecast_id
                   WHERE fh.asset=? AND fh.horizon_code=? AND fh.model_id=?
                   ORDER BY fh.forecast_origin ASC LIMIT 200""",
                conn, params=(asset, horizon_code, model_id),
            )
    except Exception:
        forecasts = pd.DataFrame()

    if forecasts.empty:
        fig.update_layout(title=f"{asset} {horizon_code} {model_id} — No data yet",
                          template="plotly_dark")
        return fig

    # Element 1: OBSERVED PRICE (actual outcomes)
    observed = forecasts.dropna(subset=["actual_price"])
    if not observed.empty:
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(observed["target_timestamp"]),
            y=observed["actual_price"],
            mode="markers", name="Observed Price",
            marker=dict(symbol="circle", size=8, color="white"),
        ))

    # Element 2: HISTORICAL PREDICTED PRICE
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(forecasts["target_timestamp"]),
        y=forecasts["predicted_price"],
        mode="lines+markers", name="Predicted Price",
        line=dict(color="yellow", dash="dot"),
    ))

    # Element 3: FORECAST RANGE (confidence band)
    has_bounds = forecasts["lower_bound"].notna() & forecasts["upper_bound"].notna()
    if has_bounds.any():
        band = forecasts[has_bounds]
        fig.add_trace(go.Scatter(
            x=pd.concat([pd.to_datetime(band["target_timestamp"]),
                         pd.to_datetime(band["target_timestamp"]).iloc[::-1]]),
            y=pd.concat([band["upper_bound"], band["lower_bound"].iloc[::-1]]),
            fill="toself", fillcolor="rgba(255,255,0,0.08)",
            line=dict(color="rgba(0,0,0,0)"),
            name="Forecast Range (90%)", showlegend=True,
        ))

    # Element 4: CURRENT FORECAST (latest row without an outcome)
    pending = forecasts[forecasts["actual_price"].isna()]
    if not pending.empty:
        latest = pending.iloc[-1]
        fig.add_trace(go.Scatter(
            x=[pd.to_datetime(latest["target_timestamp"])],
            y=[latest["predicted_price"]],
            mode="markers", name="Current Forecast",
            marker=dict(symbol="star", size=14, color="cyan"),
        ))

    # Element 5: FORECAST ORIGIN markers
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(forecasts["forecast_origin"]),
        y=forecasts["price_at_forecast"],
        mode="markers", name="Forecast Origin",
        marker=dict(symbol="triangle-right", size=8, color="orange"),
    ))

    # Element 6: VERIFICATION POINTS
    verified = forecasts.dropna(subset=["outcome_verified_at"])
    if not verified.empty:
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(verified["outcome_verified_at"]),
            y=verified["actual_price"],
            mode="markers", name="Verification Point",
            marker=dict(symbol="diamond", size=10, color="lime"),
        ))

    fig.update_layout(
        title=f"{asset} {horizon_code} | {model_id} | Forecast vs Actual",
        yaxis_title="Price (USD — FUTURES/DERIVED)",
        template="plotly_dark",
        hovermode="x unified",
    )
    return fig
