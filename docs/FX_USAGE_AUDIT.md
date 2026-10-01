# FX PAIR USAGE AUDIT

Verified from source code (grep of all .py files).

| FX Pair | Used in UI | Used in Features | Used in Model | Used in DB | Decision |
|---------|-----------|-----------------|--------------|-----------|----------|
| USD/INR | YES — overview FX table, markets FX chart/dropdown | YES — fx_history passed to build_features() | YES — XGBoost feature column `fx_usd_inr` | YES — feature_snapshots columns: usd_inr, usd_inr_source, usd_inr_resolution, usd_inr_quality, usd_inr_fetched_at | **KEEP** |
| EUR/INR | YES — overview FX table, markets FX chart/dropdown | YES | YES — XGBoost feature column `fx_eur_inr` | YES — feature_snapshots: eur_inr cols | **KEEP** |
| CNY/INR | YES — overview FX table, markets FX chart/dropdown | YES | YES — XGBoost feature column `fx_cny_inr` | YES — feature_snapshots: cny_inr cols | **KEEP** |
| JPY/INR | YES — overview FX table, markets FX chart/dropdown | YES — included because FX_PAIRS iterates all 5 | YES — XGBoost feature column `fx_jpy_inr` | YES — feature_snapshots: jpy_inr cols | **KEEP for now — evaluate at feature engineering stage** |
| CHF/INR | YES — overview FX table, markets FX chart/dropdown | YES | YES — XGBoost feature column `fx_chf_inr` | YES — feature_snapshots: chf_inr cols | **KEEP for now — evaluate at feature engineering stage** |

## Evidence

All 5 pairs enter the feature pipeline identically:

```python
# pages/forecasts.py:124
for p in FX_PAIRS:           # iterates all 5
    r = get_fx_history(p)
    if r.status in ("LIVE", "STALE") and r.value is not None:
        fx_history[p.pair] = r.value["rate"].reindex(series.index, method="ffill")
```

All 5 pairs are then passed to `models/features.py:build_features(fx_history=fx_history)` which loops:

```python
for pair_name, fx_series in fx_history.items():
    col = pair_name.lower().replace("/", "_")
    df[f"fx_{col}"] = aligned.shift(1)
```

Removing JPY/INR or CHF/INR would:
- Remove 2 yfinance API calls per forecast run
- Remove 2 feature columns from XGBoost
- Remove those pairs from the overview FX table
- Remove them from the markets FX chart dropdown
- NOT break any table (feature_snapshots uses nullable columns)

## Recommendation

Defer removal to the Feature Engineering stage (Prompt 4+) when we:
1. Do feature importance analysis
2. Confirm which pairs actually contribute to XGBoost predictive accuracy
3. Decide the canonical feature set

Do not remove based on architecture preferences alone.
