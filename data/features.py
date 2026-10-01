"""
ML-ready market feature engineering.

Reads from raw_market_data (SQLite) and produces a leakage-safe feature
DataFrame suitable for ML training.  The raw table is NEVER modified.

All features use only information at or before the feature timestamp t.
Targets use strictly future information (close[t+N]).

See docs/PROMPT_4_FEATURE_PLAN.md for the full data contract.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

FEATURE_VERSION = "v1"

# ── Read helpers ────────────────────────────────────────────────────────────


def load_raw_ohlcv(symbol: str, interval: str = "1h",
                   db_path=None) -> pd.DataFrame:
    """
    Load OHLCV rows from raw_market_data for one symbol.
    Returns a DataFrame indexed by UTC DatetimeTZDtype, sorted ascending.
    Returns empty DataFrame if no data exists.
    """
    from config import DB_PATH as _default
    dbp = Path(db_path) if db_path else _default
    try:
        with sqlite3.connect(dbp) as conn:
            df = pd.read_sql_query(
                "SELECT timestamp_utc, open, high, low, close, volume "
                "FROM raw_market_data WHERE symbol=? AND interval=? "
                "ORDER BY timestamp_utc",
                conn, params=(symbol, interval),
            )
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    return df.set_index("timestamp_utc").sort_index()


# ── Core price features ──────────────────────────────────────────────────────


def add_return_features(df: pd.DataFrame) -> pd.DataFrame:
    """Log returns over various lookback windows. Uses close[t] and prior bars."""
    log_c = np.log(df["close"])
    for h in (1, 2, 3, 6, 12, 24, 48):
        df[f"return_{h}h"] = log_c - log_c.shift(h)
    return df


def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """Lagged close prices."""
    for lag in (1, 2, 3, 6, 12, 24, 48):
        df[f"close_lag_{lag}"] = df["close"].shift(lag)
    return df


def add_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling mean, std, min, max — window ends at t (inclusive)."""
    c = df["close"]
    for w in (6, 12, 24, 48):
        df[f"rolling_mean_{w}h"] = c.rolling(w).mean()
        df[f"rolling_std_{w}h"] = c.rolling(w).std()
    for w in (24, 48):
        df[f"rolling_min_{w}h"] = c.rolling(w).min()
        df[f"rolling_max_{w}h"] = c.rolling(w).max()
    return df


def add_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """Price difference over lookback windows."""
    c = df["close"]
    for h in (3, 6, 12, 24, 48):
        df[f"momentum_{h}h"] = c - c.shift(h)
    return df


def add_volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling std of hourly log returns."""
    ret = np.log(df["close"]) - np.log(df["close"].shift(1))
    for w in (6, 12, 24, 48):
        df[f"volatility_{w}h"] = ret.rolling(w).std()
    return df


def add_ohlc_structure(df: pd.DataFrame) -> pd.DataFrame:
    """Single-bar OHLC structure features. No future information."""
    if not all(c in df.columns for c in ("open", "high", "low")):
        return df
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    df["high_low_range"] = h - l
    df["open_close_change"] = c - o
    df["upper_wick"] = h - pd.concat([o, c], axis=1).max(axis=1)
    df["lower_wick"] = pd.concat([o, c], axis=1).min(axis=1) - l
    df["body_size"] = (c - o).abs()
    safe_open = o.replace(0, np.nan)
    df["range_pct"] = (h - l) / safe_open
    return df


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Deterministic calendar features from the timestamp index."""
    idx = df.index
    df["hour"] = idx.hour
    df["day_of_week"] = idx.dayofweek
    df["day_of_month"] = idx.day
    df["month"] = idx.month
    df["quarter"] = idx.quarter
    df["hour_sin"] = np.sin(2 * np.pi * idx.hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * idx.hour / 24)
    df["dow_sin"] = np.sin(2 * np.pi * idx.dayofweek / 7)
    df["dow_cos"] = np.cos(2 * np.pi * idx.dayofweek / 7)
    df["month_sin"] = np.sin(2 * np.pi * idx.month / 12)
    df["month_cos"] = np.cos(2 * np.pi * idx.month / 12)
    return df


# ── FX features ─────────────────────────────────────────────────────────────


def add_fx_features(df: pd.DataFrame, fx_dfs: dict[str, pd.DataFrame],
                    ) -> pd.DataFrame:
    """
    As-of join FX data to the feature index.

    For each FX pair, only rows with timestamp <= feature_timestamp are used
    (pd.merge_asof direction='backward').  No future FX observation is attached.
    """
    for pair_key, fx_df in fx_dfs.items():
        if fx_df.empty or "close" not in fx_df.columns:
            continue
        # Prepare FX series: sorted, UTC-aware index, explicitly named
        fx = fx_df[["close"]].copy()
        fx.index = pd.to_datetime(fx.index, utc=True)
        fx = fx.sort_index()
        fx.index.name = "ts"
        fx.columns = [f"{pair_key}_close_raw"]

        # as-of join (right side is the FX data; left side is feature timestamps)
        feat_ts = df.index.to_frame(index=False, name="ts")
        fx_reset = fx.reset_index()
        merged = pd.merge_asof(feat_ts, fx_reset, on="ts", direction="backward")
        merged = merged.set_index("ts")
        merged.index = pd.to_datetime(merged.index, utc=True)

        raw_col = f"{pair_key}_close_raw"
        level_col = f"{pair_key}_level"
        ret_col = f"{pair_key}_return"

        df[level_col] = merged[raw_col].values
        # Log return of FX level (using the level series we just joined)
        fx_levels = df[level_col]
        df[ret_col] = np.log(fx_levels) - np.log(fx_levels.shift(1))

    return df


