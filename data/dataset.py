"""
ML dataset orchestrator.

Reads raw_market_data, builds features, attaches news/FinBERT features,
and saves leakage-safe parquet files to data/processed/.

Usage:
    from data.dataset import build_all_datasets
    results = build_all_datasets()   # writes gold/silver parquets
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import METAL_FUTURES_TICKERS, FX_PAIRS, ASSETS
from data.features import (
    build_feature_df, load_raw_ohlcv, check_feature_quality, FEATURE_VERSION,
)
from data.news_features import attach_news_features, get_backend

PROCESSED_DIR = Path(__file__).parent / "processed"

_FX_SYMBOL_MAP = {fx.pair.lower().replace("/", "_"): fx for fx in FX_PAIRS}


def _load_all_fx(interval: str = "1h", db_path=None) -> dict[str, pd.DataFrame]:
    """Load OHLCV for all 5 FX pairs. Returns {pair_key: df}."""
    from data.features import load_raw_ohlcv
    result = {}
    for fx in FX_PAIRS:
        key = fx.pair.lower().replace("/", "_")
        df = load_raw_ohlcv(fx.yf_ticker, interval=interval, db_path=db_path)
        if not df.empty:
            result[key] = df
    return result


def build_asset_dataset(
    asset: str,
    interval: str = "1h",
    db_path=None,
    force_stub_finbert: bool = False,
) -> pd.DataFrame:
    """
    Build the complete ML-ready feature DataFrame for one asset.

    Steps:
      1. Load raw OHLCV from raw_market_data
      2. Load FX raw OHLCV for all 5 pairs
      3. Load other asset's raw OHLCV (for cross-asset features)
      4. Build price/technical/time/FX/cross-asset features
      5. Attach FinBERT news features
      6. Add metadata columns

    Returns an empty DataFrame if no raw data is available.
    """
    symbol = METAL_FUTURES_TICKERS[asset]
    ohlcv = load_raw_ohlcv(symbol, interval=interval, db_path=db_path)
    if ohlcv.empty:
        return pd.DataFrame()

    fx_dfs = _load_all_fx(interval=interval, db_path=db_path)

    # Cross-asset: load the other metal
    other_asset = "XAG" if asset == "XAU" else "XAU"
    other_symbol = METAL_FUTURES_TICKERS[other_asset]
    other_ohlcv = load_raw_ohlcv(other_symbol, interval=interval, db_path=db_path)
    other_name = "silver" if asset == "XAU" else "gold"

    df = build_feature_df(
        ohlcv=ohlcv,
        fx_dfs=fx_dfs if fx_dfs else None,
        other_asset_df=other_ohlcv if not other_ohlcv.empty else None,
        other_asset_name=other_name,
        asset=asset,
    )

    if df.empty:
        return df

    # Attach FinBERT news features
    backend = get_backend(force_stub=force_stub_finbert)
    df = attach_news_features(df, asset=asset, backend=backend, db_path=db_path)

    df["generated_at"] = datetime.now(timezone.utc).isoformat()

    return df


def save_dataset(df: pd.DataFrame, asset: str, out_dir: Path | None = None) -> Path:
    """Save the dataset as parquet, return the path."""
    out = Path(out_dir) if out_dir else PROCESSED_DIR
    out.mkdir(parents=True, exist_ok=True)
    filename = f"{asset.lower()}_features.parquet"
    path = out / filename
    df.to_parquet(path, index=True)
    return path


def build_all_datasets(
    interval: str = "1h",
    db_path=None,
    out_dir: Path | None = None,
    force_stub_finbert: bool = False,
) -> dict[str, Any]:
    """
    Build and save ML-ready datasets for Gold and Silver.

    Returns a summary dict with paths, row counts, and quality issues.
    """
    results = {}
    for asset in ASSETS:
        df = build_asset_dataset(
            asset, interval=interval, db_path=db_path,
            force_stub_finbert=force_stub_finbert,
        )
        issues = check_feature_quality(df)
        if not df.empty:
            path = save_dataset(df, asset, out_dir=out_dir)
        else:
            path = None
        results[asset] = {
            "rows": len(df),
            "columns": len(df.columns),
            "path": str(path) if path else None,
            "quality_issues": issues,
        }
    return results
