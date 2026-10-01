"""Tests for models/grader.py scoring logic — no yfinance calls."""
import sqlite3
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

# Point at a temp DB so tests don't touch opinion.db
@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db = tmp_path / "test_opinion.db"
    monkeypatch.setenv("OPINION_DB", str(db))
    # Re-import config so DB_PATH picks up the env var
    import importlib, config, db.schema as schema, db.ops as ops
    importlib.reload(config)
    importlib.reload(schema)
    importlib.reload(ops)
    schema.init_db(db)
    yield db


def _insert_forecast(db_path, forecast_id, asset, predicted_direction, price_at_forecast, target_ts):
    """Insert a minimal forecast row directly."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT INTO feature_snapshots
            (created_at, dataset_version, feature_version)
            VALUES (?,?,?)
        """, (datetime.now(timezone.utc).isoformat(), "1.0.0", "1.0.0"))
        snap_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("""
            INSERT INTO forecast_history
            (forecast_id, created_at, forecast_origin, target_timestamp,
             horizon_definition, asset, currency, price_type, horizon_code,
             horizon_minutes, price_at_forecast, predicted_price,
             predicted_direction, model_id, model_version,
             dataset_version, feature_version, feature_snapshot_id, training_cutoff)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            forecast_id,
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            target_ts,
            "test horizon",
            asset, "USD", "FUTURES", "1h", 60,
            price_at_forecast,
            price_at_forecast * 1.01,  # predicted price slightly above
            predicted_direction,
            "test_model", "0.0.1",
            "1.0.0", "1.0.0", snap_id,
            datetime.now(timezone.utc).isoformat(),
        ))


def test_correct_direction_scores_plus3(temp_db, monkeypatch):
    from config import SCORE_CORRECT
    from models import grader

    fc_id = "test-correct-001"
    past_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    _insert_forecast(temp_db, fc_id, "XAU", "UP", 1900.0, past_ts)

    # Mock yfinance to return a price higher than 1900 (actual_direction=UP → correct)
    with patch.object(grader, "_fetch_actual_price", return_value=(1950.0, "LIVE")):
        outcomes = grader.grade_pending()

    assert len(outcomes) == 1
    assert outcomes[0]["direction_correct"] == 1
    assert outcomes[0]["score"] == SCORE_CORRECT  # +3


def test_incorrect_direction_scores_minus6(temp_db, monkeypatch):
    from config import SCORE_INCORRECT
    from models import grader

    fc_id = "test-incorrect-001"
    past_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    _insert_forecast(temp_db, fc_id, "XAU", "UP", 1900.0, past_ts)

    # Actual price LOWER than 1900 → DOWN → predicted UP → incorrect
    with patch.object(grader, "_fetch_actual_price", return_value=(1850.0, "LIVE")):
        outcomes = grader.grade_pending()

    assert len(outcomes) == 1
    assert outcomes[0]["direction_correct"] == 0
    assert outcomes[0]["score"] == SCORE_INCORRECT  # -6


def test_unavailable_price_not_graded(temp_db, monkeypatch):
    from models import grader

    fc_id = "test-unavail-001"
    past_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    _insert_forecast(temp_db, fc_id, "XAU", "UP", 1900.0, past_ts)

    with patch.object(grader, "_fetch_actual_price", return_value=(None, "UNAVAILABLE")):
        outcomes = grader.grade_pending()

    assert outcomes == [], "Should not grade when actual price unavailable"


def test_already_graded_not_regraded(temp_db, monkeypatch):
    from models import grader
    from db.ops import insert_forecast_outcome

    fc_id = "test-already-001"
    past_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    _insert_forecast(temp_db, fc_id, "XAU", "UP", 1900.0, past_ts)

    # Insert an existing outcome
    insert_forecast_outcome({
        "forecast_id": fc_id,
        "actual_price": 1950.0,
        "actual_direction": "UP",
        "direction_correct": 1,
        "score": 3,
    })

    with patch.object(grader, "_fetch_actual_price", return_value=(1950.0, "LIVE")):
        outcomes = grader.grade_pending()

    assert outcomes == [], "Already-graded forecast must not be graded again"


def test_flat_direction_deadband(temp_db, monkeypatch):
    """Price within ±0.01% deadband → FLAT direction."""
    from models import grader

    fc_id = "test-flat-001"
    past_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    base = 1900.0
    _insert_forecast(temp_db, fc_id, "XAU", "FLAT", base, past_ts)

    # actual price within 0.01% of 1900 → FLAT
    flat_price = base * 1.000005  # 0.0005% change — within deadband
    with patch.object(grader, "_fetch_actual_price", return_value=(flat_price, "LIVE")):
        outcomes = grader.grade_pending()

    assert len(outcomes) == 1
    assert outcomes[0]["actual_direction"] == "FLAT"
    assert outcomes[0]["direction_correct"] == 1  # predicted FLAT, actual FLAT
