# PROMPT 3 — Data Pipeline Implementation Note

## What we're building

A local raw OHLCV store for all 7 symbols (GC=F, SI=F, USDINR=X, EURINR=X,
CNYINR=X, JPYINR=X, CHFINR=X) with idempotent ingestion and validation.
The store is append-only for current consumers; the existing forecasting/backtest
pipeline continues to fetch live from yfinance unchanged.

## New files

| File | Purpose |
|------|---------|
| `data/validation.py` | `ValidationResult` dataclass + `validate_ohlcv()` |
| `data/ingestion.py` | `ingest_ohlcv()`, `get_latest_stored_ts()`, `backfill()`, `update_incremental()` |
| `tests/test_validation.py` | 8 tests — no network |
| `tests/test_ingestion.py` | 8 tests — yfinance mocked |

## Schema additions (db/schema.py)

Two new tables appended to SCHEMA constant (CREATE TABLE IF NOT EXISTS — safe to re-run):

```
raw_market_data  — OHLCV rows, UNIQUE(symbol, timestamp_utc, interval)
ingestion_log    — per-run metadata (rows_received, rows_stored, validation_status)
```

Index: `idx_raw_symbol_ts ON raw_market_data (symbol, timestamp_utc)` for
fast range queries.

## Key design decisions

**Deduplication**: `INSERT OR IGNORE` on `UNIQUE(symbol, timestamp_utc, interval)`.
No UPDATE — raw layer is immutable; we never overwrite a stored observation.

**Incremental logic** (inside `ingest_ohlcv`):
- If no data stored → `period=f"{lookback_days}d"` (full backfill, default 730d)
- If latest stored timestamp exists → `start=(latest_ts - 1h)` to catch the most
  recent bar (yfinance hourly can return the current open bar as a partial bar;
  the -1h overlap re-fetches it and INSERT OR IGNORE handles the duplicate)

**Validation policy**:
- Close missing or ≤ 0 → row excluded from storage (ValidationResult.rows_invalid++)
- OHLC inconsistency (high < max(O,C,L)) → row retained, issue flagged
- Duplicate timestamps within a batch → first kept, rest excluded
- Gaps > 48h → counted and flagged (weekends/holidays are normal; only very large gaps noted)

**Testability**: functions accept optional `db_path=None`; tests pass `tmp_path`
directly. No module reload needed.

**What this does NOT change**:
- MetalsFuturesProvider, YFinanceFXProvider — unchanged
- Forecasting/backtest live-fetch path — unchanged
- data/cache.py TTL layer — unchanged
- All 8 dashboard pages — unchanged
- Existing 24 tests — must still pass

## Symbols ingested

| Symbol | Asset | Type |
|--------|-------|------|
| GC=F | XAU | FUTURES |
| SI=F | XAG | FUTURES |
| USDINR=X | USD/INR | FX |
| EURINR=X | EUR/INR | FX |
| CNYINR=X | CNY/INR | FX |
| JPYINR=X | JPY/INR | FX |
| CHFINR=X | CHF/INR | FX |

Derived from `config.METAL_FUTURES_TICKERS` + `config.FX_PAIRS` — no hardcoded tickers
in ingestion.py.
