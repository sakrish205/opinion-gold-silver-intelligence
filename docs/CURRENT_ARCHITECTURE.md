# CURRENT ARCHITECTURE
> Based entirely on source code inspection. Where source code and README contradict, source code wins.

---

## 1. Entry Point

```
app.py
```

- Creates `Dash` app with `use_pages=True`
- Calls `db.schema.init_db()` on startup (creates all tables)
- 8-page sidebar navigation (grouped)
- Opens browser on `http://127.0.0.1:8050` via threading.Timer

README says "18 pages" — **THIS IS WRONG**. Actual page count: **8**.

---

## 2. Actual Data Flow

```
yfinance (GC=F, SI=F)
        │
        ▼
MetalsFuturesProvider.fetch(asset)
        │
        ▼
DataResult (DataFrame: Open/High/Low/Close/Volume, 730d × 1h)
        │
  ┌─────┴──────────────┐
  ▼                    ▼
pages/metals.py     models/forecaster.py → run_forecast()
(candlestick chart)         │
                            ▼
                    5 models × 5 horizons = up to 25 forecast rows
                            │
                            ▼
                    db/ops.insert_feature_snapshot()
                    db/ops.insert_forecast()
                            │
                            ▼
                    forecast_history table (append-only)

                    [time passes — target_timestamp elapses]

                    models/grader.grade_pending()
                            │
                            ▼
                    yfinance.download(GC=F or SI=F, ±3h)
                            │
                            ▼
                    actual_price → score (+3/-6)
                            │
                            ▼
                    db/ops.insert_forecast_outcome()
```

FX flow (parallel to metals):
```
yfinance (USDINR=X etc.)                open.er-api.com (fallback, daily)
        │                                       │
        ▼                                       ▼
YFinanceFXProvider.fetch_latest()   OpenERAPIFXProvider.fetch()
        │                                       │
        └───────────────┬───────────────────────┘
                        ▼
               get_fx_latest(pair) → DataResult
                        │
                ┌───────┴────────┐
                ▼                ▼
         pages/overview.py   models/features.py
         (FX table)          (FX features for XGBoost)
```

News flow:
```
6 × RSS feeds (Kitco, ET, Moneycontrol, Business Standard, Mining.com, GoldPrice.org)
        │
        ▼
RSSNewsProvider.fetch() → relevance filter (RELEVANCE_KEYWORDS)
        │
        ▼
get_news() → list[dict] (deduplicated, relevant only)
        │
        ▼
pages/intelligence.py → Ollama LLM → analyse_news() [qualitative only]
        │
        ▼
db/ops.insert_news_event() → news_events table
```

---

## 3. Module Dependency Map

```
app.py
 ├── db/schema.py        (init_db)
 └── pages/              (Dash pages, auto-discovered)

pages/overview.py
 ├── config.py
 ├── data/providers/metals_futures.py
 ├── data/providers/metals_spot.py      (always UNAVAILABLE)
 └── data/providers/forex.py

pages/metals.py
 ├── config.py
 ├── data/providers/metals_futures.py
 └── data/cache.py

pages/markets.py
 ├── config.py
 ├── data/providers/metals_futures.py
 ├── data/providers/forex.py
 └── data/cache.py

pages/analytics.py
 ├── config.py
 ├── data/providers/metals_futures.py
 ├── data/providers/forex.py
 ├── db/ (ops, direct sqlite3)
 └── models/backtest.py

pages/forecasts.py
 ├── config.py
 ├── data/providers/metals_futures.py
 ├── data/providers/forex.py
 ├── db/ops.py
 ├── models/forecaster.py
 └── models/grader.py

pages/models.py
 ├── config.py
 └── db/ (direct sqlite3)

pages/system.py
 ├── config.py
 ├── data/providers/ (all 4 providers)
 ├── llm/ollama_client.py
 └── db/ (direct sqlite3)

pages/intelligence.py
 ├── config.py
 ├── data/providers/news.py
 ├── llm/ollama_client.py
 └── db/ops.py

models/forecaster.py
 ├── config.py
 ├── models/features.py
 ├── statsforecast (Naive, AutoARIMA, AutoETS, Theta)
 └── xgboost

models/backtest.py
 ├── config.py
 ├── models/features.py
 ├── db/ops.py
 ├── statsforecast
 └── xgboost

models/grader.py
 ├── config.py
 ├── db/ops.py
 └── yfinance

models/features.py
 └── numpy, pandas

data/providers/base.py
 ├── config.py              (DB_PATH for data_source_log)
 └── sqlite3 (direct write to data_source_log on EVERY fetch)

data/cache.py
 └── sqlite3 → _cache table (pickle + TTL)
```

