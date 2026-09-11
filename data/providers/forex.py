"""
FX rates for all five INR pairs via yfinance with open.er-api.com fallback.

Rates are fetched hourly and stored as model features (not display-only).
Each result carries: source, resolution, quality, fetched_at.

Provider matrix:
  yfinance        ₹0 | no key | unofficial | hourly | Yahoo ToS personal
  open.er-api.com ₹0 | no key | 1500/month | daily  | personal+commercial
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import requests
import yfinance as yf

from config import FX_PAIRS, FXPair
from data.providers.base import DataProvider, DataResult, ProviderSpec


class YFinanceFXProvider(DataProvider):
    spec = ProviderSpec(
        name="yfinance_fx",
        endpoint="https://query1.finance.yahoo.com (yfinance)",
        cost="₹0",
        requires_key=False,
        rate_limit="unofficial; avoid aggressive polling",
        resolution="1h",
        historical_coverage="730 days for 1h interval",
        timestamp_quality="delayed",
        reliability="medium",
        license="Yahoo Finance ToS",
        storage_rights="personal_only",
        redistribution="prohibited",
        commercial_use="unknown",
    )

    def fetch(self, pair: FXPair, period: str = "730d", interval: str = "1h", **kwargs) -> DataResult:
        t0 = time.monotonic()
        try:
            df = yf.Ticker(pair.yf_ticker).history(period=period, interval=interval)
            latency_ms = int((time.monotonic() - t0) * 1000)
            if df is None or df.empty:
                return self._result(None, "UNAVAILABLE", "FX", latency_ms, "Empty response")
            df = df[["Close"]].rename(columns={"Close": "rate"})
            df.attrs["pair"] = pair.pair
            df.attrs["resolution"] = "1h"
            df.attrs["source"] = self.spec.name
            return self._result(df, "LIVE", "FX", latency_ms)
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            return self._result(None, "ERROR", "FX", latency_ms, str(exc))

    def fetch_latest(self, pair: FXPair) -> DataResult:
        result = self.fetch(pair=pair, period="5d", interval="1h")
        if result.status not in ("LIVE", "STALE") or result.value is None:
            return result
        df = result.value
        rate = float(df["rate"].iloc[-1])
        ts = df.index[-1].isoformat()
        return self._result(
            {"rate": rate, "pair": pair.pair, "timestamp": ts,
             "resolution": "1h", "source": self.spec.name},
            "LIVE", "FX", result.latency_ms,
        )


class OpenERAPIFXProvider(DataProvider):
    """
    Fallback: open.er-api.com — free, no key, daily resolution.
    Permits personal and commercial use per site terms.
    Returns daily rate (not hourly); labelled resolution='daily', quality='STALE'.
    """
    spec = ProviderSpec(
        name="open_er_api",
        endpoint="https://open.er-api.com/v6/latest/USD",
        cost="₹0",
        requires_key=False,
        rate_limit="1500/month free tier",
        resolution="daily",
        historical_coverage="current rate only",
        timestamp_quality="estimated",
        reliability="medium",
        license="open.er-api.com terms",
        storage_rights="permitted",
        redistribution="unknown",
        commercial_use="permitted",
    )

    def fetch(self, pair: FXPair, **kwargs) -> DataResult:
        t0 = time.monotonic()
        try:
            resp = requests.get(
                "https://open.er-api.com/v6/latest/USD", timeout=10
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            resp.raise_for_status()
            data = resp.json()
            rates = data.get("rates", {})
            base_to_inr = rates.get("INR")
            base_currency = pair.base
            if base_currency == "USD":
                rate = base_to_inr
            else:
                base_in_usd = rates.get(base_currency)
                if not base_in_usd or not base_to_inr:
                    return self._result(None, "UNAVAILABLE", "FX", latency_ms, f"Missing rate for {base_currency}")
                rate = base_to_inr / base_in_usd  # cross rate via USD
            if rate is None:
                return self._result(None, "UNAVAILABLE", "FX", latency_ms, "Rate not in response")
            ts = datetime.now(timezone.utc).isoformat()
            return self._result(
                {"rate": float(rate), "pair": pair.pair, "timestamp": ts,
                 "resolution": "daily", "source": self.spec.name, "quality": "STALE"},
                "STALE", "FX", latency_ms,
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            return self._result(None, "ERROR", "FX", latency_ms, str(exc))


_YF = YFinanceFXProvider()
_ER = OpenERAPIFXProvider()


def get_fx_latest(pair: FXPair) -> DataResult:
    """Primary: yfinance hourly. Fallback: open.er-api.com daily."""
    result = _YF.fetch_latest(pair=pair)
    if result.status in ("LIVE", "STALE"):
        return result
    return _ER.fetch(pair=pair)


def get_fx_history(pair: FXPair, period: str = "730d") -> DataResult:
    """Hourly history for model features. Falls back to UNAVAILABLE (no history from ER API)."""
    return _YF.fetch(pair=pair, period=period, interval="1h")


def get_all_fx_latest() -> dict[str, DataResult]:
    return {p.pair: get_fx_latest(p) for p in FX_PAIRS}
