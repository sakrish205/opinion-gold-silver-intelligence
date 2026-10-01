"""
Raw market data ingestion.

Downloads OHLCV from yfinance and stores it in raw_market_data (SQLite).
Idempotent: re-running does not create duplicates (INSERT OR IGNORE on UNIQUE key).

Entry points:
  ingest_ohlcv(symbol, asset, data_type, ...)  — one symbol
  backfill(lookback_days, interval)             — all symbols, full history
  update_incremental(interval)                  — all symbols, only new bars
"""
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

_SOURCE = "yfinance"


def _cfg():
    """Lazy config read so env-var overrides work in tests."""
    import config as c
    return c


def _symbols() -> list[dict]:
    c = _cfg()
    rows = [
        {"symbol": c.METAL_FUTURES_TICKERS[a], "asset": a, "data_type": "FUTURES"}
        for a in c.ASSETS
    ]
    rows += [
        {"symbol": fx.yf_ticker, "asset": fx.pair, "data_type": "FX"}
        for fx in c.FX_PAIRS
    ]
    return rows


def _db(db_path=None) -> Path:
    return Path(db_path) if db_path else _cfg().DB_PATH


def _nan_to_none(v):
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


# ── Fetch ────────────────────────────────────────────────────────────────────


def _fetch(symbol: str, interval: str, lookback_days: int = 730,
           since: datetime | None = None) -> pd.DataFrame | None:
    try:
        ticker = yf.Ticker(symbol)
        if since is not None:
            start = (since - timedelta(hours=1)).strftime("%Y-%m-%d")
            df = ticker.history(start=start, interval=interval)
        else:
            df = ticker.history(period=f"{lookback_days}d", interval=interval)
        return df if (df is not None and not df.empty) else None
    except Exception:
        return None


# ── Normalise ────────────────────────────────────────────────────────────────


def _normalize(df: pd.DataFrame, symbol: str, asset: str,
               data_type: str, interval: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    df.index = pd.to_datetime(df.index, utc=True)

    keep = {c: c.lower() for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns}
    out = df[list(keep)].rename(columns=keep).copy()

    out["timestamp_utc"] = out.index.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    out["symbol"] = symbol
    out["asset"] = asset
    out["data_type"] = data_type
    out["interval"] = interval
    out["source"] = _SOURCE
    out["ingested_at"] = now
    return out.reset_index(drop=True)


# ── Store ────────────────────────────────────────────────────────────────────

_COLS = ["symbol", "asset", "data_type", "interval", "timestamp_utc",
         "open", "high", "low", "close", "volume", "source", "ingested_at"]


def _store(df: pd.DataFrame, symbol: str, interval: str,
           db_path=None) -> tuple[int, int]:
    """INSERT OR IGNORE rows. Returns (rows_stored, rows_duplicate)."""
    if df.empty:
        return 0, 0
    # Guard: close must be present and positive (validate_ohlcv already enforces this)
    df = df.dropna(subset=["close"])
    df = df[df["close"] > 0]
    if df.empty:
        return 0, 0

    rows = [
        tuple(_nan_to_none(row.get(c)) for c in _COLS)
        for _, row in df.iterrows()
    ]
    ph = ",".join("?" * len(_COLS))
    sql = f"INSERT OR IGNORE INTO raw_market_data ({','.join(_COLS)}) VALUES ({ph})"

    dbp = _db(db_path)
    with sqlite3.connect(dbp) as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM raw_market_data WHERE symbol=? AND interval=?",
            (symbol, interval),
        ).fetchone()[0]
        conn.executemany(sql, rows)
        after = conn.execute(
            "SELECT COUNT(*) FROM raw_market_data WHERE symbol=? AND interval=?",
            (symbol, interval),
        ).fetchone()[0]

    stored = after - before
    return stored, len(rows) - stored


# ── Ingestion log ────────────────────────────────────────────────────────────


