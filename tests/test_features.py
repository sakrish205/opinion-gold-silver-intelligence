"""Tests for models/features.py — no future leakage, correct columns."""
import numpy as np
import pandas as pd
import pytest

from models.features import build_features, get_feature_names


def _make_series(n=200):
    idx = pd.date_range("2023-01-01", periods=n, freq="h", tz="UTC")
    prices = 1900.0 + np.cumsum(np.random.default_rng(42).normal(0, 5, n))
    return pd.Series(prices, index=idx)


def test_returns_dataframe_and_series():
    series = _make_series()
    X, y = build_features(series)
    assert isinstance(X, pd.DataFrame)
    assert isinstance(y, pd.Series)


def test_no_nans_in_output():
    series = _make_series()
    X, y = build_features(series)
    assert not X.isna().any().any(), "X contains NaN after dropna"
    assert not y.isna().any(), "y contains NaN after dropna"


def test_expected_base_columns():
    series = _make_series()
    X, _ = build_features(series)
    for lag in range(1, 25):
        assert f"lag_{lag}" in X.columns, f"Missing lag_{lag}"
    for col in ["mean_6h", "std_6h", "mean_24h", "std_24h", "last_return",
                "hour_sin", "hour_cos", "dow_sin", "dow_cos"]:
        assert col in X.columns, f"Missing column: {col}"


def test_no_future_leakage_lag1():
    """lag_1 at row i must equal y at row i-1 (price one step back)."""
    series = _make_series(100)
    X, y = build_features(series, horizon=1)
    # X.index and y.index are aligned after dropna
    # lag_1[i] == series[i-1] == y[i-1]  (for horizon=1, y[i] = series[i+1])
    lag1 = X["lag_1"]
    for i in range(1, len(lag1)):
        ts = lag1.index[i]
        ts_prev = lag1.index[i - 1]
        # lag_1 at ts equals the original series at the bar before ts
        expected = series.loc[ts_prev] if ts_prev in series.index else None
        if expected is not None:
            assert abs(lag1.iloc[i] - expected) < 1e-6, (
                f"Leakage detected: lag_1[{i}]={lag1.iloc[i]:.4f} != series[{i-1}]={expected:.4f}"
            )


def test_target_is_horizon_steps_ahead():
    """y[i] should be the price `horizon` steps after X[i]."""
    series = _make_series(200)
    for horizon in [1, 5, 12]:
        X, y = build_features(series, horizon=horizon)
        for i in range(min(10, len(X))):
            ts = X.index[i]
            # Find the bar `horizon` steps ahead in the original series
            loc = series.index.get_loc(ts)
            if loc + horizon < len(series):
                expected = series.iloc[loc + horizon]
                assert abs(y.iloc[i] - expected) < 1e-6, (
                    f"horizon={horizon}: y[{i}]={y.iloc[i]:.4f} != series[{loc+horizon}]={expected:.4f}"
                )


def test_fx_features_added():
    series = _make_series(200)
    idx = series.index
    fx = {"USD/INR": pd.Series(83.5 + np.random.default_rng(1).normal(0, 0.1, len(idx)), index=idx)}
    X, _ = build_features(series, fx_history=fx)
    assert "fx_usd_inr" in X.columns


def test_index_is_chronological():
    series = _make_series()
    X, y = build_features(series)
    assert X.index.is_monotonic_increasing


def test_get_feature_names_count():
    names = get_feature_names()
    # 24 lags + 5 rolling/return + 4 cyclical = 33
    assert len(names) == 33
    names_fx = get_feature_names(["USD/INR", "EUR/INR"])
    assert len(names_fx) == 35
