# SIMPLIFICATION PLAN

---

## Proposed Architecture (minimal path to target)

```
                    DATA SOURCES
              yfinance GC=F / SI=F (FUTURES)
              yfinance FX: USD/INR, EUR/INR, CNY/INR
              RSS news (6 verified sources)
                         │
                         ▼
                    RAW DATA STORE
              data/providers/metals_futures.py (already exists)
              data/providers/forex.py (already exists)
                         │
                         ▼
                  DATA VALIDATION
              DataResult quality flags (already exists)
              XAU/INR cross-check (config exists, not wired)
                         │
                         ▼
                FEATURE ENGINEERING
              models/features.py — lag-24, rolling, FX, cyclical
              [ADD: FinBERT news sentiment features later]
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
           GOLD DATA             SILVER DATA
              │                     │
              └──────────┬──────────┘
                         ▼
                   ML TRAINING
            walk-forward, models/backtest.py
                  ┌──────┴──────┐
                  ▼             ▼
              GOLD MODEL     SILVER MODEL
              XGBoost+FX    XGBoost+FX
                  │             │
                  └──────┬──────┘
                         ▼
                     FORECAST
              5 horizons, 5 models, +3/-6 scoring
                         │
                         ▼
                  SIGNAL ENGINE  ← NOT PRESENT, BUILD LATER
                         │
                         ▼
                  SIMPLE DASHBOARD
              4-5 pages (Overview, Forecasts, Models, System)
                         │
                         ▼
                    CUSTOM API  ← NOT PRESENT, BUILD LATER
```

---

## Component Decision Table

| Component | Current Status | Decision | Reason |
|-----------|---------------|----------|--------|
| `app.py` | EXISTS | **KEEP** | Entry point works; sidebar navigation is clean |
| `config.py` | EXISTS | **KEEP** | Horizons, FX pairs, scoring — correct and used |
| `data/providers/metals_futures.py` | EXISTS | **KEEP** | Core; GC=F/SI=F correctly labelled FUTURES |
| `data/providers/forex.py` | EXISTS | **KEEP** | yfinance + er-api fallback; INR pairs used for features |
| `data/providers/base.py` | EXISTS | **KEEP** (minor cleanup) | DataProvider ABC + DataResult are solid; `ProviderChain` is dead code — remove it |
| `data/providers/metals_spot.py` | EXISTS (UNAVAILABLE) | **KEEP as-is** | Honest placeholder; removing it breaks imports in overview.py |
| `data/providers/news.py` | EXISTS | **KEEP** | RSS works; VERIFIED_SOURCES populated with 6 sources |
| `data/cache.py` | EXISTS | **KEEP** | SQLite TTL cache prevents hammering yfinance |
| `db/schema.py` | EXISTS | **KEEP** (minor cleanup) | 11 tables; remove `data_quality_alerts` if never used, or keep as-is |
| `db/ops.py` | EXISTS | **KEEP** | Clean typed insert functions |
| `models/features.py` | EXISTS | **KEEP** | Lag-24 + rolling + FX + cyclical features, no leakage |
| `models/forecaster.py` | EXISTS | **KEEP** | All 5 models wired; `run_forecast()` is the core function |
| `models/backtest.py` | EXISTS | **KEEP** | Walk-forward, correct; used by analytics page |
| `models/grader.py` | EXISTS | **KEEP** | +3/-6 scoring, LLM-free, correct |
| `llm/ollama_client.py` | EXISTS | **KEEP** | News analysis only; clean LLM boundary |
| `llm/llm_registry.py` | EXISTS | **KEEP** | Configurable; finance models can be added later |
| `pages/overview.py` | EXISTS | **KEEP** | INR-first, quality-badged prices — core |
| `pages/metals.py` | EXISTS | **KEEP** | Candlestick + technicals — useful |
| `pages/markets.py` | EXISTS | **SIMPLIFY** | Overlaps with overview; keep FX chart, remove redundant international prices table |
| `pages/analytics.py` | EXISTS | **KEEP** | Currency influence + backtesting both useful |
| `pages/forecasts.py` | EXISTS | **KEEP** | Core: Run/Grade/Audit/Verify |
| `pages/models.py` | EXISTS | **KEEP** | Model registry and performance tracking |
| `pages/intelligence.py` | EXISTS | **KEEP** | News tab useful; Decisions tab optional |
| `pages/system.py` | EXISTS | **KEEP** | Provider health, settings — operational necessity |
| `ProviderChain` (base.py) | ORPHANED | **REMOVE** | Defined but never used; adds confusion |
| `data_quality_alerts` table | ORPHANED | **REMOVE** | Table + ops function exist; nothing calls `insert_data_quality_alert()` |
| JPY/INR, CHF/INR FX pairs | EXISTS | **REMOVE from target features** | Target architecture prioritises USD/INR, EUR/INR, CNY/INR; JPY and CHF add API calls with marginal ML value |
| FinBERT | MISSING | **BUILD LATER** | Significant infrastructure needed (transformers, GPU or CPU inference); do not rush |
| Signal engine | MISSING | **BUILD LATER** | Must come after models are validated |
| Custom API | MISSING | **BUILD LATER** | FastAPI wrapper over forecast and grader functions; straightforward once models stabilise |
| Tests | MISSING | **BUILD** | At minimum: one test per grader function, one for features, one for backtest sanity |
| Macro data (DXY, VIX, yields, crude) | MISSING | **EVALUATE** | Confirm free sources exist before adding; do not add paid APIs |
| Continuous raw data store | MISSING | **EVALUATE** | Currently models fetch live from yfinance on every run; a local OHLCV store (SQLite or parquet) would speed up backtesting significantly at the cost of storage management |
| README | WRONG | **FIX** | Says "18 pages" — actual count is 8; architecture section is outdated |

