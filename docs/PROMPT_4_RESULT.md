# PROMPT 4 RESULT

## Implementation

### Files Created

| File | Purpose |
|------|---------|
| `data/features.py` | Market feature builder — returns, lags, rolling, momentum, volatility, OHLC structure, FX, cross-asset, time features, targets |
| `data/news_features.py` | FinBERT backend (TransformersFinBERT + StubFinBERT), cache, news loading, sentiment aggregation |
| `data/dataset.py` | Orchestrator — builds Gold/Silver datasets from raw_market_data, saves parquet to `data/processed/` |
| `data/processed/` | Output directory for ML-ready parquet files |
| `docs/PROMPT_4_FEATURE_PLAN.md` | Full data contract |
| `tests/test_features_ml.py` | 30 market feature tests (returns, lags, rolling, OHLC, time, FX, targets, quality) |
| `tests/test_news_features.py` | 10 news feature tests (FinBERT schema, cache, aggregation, temporal alignment) |
| `tests/test_leakage.py` | 11 adversarial leakage tests |

### Files Modified

| File | What changed |
|------|-------------|
| `db/schema.py` | Added `finbert_cache` table; docstring 13 → 14 tables |
| `requirements.txt` | Added `transformers>=4.40` |

---

## Features Implemented

### Price / Return Features (per asset)
```
return_1h, return_2h, return_3h, return_6h, return_12h, return_24h, return_48h
close_lag_1, close_lag_2, close_lag_3, close_lag_6, close_lag_12, close_lag_24, close_lag_48
rolling_mean_6h, rolling_mean_12h, rolling_mean_24h, rolling_mean_48h
rolling_std_6h,  rolling_std_12h,  rolling_std_24h,  rolling_std_48h
rolling_min_24h, rolling_min_48h, rolling_max_24h, rolling_max_48h
momentum_3h, momentum_6h, momentum_12h, momentum_24h, momentum_48h
volatility_6h, volatility_12h, volatility_24h, volatility_48h
```

### OHLC Structure
```
high_low_range, open_close_change, upper_wick, lower_wick, body_size, range_pct
```

### Time / Calendar
```
hour, day_of_week, day_of_month, month, quarter
hour_sin, hour_cos, dow_sin, dow_cos, month_sin, month_cos
```

### FX (5 pairs, as-of joined)
```
{pair}_level, {pair}_return  (usd_inr, eur_inr, cny_inr, jpy_inr, chf_inr)
```

### Cross-Asset (Gold ↔ Silver, as-of joined)
```
gold_silver_ratio, gold_silver_ratio_change
gold_return_vs_silver  (for Gold feature set)
silver_return_vs_gold  (for Silver feature set)
```

### FinBERT News (per window W ∈ {1,6,12,24,48}h)
```
news_count_{W}h, sentiment_mean_{W}h, sentiment_pos_ratio_{W}h
```

### Targets (log returns, 5 horizons)
```
target_return_1h  = log(close[t+1]  / close[t])
target_return_5h  = log(close[t+5]  / close[t])
target_return_12h = log(close[t+12] / close[t])
target_return_24h = log(close[t+24] / close[t])
target_return_48h = log(close[t+48] / close[t])
```

---

## Target Formulation

**Log return.** Rationale: stationary (vs I(1) price), scale-invariant across
Gold/Silver, additive over horizons. Predicted price can be reconstructed as
`close[t] * exp(predicted_return)`. Full justification in
`docs/PROMPT_4_FEATURE_PLAN.md`.

---

## FinBERT Implementation

| Item | Value |
|------|-------|
| Model | `ProsusAI/finbert` (Apache-2.0) |
| Library | HuggingFace Transformers 5.18.0 |
| PyTorch | 2.5.1+cu121 (CUDA available) |
| Inference | CUDA if available, else CPU |
| Weights | Downloaded lazily on first use, cached by Transformers |
| Cache | SQLite `finbert_cache` table, key = (content_hash, model_name, model_version) |
| Fallback | `StubFinBERTBackend` returns uniform probs (1/3 each) when transformers unavailable |
| Limitation | news_events currently has 0 rows; news features fill with 0/NaN when empty |

---

## Dataset Storage

```
data/processed/
    gold_features.parquet     (empty — raw_market_data not yet populated)
    silver_features.parquet   (empty — raw_market_data not yet populated)
```

`raw_market_data` was added to schema in Prompt 3 but `init_db()` has not been
run on the live `opinion.db`, and no backfill has been executed.
Running `data.ingestion.backfill()` then `data.dataset.build_all_datasets()`
will populate both parquet files.

---

## Temporal Alignment Rules

| Feature type | Alignment rule |
|-------------|----------------|
| Price / OHLC features | Current bar (t) only — no shift needed |
| FX features | `pd.merge_asof(direction='backward')` on FX hourly data |
| Cross-asset | `pd.merge_asof(direction='backward')` on other asset's close |
| News features | `published_at <= t` strict filter (fetched_at never used as proxy) |
| Targets | `close[t+N]` — intentionally future; NaN at series end |

---

## Missing Data Policy

- Features with insufficient history → NaN (rows kept, not dropped)
- Targets where future bar unavailable → NaN (rows kept, not zeroed)
- No interpolation, no forward-fill of raw OHLCV
- News with unparseable published_at → excluded from features

---

## Validation

```
Tests run:   86
Passed:      86
Failed:        0
```

### Leakage tests performed

| Test | Status |
|------|--------|
| Future OHLCV does not change past features | PASS |
| return_1h uses only close[t] and close[t-1] | PASS |
| Future FX bar does not affect prior FX features | PASS |
| FX as-of join uses only latest prior value | PASS |
| Cross-asset uses only prior silver/gold close | PASS |
| target_1h is strictly log(close[t+1]/close[t]) | PASS |
| target positive when future price higher | PASS |
| Future news excluded from sentiment at t | PASS |
| Adding future news does not change past features | PASS |

---

## Environment

```
Python:        3.12.10
PyTorch:       2.5.1+cu121 (CUDA 12.1)
Transformers:  5.18.0 (newly installed)
FinBERT model: ProsusAI/finbert (weights on first use)
Device:        CUDA (when available), CPU fallback
```

---

## Scope Boundary

```
[ ] XGBoost training       — NOT STARTED
[ ] Signal engine          — NOT STARTED
[ ] Dashboard redesign     — NOT STARTED
[ ] Custom API             — NOT STARTED
```
