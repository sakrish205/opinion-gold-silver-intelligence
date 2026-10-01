"""Tests for data/validation.py — no network calls."""
import numpy as np
import pandas as pd
import pytest

from data.validation import validate_ohlcv, ValidationResult


def _make_df(n=50, base_price=1900.0, seed=42):
    """Synthetic OHLCV DataFrame as normalize() would produce it.
    Constructed so OHLC relationships are always valid.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    close = base_price + np.cumsum(rng.normal(0, 2, n))
    open_ = close * rng.uniform(0.999, 1.001, n)
    high  = np.maximum(open_, close) * rng.uniform(1.0001, 1.002, n)
    low   = np.minimum(open_, close) * rng.uniform(0.998, 0.9999, n)
    df = pd.DataFrame({
        "timestamp_utc": idx.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "open":   open_,
        "high":   high,
        "low":    low,
        "close":  close,
        "volume": rng.integers(1000, 50000, n).astype(float),
    })
    return df


def test_valid_ohlcv_passes():
    df = _make_df()
    valid_df, result = validate_ohlcv(df, "GC=F", "yfinance", "1h")
    assert result.status == "OK"
    assert result.rows_received == 50
    assert result.rows_valid == 50
    assert result.rows_invalid == 0
    assert len(valid_df) == 50


def test_empty_dataframe_returns_failed():
    _, result = validate_ohlcv(pd.DataFrame(), "GC=F", "yfinance", "1h")
    assert result.status == "FAILED"
    assert result.rows_received == 0
    assert any("Empty" in i for i in result.issues)


def test_missing_close_column_returns_failed():
    df = _make_df().drop(columns=["close"])
    _, result = validate_ohlcv(df, "GC=F", "yfinance", "1h")
    assert result.status == "FAILED"


def test_rows_with_missing_close_excluded():
    df = _make_df(n=10)
    df.loc[3, "close"] = float("nan")
    df.loc[7, "close"] = float("nan")
    valid_df, result = validate_ohlcv(df, "GC=F", "yfinance", "1h")
    assert result.missing_close == 2
    assert result.rows_invalid == 2
    assert len(valid_df) == 8
    assert result.status == "WARNINGS"


def test_negative_close_excluded():
    df = _make_df(n=10)
    df.loc[4, "close"] = -5.0
    valid_df, result = validate_ohlcv(df, "GC=F", "yfinance", "1h")
    assert result.negative_price_rows == 1
    assert result.rows_invalid == 1
    assert len(valid_df) == 9
    assert result.status == "WARNINGS"


def test_zero_close_excluded():
    df = _make_df(n=10)
    df.loc[2, "close"] = 0.0
    valid_df, result = validate_ohlcv(df, "GC=F", "yfinance", "1h")
    assert result.negative_price_rows == 1
    assert len(valid_df) == 9


def test_invalid_ohlc_flagged_but_row_kept():
    """high < low → flagged but the row stays in valid_df."""
    df = _make_df(n=10)
    # Swap high and low for row 5 to force invalid OHLC
    df.loc[5, "high"] = 100.0
    df.loc[5, "low"] = 2000.0
    valid_df, result = validate_ohlcv(df, "GC=F", "yfinance", "1h")
    assert result.invalid_ohlc_rows >= 1
    assert result.rows_invalid == 0        # still stored
    assert len(valid_df) == 10             # all rows present
    assert result.status == "WARNINGS"


def test_duplicate_timestamps_deduplicated():
    df = _make_df(n=10)
    # Duplicate row 3
    df = pd.concat([df, df.iloc[[3]]], ignore_index=True)
    valid_df, result = validate_ohlcv(df, "GC=F", "yfinance", "1h")
    assert result.duplicate_timestamps == 1
    assert len(valid_df) == 10    # duplicate removed
    assert result.status == "WARNINGS"


def test_missing_other_ohlc_row_retained():
    """Rows where open/high/low are NaN but close is valid must be kept (never fabricated)."""
    df = _make_df(n=10)
    df.loc[4, "open"] = float("nan")
    df.loc[4, "high"] = float("nan")
    df.loc[4, "low"] = float("nan")
    valid_df, result = validate_ohlcv(df, "USDINR=X", "yfinance", "1h")
    assert result.missing_other_ohlc == 1
    assert result.rows_invalid == 0    # row is retained
    assert len(valid_df) == 10         # all 10 rows present
    assert result.status == "WARNINGS"
    assert any("open/high/low" in i for i in result.issues)


def test_date_range_populated():
    df = _make_df(n=20)
    _, result = validate_ohlcv(df, "GC=F", "yfinance", "1h")
    assert result.date_range is not None
    assert len(result.date_range) == 2
    assert result.date_range[0] < result.date_range[1]