---

## What to Do Next (ordered by value / safety)

### Phase 1 — Clean up, no risk (do now)
1. Fix README: "8 pages" not "18"
2. Remove `ProviderChain` from base.py (dead code)
3. Drop `data_quality_alerts` table and its ops.py function (orphaned)
4. Remove JPY/INR and CHF/INR from FX_PAIRS in config.py (reduce noisy API calls)
5. Delete stale `pages/__pycache__/*.pyc` files for removed pages

### Phase 2 — Add tests (important)
1. `test_grader.py` — mock yfinance, verify +3/-6 scores correct
2. `test_features.py` — assert no future leakage (target shifted correctly), correct column count
3. `test_backtest.py` — assert walk-forward windows never use future data

### Phase 3 — Strengthen data layer
1. Add a local OHLCV store (sqlite or parquet file) so backtest doesn't hit yfinance on every run
2. Wire XAU/INR cross-check anomaly detection (config has the threshold; nothing calls `insert_data_quality_alert`)

### Phase 4 — Signal engine
1. Define signal logic: if majority of forecasts (≥3/5 models, ≥2/5 horizons) agree → generate signal
2. Store in decision_history with `system_signal` populated
3. Display on overview page

### Phase 5 — FinBERT
1. Evaluate `sentence-transformers` with `ProsusAI/finbert`
2. Replace/augment Ollama news tags with FinBERT sentiment scores as model features
3. Add `news_sentiment` feature to models/features.py

### Phase 6 — Custom API
1. FastAPI wrapper with endpoints: `/forecast/latest`, `/forecast/history`, `/grade/pending`
2. Reuse existing ops.py and grader.py functions
3. Authentication: API key or local-only binding

---

## What NOT to Build (YAGNI)

- Spot price provider — no verified free source; label UNAVAILABLE is honest and correct
- Additional statsforecast models (e.g. CES, TBATS) — XGBoost+FX is already the differentiator
- Multi-user / cloud deployment — ₹0 budget, local-first
- Real-time websocket price streaming — hourly resolution is sufficient for 1h+ forecasts
- Portfolio tracking — out of scope; this is intelligence, not portfolio management
