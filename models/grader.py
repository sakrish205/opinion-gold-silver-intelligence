"""
Forecast grading engine.

For each forecast where target_timestamp has elapsed and no outcome exists:
  1. Fetch actual price at target_timestamp from yfinance (FUTURES only)
  2. Compute actual_direction vs price_at_forecast
  3. direction_correct = predicted_direction == actual_direction
  4. score = +3 correct | -6 incorrect  (NEVER via LLM — market data only)
  5. INSERT into forecast_outcomes (append-only)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

from config import SCORE_CORRECT, SCORE_INCORRECT
from db import ops

log = logging.getLogger(__name__)

_TICKER = {"XAU": "GC=F", "XAG": "SI=F"}


def _fetch_actual_price(asset: str, target_ts: str) -> tuple[float | None, str]:
    """
    Return (actual_price, quality).
    Fetches hourly OHLCV and picks the close bar at or nearest to target_ts.
    """
    ticker = _TICKER.get(asset)
    if not ticker:
        return None, "UNAVAILABLE"

    try:
        target_dt = pd.to_datetime(target_ts, utc=True)
        start = (target_dt - timedelta(hours=3)).strftime("%Y-%m-%d")
        end   = (target_dt + timedelta(hours=3)).strftime("%Y-%m-%d")
        df = yf.download(ticker, start=start, end=end, interval="1h",
                         progress=False, auto_adjust=True)
        if df.empty:
            return None, "UNAVAILABLE"
        df.index = pd.to_datetime(df.index, utc=True)
        # nearest bar
        idx = (df.index - target_dt).abs().argmin()
        price = float(df["Close"].iloc[idx])
        gap_hours = abs((df.index[idx] - target_dt).total_seconds()) / 3600
        quality = "LIVE" if gap_hours <= 1 else "STALE"
        return price, quality
    except Exception as exc:
        log.warning("grader fetch error for %s @ %s: %s", asset, target_ts, exc)
        return None, "ERROR"


def grade_pending() -> list[dict[str, Any]]:
    """
    Grade all pending forecasts. Returns list of outcome dicts that were inserted.
    Safe to call repeatedly — already-graded forecasts are skipped via NOT EXISTS.
    """
    pending = ops.get_pending_forecasts()
    results = []
    for fc in pending:
        asset       = fc["asset"]
        target_ts   = fc["target_timestamp"]
        predicted   = fc["predicted_direction"]
        price_origin = fc["price_at_forecast"]
        forecast_id = fc["forecast_id"]

        actual_price, quality = _fetch_actual_price(asset, target_ts)
        if actual_price is None:
            continue  # can't grade without actual price

        # direction relative to price at forecast time
        if actual_price > price_origin * 1.0001:
            actual_direction = "UP"
        elif actual_price < price_origin * 0.9999:
            actual_direction = "DOWN"
        else:
            actual_direction = "FLAT"

        direction_correct = int(actual_direction == predicted)
        score = SCORE_CORRECT if direction_correct else SCORE_INCORRECT
        abs_err = abs(actual_price - fc["predicted_price"]) if fc.get("predicted_price") else None
        pct_err = abs_err / price_origin * 100 if abs_err and price_origin else None

        lb = fc.get("lower_bound")
        ub = fc.get("upper_bound")
        interval_covered = (
            int(lb <= actual_price <= ub) if lb is not None and ub is not None else None
        )

        outcome = {
            "forecast_id":         forecast_id,
            "actual_price":        actual_price,
            "actual_price_type":   "FUTURES",
            "actual_price_source": f"yfinance/{_TICKER.get(asset, '?')}",
            "actual_direction":    actual_direction,
            "absolute_error":      abs_err,
            "percentage_error":    pct_err,
            "direction_correct":   direction_correct,
            "score":               score,
            "interval_covered":    interval_covered,
        }
        try:
            ops.insert_forecast_outcome(outcome)
            results.append(outcome)
        except Exception as exc:
            log.warning("grader insert error for %s: %s", forecast_id, exc)

    return results