def _log(summary: dict, db_path=None) -> None:
    cols = ["ingested_at", "symbol", "asset", "interval", "source",
            "first_timestamp", "last_timestamp", "rows_received",
            "rows_stored", "rows_duplicate", "rows_invalid",
            "validation_status", "error_message"]
    vals = [summary.get(c) for c in cols]
    dbp = _db(db_path)
    with sqlite3.connect(dbp) as conn:
        conn.execute(
            f"INSERT INTO ingestion_log ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
            vals,
        )


# ── Public API ───────────────────────────────────────────────────────────────


def get_latest_stored_ts(symbol: str, interval: str,
                         db_path=None) -> datetime | None:
    """Return the most recent UTC timestamp stored for a symbol, or None."""
    dbp = _db(db_path)
    with sqlite3.connect(dbp) as conn:
        row = conn.execute(
            "SELECT MAX(timestamp_utc) FROM raw_market_data WHERE symbol=? AND interval=?",
            (symbol, interval),
        ).fetchone()
    if row and row[0]:
        return pd.to_datetime(row[0], utc=True).to_pydatetime()
    return None


def ingest_ohlcv(
    symbol: str,
    asset: str,
    data_type: str,
    interval: str = "1h",
    lookback_days: int = 730,
    db_path=None,
) -> dict[str, Any]:
    """
    Download, validate, and store OHLCV data for one symbol.
    Idempotent — safe to call repeatedly.

    Returns a summary dict with ingestion metadata.
    """
    from data.validation import validate_ohlcv

    now = datetime.now(timezone.utc).isoformat()
    latest_ts = get_latest_stored_ts(symbol, interval, db_path=db_path)

    raw_df = _fetch(symbol, interval, lookback_days=lookback_days, since=latest_ts)

    if raw_df is None:
        summary = {
            "ingested_at": now, "symbol": symbol, "asset": asset,
            "interval": interval, "source": _SOURCE,
            "first_timestamp": None, "last_timestamp": None,
            "rows_received": 0, "rows_stored": 0, "rows_duplicate": 0,
            "rows_invalid": 0, "validation_status": "FAILED",
            "error_message": "No data from provider",
        }
        _log(summary, db_path=db_path)
        return summary

    norm_df = _normalize(raw_df, symbol, asset, data_type, interval)
    valid_df, vresult = validate_ohlcv(norm_df, symbol, _SOURCE, interval)
    rows_stored, rows_dup = _store(valid_df, symbol, interval, db_path=db_path)

    first_ts = norm_df["timestamp_utc"].min() if not norm_df.empty else None
    last_ts = norm_df["timestamp_utc"].max() if not norm_df.empty else None

    summary = {
        "ingested_at": now, "symbol": symbol, "asset": asset,
        "interval": interval, "source": _SOURCE,
        "first_timestamp": str(first_ts) if first_ts else None,
        "last_timestamp": str(last_ts) if last_ts else None,
        "rows_received": vresult.rows_received,
        "rows_stored": rows_stored,
        "rows_duplicate": rows_dup,
        "rows_invalid": vresult.rows_invalid,
        "validation_status": vresult.status,
        "error_message": "; ".join(vresult.issues) if vresult.issues else None,
    }
    _log(summary, db_path=db_path)
    return summary


def backfill(lookback_days: int = 730, interval: str = "1h",
             db_path=None) -> list[dict]:
    """Full historical backfill for all configured symbols."""
    return [
        ingest_ohlcv(s["symbol"], s["asset"], s["data_type"],
                     interval=interval, lookback_days=lookback_days,
                     db_path=db_path)
        for s in _symbols()
    ]


def update_incremental(interval: str = "1h", db_path=None) -> list[dict]:
    """
    Fetch only bars newer than the latest stored timestamp for each symbol.
    If no data exists for a symbol, falls back to full 730-day backfill.
    Safe to run on a schedule.
    """
    return [
        ingest_ohlcv(s["symbol"], s["asset"], s["data_type"],
                     interval=interval, lookback_days=730,
                     db_path=db_path)
        for s in _symbols()
    ]
