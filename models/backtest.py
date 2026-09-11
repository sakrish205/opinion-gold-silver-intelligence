"""
Walk-forward backtesting for all 5 models.

Rules:
  - Walk-forward only (no random splits, no future leakage).
  - Writes results to backtest_runs and backtest_results tables.
  - Does NOT write to forecast_history or forecast_outcomes.
  - After completion, updates model_registry with aggregate metrics
    and sets status='production' for the best model per (asset × horizon).
  - Best model = highest directional_accuracy; sMAPE as tiebreaker.
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

from config import ASSETS, DATASET_VERSION, FEATURE_VERSION, HORIZONS, SCORE_CORRECT, SCORE_INCORRECT
from db.ops import (
    complete_backtest_run,
    insert_backtest_result,
    insert_backtest_run,
    update_model_metrics,
)
from models.features import build_features


def _direction(a: float, b: float) -> str:
    if a > b:
        return "UP"
    if a < b:
        return "DOWN"
    return "FLAT"


def _metrics(results: list[dict]) -> dict:
    if not results:
        return {}
    errors = [abs(r["absolute_error"]) for r in results if r["absolute_error"] is not None]
    pct_errors = [abs(r["percentage_error"]) for r in results if r["percentage_error"] is not None]
    correct = [r["direction_correct"] for r in results if r["direction_correct"] is not None]
    covered = [r["interval_covered"] for r in results if r["interval_covered"] is not None]
    scores = [r["score"] for r in results if r["score"] is not None]

    mae = float(np.mean(errors)) if errors else None
    rmse = float(np.sqrt(np.mean(np.array(errors) ** 2))) if errors else None
    # sMAPE
    smape = None
    if pct_errors:
        smape = float(np.mean(pct_errors)) * 2  # symmetric formulation
    dir_acc = float(np.mean(correct)) if correct else None
    cov = float(np.mean(covered)) if covered else None
    cum_score = int(sum(scores)) if scores else 0
    return {
        "mae": mae, "rmse": rmse, "smape": smape,
        "directional_accuracy": dir_acc,
        "interval_coverage": cov,
        "cumulative_score": cum_score,
    }


def run_backtest(
    asset: str,
    series: pd.Series,
    fx_history: dict[str, pd.Series] | None = None,
    n_windows: int = 12,
    step_size_hours: int = 24,
    currency: str = "USD",
    method: str = "walk_forward",
) -> None:
    """Run walk-forward backtest for all 5 models × 5 horizons for one asset."""
    min_train = 200  # minimum hourly bars for a valid training window
    if len(series) < min_train + step_size_hours:
        return

    model_window_results: dict[tuple[str, str], list[dict]] = {}

    for horizon_def in HORIZONS:
        h = horizon_def.steps
        model_ids = ["sf_naive", "sf_autoarima", "sf_autoets", "sf_theta", "xgboost_fx"]

        for window_idx in range(n_windows):
            # Walk-forward: train end moves forward by step_size each window
            test_end_idx = len(series) - 1 - window_idx * step_size_hours
            test_start_idx = test_end_idx - h
            train_end_idx = test_start_idx - 1
            train_start_idx = max(0, train_end_idx - 730)  # cap training window

            if train_end_idx < min_train or test_start_idx < 0:
                break

            train = series.iloc[train_start_idx:train_end_idx + 1]
            actual_price = float(series.iloc[test_end_idx])
            price_at_train_end = float(train.iloc[-1])
            actual_dir = _direction(actual_price, price_at_train_end)

            train_start = train.index[0].isoformat()
            train_end = train.index[-1].isoformat()
            test_start = series.index[test_start_idx].isoformat()
            test_end = series.index[test_end_idx].isoformat()

            # StatsForecast models
            try:
                sf_df = pd.DataFrame({
                    "unique_id": "asset",
                    "ds": train.index,
                    "y": train.values,
                })
                sf = StatsForecast(
                    models=[Naive(), AutoARIMA(), AutoETS(), Theta()],
                    freq="h", n_jobs=1,
                )
                sf.fit(sf_df)
                preds_df = sf.predict(h=h, level=[90])
                sf_row = preds_df[preds_df["unique_id"] == "asset"].iloc[h - 1]
            except Exception:
                sf_row = None

            for sf_name, model_id in [
                ("Naive", "sf_naive"),
                ("AutoARIMA", "sf_autoarima"),
                ("AutoETS", "sf_autoets"),
                ("Theta", "sf_theta"),
            ]:
                predicted = None
                lower = upper = None
                if sf_row is not None:
                    col = next((c for c in sf_row.index if c == sf_name or c.startswith(sf_name)), None)
                    if col:
                        predicted = float(sf_row[col])
                        lo = f"{col}-lo-90"; hi = f"{col}-hi-90"
                        lower = float(sf_row[lo]) if lo in sf_row.index else None
                        upper = float(sf_row[hi]) if hi in sf_row.index else None

                _append_result(
                    model_window_results, model_id, horizon_def.code,
                    asset, currency, method, n_windows, step_size_hours,
                    window_idx, train_start, train_end, test_start, test_end,
                    actual_price, predicted, lower, upper, actual_dir,
                )

            # XGBoost
            xgb_pred = None
            try:
                fx_train = None
                if fx_history:
                    fx_train = {k: v.iloc[:train_end_idx + 1] for k, v in fx_history.items()}
                X, y = build_features(train, fx_history=fx_train, horizon=h)
                if len(X) >= 50:
                    model = xgb.XGBRegressor(
                        n_estimators=200, learning_rate=0.05, max_depth=4,
                        subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=1,
                    )
                    model.fit(X.values, y.values)
                    xgb_pred = float(model.predict(X.iloc[[-1]].values)[0])
            except Exception:
                pass

            _append_result(
                model_window_results, "xgboost_fx", horizon_def.code,
                asset, currency, method, n_windows, step_size_hours,
                window_idx, train_start, train_end, test_start, test_end,
                actual_price, xgb_pred, None, None, actual_dir,
            )

    # Flush to DB and update model_registry
    _flush_to_db(model_window_results, asset, currency, method, n_windows, step_size_hours, series)


def _append_result(
    store: dict, model_id: str, horizon_code: str,
    asset: str, currency: str, method: str, n_windows: int, step_size_hours: int,
    window_idx: int, train_start: str, train_end: str, test_start: str, test_end: str,
    actual: float, predicted: float | None, lower: float | None, upper: float | None,
    actual_dir: str,
) -> None:
    key = (model_id, horizon_code)
    if key not in store:
        store[key] = []
    abs_err = abs(actual - predicted) if predicted is not None else None
    pct_err = (abs_err / actual * 100) if abs_err is not None and actual else None
    pred_dir = _direction(predicted, actual) if predicted is not None else None
    dir_correct = int(pred_dir == actual_dir) if pred_dir else None
    score = (SCORE_CORRECT if dir_correct == 1 else SCORE_INCORRECT) if dir_correct is not None else None
    covered = (
        int(lower <= actual <= upper)
        if lower is not None and upper is not None else None
    )
    store[key].append({
        "window_index": window_idx,
        "train_start": train_start, "train_end": train_end,
        "test_start": test_start, "test_end": test_end,
        "actual_price": actual,
        "predicted_price": predicted,
        "lower_bound": lower, "upper_bound": upper,
        "absolute_error": abs_err,
        "percentage_error": pct_err,
        "direction_correct": dir_correct,
        "score": score,
        "interval_covered": covered,
    })


def _flush_to_db(
    store: dict, asset: str, currency: str, method: str,
    n_windows: int, step_size_hours: int, series: pd.Series,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    cutoff = series.index[-1].isoformat()

    # Track best model per horizon (directional_accuracy primary, smape tiebreaker)
    best_per_horizon: dict[str, tuple[str, float, float]] = {}  # horizon_code → (model_id, dir_acc, smape)

    for (model_id, horizon_code), results in store.items():
        run_id = str(uuid.uuid4())
        insert_backtest_run({
            "run_id": run_id,
            "started_at": now,
            "model_id": model_id,
            "asset": asset,
            "currency": currency,
            "horizon_code": horizon_code,
            "method": method,
            "n_windows": n_windows,
            "step_size_hours": step_size_hours,
            "training_cutoff": cutoff,
            "status": "running",
        })

        for r in results:
            insert_backtest_result({"run_id": run_id, **r})

        complete_backtest_run(run_id, "completed")

        m = _metrics(results)
        update_model_metrics(
            model_id,
            mae=m.get("mae"), rmse=m.get("rmse"), smape=m.get("smape"),
            directional_accuracy=m.get("directional_accuracy"),
            interval_coverage=m.get("interval_coverage"),
            cumulative_score=m.get("cumulative_score"),
            status="benchmark",
        )

        dir_acc = m.get("directional_accuracy") or 0.0
        smape = m.get("smape") or 999.0
        prev = best_per_horizon.get(horizon_code)
        if prev is None or dir_acc > prev[1] or (dir_acc == prev[1] and smape < prev[2]):
            best_per_horizon[horizon_code] = (model_id, dir_acc, smape)

    # Set production status for winners
    for horizon_code, (best_model_id, _, _) in best_per_horizon.items():
        update_model_metrics(best_model_id, status="production")
