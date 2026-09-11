"""
OPINION forecasting engine — 5 models × 5 horizons per asset.

Models:
  1. Naive (persistence)       — statsforecast
  2. AutoARIMA                 — statsforecast
  3. AutoETS                   — statsforecast
  4. Theta                     — statsforecast
  5. XGBoost (feature-based)   — xgboost + models/features.py

All models use freq='h' (hourly). No future leakage.
Training window always ends strictly before forecast_origin.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from statsforecast import StatsForecast
from statsforecast.models import AutoARIMA, AutoETS, Naive, Theta

from config import (
    DATASET_VERSION,
    FEATURE_VERSION,
    HORIZONS,
    HorizonDef,
    SCORE_PENDING,
)
from models.features import build_features

import importlib
import statsforecast
import xgboost as _xgb

_SF_VERSION = statsforecast.__version__
_XGB_VERSION = _xgb.__version__

SF_MODELS = [Naive(), AutoARIMA(), AutoETS(), Theta()]
SF_MODEL_NAMES = ["Naive", "AutoARIMA", "AutoETS", "Theta"]


def _sf_forecast(
    series: pd.Series,
    horizon_def: HorizonDef,
) -> dict[str, dict]:
    """
    Run all 4 statsforecast models for a single horizon.
    Returns {model_name: {predicted_price, lower_bound, upper_bound, predicted_direction}}.
    """
    df = pd.DataFrame({
        "unique_id": "asset",
        "ds": series.index,
        "y": series.values,
    })
    sf = StatsForecast(models=SF_MODELS, freq="h", n_jobs=1)
    sf.fit(df)
    pred_df = sf.predict(h=horizon_def.steps, level=[90])

    last_price = float(series.iloc[-1])
    results = {}
    for name in SF_MODEL_NAMES:
        col = name
        if col not in pred_df.columns:
            # statsforecast column naming varies
            col = next((c for c in pred_df.columns if c.startswith(name)), None)
        if col is None:
            continue
        row = pred_df[pred_df["unique_id"] == "asset"].iloc[horizon_def.steps - 1]
        predicted = float(row[col])
        lo_col = f"{col}-lo-90"
        hi_col = f"{col}-hi-90"
        lower = float(row[lo_col]) if lo_col in row.index else None
        upper = float(row[hi_col]) if hi_col in row.index else None
        direction = "UP" if predicted > last_price else ("DOWN" if predicted < last_price else "FLAT")
        results[name] = {
            "predicted_price": predicted,
            "lower_bound": lower,
            "upper_bound": upper,
            "predicted_direction": direction,
        }
    return results


def _xgb_forecast(
    series: pd.Series,
    horizon_def: HorizonDef,
    fx_history: dict[str, pd.Series] | None,
) -> dict:
    """
    XGBoost forecast for one horizon. Uses FX features.
    No future leakage: training uses only data before forecast_origin.
    """
    X, y = build_features(series, fx_history=fx_history, horizon=horizon_def.steps)
    if len(X) < 50:
        return {}  # insufficient training data

    model = xgb.XGBRegressor(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=1,
    )
    model.fit(X.values, y.values)

    # Predict: build features for the most recent bar
    # The last row of X is the feature vector for predicting `horizon` steps ahead
    last_features = X.iloc[[-1]].values
    predicted = float(model.predict(last_features)[0])
    last_price = float(series.iloc[-1])
    direction = "UP" if predicted > last_price else ("DOWN" if predicted < last_price else "FLAT")

    return {
        "predicted_price": predicted,
        "lower_bound": None,   # XGBoost has no built-in PI; add quantile regression later
        "upper_bound": None,
        "predicted_direction": direction,
    }


def run_forecast(
    asset: str,
    series: pd.Series,
    currency: str,
    price_type: str,
    feature_snapshot_id: int,
    fx_history: dict[str, pd.Series] | None = None,
    training_cutoff: str | None = None,
) -> list[dict[str, Any]]:
    """
    Run all 5 models × 5 horizons for one asset.
    Returns list of forecast dicts ready for db/ops.insert_forecast().
    No UPDATE/DELETE; caller inserts these as new rows.
    """
    now = datetime.now(timezone.utc).isoformat()
    cutoff = training_cutoff or series.index[-1].isoformat()
    last_ts = series.index[-1]

    # Estimate target timestamps from series index
    freq_seconds = 3600  # hourly
    ts_list = series.index.tolist()

    records: list[dict] = []

    # 1–4: statsforecast models
    for horizon_def in HORIZONS:
        try:
            sf_results = _sf_forecast(series, horizon_def)
        except Exception:
            sf_results = {}

        for model_name, pred in sf_results.items():
            target_ts = (last_ts + pd.Timedelta(hours=horizon_def.steps)).isoformat()
            records.append({
                "forecast_id": str(uuid.uuid4()),
                "created_at": now,
                "forecast_origin": last_ts.isoformat(),
                "target_timestamp": target_ts,
                "horizon_definition": (
                    f"Predicted price {horizon_def.steps} hourly market-time "
                    f"steps ahead from forecast_origin"
                ),
                "asset": asset,
                "currency": currency,
                "price_type": price_type,
                "horizon_code": horizon_def.code,
                "horizon_minutes": horizon_def.minutes,
                "price_at_forecast": float(series.iloc[-1]),
                "model_id": f"sf_{model_name.lower()}",
                "model_version": _SF_VERSION,
                "dataset_version": DATASET_VERSION,
                "feature_version": FEATURE_VERSION,
                "feature_snapshot_id": feature_snapshot_id,
                "training_cutoff": cutoff,
                **pred,
            })

    # 5: XGBoost
    for horizon_def in HORIZONS:
        try:
            xgb_pred = _xgb_forecast(series, horizon_def, fx_history)
        except Exception:
            xgb_pred = {}
        if not xgb_pred:
            continue
        target_ts = (last_ts + pd.Timedelta(hours=horizon_def.steps)).isoformat()
        records.append({
            "forecast_id": str(uuid.uuid4()),
            "created_at": now,
            "forecast_origin": last_ts.isoformat(),
            "target_timestamp": target_ts,
            "horizon_definition": (
                f"Predicted price {horizon_def.steps} hourly market-time "
                f"steps ahead from forecast_origin (XGBoost+FX features)"
            ),
            "asset": asset,
            "currency": currency,
            "price_type": price_type,
            "horizon_code": horizon_def.code,
            "horizon_minutes": horizon_def.minutes,
            "price_at_forecast": float(series.iloc[-1]),
            "model_id": "xgboost_fx",
            "model_version": _XGB_VERSION,
            "dataset_version": DATASET_VERSION,
            "feature_version": FEATURE_VERSION,
            "feature_snapshot_id": feature_snapshot_id,
            "training_cutoff": cutoff,
            **xgb_pred,
        })

    return records
