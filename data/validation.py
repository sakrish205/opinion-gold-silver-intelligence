"""
OHLCV validation for raw market data.

validate_ohlcv() returns (valid_df, ValidationResult).
Only rows with missing or non-positive close are excluded from valid_df.
OHLC inconsistencies are flagged but rows are kept — may be provider artifacts.
"""
from __future__ import annotations
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ValidationResult:
    symbol: str
    source: str
    interval: str
    rows_received: int = 0
    rows_valid: int = 0
    rows_invalid: int = 0
    duplicate_timestamps: int = 0
    missing_value_rows: int = 0
    invalid_ohlc_rows: int = 0
    negative_price_rows: int = 0
    large_gap_count: int = 0
    date_range: tuple[str, str] | None = None
    issues: list[str] = field(default_factory=list)
    status: str = "OK"   # "OK" | "WARNINGS" | "FAILED"


def validate_ohlcv(
    df: pd.DataFrame,
    symbol: str,
    source: str,
    interval: str,
) -> tuple[pd.DataFrame, ValidationResult]:
    """
    Validate a normalized OHLCV DataFrame (columns: timestamp_utc, open, high, low, close, volume).

    Returns:
      valid_df — rows fit for storage (close present and > 0)
      ValidationResult — counts of all issues found
    """
    result = ValidationResult(symbol=symbol, source=source, interval=interval)

    if df is None or df.empty:
        result.status = "FAILED"
        result.issues.append("Empty DataFrame received")
        return pd.DataFrame(), result

    result.rows_received = len(df)

    # 1. Duplicate timestamps within the batch
    if "timestamp_utc" in df.columns:
        dup_mask = df["timestamp_utc"].duplicated(keep="first")
        result.duplicate_timestamps = int(dup_mask.sum())
        if result.duplicate_timestamps:
            result.issues.append(
                f"{result.duplicate_timestamps} duplicate timestamps — first occurrence kept"
            )
            df = df[~dup_mask].copy()

    # 2. Missing close column
    if "close" not in df.columns:
        result.status = "FAILED"
        result.issues.append("No 'close' column")
        return pd.DataFrame(), result

    # 3. Missing close values
    missing_close = df["close"].isna()
    result.missing_value_rows = int(missing_close.sum())
    if result.missing_value_rows:
        result.issues.append(f"{result.missing_value_rows} rows with missing close value")

    # 4. Non-positive close price
    negative_mask = df["close"].notna() & (df["close"] <= 0)
    result.negative_price_rows = int(negative_mask.sum())
    if result.negative_price_rows:
        result.issues.append(f"{result.negative_price_rows} rows with non-positive close price")

    # 5. OHLC consistency (only when all four are present)
    if all(c in df.columns for c in ("open", "high", "low", "close")):
        has_all = df[["open", "high", "low", "close"]].notna().all(axis=1)
        high_ok = df["high"] >= df[["open", "close", "low"]].max(axis=1)
        low_ok = df["low"] <= df[["open", "close", "high"]].min(axis=1)
        ohlc_bad = has_all & ~(high_ok & low_ok)
        result.invalid_ohlc_rows = int(ohlc_bad.sum())
        if result.invalid_ohlc_rows:
            result.issues.append(
                f"{result.invalid_ohlc_rows} rows with invalid OHLC relationship "
                "(flagged; rows retained)"
            )

    # 6. Timestamp gaps > 48h (weekends/holidays expected; only very large gaps noted)
    if "timestamp_utc" in df.columns and len(df) > 1:
        ts = pd.to_datetime(df["timestamp_utc"], utc=True).sort_values()
        gaps = ts.diff().dropna()
        large_gaps = gaps[gaps.dt.total_seconds() > 48 * 3600]
        result.large_gap_count = len(large_gaps)
        if result.large_gap_count:
            result.issues.append(f"{result.large_gap_count} timestamp gap(s) > 48h")

    # Build valid_df: exclude only rows where close is missing or non-positive
    exclude = missing_close | negative_mask
    valid_df = df[~exclude].copy()
    result.rows_invalid = int(exclude.sum())
    result.rows_valid = len(valid_df)

    if not valid_df.empty and "timestamp_utc" in valid_df.columns:
        result.date_range = (
            str(valid_df["timestamp_utc"].min()),
            str(valid_df["timestamp_utc"].max()),
        )

    if result.rows_valid == 0:
        result.status = "FAILED"
        result.issues.append("No usable rows after validation")
    elif (
        result.rows_invalid > 0
        or result.duplicate_timestamps > 0
        or result.invalid_ohlc_rows > 0
        or result.large_gap_count > 0
    ):
        result.status = "WARNINGS"
    else:
        result.status = "OK"

    return valid_df, result
