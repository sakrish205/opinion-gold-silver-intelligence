"""
FinBERT news sentiment features.

Architecture:
  news_events table → temporal filter → FinBERTBackend.score() → finbert_cache
  → sentiment aggregation → ML features (news_count_*, sentiment_mean_*)

Leakage rule: only news with published_at <= feature_timestamp is used.
              fetched_at is never used as a proxy for publication time.

See docs/PROMPT_4_FEATURE_PLAN.md §J for the full contract.
"""
from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

MODEL_NAME = "ProsusAI/finbert"
MODEL_VERSION = "1.0"   # increment to invalidate cache


# ── Sentiment result ─────────────────────────────────────────────────────────


@dataclass
class SentimentResult:
    positive: float
    negative: float
    neutral: float

    @property
    def score(self) -> float:
        """Derived score: positive_prob - negative_prob."""
        return self.positive - self.negative


# ── Abstract backend ─────────────────────────────────────────────────────────


class FinBERTBackend(ABC):
    @abstractmethod
    def score_batch(self, texts: list[str]) -> list[SentimentResult]:
        """Score a batch of texts. Implementations must be deterministic."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def model_version(self) -> str: ...


# ── Real backend (ProsusAI/finbert via Transformers) ─────────────────────────


class TransformersFinBERT(FinBERTBackend):
    """
    Local FinBERT via HuggingFace Transformers.
    Model weights are downloaded once and cached by Transformers (~500MB).
    Inference runs on CUDA if available, else CPU.
    """
    def __init__(self) -> None:
        try:
            import torch
            from transformers import pipeline as hf_pipeline
        except ImportError as exc:
            raise RuntimeError(
                "transformers library is required for TransformersFinBERT. "
                "Install with: pip install transformers"
            ) from exc
        device = 0 if torch.cuda.is_available() else -1
        self._pipe = hf_pipeline(
            "text-classification",
            model=MODEL_NAME,
            top_k=None,
            device=device,
            truncation=True,
            max_length=512,
        )

    @property
    def model_name(self) -> str:
        return MODEL_NAME

    @property
    def model_version(self) -> str:
        return MODEL_VERSION

    def score_batch(self, texts: list[str]) -> list[SentimentResult]:
        if not texts:
            return []
        results = self._pipe(texts, batch_size=32)
        out = []
        for item in results:
            probs = {d["label"].lower(): d["score"] for d in item}
            out.append(SentimentResult(
                positive=probs.get("positive", 0.0),
                negative=probs.get("negative", 0.0),
                neutral=probs.get("neutral", 0.0),
            ))
        return out


# ── Stub backend (for tests / when transformers not available) ───────────────


class StubFinBERTBackend(FinBERTBackend):
    """
    Deterministic stub that returns uniform probabilities.
    Used in tests and as a fallback when transformers is not installed.
    Never used in production feature generation.
    """
    @property
    def model_name(self) -> str:
        return "stub"

    @property
    def model_version(self) -> str:
        return "0"

    def score_batch(self, texts: list[str]) -> list[SentimentResult]:
        return [SentimentResult(positive=1/3, negative=1/3, neutral=1/3)
                for _ in texts]


def get_backend(force_stub: bool = False) -> FinBERTBackend:
    """Return the best available backend. Tests should pass force_stub=True."""
    if force_stub:
        return StubFinBERTBackend()
    try:
        return TransformersFinBERT()
    except Exception:
        return StubFinBERTBackend()


# ── SQLite cache ─────────────────────────────────────────────────────────────


def _db(db_path=None) -> Path:
    from config import DB_PATH
    return Path(db_path) if db_path else DB_PATH


def score_with_cache(
    articles: list[dict],   # each must have 'content_hash', 'headline'
    backend: FinBERTBackend,
    db_path=None,
) -> dict[str, SentimentResult]:
    """
    Score articles via backend, using SQLite cache to avoid re-running FinBERT.
    Cache key: (content_hash, model_name, model_version).
    Returns {content_hash: SentimentResult}.
    """
    dbp = _db(db_path)
    results: dict[str, SentimentResult] = {}

    with sqlite3.connect(dbp) as conn:
        # Look up cached results
        uncached = []
        for art in articles:
            ch = art["content_hash"]
            row = conn.execute(
                "SELECT positive_prob, negative_prob, neutral_prob "
                "FROM finbert_cache "
                "WHERE content_hash=? AND model_name=? AND model_version=?",
                (ch, backend.model_name, backend.model_version),
            ).fetchone()
            if row:
                results[ch] = SentimentResult(
                    positive=row[0], negative=row[1], neutral=row[2]
                )
            else:
                uncached.append(art)

    if not uncached:
        return results

    # Run FinBERT on uncached articles
    texts = [a["headline"] for a in uncached]
    scores = backend.score_batch(texts)
    now = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(dbp) as conn:
        for art, s in zip(uncached, scores):
            ch = art["content_hash"]
            results[ch] = s
            conn.execute(
                "INSERT OR IGNORE INTO finbert_cache "
                "(content_hash, model_name, model_version, "
                " positive_prob, negative_prob, neutral_prob, cached_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (ch, backend.model_name, backend.model_version,
                 s.positive, s.negative, s.neutral, now),
            )

    return results


# ── News loading ─────────────────────────────────────────────────────────────


def load_news(asset: str | None = None, db_path=None) -> pd.DataFrame:
    """
    Load news_events from SQLite.
    Returns DataFrame with columns: news_id, content_hash, headline,
    published_at (UTC-aware), fetched_at, asset, relevance.
    Only rows where published_at is parseable are included.
    """
    dbp = _db(db_path)
    try:
        with sqlite3.connect(dbp) as conn:
            df = pd.read_sql_query(
                "SELECT news_id, content_hash, headline, "
                "published_at, fetched_at, asset, relevance "
                "FROM news_events "
                "WHERE headline IS NOT NULL AND content_hash IS NOT NULL",
                conn,
            )
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return df

    # Parse published_at; rows where it fails are excluded from time features
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    df = df[df["published_at"].notna()].copy()

    # Optionally filter by asset relevance
    if asset and "asset" in df.columns:
        mask = df["asset"].isna() | (df["asset"].str.upper() == asset.upper())
        df = df[mask]

    return df.reset_index(drop=True)


# ── Sentiment aggregation ────────────────────────────────────────────────────

_WINDOWS = (1, 6, 12, 24, 48)


def aggregate_sentiment(
    feature_timestamps: pd.DatetimeIndex,
    news_df: pd.DataFrame,
    sentiment_map: dict[str, SentimentResult],
) -> pd.DataFrame:
    """
    For each feature timestamp t, aggregate news published in [t-W, t].
    Only articles with published_at <= t are used (strict causal).

    Returns a DataFrame indexed by feature_timestamps with columns:
      news_count_{W}h, sentiment_mean_{W}h,
      sentiment_pos_ratio_{W}h (for W in _WINDOWS)
    """
    if news_df.empty or not sentiment_map:
        cols = (
            [f"news_count_{w}h" for w in _WINDOWS]
            + [f"sentiment_mean_{w}h" for w in _WINDOWS]
            + [f"sentiment_pos_ratio_{w}h" for w in _WINDOWS]
        )
        return pd.DataFrame(0.0, index=feature_timestamps, columns=cols)

    # Attach sentiment scores to news rows
    news = news_df.copy()
    news["score"] = news["content_hash"].map(
        lambda ch: sentiment_map.get(ch, SentimentResult(1/3, 1/3, 1/3)).score
    )
    news["is_positive"] = news["content_hash"].map(
        lambda ch: 1.0 if sentiment_map.get(ch, SentimentResult(0,0,0)).positive > 1/3 else 0.0
    )
    news_sorted = news.sort_values("published_at")
    pub_ts = news_sorted["published_at"].values  # numpy datetime64[ns]
    scores = news_sorted["score"].values
    is_pos = news_sorted["is_positive"].values

    records = []
    for ts in feature_timestamps:
        row: dict[str, float] = {}
        for w in _WINDOWS:
            cutoff = ts - pd.Timedelta(f"{w}h")
            # Articles published in (ts-W, ts] — strictly causal
            mask = (pub_ts > cutoff.to_datetime64()) & (pub_ts <= ts.to_datetime64())
            cnt = mask.sum()
            row[f"news_count_{w}h"] = float(cnt)
            if cnt > 0:
                row[f"sentiment_mean_{w}h"] = float(scores[mask].mean())
                row[f"sentiment_pos_ratio_{w}h"] = float(is_pos[mask].mean())
            else:
                row[f"sentiment_mean_{w}h"] = float("nan")
                row[f"sentiment_pos_ratio_{w}h"] = float("nan")
        records.append(row)

    return pd.DataFrame(records, index=feature_timestamps)


# ── Top-level: build news features for a feature DataFrame ──────────────────


def attach_news_features(
    feature_df: pd.DataFrame,
    asset: str,
    backend: FinBERTBackend,
    db_path=None,
) -> pd.DataFrame:
    """
    Score all relevant news via FinBERT (cached) and aggregate into
    time-aligned features, then join onto feature_df.

    Temporal rule: only news with published_at <= feature_timestamp.
    """
    news_df = load_news(asset=asset, db_path=db_path)

    if news_df.empty:
        # Fill with zeros — no news available
        for w in _WINDOWS:
            feature_df[f"news_count_{w}h"] = 0.0
            feature_df[f"sentiment_mean_{w}h"] = float("nan")
            feature_df[f"sentiment_pos_ratio_{w}h"] = float("nan")
        return feature_df

    articles = news_df[["content_hash", "headline"]].to_dict("records")
    sentiment_map = score_with_cache(articles, backend, db_path=db_path)

    sentiment_df = aggregate_sentiment(
        feature_df.index, news_df, sentiment_map
    )
    for col in sentiment_df.columns:
        feature_df[col] = sentiment_df[col].values

    return feature_df
