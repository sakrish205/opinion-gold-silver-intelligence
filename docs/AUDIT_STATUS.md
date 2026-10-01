# AUDIT STATUS

```
Repository inspected:     YES
Application starts:       UNKNOWN — not started during audit (Windows env; no live yfinance test)
Tests exist:              NO — zero test files
Tests passing:            N/A
Major errors found:       See below
Missing dependencies:     None (requirements.txt covers all imports)
Unused components found:  YES — 3 items (see below)
Architecture understood:  YES
```

---

## Files Inspected

| File | Lines | Inspected |
|------|-------|-----------|
| app.py | 125 | YES |
| config.py | 91 | YES |
| requirements.txt | 10 | YES |
| README.md | 77 | YES |
| db/schema.py | 266 | YES |
| db/ops.py | 283 | YES |
| data/providers/base.py | 137 | YES |
| data/providers/metals_futures.py | 82 | YES |
| data/providers/metals_spot.py | 67 | YES |
| data/providers/forex.py | 143 | YES |
| data/providers/news.py | 151 | YES |
| data/cache.py | 58 | YES |
| models/features.py | 83 | YES |
| models/forecaster.py | 218 | YES |
| models/backtest.py | 260 | YES |
| models/grader.py | 113 | YES |
| llm/ollama_client.py | 114 | YES |
| llm/llm_registry.py | 85 | YES |
| pages/overview.py | 138 | YES |
| pages/metals.py | 115 | YES |
| pages/markets.py | ~200 | YES (from session context) |
| pages/analytics.py | ~200 | YES (from session context) |
| pages/forecasts.py | 376 | YES |
| pages/models.py | 131 | YES |
| pages/system.py | 213 | YES |
| pages/intelligence.py | 160 | YES |

---

## Major Issues Found

### 1. README page count is wrong
- README says: "18 dashboard pages"
- Actual: **8 pages** (overview, metals, markets, analytics, forecasts, models, system, intelligence)
- Severity: DOCUMENTATION BUG — misleading

### 2. `data_quality_alerts` table is fully orphaned
- `insert_data_quality_alert()` in db/ops.py
- Table created in db/schema.py
- **Zero calls to this function anywhere in the codebase**
- Severity: DEAD CODE

### 3. `ProviderChain` class is never used
- Defined in data/providers/base.py (lines 72–112)
- Documented with a docstring
- **Never instantiated or imported by any provider or page**
- Severity: DEAD CODE

### 4. No tests at all
- Zero `test_*.py` or `*_test.py` files
- No pytest, unittest, or any testing framework referenced in requirements.txt
- Severity: RISK — no safety net for grader, features, or backtest logic

### 5. `data/cache.py` uses `pickle.dumps`
- Line 46: `pickle.dumps(value)` stored in SQLite BLOB
- Pickle is safe for local use only; would be a security issue if cache values ever came from untrusted sources
- For this local-only use case: acceptable but worth noting
- Severity: LOW (local only)

### 6. `data_source_log` grows unbounded
- Every `DataProvider.fetch()` call writes a row via `_log_result()` in base.py
- No cleanup, no TTL, no rotation
- Health checks fire every 30 seconds per provider
- Severity: MEDIUM — will become large over time

### 7. `feature_snapshots` table has 50+ columns
- This is the design choice for full reproducibility
- Not a bug, but: reading this table back for any purpose is complex
- Only written to, never read by any current page
- Severity: ARCHITECTURAL NOTE — over-engineered for current use

### 8. `models/forecaster.py` imports `importlib` but never uses it
- Line 35: `import importlib` — unused import
- Severity: MINOR (cosmetic)

---

## Unused Dependencies (from requirements.txt)

All 10 dependencies are used:
| Package | Used by |
|---------|---------|
| dash | app.py, all pages |
| dash-bootstrap-components | all pages |
| plotly | metals, markets, analytics, forecasts |
| yfinance | metals_futures.py, forex.py, grader.py |
| statsforecast | forecaster.py, backtest.py |
| xgboost | forecaster.py, backtest.py |
| scikit-learn | NOT directly used (likely pulled in by statsforecast or xgboost) |
| pandas | everywhere |
| requests | forex.py, ollama_client.py |
| feedparser | news.py |

`scikit-learn` — **UNKNOWN if directly used**. Appears in requirements.txt. Not found in any import statement in the source files. Likely a transitive dependency of statsforecast/xgboost, or left over from a previous feature.

---

## Architecture Understanding

```
CONFIRMED FLOWS (verified from imports + code):
  yfinance → MetalsFuturesProvider → pages (display + forecast input)
  yfinance → YFinanceFXProvider → pages (FX display + model features)
  forecaster.run_forecast() → forecast_history (via ops)
  grader.grade_pending() → forecast_outcomes (via ops) — +3/-6, LLM-free
  RSS → news.get_news() → intelligence page → Ollama → news_events
  backtest.run_backtest() → backtest_runs/results → model_registry status update

CONFIRMED NOT CONNECTED:
  ProviderChain — defined, never used
  data_quality_alerts — table exists, never written
  insert_data_quality_alert() — function exists, never called
  XAU/INR cross-check anomaly — threshold in config, column in feature_snapshots, never triggers an alert
```
