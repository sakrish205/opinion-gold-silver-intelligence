"""Tests for data/ingestion.py — yfinance mocked, no network."""
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from db.schema import init_db


def _make_yf_df(n=100, base_price=1900.0, seed=42):
    """Synthetic DataFrame mimicking yfinance Ticker.history() output."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    close = base_price + np.cumsum(rng.normal(0, 2, n))
    return pd.DataFrame(
        {
            "Open":   close * rng.uniform(0.999, 1.001, n),
            "High":   close * rng.uniform(1.000, 1.002, n),
            "Low":    close * rng.uniform(0.998, 1.000, n),
            "Close":  close,
            "Volume": rng.integers(1000, 50000, n).astype(float),
            "Dividends": 0.0,
            "Stock Splits": 0.0,
        },
        index=idx,
    )


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_ingestion.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def mock_yf(db):
    """Patch yfinance and return the mock history callable."""
    yf_df = _make_yf_df()
    with patch("data.ingestion.yf.Ticker") as mock_ticker_cls:
        mock_inst = MagicMock()
        mock_ticker_cls.return_value = mock_inst
        mock_inst.history.return_value = yf_df
        yield mock_inst, yf_df


def test_ingest_stores_valid_rows(db, mock_yf):
    from data.ingestion import ingest_ohlcv
    mock_inst, yf_df = mock_yf
    result = ingest_ohlcv("GC=F", "XAU", "FUTURES", db_path=db)
    assert result["rows_received"] == len(yf_df)
    assert result["rows_stored"] > 0
    assert result["validation_status"] in ("OK", "WARNINGS")


def test_ingest_idempotent(db, mock_yf):
    """Running twice must not create duplicate rows."""
    from data.ingestion import ingest_ohlcv
    ingest_ohlcv("GC=F", "XAU", "FUTURES", db_path=db)
    r2 = ingest_ohlcv("GC=F", "XAU", "FUTURES", db_path=db)
    # Second run: all rows are duplicates (same yf mock returns same data)
    assert r2["rows_stored"] == 0
    assert r2["rows_duplicate"] == r2["rows_received"]


def test_ingest_skips_negative_close(db):
    """Rows with negative close must not be stored."""
    from data.ingestion import ingest_ohlcv
    bad_df = _make_yf_df(n=10)
    bad_df.iloc[0, bad_df.columns.get_loc("Close")] = -1.0
    with patch("data.ingestion.yf.Ticker") as mock_cls:
        inst = MagicMock()
        mock_cls.return_value = inst
        inst.history.return_value = bad_df
        result = ingest_ohlcv("GC=F", "XAU", "FUTURES", db_path=db)
    assert result["rows_stored"] == 9
    assert result["rows_invalid"] == 1


def test_get_latest_stored_ts_none_when_empty(db):
    from data.ingestion import get_latest_stored_ts
    assert get_latest_stored_ts("GC=F", "1h", db_path=db) is None


def test_get_latest_stored_ts_returns_value(db, mock_yf):
    from data.ingestion import ingest_ohlcv, get_latest_stored_ts
    ingest_ohlcv("GC=F", "XAU", "FUTURES", db_path=db)
    ts = get_latest_stored_ts("GC=F", "1h", db_path=db)
    assert ts is not None
    assert ts.tzinfo is not None  # must be timezone-aware


def test_incremental_uses_start_param(db):
    """Second call with existing data should pass `start=` to yfinance, not `period=`."""
    from data.ingestion import ingest_ohlcv
    first_df = _make_yf_df(n=50)
    # incremental batch: 10 new rows, same first row to allow INSERT OR IGNORE
    second_df = _make_yf_df(n=10, seed=99)
    calls = []

    def history_side_effect(**kwargs):
        calls.append(dict(kwargs))
        return first_df if not calls[1:] else second_df

    with patch("data.ingestion.yf.Ticker") as mock_cls:
        inst = MagicMock()
        mock_cls.return_value = inst
        inst.history.side_effect = history_side_effect
        ingest_ohlcv("GC=F", "XAU", "FUTURES", db_path=db)   # first: period=
        ingest_ohlcv("GC=F", "XAU", "FUTURES", db_path=db)   # second: start=

    assert "period" in calls[0]
    assert "start" in calls[1]


def test_ingestion_log_recorded(db, mock_yf):
    from data.ingestion import ingest_ohlcv
    ingest_ohlcv("GC=F", "XAU", "FUTURES", db_path=db)
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT * FROM ingestion_log WHERE symbol='GC=F'").fetchall()
    assert len(rows) == 1


def test_no_data_from_provider_logged(db):
    from data.ingestion import ingest_ohlcv
    with patch("data.ingestion.yf.Ticker") as mock_cls:
        inst = MagicMock()
        mock_cls.return_value = inst
        inst.history.return_value = pd.DataFrame()   # empty → no data
        result = ingest_ohlcv("GC=F", "XAU", "FUTURES", db_path=db)
    assert result["rows_stored"] == 0
    assert result["validation_status"] == "FAILED"
    # Failure must still be logged
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT * FROM ingestion_log WHERE symbol='GC=F'").fetchall()
    assert len(rows) == 1
