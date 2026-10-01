"""
Tests for data/news_features.py — FinBERT backend + sentiment aggregation.
All use the StubFinBERTBackend; no model weights required.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from db.schema import init_db
from data.news_features import (
    SentimentResult,
    StubFinBERTBackend,
    score_with_cache,
    aggregate_sentiment,
    load_news,
    attach_news_features,
    _WINDOWS,
)


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_news.db"
    init_db(db_path)
    return db_path


def _insert_news(db_path, news_id, content_hash, headline, published_at, asset="XAU"):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO news_events "
            "(news_id, content_hash, headline, published_at, fetched_at, "
            " source, asset, status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (news_id, content_hash, headline,
             published_at.isoformat(), datetime.now(timezone.utc).isoformat(),
             "test", asset, "RAW"),
        )


# ── SentimentResult ──────────────────────────────────────────────────────────


def test_sentiment_score_formula():
    s = SentimentResult(positive=0.7, negative=0.2, neutral=0.1)
    assert s.score == pytest.approx(0.5)


def test_stub_backend_returns_uniform():
    stub = StubFinBERTBackend()
    results = stub.score_batch(["Gold prices rise", "Silver falls"])
    assert len(results) == 2
    for r in results:
        assert r.positive == pytest.approx(1/3, rel=1e-6)
        assert r.negative == pytest.approx(1/3, rel=1e-6)
        assert r.neutral  == pytest.approx(1/3, rel=1e-6)


def test_stub_backend_empty_input():
    stub = StubFinBERTBackend()
    assert stub.score_batch([]) == []


# ── FinBERT cache ─────────────────────────────────────────────────────────────


def test_finbert_cache_stores_result(db):
    stub = StubFinBERTBackend()
    arts = [{"content_hash": "abc123", "headline": "Gold hits record high"}]
    r1 = score_with_cache(arts, stub, db_path=db)
    # Second call — must come from cache, not re-run FinBERT
    r2 = score_with_cache(arts, stub, db_path=db)
    assert r1["abc123"].positive == pytest.approx(r2["abc123"].positive)
    # Verify it's in the DB
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT * FROM finbert_cache WHERE content_hash='abc123'"
        ).fetchone()
    assert row is not None


def test_finbert_cache_key_includes_model_version(db):
    """Different model_version → different cache entry."""
    class V2Stub(StubFinBERTBackend):
        @property
        def model_version(self):
            return "99"

    arts = [{"content_hash": "xyz", "headline": "Silver falls"}]
    stub_v1 = StubFinBERTBackend()
    stub_v2 = V2Stub()
    score_with_cache(arts, stub_v1, db_path=db)
    score_with_cache(arts, stub_v2, db_path=db)
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT model_version FROM finbert_cache WHERE content_hash='xyz'"
        ).fetchall()
    versions = {r[0] for r in rows}
    assert "0" in versions and "99" in versions


# ── News loading ──────────────────────────────────────────────────────────────


def test_load_news_empty_when_no_data(db):
    df = load_news(asset="XAU", db_path=db)
    assert df.empty


def test_load_news_returns_parseable_dates(db):
    t = datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc)
    _insert_news(db, "n1", "hash1", "Gold up", t)
    df = load_news(asset="XAU", db_path=db)
    assert len(df) == 1
    assert pd.api.types.is_datetime64_any_dtype(df["published_at"])
    assert df["published_at"].iloc[0].tzinfo is not None


# ── Sentiment aggregation ─────────────────────────────────────────────────────


def test_sentiment_aggregation_future_excluded(db):
    """News published AFTER the feature timestamp must NOT appear in features."""
    stub = StubFinBERTBackend()
    now = pd.Timestamp("2024-06-01 12:00:00", tz="UTC")
    future = now + pd.Timedelta("1h")

    past_art = {"content_hash": "past", "headline": "Gold rises"}
    future_art = {"content_hash": "future", "headline": "Silver falls"}

    news_data = [
        {"content_hash": "past", "headline": "Gold rises",
         "published_at": now - pd.Timedelta("2h")},
        {"content_hash": "future", "headline": "Silver falls",
         "published_at": future},
    ]
    news_df = pd.DataFrame(news_data)
    news_df["published_at"] = pd.to_datetime(news_df["published_at"], utc=True)

    sentiment_map = {
        "past": SentimentResult(0.8, 0.1, 0.1),
        "future": SentimentResult(0.1, 0.8, 0.1),
    }

    ts_index = pd.DatetimeIndex([now])
    agg = aggregate_sentiment(ts_index, news_df, sentiment_map)

    # Only 1 article in 6h window (the past one, not the future one)
    assert agg["news_count_6h"].iloc[0] == 1.0


def test_sentiment_aggregation_zero_news():
    """Empty news → news_count_*h = 0 for all windows."""
    ts = pd.DatetimeIndex([pd.Timestamp("2024-01-01 12:00", tz="UTC")])
    agg = aggregate_sentiment(ts, pd.DataFrame(), {})
    for w in _WINDOWS:
        assert agg[f"news_count_{w}h"].iloc[0] == 0.0


# ── Integration: attach_news_features ────────────────────────────────────────


def test_attach_news_features_adds_columns(db):
    stub = StubFinBERTBackend()
    idx = pd.date_range("2024-01-01", periods=10, freq="h", tz="UTC")
    df = pd.DataFrame({"close": 1900.0}, index=idx)
    df = attach_news_features(df, asset="XAU", backend=stub, db_path=db)
    for w in _WINDOWS:
        assert f"news_count_{w}h" in df.columns
        assert f"sentiment_mean_{w}h" in df.columns
