"""
Create all 11 OPINION SQLite tables.
Run once on first start; safe to re-run (CREATE TABLE IF NOT EXISTS).
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "opinion.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS feature_snapshots (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    xau_usd_futures REAL,
    xau_usd_futures_type TEXT NOT NULL DEFAULT 'FUTURES',
    xau_usd_futures_source TEXT,
    xau_usd_futures_quality TEXT,
    xag_usd_futures REAL,
    xag_usd_futures_type TEXT NOT NULL DEFAULT 'FUTURES',
    xag_usd_futures_source TEXT,
    xag_usd_futures_quality TEXT,
    xau_usd_spot REAL,
    xau_usd_spot_type TEXT NOT NULL DEFAULT 'SPOT',
    xau_usd_spot_source TEXT,
    xau_usd_spot_quality TEXT,
    xag_usd_spot REAL,
    xag_usd_spot_type TEXT NOT NULL DEFAULT 'SPOT',
    xag_usd_spot_source TEXT,
    xag_usd_spot_quality TEXT,
    xau_eur REAL,
    xau_eur_type TEXT NOT NULL DEFAULT 'DERIVED',
    xau_cny REAL,
    xau_cny_type TEXT NOT NULL DEFAULT 'DERIVED',
    xau_inr REAL,
    xau_inr_type TEXT NOT NULL DEFAULT 'DERIVED',
    xag_eur REAL,
    xag_eur_type TEXT NOT NULL DEFAULT 'DERIVED',
    xag_cny REAL,
    xag_cny_type TEXT NOT NULL DEFAULT 'DERIVED',
    xag_inr REAL,
    xag_inr_type TEXT NOT NULL DEFAULT 'DERIVED',
    usd_inr REAL,
    usd_inr_source TEXT,
    usd_inr_resolution TEXT,
    usd_inr_quality TEXT,
    usd_inr_fetched_at TEXT,
    eur_inr REAL,
    eur_inr_source TEXT,
    eur_inr_resolution TEXT,
    eur_inr_quality TEXT,
    eur_inr_fetched_at TEXT,
    cny_inr REAL,
    cny_inr_source TEXT,
    cny_inr_resolution TEXT,
    cny_inr_quality TEXT,
    cny_inr_fetched_at TEXT,
    jpy_inr REAL,
    jpy_inr_source TEXT,
    jpy_inr_resolution TEXT,
    jpy_inr_quality TEXT,
    jpy_inr_fetched_at TEXT,
    chf_inr REAL,
    chf_inr_source TEXT,
    chf_inr_resolution TEXT,
    chf_inr_quality TEXT,
    chf_inr_fetched_at TEXT,
    xau_inr_cross_check_delta_pct REAL,
    xau_inr_cross_check_anomaly INTEGER NOT NULL DEFAULT 0,
    dataset_version TEXT NOT NULL,
    feature_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_registry (
    model_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_type TEXT NOT NULL,
    library TEXT NOT NULL,
    library_version TEXT NOT NULL,
    parameters TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    training_cutoff TEXT,
    evaluation_period TEXT,
    mae REAL,
    rmse REAL,
    smape REAL,
    directional_accuracy REAL,
    interval_coverage REAL,
    cumulative_score INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecast_history (
    forecast_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    forecast_origin TEXT NOT NULL,
    target_timestamp TEXT NOT NULL,
    horizon_definition TEXT NOT NULL,
    asset TEXT NOT NULL,
    currency TEXT NOT NULL,
    price_type TEXT NOT NULL,
    horizon_code TEXT NOT NULL,
    horizon_minutes INTEGER NOT NULL,
    price_at_forecast REAL NOT NULL,
    predicted_price REAL NOT NULL,
    lower_bound REAL,
    upper_bound REAL,
    predicted_direction TEXT NOT NULL,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    feature_snapshot_id INTEGER NOT NULL,
    training_cutoff TEXT NOT NULL,
    FOREIGN KEY (model_id) REFERENCES model_registry(model_id),
    FOREIGN KEY (feature_snapshot_id) REFERENCES feature_snapshots(id)
);

CREATE TABLE IF NOT EXISTS forecast_outcomes (
    id INTEGER PRIMARY KEY,
    forecast_id TEXT NOT NULL,
    actual_price REAL,
    actual_price_type TEXT,
    actual_price_source TEXT,
    actual_direction TEXT,
    absolute_error REAL,
    percentage_error REAL,
    direction_correct INTEGER,
    score INTEGER,
    interval_covered INTEGER,
    outcome_verified_at TEXT,
    FOREIGN KEY (forecast_id) REFERENCES forecast_history(forecast_id)
);

CREATE TABLE IF NOT EXISTS human_verification (
    id INTEGER PRIMARY KEY,
    forecast_id TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    machine_direction_correct INTEGER,
    machine_score INTEGER,
    human_direction_correct INTEGER,
    human_score INTEGER,
    status TEXT NOT NULL,
    reviewer_note TEXT,
    reviewed_at TEXT,
    reviewed_by TEXT,
    FOREIGN KEY (forecast_id) REFERENCES forecast_history(forecast_id)
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    model_id TEXT NOT NULL,
    asset TEXT NOT NULL,
    currency TEXT NOT NULL,
    horizon_code TEXT NOT NULL,
    method TEXT NOT NULL,
    n_windows INTEGER,
    step_size_hours INTEGER,
    training_cutoff TEXT,
    status TEXT NOT NULL,
    FOREIGN KEY (model_id) REFERENCES model_registry(model_id)
);

CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    window_index INTEGER NOT NULL,
    train_start TEXT,
    train_end TEXT,
    test_start TEXT,
    test_end TEXT,
    actual_price REAL,
    predicted_price REAL,
    lower_bound REAL,
    upper_bound REAL,
    absolute_error REAL,
    percentage_error REAL,
    direction_correct INTEGER,
    score INTEGER,
    interval_covered INTEGER,
    FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)
);

CREATE TABLE IF NOT EXISTS data_source_log (
    id INTEGER PRIMARY KEY,
    logged_at TEXT NOT NULL,
    source TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    data_type TEXT NOT NULL,
    http_status INTEGER,
    latency_ms INTEGER,
    ok INTEGER NOT NULL,
    quality TEXT NOT NULL,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS decision_history (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    metal TEXT NOT NULL,
    system_signal TEXT,
    system_confidence REAL,
    forecast_ids TEXT,
    user_decision TEXT,
    user_rationale TEXT,
    price_inr_at_decision REAL,
    price_type_at_decision TEXT,
    price_source_at_decision TEXT
);

CREATE TABLE IF NOT EXISTS news_events (
    news_id TEXT PRIMARY KEY,
    original_news_id TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    headline TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    relevance TEXT,
    asset TEXT,
    event TEXT,
    direction TEXT,
    impact TEXT,
    confidence REAL,
    source_reliability TEXT,
    llm_model_id TEXT,
    llm_model_version TEXT,
    analysis_timestamp TEXT,
    raw_reference TEXT,
    status TEXT NOT NULL DEFAULT 'RAW',
    FOREIGN KEY (original_news_id) REFERENCES news_events(news_id)
);

CREATE TABLE IF NOT EXISTS data_quality_alerts (
    id INTEGER PRIMARY KEY,
    detected_at TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    asset TEXT,
    pair TEXT,
    source TEXT,
    description TEXT NOT NULL,
    value_a REAL,
    value_b REAL,
    delta_pct REAL,
    severity TEXT NOT NULL DEFAULT 'MEDIUM',
    resolved INTEGER NOT NULL DEFAULT 0,
    resolved_at TEXT
);
"""


def init_db(db_path: Path = DB_PATH) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")


if __name__ == "__main__":
    init_db()
    print(f"Database initialised at {DB_PATH}")
    with sqlite3.connect(DB_PATH) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        print(f"{len(tables)} tables: {[t[0] for t in tables]}")