---

## 4. Data Sources (Verified from Code)

| Source | Provider/Library | Ticker/URL | Asset/Data | Frequency | Type | Status | File |
|--------|-----------------|------------|------------|-----------|------|--------|------|
| Yahoo Finance | yfinance | GC=F | Gold FUTURES USD/oz | on demand (cached 5min) | historical + latest | LIVE | metals_futures.py |
| Yahoo Finance | yfinance | SI=F | Silver FUTURES USD/oz | on demand (cached 5min) | historical + latest | LIVE | metals_futures.py |
| Yahoo Finance | yfinance | USDINR=X, EURINR=X, CNYINR=X, JPYINR=X, CHFINR=X | FX rates → INR | on demand | historical + latest | LIVE | forex.py |
| open.er-api.com | requests | /v6/latest/USD | FX rates (daily, fallback) | on demand | current only | LIVE (fallback) | forex.py |
| Kitco News | feedparser | RSS | Gold/silver headlines | on-demand (manual button) | news | LIVE | news.py |
| Economic Times | feedparser | RSS | Commodities headlines | on-demand | news | LIVE | news.py |
| Moneycontrol | feedparser | RSS | Commodities headlines | on-demand | news | LIVE | news.py |
| Business Standard | feedparser | RSS | Markets headlines | on-demand | news | LIVE | news.py |
| Mining.com | feedparser | RSS | Mining/metals news | on-demand | news | LIVE | news.py |
| GoldPrice.org | feedparser | RSS | Gold/silver prices news | on-demand | news | LIVE | news.py |
| XAU/XAG Spot | N/A | N/A | Spot price | N/A | N/A | **UNAVAILABLE** (no verified free source) | metals_spot.py |

---

## 5. Models

| Model | File | Input | Output | Trained? | Used in Dashboard? | Status |
|-------|------|-------|--------|----------|-------------------|--------|
| Naive (persistence) | models/forecaster.py | hourly price series (statsforecast) | predicted price ± PI | yes, at forecast time (in-memory) | YES — Forecasts > Run tab | IMPLEMENTED + USED |
| AutoARIMA | models/forecaster.py | hourly price series | predicted price ± PI | yes, at forecast time (in-memory) | YES | IMPLEMENTED + USED |
| AutoETS | models/forecaster.py | hourly price series | predicted price ± PI | yes, at forecast time (in-memory) | YES | IMPLEMENTED + USED |
| Theta | models/forecaster.py | hourly price series | predicted price ± PI | yes, at forecast time (in-memory) | YES | IMPLEMENTED + USED |
| XGBoost+FX | models/forecaster.py + models/features.py | lag-24 price features + FX rates | predicted price (no PI) | yes, at forecast time (in-memory) | YES | IMPLEMENTED + USED |
| FinBERT | N/A | N/A | N/A | NO | NO | **NOT PRESENT** |
| Signal Engine (BUY/HOLD/SELL) | N/A | N/A | N/A | NO | NO | **NOT PRESENT** |

All 5 models are re-trained from scratch each time "Run Forecasts" is clicked. No persisted model weights.

Walk-forward backtest engine (models/backtest.py) exists and is connected to the Analytics page. It re-trains each model per window and stores results in backtest_runs/backtest_results.

---

## 6. Database

- **Type**: SQLite
- **File**: `opinion.db` (project root, or `$OPINION_DB` env var)
- **Tables**: 11 schema tables + 2 internal tables (`_cache`, `_settings`)

