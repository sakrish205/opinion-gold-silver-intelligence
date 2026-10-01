# MODEL MIGRATION PLAN

---

## CURRENT (exists and running)

```
models/forecaster.py  — run_forecast(asset, series, ...)
models/backtest.py    — run_backtest(asset, series, ...)
models/grader.py      — grade_pending()
models/features.py    — build_features(price_series, fx_history, horizon)

Models trained in-memory at forecast time (no persisted weights):
  Naive         — statsforecast.models.Naive
  AutoARIMA     — statsforecast.models.AutoARIMA
  AutoETS       — statsforecast.models.AutoETS
  Theta         — statsforecast.models.Theta
  XGBoost+FX    — xgboost.XGBRegressor + lag/rolling/FX/cyclical features

Horizons: 1h, 5h, 12h, 24h, 48h
Assets:   XAU, XAG (same model type used for both)
Currency: INR or USD (passed as metadata; XAG/XAU in USD, INR is DERIVED)
Scoring:  +3 direction correct / -6 incorrect (grader.py, LLM-free)
```

---

## TARGET (future — do not build yet)

```
Separate gold and silver models with persisted weights:

Gold (XAU):
  horizon_1h  → models/saved/xau_1h.json
  horizon_5h  → models/saved/xau_5h.json
  horizon_12h → models/saved/xau_12h.json
  horizon_24h → models/saved/xau_24h.json
  horizon_48h → models/saved/xau_48h.json

Silver (XAG):
  horizon_1h  → models/saved/xag_1h.json
  horizon_5h  → models/saved/xag_5h.json
  horizon_12h → models/saved/xag_12h.json
  horizon_24h → models/saved/xag_24h.json
  horizon_48h → models/saved/xag_48h.json

Training:
  Walk-forward on local OHLCV store (not live yfinance on every run)
  Optional: FinBERT news sentiment as additional feature
  Hyperparameter tuning per asset (not shared defaults)
  Model versioning via model_registry table (already exists)
```

---

## Migration Path

```
CURRENT                              TARGET
────────────────────────────────     ────────────────────────────────
models/forecaster.py                 models/train.py  (new)
  run_forecast() called on demand      train_gold(horizon) — saves weights
  re-trains from scratch each time     train_silver(horizon) — saves weights
  same XGB params for XAU and XAG      asset-specific tuning

models/backtest.py                   models/backtest.py  (keep, augment)
  walk-forward, in-memory              walk-forward, on local OHLCV store
  12 windows × 24h step                configurable windows/step

models/features.py                   models/features.py  (augment)
  lag-24, rolling, FX, cyclical        + FinBERT sentiment score (future)
  5 FX pairs                           feature importance-trimmed FX pairs

models/grader.py                     models/grader.py  (keep as-is)
  +3/-6 from yfinance FUTURES          no change; scoring is correct

Naive/AutoARIMA/AutoETS/Theta        REMOVED (after XGBoost validated)
  baseline models via statsforecast    keep in requirements.txt until removed
```

---

## DO NOT DO YET

- Do not delete Naive/AutoARIMA/AutoETS/Theta — they serve as baselines
- Do not persist XGBoost weights until a local OHLCV store exists
- Do not split gold/silver training until feature importance is understood
- Do not add FinBERT until sentence-transformers + local inference is tested

## SIGNAL ENGINE NOTE (separate from model migration)

The signal engine is NOT a model — it is logic applied to forecast outputs:

```python
# pseudocode only — not implemented
def generate_signal(asset, outcomes):
    if majority_direction(outcomes) and min_horizon_agreement(outcomes):
        return "BUY" | "SELL" | "HOLD"
```

This belongs in a separate `signals/` module, not in `models/`.
