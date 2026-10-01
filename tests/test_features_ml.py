"""
Tests for data/features.py — market feature engineering.
All use synthetic data; no network calls.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.features import (
    add_return_features,
    add_lag_features,
    add_rolling_features,
    add_momentum_features,
    add_volatility_features,
    add_ohlc_structure,
    add_time_features,
    add_fx_features,
    add_cross_asset_features,
    add_targets,
    build_feature_df,
    check_feature_quality,
    FEATURE_VERSION,
)


def _ohlcv(n=200, base=1900.0, seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    close = base + np.cumsum(rng.normal(0, 2, n))
    open_ = close * rng.uniform(0.999, 1.001, n)
    high  = np.maximum(open_, close) * rng.uniform(1.0001, 1.002, n)
    low   = np.minimum(open_, close) * rng.uniform(0.998, 0.9999, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.integers(100, 5000, n).astype(float)},
        index=idx,
    )


def _fx_dfs(n=200, seed=7) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    return {
        "usd_inr": pd.DataFrame({"close": 83 + rng.normal(0, 0.1, n)}, index=idx),
    }


# ── Return features ──────────────────────────────────────────────────────────


def test_return_features_present():
    df = add_return_features(_ohlcv().copy())
    for h in (1, 2, 3, 6, 12, 24, 48):
        assert f"return_{h}h" in df.columns


def test_return_features_no_future():
    """return_1h[t] must equal log(close[t] / close[t-1]) — no future data."""
    df = add_return_features(_ohlcv(n=100).copy())
    log_c = np.log(df["close"])
    expected = log_c - log_c.shift(1)
    pd.testing.assert_series_equal(df["return_1h"], expected, check_names=False)


# ── Lag features ─────────────────────────────────────────────────────────────


def test_lag_features_present():
    df = add_lag_features(_ohlcv().copy())
    for lag in (1, 2, 3, 6, 12, 24, 48):
        assert f"close_lag_{lag}" in df.columns


def test_lag_1_equals_prior_close():
    """close_lag_1[t] must equal close[t-1]."""
    df = add_lag_features(_ohlcv(n=50).copy())
    for i in range(1, len(df)):
        assert df["close_lag_1"].iloc[i] == pytest.approx(df["close"].iloc[i - 1])


# ── Rolling features ─────────────────────────────────────────────────────────


def test_rolling_features_present():
    df = add_rolling_features(_ohlcv().copy())
    for w in (6, 12, 24, 48):
        assert f"rolling_mean_{w}h" in df.columns
        assert f"rolling_std_{w}h" in df.columns


def test_rolling_mean_24h_value():
    """rolling_mean_24h[t] = mean of close[t-23..t]."""
    df = add_rolling_features(_ohlcv(n=100).copy())
    t = 50
    expected = df["close"].iloc[t - 23:t + 1].mean()
    assert df["rolling_mean_24h"].iloc[t] == pytest.approx(expected, rel=1e-6)


# ── Volatility features ───────────────────────────────────────────────────────


def test_volatility_features_present():
    df = add_volatility_features(_ohlcv().copy())
    for w in (6, 12, 24, 48):
        assert f"volatility_{w}h" in df.columns


# ── OHLC structure ────────────────────────────────────────────────────────────


def test_ohlc_structure_present():
    df = add_ohlc_structure(_ohlcv().copy())
    for col in ("high_low_range", "open_close_change", "upper_wick",
                "lower_wick", "body_size", "range_pct"):
        assert col in df.columns


def test_high_low_range_nonnegative():
    df = add_ohlc_structure(_ohlcv().copy())
    assert (df["high_low_range"].dropna() >= 0).all()


# ── Time features ─────────────────────────────────────────────────────────────


def test_time_features_present():
    df = add_time_features(_ohlcv().copy())
    for col in ("hour", "day_of_week", "month", "hour_sin", "hour_cos",
                "dow_sin", "dow_cos", "month_sin", "month_cos"):
        assert col in df.columns


def test_time_features_bounded():
    df = add_time_features(_ohlcv().copy())
    assert df["hour"].between(0, 23).all()
    assert df["day_of_week"].between(0, 6).all()
    assert df["hour_sin"].between(-1, 1).all()


# ── FX alignment ──────────────────────────────────────────────────────────────


def test_fx_features_added():
    df = add_fx_features(_ohlcv().copy(), _fx_dfs())
    assert "usd_inr_level" in df.columns
    assert "usd_inr_return" in df.columns


def test_fx_alignment_causal():
    """FX level at t must equal the FX close at or before t (not after)."""
    n = 50
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    ohlcv = pd.DataFrame({"close": np.ones(n) * 1900}, index=idx)

    # FX only has data at even hours → odd-hour feature rows should get last even value
    fx_idx = idx[::2]  # every 2h
    fx_vals = np.arange(1, len(fx_idx) + 1, dtype=float)
    fx_df = pd.DataFrame({"close": fx_vals}, index=fx_idx)

    df = add_fx_features(ohlcv.copy(), {"usd_inr": fx_df})

    # At any feature timestamp, the FX level must be <= the latest FX close at or before that ts
    for i, ts in enumerate(idx):
        fx_avail = fx_vals[fx_idx <= ts]
        if len(fx_avail) == 0:
            continue
        assert df["usd_inr_level"].iloc[i] == pytest.approx(fx_avail[-1])


# ── Cross-asset features ───────────────────────────────────────────────────────


def test_gold_silver_features():
    gold = _ohlcv(n=200, base=1900, seed=1)
    silver = _ohlcv(n=200, base=25, seed=2)
    df = add_cross_asset_features(gold.copy(), silver, "silver")
    assert "gold_silver_ratio" in df.columns
    assert "gold_silver_ratio_change" in df.columns
    assert "gold_return_vs_silver" in df.columns


# ── Targets ───────────────────────────────────────────────────────────────────


def _check_target_direction(n=100, horizon=1):
    df = add_targets(_ohlcv(n=n).copy())
    col = f"target_return_{horizon}h"
    valid = df[[col, "close"]].dropna()
    for i in range(min(10, len(valid))):
        t_idx = valid.index[i]
        t_pos = df.index.get_loc(t_idx)
        if t_pos + horizon < len(df):
            future_close = df["close"].iloc[t_pos + horizon]
            current_close = df["close"].iloc[t_pos]
            expected = np.log(future_close / current_close)
            assert valid[col].iloc[i] == pytest.approx(expected, rel=1e-6)


def test_target_1h():
    _check_target_direction(horizon=1)


def test_target_5h():
    _check_target_direction(horizon=5)


def test_target_12h():
    _check_target_direction(horizon=12)


def test_target_24h():
    _check_target_direction(horizon=24)


def test_target_48h():
    _check_target_direction(horizon=48)


def test_targets_all_present():
    df = add_targets(_ohlcv().copy())
    for h in (1, 5, 12, 24, 48):
        assert f"target_return_{h}h" in df.columns


def test_target_end_rows_are_nan():
    """Last 48 rows must have NaN target_return_48h (future not available)."""
    df = add_targets(_ohlcv(n=100).copy())
    assert df["target_return_48h"].iloc[-48:].isna().all()


# ── Quality checks ─────────────────────────────────────────────────────────────


def test_quality_check_ok():
    df = build_feature_df(_ohlcv(), asset="XAU")
    issues = check_feature_quality(df)
    assert all("Inf" not in i for i in issues)
    assert all("not monoton" not in i for i in issues)


def test_feature_version_present():
    df = build_feature_df(_ohlcv(), asset="XAU")
    assert "feature_version" in df.columns
    assert (df["feature_version"] == FEATURE_VERSION).all()
