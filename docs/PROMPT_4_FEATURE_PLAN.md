# PROMPT 4 — ML Feature Engineering Data Contract

## Assets

| Asset | Symbol | Type |
|-------|--------|------|
| Gold | GC=F | FUTURES |
| Silver | SI=F | FUTURES |

## Horizons

| Code | Steps | Label |
|------|-------|-------|
| 1h | 1 | +1 hour |
| 5h | 5 | +5 hours |
| 12h | 12 | +12 hours |
| 24h | 24 | +24 hours |
| 48h | 48 | +48 hours |

---

## Target Formulation

**Chosen: log return**

```
target_return_Nh(t) = log( close[t+N] / close[t] )
```

**Rationale:**
- Log returns are approximately stationary (vs. absolute price which is I(1))
- Scale-invariant across gold and silver (both measured in USD but at very different levels)
- Log returns are additive: `log(P[t+5]/P[t]) = Σ log(P[t+i]/P[t+i-1])` for i=1..5
- Predicted price can be reconstructed: `predicted_price = close[t] * exp(predicted_return)`
- Consistent with standard financial ML literature

**Existing project convention:** The existing `models/features.py` uses `df["target"] = df["y"].shift(-horizon)` (future price). The new ML pipeline diverges here in favour of log returns. The old forecasting pipeline (`models/forecaster.py`) is unchanged and continues to use the old target.

---

## Feature Timestamp

Each row in the ML-ready dataset represents features computed from information
strictly available **at or before** timestamp `t` (the bar close time).

```
feature_timestamp = close time of the bar at t
```

The bar at timestamp `t` carries `open[t], high[t], low[t], close[t], volume[t]`.
These are all finalized at `t`. No future bar may be used.

---

## Feature Families

### A. Log Returns (current and lagged)
```
return_1h   = log(close[t]   / close[t-1])
return_2h   = log(close[t]   / close[t-2])
return_3h   = log(close[t]   / close[t-3])
return_6h   = log(close[t]   / close[t-6])
return_12h  = log(close[t]   / close[t-12])
return_24h  = log(close[t]   / close[t-24])
return_48h  = log(close[t]   / close[t-48])
```
All use only bars at t and earlier. No leakage.

### B. Lagged Close
```
close_lag_1 .. close_lag_48  (selected lags)
```

### C. Rolling Statistics (window ends at t, inclusive)
```
rolling_mean_6h, rolling_mean_12h, rolling_mean_24h, rolling_mean_48h
rolling_std_6h,  rolling_std_12h,  rolling_std_24h,  rolling_std_48h
rolling_min_24h, rolling_min_48h
rolling_max_24h, rolling_max_48h
```
All `rolling(...).mean()` etc. on `close` without any additional shift — they
use data up to and including bar `t`.

### D. Momentum
```
momentum_3h  = close[t] - close[t-3]
momentum_6h  = close[t] - close[t-6]
momentum_12h = close[t] - close[t-12]
momentum_24h = close[t] - close[t-24]
momentum_48h = close[t] - close[t-48]
```

### E. Volatility (rolling std of returns)
```
volatility_6h  = std(return_1h over last 6 bars)
volatility_12h = std(return_1h over last 12 bars)
volatility_24h = std(return_1h over last 24 bars)
volatility_48h = std(return_1h over last 48 bars)
```

### F. OHLC Structure
```
high_low_range   = high[t] - low[t]
open_close_change = close[t] - open[t]
upper_wick       = high[t] - max(open[t], close[t])
lower_wick       = min(open[t], close[t]) - low[t]
body_size        = abs(close[t] - open[t])
range_pct        = (high[t] - low[t]) / open[t]  (if open > 0)
```
Uses only current bar. No future information.

### G. Gold/Silver Cross-Asset Features
```
gold_silver_ratio        = gold_close[t] / silver_close[t]
gold_silver_ratio_change = gold_silver_ratio[t] - gold_silver_ratio[t-1]
gold_return_vs_silver    = gold_return_1h[t] - silver_return_1h[t]
silver_return_vs_gold    = silver_return_1h[t] - gold_return_1h[t]
```

**Temporal alignment rule:** For Gold features at timestamp `t`, Silver
observations are joined using `pd.merge_asof(direction='backward')` — only
Silver bars with `timestamp <= t` are used. Identical rule for Silver features
using Gold. This is a strict as-of join: no future cross-asset data.

### H. FX Features (5 pairs → INR)
```
{pair}_level    = FX close at or before t  (as-of join)
{pair}_return   = log(FX close[t] / FX close[t-1])  — same as-of alignment
```
Pairs: usd_inr, eur_inr, cny_inr, jpy_inr, chf_inr

**Alignment rule:** `pd.merge_asof(direction='backward')` on FX hourly data
keyed to the feature timestamp. No FX observation from after `t` is ever used.

### I. Time / Calendar Features
```
hour           (0-23)
day_of_week    (0=Mon, 6=Sun)
day_of_month   (1-31)
month          (1-12)
quarter        (1-4)
hour_sin, hour_cos         (cyclical)
dow_sin, dow_cos           (cyclical)
month_sin, month_cos       (cyclical)
```
Deterministic from the timestamp. No data dependency.

### J. FinBERT News Features
```
news_count_{W}h         — number of relevant articles in past W hours
sentiment_mean_{W}h     — mean sentiment score in past W hours
sentiment_pos_ratio_{W}h — fraction of positive articles
```
Windows W ∈ {1, 6, 12, 24, 48}

**Temporal alignment:** Only articles with `published_at <= t` are included.
`fetched_at` is never used as a proxy for publication time.
If `published_at` is missing, the article is excluded from time-sensitive features.

---

## Missing Data Policy

- **Raw OHLCV gaps**: Features requiring bars that don't exist produce NaN.
  Rows with NaN features are kept in the dataset but flagged. The model
  training step (Prompt 5) will decide how to handle them.
- **Targets**: If `close[t+N]` doesn't exist (end of series), target is NaN.
  These rows are NOT silently dropped or zeroed.
- **No imputation**: No forward-fill, back-fill, or interpolation on raw data.
- **FinBERT**: If no news exists for a window, features are 0 (count) or NaN (mean).

---

## Feature Versioning

```
FEATURE_VERSION = "v1"
```

Every generated parquet file embeds:
- `feature_version`: string
- `generated_at`: ISO-8601 UTC timestamp
- Source data range in filename

---

## Dataset Storage

```
data/processed/
    gold_features.parquet
    silver_features.parquet
```

Schema: `timestamp | asset | <all features> | <targets> | feature_version`

Sorted deterministically by `timestamp` ascending.

---

## FinBERT Architecture

```
news_events table
    ↓
Temporal filter (published_at <= t)
    ↓
FinBERTBackend.score(texts)  ← abstract; real=ProsusAI/finbert, stub=uniform
    ↓
finbert_cache (SQLite, keyed by content_hash + model_name + model_version)
    ↓
Sentiment aggregation over time windows
    ↓
ML features (news_count_*, sentiment_mean_*)
```

**Model:** `ProsusAI/finbert` (HuggingFace, Apache-2.0 license)
**Device:** CUDA if available (torch 2.5.1+cu121 detected), else CPU
**Cache:** SQLite `finbert_cache` table; key = `(content_hash, model_name, model_version)`
**Fallback:** If `transformers` is not available, `StubFinBERTBackend` returns
uniform probabilities (0.333, 0.333, 0.333). Tests always use the stub.
