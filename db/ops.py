"""
Typed DB insert functions for all 11 OPINION tables.

Rules:
  - All audit/history tables (feature_snapshots, forecast_history,
    forecast_outcomes, human_verification, backtest_runs, backtest_results,
    data_source_log, decision_history, news_events, data_quality_alerts)
    are INSERT-only. No UPDATE or DELETE ever.
  - model_registry: aggregate metrics and status MAY be updated via
    update_model_metrics(). model_id, parameters, library_version,
    training_cutoff, created_at are immutable after insert.
  - Verification always INSERTs a new forecast_outcomes row.
  - Human review always INSERTs a new human_verification row (revision++).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from config import DB_PATH


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── feature_snapshots ─────────────────────────────────────────────────────────

def insert_feature_snapshot(snap: dict[str, Any]) -> int:
    """Insert and return new id. snap keys match column names."""
    cols = list(snap.keys())
    placeholders = ", ".join("?" * len(cols))
    sql = f"INSERT INTO feature_snapshots ({', '.join(cols)}) VALUES ({placeholders})"
    with _conn() as conn:
        cur = conn.execute(sql, list(snap.values()))
        return cur.lastrowid


# ── model_registry ────────────────────────────────────────────────────────────

def insert_model(model: dict[str, Any]) -> None:
    if "created_at" not in model:
        model["created_at"] = _now()
    cols = list(model.keys())
    sql = f"INSERT OR IGNORE INTO model_registry ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})"
    with _conn() as conn:
        conn.execute(sql, list(model.values()))


def update_model_metrics(
    model_id: str,
    *,
    mae: float | None = None,
    rmse: float | None = None,
    smape: float | None = None,
    directional_accuracy: float | None = None,
    interval_coverage: float | None = None,
    cumulative_score: int | None = None,
    status: str | None = None,
) -> None:
    """Only mutable fields may be set here. Immutable fields are never touched."""
    updates: list[tuple[str, Any]] = []
    for col, val in [
        ("mae", mae), ("rmse", rmse), ("smape", smape),
        ("directional_accuracy", directional_accuracy),
        ("interval_coverage", interval_coverage),
        ("cumulative_score", cumulative_score),
        ("status", status),
    ]:
        if val is not None:
            updates.append((col, val))
    if not updates:
        return
    set_clause = ", ".join(f"{c}=?" for c, _ in updates)
    vals = [v for _, v in updates] + [model_id]
    with _conn() as conn:
        conn.execute(f"UPDATE model_registry SET {set_clause} WHERE model_id=?", vals)


# ── forecast_history ──────────────────────────────────────────────────────────

def insert_forecast(forecast: dict[str, Any]) -> None:
    """Append-only. forecast_id must be a UUID string supplied by caller."""
    if "created_at" not in forecast:
        forecast["created_at"] = _now()
    cols = list(forecast.keys())
    sql = f"INSERT INTO forecast_history ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})"
    with _conn() as conn:
        conn.execute(sql, list(forecast.values()))


# ── forecast_outcomes ─────────────────────────────────────────────────────────

def insert_forecast_outcome(outcome: dict[str, Any]) -> None:
    """
    Append-only. Verification always INSERTs a new row; never UPDATEs.
    outcome must include forecast_id.
    """
    if "outcome_verified_at" not in outcome:
        outcome["outcome_verified_at"] = _now()
    cols = list(outcome.keys())
    sql = f"INSERT INTO forecast_outcomes ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})"
    with _conn() as conn:
        conn.execute(sql, list(outcome.values()))


def get_pending_forecasts() -> list[dict]:
    """Return forecasts whose target_timestamp has elapsed and have no outcome yet."""
    now = _now()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT fh.* FROM forecast_history fh
               WHERE fh.target_timestamp <= ?
               AND NOT EXISTS (
                   SELECT 1 FROM forecast_outcomes fo
                   WHERE fo.forecast_id = fh.forecast_id
               )""",
            (now,),
        ).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM forecast_history LIMIT 0").description or []]
        # re-fetch with description
        rows2 = conn.execute(
            """SELECT fh.* FROM forecast_history fh
               WHERE fh.target_timestamp <= ?
               AND NOT EXISTS (
                   SELECT 1 FROM forecast_outcomes fo
                   WHERE fo.forecast_id = fh.forecast_id
               )""",
            (now,),
        )
        cols2 = [d[0] for d in rows2.description]
        return [dict(zip(cols2, r)) for r in rows2.fetchall()]


