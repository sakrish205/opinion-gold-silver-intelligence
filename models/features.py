"""
XGBoost feature builder.

Features are built per training window with ZERO future leakage:
  - Lagged prices: y(t-1) … y(t-24)
  - Rolling stats: mean_6h, std_6h, mean_24h, std_24h
  - FX features: all 5 INR pairs lagged to t-1 (never t)
  - Hour-of-day and day-of-week (cyclical encoded)
  - XAU/INR cross-check delta (if available)

FX rates are passed in from feature_snapshots so the exact values
available at forecast time are preserved and reproducible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_features(
    price_series: pd.Series,
    fx_history: dict[str, pd.Series] | None = None,
    horizon: int = 1,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Build (X, y) for a single asset/horizon combination.

    Args:
        price_series: hourly closing prices indexed by UTC datetime.
        fx_history:   {pair: hourly rate series} — all aligned to price_series.
        horizon:      number of steps ahead for the target (1, 5, 12, 24, 48).

    Returns:
        X: feature DataFrame, y: target series (price horizon steps ahead).
    """
    df = pd.DataFrame({"y": price_series})

    # Lagged prices (no leakage: all lags ≥ 1)
    for lag in range(1, 25):
        df[f"lag_{lag}"] = df["y"].shift(lag)

    # Rolling stats on lagged values (shift 1 to avoid leakage)
    df["mean_6h"] = df["y"].shift(1).rolling(6).mean()
    df["std_6h"] = df["y"].shift(1).rolling(6).std()
    df["mean_24h"] = df["y"].shift(1).rolling(24).mean()
    df["std_24h"] = df["y"].shift(1).rolling(24).std()

    # Price direction of last bar
    df["last_return"] = df["y"].pct_change().shift(1)

    # FX features — lagged to t-1 (available before forecast)
    if fx_history:
        for pair_name, fx_series in fx_history.items():
            col = pair_name.lower().replace("/", "_")
            aligned = fx_series.reindex(df.index, method="ffill")
            df[f"fx_{col}"] = aligned.shift(1)

    # Time features (cyclical)
    idx = df.index
    df["hour_sin"] = np.sin(2 * np.pi * idx.hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * idx.hour / 24)
    df["dow_sin"] = np.sin(2 * np.pi * idx.dayofweek / 7)
    df["dow_cos"] = np.cos(2 * np.pi * idx.dayofweek / 7)

    # Target: price horizon steps ahead
    df["target"] = df["y"].shift(-horizon)

    # Drop rows with any NaN (initial lags, end of series)
    df = df.dropna()

    feature_cols = [c for c in df.columns if c not in ("y", "target")]
    return df[feature_cols], df["target"]


def get_feature_names(fx_pairs: list[str] | None = None) -> list[str]:
    """Return the list of feature column names (for logging/registry)."""
    names = [f"lag_{i}" for i in range(1, 25)]
    names += ["mean_6h", "std_6h", "mean_24h", "std_24h", "last_return"]
    if fx_pairs:
        names += [f"fx_{p.lower().replace('/', '_')}" for p in fx_pairs]
    names += ["hour_sin", "hour_cos", "dow_sin", "dow_cos"]
    return names