| Table | Written by | Read by | Notes |
|-------|-----------|---------|-------|
| feature_snapshots | pages/forecasts.py (via ops) | not read by any page directly | 50+ columns; stores all FX/price data at forecast time |
| model_registry | models/backtest.py (via ops) | pages/models.py | aggregate metrics; status updated to 'production' for best model |
| forecast_history | pages/forecasts.py (via ops) | pages/forecasts.py | append-only; all 25 forecast rows per run |
| forecast_outcomes | models/grader.py (via ops) | pages/forecasts.py | append-only; grading results (+3/-6) |
| human_verification | pages/forecasts.py (manual form) | pages/forecasts.py | revision-based; only via manual entry |
| backtest_runs | models/backtest.py (via ops) | pages/analytics.py | walk-forward run metadata |
| backtest_results | models/backtest.py (via ops) | pages/analytics.py | per-window results |
| data_source_log | data/providers/base.py (every fetch) | pages/system.py | grows unbounded; no TTL |
| decision_history | pages/intelligence.py (via ops) | pages/intelligence.py | user-entered decisions only |
| news_events | pages/intelligence.py (via ops) | pages/intelligence.py | RSS headlines + LLM analysis |
| data_quality_alerts | **ORPHANED** — insert function in ops.py, never called | never read | dead table |
| _cache | data/cache.py | data/cache.py | pickle-serialised DataFrames, TTL-based |
| _settings | pages/system.py, llm/ollama_client.py | llm/ollama_client.py | LLM model key, thresholds |

---

## 7. Dashboard Pages

| File | Path | Purpose | Data Source | Useful for Simplified System? |
|------|------|---------|-------------|-------------------------------|
| pages/overview.py | / | INR-first prices, FX table, quality badges | metals_futures + forex | YES — core display |
| pages/metals.py | /metals | Candlestick + MA20/MA50 technicals | metals_futures | YES — core display |
| pages/markets.py | /markets | International tables, FX cards, historical chart | metals_futures + forex | PARTIAL — FX chart is useful; international table is redundant with overview |
| pages/analytics.py | /analytics | Currency influence heatmap, backtesting UI | metals_futures + forex + backtest | PARTIAL — backtesting yes; currency heatmap marginal |
| pages/forecasts.py | /forecasts | Run/Grade/Audit/Verify forecasts | metals_futures + forex + grader | YES — core |
| pages/models.py | /models | Model performance chart, registry | model_registry | YES — for model tracking |
| pages/system.py | /system | Provider specs, health, settings | all providers + ollama | YES — operational |
| pages/intelligence.py | /intelligence | News + manual decision log | news + ollama + decision_history | YES — news; decision log optional |

---

## 8. LLM

- **Runtime**: Local Ollama (`http://localhost:11434`)
- **Role**: News analysis only — qualitative direction/impact/event extraction
- **Scoring**: LLM is explicitly excluded from +3/−6 scoring (enforced in grader.py and ollama_client.py)
- **Models supported**: phi3-mini (default), llama3.2-1b, llama3.2-3b
- **Configurable**: via Settings page → `_settings` table
- **Fallback**: Returns `[LLM offline — ...]` string if Ollama not running. App continues without it.

---

## 9. Dead / Orphaned Code

| Item | Location | Why Dead |
|------|----------|----------|
| `data_quality_alerts` table | db/schema.py, db/ops.py | `insert_data_quality_alert()` exists in ops.py but is **never called** by any module |
| `ProviderChain` class | data/providers/base.py | Defined, documented, but **never instantiated** in any provider or page |
| `SpotUnavailableProvider` | data/providers/metals_spot.py | Intentionally always returns UNAVAILABLE; the import in overview.py calls `get_spot_price()` which always returns UNAVAILABLE |
| `pages/__pycache__/backtesting.cpython-312.pyc` | pages/__pycache__/ | Bytecode for a page that was removed in a prior refactor |
| `pages/__pycache__/currency_influence.cpython-312.pyc` | pages/__pycache__/ | Bytecode for a page that was removed in a prior refactor |
