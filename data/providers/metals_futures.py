"""
Gold and Silver FUTURES data via yfinance (GC=F, SI=F).

These are COMEX futures contracts, NOT spot prices.
Label: FUTURES throughout. Never display as spot.

Yahoo Finance ToS: personal/research use. Storage: personal only.
Redistribution: prohibited. Commercial use: UNKNOWN.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from config import METAL_FUTURES_TICKERS, YF_INTERVAL, YF_PERIOD
from data.providers.base import DataProvider, DataResult, ProviderSpec


class MetalsFuturesProvider(DataProvider):
    spec = ProviderSpec(
        name="yfinance_metals_futures",
        endpoint="https://query1.finance.yahoo.com (yfinance)",
        cost="₹0",
        requires_key=False,
        rate_limit="unofficial; avoid aggressive polling",
        resolution="1h",
        historical_coverage="730 days for 1h interval",
        timestamp_quality="exchange",
        reliability="medium",
        license="Yahoo Finance ToS",
        storage_rights="personal_only",
        redistribution="prohibited",
        commercial_use="unknown",
    )

    def fetch(self, asset: str, **kwargs) -> DataResult:
        ticker = METAL_FUTURES_TICKERS.get(asset)
        if not ticker:
            return self._result(None, "ERROR", "FUTURES", 0, f"Unknown asset: {asset}")

        t0 = time.monotonic()
        try:
            df = yf.Ticker(ticker).history(period=YF_PERIOD, interval=YF_INTERVAL)
            latency_ms = int((time.monotonic() - t0) * 1000)

            if df is None or df.empty:
                return self._result(None, "UNAVAILABLE", "FUTURES", latency_ms, "Empty response")

            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.index = pd.to_datetime(df.index, utc=True)
            df.attrs["ticker"] = ticker
            df.attrs["asset"] = asset
            df.attrs["data_type"] = "FUTURES"
            df.attrs["source"] = self.spec.name

            return self._result(df, "LIVE", "FUTURES", latency_ms)
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            return self._result(None, "ERROR", "FUTURES", latency_ms, str(exc))

    def fetch_latest(self, asset: str) -> DataResult:
        """Return the most recent closing price as a scalar dict."""
        result = self.fetch(asset=asset)
        if result.status not in ("LIVE", "STALE") or result.value is None:
            return result
        df: pd.DataFrame = result.value
        row = df.iloc[-1]
        return self._result(
            {
                "price": float(row["Close"]),
                "timestamp": df.index[-1].isoformat(),
                "data_type": "FUTURES",
                "ticker": METAL_FUTURES_TICKERS[asset],
            },
            result.status,
            "FUTURES",
            result.latency_ms,
        )