# ── human_verification ────────────────────────────────────────────────────────

def insert_human_verification(hv: dict[str, Any]) -> None:
    """
    Append-only. Each review creates a new row with revision = max(revision)+1.
    Never updates an existing row.
    """
    if "reviewed_at" not in hv:
        hv["reviewed_at"] = _now()
    forecast_id = hv["forecast_id"]
    with _conn() as conn:
        row = conn.execute(
            "SELECT MAX(revision) FROM human_verification WHERE forecast_id=?",
            (forecast_id,),
        ).fetchone()
        max_rev = row[0] or 0
        hv["revision"] = max_rev + 1
        cols = list(hv.keys())
        conn.execute(
            f"INSERT INTO human_verification ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})",
            list(hv.values()),
        )


# ── backtest_runs / backtest_results ──────────────────────────────────────────

def insert_backtest_run(run: dict[str, Any]) -> None:
    if "started_at" not in run:
        run["started_at"] = _now()
    cols = list(run.keys())
    with _conn() as conn:
        conn.execute(
            f"INSERT INTO backtest_runs ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})",
            list(run.values()),
        )


def complete_backtest_run(run_id: str, status: str = "completed") -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE backtest_runs SET completed_at=?, status=? WHERE run_id=?",
            (_now(), status, run_id),
        )


def insert_backtest_result(result: dict[str, Any]) -> None:
    cols = list(result.keys())
    with _conn() as conn:
        conn.execute(
            f"INSERT INTO backtest_results ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})",
            list(result.values()),
        )


# ── decision_history ──────────────────────────────────────────────────────────

def insert_decision(decision: dict[str, Any]) -> None:
    if "created_at" not in decision:
        decision["created_at"] = _now()
    cols = list(decision.keys())
    with _conn() as conn:
        conn.execute(
            f"INSERT INTO decision_history ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})",
            list(decision.values()),
        )


# ── news_events ───────────────────────────────────────────────────────────────

def insert_news_event(event: dict[str, Any]) -> None:
    """
    Append-only. LLM re-analysis of the same headline creates a new row
    with original_news_id set. Never updates existing rows.
    """
    if "fetched_at" not in event:
        event["fetched_at"] = _now()
    cols = list(event.keys())
    with _conn() as conn:
        conn.execute(
            f"INSERT OR IGNORE INTO news_events ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})",
            list(event.values()),
        )


def news_hash_exists(content_hash: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM news_events WHERE content_hash=? AND original_news_id IS NULL LIMIT 1",
            (content_hash,),
        ).fetchone()
    return row is not None


# ── data_quality_alerts ───────────────────────────────────────────────────────

def insert_data_quality_alert(alert: dict[str, Any]) -> None:
    if "detected_at" not in alert:
        alert["detected_at"] = _now()
    cols = list(alert.keys())
    with _conn() as conn:
        conn.execute(
            f"INSERT INTO data_quality_alerts ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})",
            list(alert.values()),
        )


# ── Read helpers ──────────────────────────────────────────────────────────────

def get_forecast_verification_status(forecast_id: str) -> str:
    """Derived at query time — never stored in forecast_history."""
    with _conn() as conn:
        hv = conn.execute(
            "SELECT status FROM human_verification WHERE forecast_id=? ORDER BY revision DESC LIMIT 1",
            (forecast_id,),
        ).fetchone()
        if hv:
            return hv[0]
        fo = conn.execute(
            "SELECT direction_correct FROM forecast_outcomes WHERE forecast_id=? LIMIT 1",
            (forecast_id,),
        ).fetchone()
        if fo and fo[0] is not None:
            return "VERIFIED"
    return "PENDING"


def list_forecasts(asset: str | None = None, horizon_code: str | None = None, limit: int = 200) -> list[dict]:
    where, params = [], []
    if asset:
        where.append("asset=?"); params.append(asset)
    if horizon_code:
        where.append("horizon_code=?"); params.append(horizon_code)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM forecast_history {clause} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        )
        cols = [d[0] for d in rows.description]
        return [dict(zip(cols, r)) for r in rows.fetchall()]