# ── Cross-asset features ─────────────────────────────────────────────────────


def add_cross_asset_features(df: pd.DataFrame,
                              other_df: pd.DataFrame,
                              other_name: str = "other") -> pd.DataFrame:
    """
    As-of join the other asset's close and 1h return to the current feature index.

    other_df: OHLCV DataFrame (indexed by UTC datetime) for the other asset.
    other_name: 'gold' or 'silver'
    Alignment: only bars with timestamp <= feature_timestamp are used.
    """
    if other_df.empty or "close" not in other_df.columns:
        return df

    other = other_df[["close"]].copy()
    other.index = pd.to_datetime(other.index, utc=True)
    other = other.sort_index()
    other.index.name = "ts"

    feat_ts = df.index.to_frame(index=False, name="ts")
    other_reset = other.reset_index()
    merged = pd.merge_asof(feat_ts, other_reset, on="ts", direction="backward")
    merged = merged.set_index("ts")
    merged.index = pd.to_datetime(merged.index, utc=True)

    other_close = merged["close"].values
    df[f"{other_name}_close_asof"] = other_close

    # Gold/silver ratio and related features
    if other_name == "silver":
        silver_close = df[f"{other_name}_close_asof"]
        safe_silver = silver_close.replace(0, np.nan)
        df["gold_silver_ratio"] = df["close"] / safe_silver
        df["gold_silver_ratio_change"] = df["gold_silver_ratio"] - df["gold_silver_ratio"].shift(1)
        gold_ret = np.log(df["close"]) - np.log(df["close"].shift(1))
        silver_ret = np.log(silver_close) - np.log(silver_close.shift(1))
        df["gold_return_vs_silver"] = gold_ret - silver_ret

    elif other_name == "gold":
        gold_close = df[f"{other_name}_close_asof"]
        safe_gold = gold_close.replace(0, np.nan)
        df["gold_silver_ratio"] = safe_gold / df["close"].replace(0, np.nan)
        df["gold_silver_ratio_change"] = df["gold_silver_ratio"] - df["gold_silver_ratio"].shift(1)
        gold_ret = np.log(gold_close) - np.log(gold_close.shift(1))
        silver_ret = np.log(df["close"]) - np.log(df["close"].shift(1))
        df["silver_return_vs_gold"] = silver_ret - gold_ret

    return df


# ── Targets ──────────────────────────────────────────────────────────────────


def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Log-return targets for each horizon.
    target_return_Nh(t) = log(close[t+N] / close[t])
    Uses future bars — intentionally so. NaN where future bar is unavailable.
    """
    log_c = np.log(df["close"])
    for h in (1, 5, 12, 24, 48):
        # shift(-h) aligns: at row t, value is from row t+h
        df[f"target_return_{h}h"] = log_c.shift(-h) - log_c
    return df


# ── Quality checks ───────────────────────────────────────────────────────────


def check_feature_quality(df: pd.DataFrame) -> list[str]:
    """Return a list of quality issues (empty = OK)."""
    issues = []
    if df.empty:
        issues.append("Empty dataset")
        return issues
    # No inf
    inf_cols = [c for c in df.select_dtypes("number").columns
                if df[c].isin([np.inf, -np.inf]).any()]
    if inf_cols:
        issues.append(f"Inf values in: {inf_cols}")
    # Monotonic timestamp
    if not df.index.is_monotonic_increasing:
        issues.append("Index not monotonically increasing")
    # Duplicate timestamps
    dups = df.index.duplicated().sum()
    if dups:
        issues.append(f"{dups} duplicate timestamps")
    return issues


# ── Top-level builder ────────────────────────────────────────────────────────


def build_feature_df(
    ohlcv: pd.DataFrame,
    fx_dfs: dict[str, pd.DataFrame] | None = None,
    other_asset_df: pd.DataFrame | None = None,
    other_asset_name: str = "other",
    asset: str = "",
) -> pd.DataFrame:
    """
    Build the complete feature DataFrame for one asset.

    Args:
        ohlcv: raw OHLCV, UTC-indexed, sorted ascending
        fx_dfs: {pair_key: ohlcv_df} for FX as-of join
        other_asset_df: OHLCV of the other metal (for cross-asset features)
        other_asset_name: 'gold' or 'silver'
        asset: label stored in the 'asset' column

    Returns:
        DataFrame with all features + targets, indexed by UTC timestamp.
        Raw OHLCV columns (open/high/low/close/volume) are dropped from output
        EXCEPT 'close' which is kept for reference.
    """
    if ohlcv.empty:
        return pd.DataFrame()

    df = ohlcv.copy()

    df = add_return_features(df)
    df = add_lag_features(df)
    df = add_rolling_features(df)
    df = add_momentum_features(df)
    df = add_volatility_features(df)
    df = add_ohlc_structure(df)
    df = add_time_features(df)

    if fx_dfs:
        df = add_fx_features(df, fx_dfs)

    if other_asset_df is not None and not other_asset_df.empty:
        df = add_cross_asset_features(df, other_asset_df, other_asset_name)

    df = add_targets(df)

    df["asset"] = asset
    df["feature_version"] = FEATURE_VERSION

    return df
