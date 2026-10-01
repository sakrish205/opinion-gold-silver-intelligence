# ARCHITECTURE GAP ANALYSIS
> CURRENT vs TARGET

---

## CURRENT (what actually exists)

```
yfinance GC=F / SI=F  ←  only live market data source
        │
        ▼
MetalsFuturesProvider (DataResult with quality flags)
        │
   ┌────┴──────────────────────────────┐
   ▼                                   ▼
data/cache.py (SQLite TTL)        models/forecaster.py
                                       │
                               5 statsforecast models
                               + XGBoost (lag+FX features)
                                       │
                                       ▼
                               forecast_history (SQLite)
                                       │
                               models/grader.py
                               (yfinance → actual price)
                                       │
                                       ▼
                               forecast_outcomes (SQLite)
                                       │
                               Dash dashboard (8 pages)
```

FX: yfinance (5 pairs) → open.er-api.com fallback  
News: 6 RSS feeds → feedparser → Ollama (qualitative tags only)  
No spot price, no FinBERT, no API, no signal engine, no tests.

---

## TARGET (desired future state)

```
DATA SOURCES → RAW DATA → DATA VALIDATION → FEATURE ENGINEERING
                                                    │
                                        ┌───────────┴───────────┐
                                        ▼                       ▼
                                  GOLD DATA              SILVER DATA
                                        │                       │
                                        └───────────┬───────────┘
                                                    ▼
                                            ML TRAINING
                                           ┌────┴────┐
                                           ▼         ▼
                                      GOLD MODEL  SILVER MODEL
                                           │         │
                                           └────┬────┘
                                                ▼
                                           FORECAST
                                                ▼
                                        SIGNAL ENGINE
                                        (BUY/HOLD/SELL)
                                                ▼
                                        SIMPLE DASHBOARD
                                                ▼
                                           CUSTOM API
```

With FinBERT features, walk-forward validation, transparent scoring, 1H/5H/12H/24H/48H.

---

## GAP TABLE

| Component | Target | Current Status | Gap |
|-----------|--------|---------------|-----|
| Data sources (futures) | YES | **EXISTS** — yfinance GC=F, SI=F | None |
| Data sources (FX / INR) | YES | **EXISTS** — yfinance + er-api fallback | None |
| Data sources (spot) | OPTIONAL | **UNAVAILABLE** — placeholder only | Low priority |
| Data sources (macro) | YES | **MISSING** — no VIX, DXY, bond yields, crude oil | Significant gap |
| Raw data store | YES | **PARTIAL** — feature_snapshots stores snapshot per forecast, not a continuous raw data store | Medium gap |
| Data validation pipeline | YES | **PARTIAL** — DataResult quality flags (LIVE/STALE/ERROR) exist; cross-check logic in config; but no standalone validation module | Medium gap |
| Feature engineering module | YES | **PARTIAL** — models/features.py builds XGBoost features (lag-24, rolling stats, FX, cyclical time); no pipeline orchestration | Medium gap |
| FinBERT features | YES | **MISSING** — zero NLP embedding infrastructure; Ollama does qualitative tags only (not embeddings) | Large gap |
| Gold model (custom ML) | YES | **PARTIAL** — XGBoost exists and runs; not persisted; not versioned as a standalone gold model | Medium gap |
| Silver model (custom ML) | YES | **PARTIAL** — same as gold; same model config used for both assets | Medium gap |
| Separate gold/silver model training | YES | **PARTIAL** — forecaster.py takes `asset` param but both use identical hyperparams and architecture | Small gap |
| Walk-forward validation | YES | **EXISTS** — models/backtest.py; 12 windows, 24h step | None |
| 5 forecast horizons (1h/5h/12h/24h/48h) | YES | **EXISTS** — HORIZONS in config.py; all 5 used | None |
| Forecast scoring (+3/−6, market only) | YES | **EXISTS** — models/grader.py; LLM excluded | None |
| Immutable forecast audit | YES | **EXISTS** — forecast_history append-only | None |
| Signal engine (BUY/HOLD/SELL) | YES | **MISSING** — no signal generation logic anywhere | Large gap |
| Transparent signal rationale | YES | **PARTIAL** — decision_history exists for manual decisions; no automated signal | Medium gap |
| Simple dashboard | YES | **EXISTS** — 8 Dash pages; arguably too many for "simple" | Minor cleanup |
| Custom API | YES | **MISSING** — no FastAPI/Flask routes, no REST endpoints anywhere | Large gap |
| Tests | IMPLICIT | **MISSING** — zero test files | Significant gap |
| FinGPT / Finance-specific LLM | OPTIONAL | **MISSING** — phi3-mini is general purpose; llm_registry has a comment about finance models | Low priority |
| News sentiment pipeline | YES | **PARTIAL** — RSS + Ollama qualitative tags; FinBERT would replace/augment this | Medium gap |

---

## STATUS LEGEND

```
EXISTS          — in code, wired to UI, functional
PARTIAL         — code exists, wired up, but incomplete or not matching target spec
MISSING         — no code at all
ORPHANED        — code exists but is not called or connected
UNAVAILABLE     — deliberately not implemented (no verified free source)
```

---

## BIGGEST GAPS (by impact)

1. **FinBERT** — the target's `FINBERT FEATURES` layer doesn't exist at all. The current LLM layer is Ollama (text generation), not FinBERT (embeddings/classification). These are architecturally different.

2. **Signal Engine** — no BUY/HOLD/SELL logic. decision_history only stores what the human manually entered. Nothing in the codebase translates forecast outputs into signals.

3. **Custom API** — no FastAPI, no Flask routes, no REST interface. The app is local Dash only.

4. **Macro data sources** — DXY, VIX, 10-year yields, crude oil are not present. These are standard gold/silver model inputs.

5. **Raw data store** — feature_snapshots is a per-forecast record, not a time-series datastore. There's no continuous OHLCV + macro history table. Models fetch live from yfinance on every run.

6. **Tests** — zero. None.
