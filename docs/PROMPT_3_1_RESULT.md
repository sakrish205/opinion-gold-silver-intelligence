# PROMPT 3.1 RESULT

## Tests

```
Tests run:   44
Passed:      44
Failed:        0
Duration:    ~47s
```

---

## Changes Made

### 1. Incremental ingestion precision (`data/ingestion.py`)

**Before:**
```python
start = (since - timedelta(hours=1)).strftime("%Y-%m-%d")
ticker.history(start=start, interval=interval)
```

**After:**
```python
start_dt = since - timedelta(hours=1)
ticker.history(start=start_dt, interval=interval)
```

Passing a `datetime` object instead of a date string. yfinance converts it
to a Unix timestamp internally, giving sub-day precision rather than
truncating to midnight. The 1-hour overlap is retained; INSERT OR IGNORE
handles any duplicate bars.

**yfinance limitation documented in module docstring:** Yahoo Finance's hourly
data API may return data starting from the containing market session rather
than the exact requested hour. The 1-hour overlap + INSERT OR IGNORE
deduplication handles any boundary ambiguity. This is expected behaviour from
the upstream API and cannot be controlled client-side.

### 2. Explicit OHLC completeness diagnostics (`data/validation.py`)

`ValidationResult` now distinguishes two separate counts:

| Field | Meaning | Storage outcome |
|-------|---------|----------------|
| `missing_close` | Rows where `close` is NaN | **Excluded** — unusable |
| `missing_other_ohlc` | Rows where `open`/`high`/`low` is NaN but `close` is present | **Retained** — source values not fabricated |

**Renamed:** `missing_value_rows` → `missing_close` (breaking only for internal
tests, updated below).

No forward-fill, no interpolation, no fabrication. If a provider returns a row
with only a `close` value (common for FX hourly data), the row is stored as-is
and the incomplete OHLC is flagged in `ValidationResult.issues`.

### 3. Raw vs ML-usable data documentation (`data/ingestion.py`)

Module docstring explicitly states:

```
raw_market_data  =  source observations (this module)
ML-ready dataset =  feature-engineered, gap-handled (Prompt 4 scope)
```

### 4. Schema docstring (`db/schema.py`)

Updated: "all 11 OPINION SQLite tables" → "all 13 OPINION SQLite tables".

### 5. Provider error visibility (`data/ingestion.py`)

`_fetch()` now returns `(df | None, error_message | None)` instead of just
`df | None`. Exceptions are caught and the type + message (truncated to 300
chars) is captured. `ingest_ohlcv` includes the error in the ingestion log's
`error_message` column instead of the generic "No data from provider" string.
Public API (`ingest_ohlcv`, `backfill`, `update_incremental`) is unchanged.

---

## Tests Updated/Added

| File | Change |
|------|--------|
| `tests/test_validation.py` | Renamed `missing_value_rows` → `missing_close`; added `test_missing_other_ohlc_row_retained` |
| `tests/test_ingestion.py` | Added `test_incremental_start_is_datetime_not_date_string`; added `test_provider_exception_captured_in_log` |

---

## Files Changed

| File | What |
|------|------|
| `data/ingestion.py` | datetime start, error capture, raw-vs-ML docstring, remove unused `import math` |
| `data/validation.py` | `missing_close` + `missing_other_ohlc` fields, updated logic |
| `db/schema.py` | Docstring: 11 → 13 tables |
| `tests/test_validation.py` | Field rename + new test |
| `tests/test_ingestion.py` | Two new tests |

---

## Confirmation: Prompt 4 NOT Started

The following have NOT been implemented:

- Feature engineering pipeline
- ML-ready dataset construction
- Training datasets
- XGBoost model training / persisted weights
- FinBERT
- Signal engine
- Dashboard redesign
- Custom API
- New data sources / macroeconomic datasets
