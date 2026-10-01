"""
Adversarial leakage tests for data/features.py and data/news_features.py.

Strategy: add a future observation, recompute features, verify features at t
are unchanged.  These tests are the primary guard against look-ahead leakage.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.features import (
    add_return_features,
    add_rolling_features,
    add_fx_features,
    add_cross_asset_features,
    add_targets,
    build_feature_df,
)
from data.news_features import (
    SentimentResult,
    StubFinBERTBackend,
    aggregate_sentiment,
    _WINDOWS,
)


def _ohlcv(n=100, base=1900.0, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    close = base + np.cumsum(rng.normal(0, 2, n))
    open_ = close * rng.uniform(0.999, 1.001, n)
    high  = np.maximum(open_, close) * 1.001
    low   = np.minimum(open_, close) * 0.999
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.integers(100, 5000, n).astype(float)},
        index=idx,
    )


def _fx_df(n=100, seed=9) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({"close": 83 + rng.normal(0, 0.1, n)}, index=idx)


# ── OHLCV price leakage ───────────────────────────────────────────────────────


def test_adding_future_price_does_not_change_past_features():
    """
    Adding a future bar to the OHLCV series must not alter features at earlier t.
    Tests return, rolling, momentum features.
    """
    base = _ohlcv(n=100)
    pivot_idx = 49  # check features at this row

    # Compute features on the original series
    df_base = add_return_features(add_rolling_features(base.copy()))
    features_at_t = df_base.iloc[pivot_idx].to_dict()

    # Add a "future" bar with a wildly different price
    future_idx = base.index[-1] + pd.Timedelta("1h")
    future_row = pd.DataFrame(
        {"open": [99999.0], "high": [99999.0], "low": [99999.0],
         "close": [99999.0], "volume": [0.0]},
        index=[future_idx],
    )
    extended = pd.concat([base, future_row])
    df_ext = add_return_features(add_rolling_features(extended.copy()))

    # Features at pivot_idx (bar 49) must be identical
    for col in ("return_1h", "rolling_mean_24h", "rolling_std_6h"):
        if col in df_ext.columns:
            assert df_ext.iloc[pivot_idx][col] == pytest.approx(
                features_at_t[col], rel=1e-8
            ), f"Leakage detected in {col}"


def test_return_feature_uses_only_past_close():
    """return_1h[t] depends on close[t] and close[t-1] only."""
    df = _ohlcv(n=50)
    df_feat = add_return_features(df.copy())

    # Manually change the close at t+1 (future)
    modified = df.copy()
    modified.iloc[-1, modified.columns.get_loc("close")] = 99999.0
    df_feat_mod = add_return_features(modified.copy())

    # return_1h at row 25 (well before the last row) must be unchanged
    t = 25
    assert df_feat["return_1h"].iloc[t] == pytest.approx(
        df_feat_mod["return_1h"].iloc[t], rel=1e-9
    )


# ── FX leakage ────────────────────────────────────────────────────────────────


def test_adding_future_fx_does_not_change_past_features():
    """Adding an FX bar after the feature window must not affect earlier rows."""
    ohlcv = _ohlcv(n=50)
    fx = _fx_df(n=50)

    # Features on original FX
    df1 = add_fx_features(ohlcv.copy(), {"usd_inr": fx})
    level_at_t25 = df1["usd_inr_level"].iloc[25]

    # Append a future FX bar with extreme value
    future_idx = fx.index[-1] + pd.Timedelta("1h")
    fx_extended = pd.concat([fx, pd.DataFrame({"close": [9999.0]}, index=[future_idx])])

    df2 = add_fx_features(ohlcv.copy(), {"usd_inr": fx_extended})
    assert df2["usd_inr_level"].iloc[25] == pytest.approx(level_at_t25, rel=1e-9)


def test_fx_as_of_join_uses_latest_prior_value():
    """FX level at t = most recent FX close at or before t."""
    n = 20
    ohlcv_idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    ohlcv = pd.DataFrame({"close": np.ones(n) * 1900}, index=ohlcv_idx)

    # FX only at every 3rd hour
    fx_idx = ohlcv_idx[::3]
    fx_vals = np.arange(1.0, len(fx_idx) + 1)
    fx = pd.DataFrame({"close": fx_vals}, index=fx_idx)

    df = add_fx_features(ohlcv.copy(), {"usd_inr": fx})

    for i, ts in enumerate(ohlcv_idx):
        prior = fx_vals[fx_idx <= ts]
        if len(prior) == 0:
            continue
        assert df["usd_inr_level"].iloc[i] == pytest.approx(prior[-1])


# ── Cross-asset leakage ───────────────────────────────────────────────────────


def test_cross_asset_uses_only_prior_bars():
    """gold_silver_ratio at t must use silver close at or before t."""
    n = 50
    gold = _ohlcv(n=n, base=1900, seed=1)
    silver = _ohlcv(n=n, base=25, seed=2)

    df1 = add_cross_asset_features(gold.copy(), silver, "silver")
    ratio_at_t20 = df1["gold_silver_ratio"].iloc[20]

    # Add a future silver bar with extreme value
    future_silver_idx = silver.index[-1] + pd.Timedelta("1h")
    future_silver = pd.concat([
        silver,
        pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0],
                      "close": [0.001], "volume": [0.0]},
                     index=[future_silver_idx]),
    ])
    df2 = add_cross_asset_features(gold.copy(), future_silver, "silver")
    assert df2["gold_silver_ratio"].iloc[20] == pytest.approx(ratio_at_t20, rel=1e-9)


# ── Target direction verification ─────────────────────────────────────────────


def test_target_1h_is_strictly_future():
    """target_return_1h[t] must equal log(close[t+1]/close[t]), not log(close[t]/close[t-1])."""
    df = add_targets(_ohlcv(n=50).copy())
    for i in range(1, len(df) - 1):
        if pd.isna(df["target_return_1h"].iloc[i]):
            continue
        expected = np.log(df["close"].iloc[i + 1] / df["close"].iloc[i])
        assert df["target_return_1h"].iloc[i] == pytest.approx(expected, rel=1e-9)


def test_target_positive_when_price_rises():
    """If close[t+1] > close[t], target_return_1h[t] > 0."""
    idx = pd.date_range("2024-01-01", periods=10, freq="h", tz="UTC")
    close = np.array([100.0, 105, 103, 108, 107, 110, 109, 112, 111, 115])
    df = pd.DataFrame({"close": close}, index=idx)
    df = add_targets(df)
    for i in range(len(df) - 1):
        if pd.isna(df["target_return_1h"].iloc[i]):
            continue
        if close[i + 1] > close[i]:
            assert df["target_return_1h"].iloc[i] > 0


# ── News leakage ──────────────────────────────────────────────────────────────


def test_future_news_excluded_from_sentiment():
    """News published AFTER feature_timestamp must never influence features at t."""
    stub = StubFinBERTBackend()
    t = pd.Timestamp("2024-06-01 10:00", tz="UTC")

    past_article = {
        "content_hash": "past1",
        "headline": "Gold up",
        "published_at": t - pd.Timedelta("1h"),
    }
    future_article = {
        "content_hash": "future1",
        "headline": "Silver crash",
        "published_at": t + pd.Timedelta("1h"),
    }
    news_df = pd.DataFrame([past_article, future_article])
    news_df["published_at"] = pd.to_datetime(news_df["published_at"], utc=True)

    sentiment_map = {
        "past1": SentimentResult(0.9, 0.05, 0.05),
        "future1": SentimentResult(0.05, 0.9, 0.05),
    }

    ts_idx = pd.DatetimeIndex([t])
    agg = aggregate_sentiment(ts_idx, news_df, sentiment_map)
    # Only 1 article (past) should count
    assert agg["news_count_6h"].iloc[0] == 1.0
    # Mean sentiment should be based on the positive past article
    assert agg["sentiment_mean_6h"].iloc[0] == pytest.approx(
        SentimentResult(0.9, 0.05, 0.05).score, rel=1e-6
    )


def test_adding_future_news_does_not_change_past_features():
    """Adding a future article to the news pool must not change features at earlier t."""
    stub = StubFinBERTBackend()
    t = pd.Timestamp("2024-06-01 10:00", tz="UTC")
    early_article = {
        "content_hash": "a1",
        "headline": "Gold rises",
        "published_at": t - pd.Timedelta("2h"),
    }
    news_df_base = pd.DataFrame([early_article])
    news_df_base["published_at"] = pd.to_datetime(news_df_base["published_at"], utc=True)
    sentiment_map = {"a1": SentimentResult(0.7, 0.2, 0.1)}

    ts_idx = pd.DatetimeIndex([t])
    agg1 = aggregate_sentiment(ts_idx, news_df_base, sentiment_map)

    # Now add a future article (after t)
    future_article = {
        "content_hash": "a2",
        "headline": "Silver crash",
        "published_at": t + pd.Timedelta("3h"),
    }
    news_df_ext = pd.concat([
        news_df_base,
        pd.DataFrame([future_article]).assign(
            published_at=pd.to_datetime([future_article["published_at"]], utc=True)
        ),
    ])
    sentiment_map["a2"] = SentimentResult(0.1, 0.8, 0.1)
    agg2 = aggregate_sentiment(ts_idx, news_df_ext, sentiment_map)

    assert agg1["news_count_6h"].iloc[0] == agg2["news_count_6h"].iloc[0]
    assert agg1["sentiment_mean_6h"].iloc[0] == pytest.approx(
        agg2["sentiment_mean_6h"].iloc[0], rel=1e-9
    )
