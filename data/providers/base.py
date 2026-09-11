"""DataProvider ABC, DataResult, ProviderChain."""
from __future__ import annotations

import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from config import DB_PATH


DataStatus = Literal["LIVE", "STALE", "UNAVAILABLE", "ERROR"]
DataType = Literal["SPOT", "FUTURES", "DERIVED", "FX", "NEWS"]


@dataclass
class DataResult:
    value: Any                          # DataFrame, dict, list, or None
    status: DataStatus
    data_type: DataType
    source: str
    fetched_at: str                     # ISO-8601
    latency_ms: int
    error: str | None = None


@dataclass
class ProviderSpec:
    name: str
    endpoint: str
    cost: str = "₹0"
    requires_key: bool = False
    rate_limit: str = "unknown"
    resolution: str = "1h"
    historical_coverage: str = "unknown"
    timestamp_quality: str = "unknown"
    reliability: str = "unknown"
    license: str = "unknown"
    storage_rights: str = "unknown"
    redistribution: str = "unknown"
    commercial_use: str = "unknown"


class DataProvider(ABC):
    spec: ProviderSpec

    @abstractmethod
    def fetch(self, **kwargs) -> DataResult:
        ...

    def _result(
        self,
        value: Any,
        status: DataStatus,
        data_type: DataType,
        latency_ms: int,
        error: str | None = None,
    ) -> DataResult:
        return DataResult(
            value=value,
            status=status,
            data_type=data_type,
            source=self.spec.name,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=latency_ms,
            error=error,
        )


class ProviderChain:
    """Try providers in order; return first LIVE or STALE result.
    Falls through to UNAVAILABLE if all fail."""

    def __init__(self, providers: list[DataProvider], data_type: DataType) -> None:
        self.providers = providers
        self.data_type = data_type

    def fetch(self, **kwargs) -> DataResult:
        last_error = None
        for provider in self.providers:
            t0 = time.monotonic()
            try:
                result = provider.fetch(**kwargs)
            except Exception as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                result = DataResult(
                    value=None,
                    status="ERROR",
                    data_type=self.data_type,
                    source=provider.spec.name,
                    fetched_at=datetime.now(timezone.utc).isoformat(),
                    latency_ms=latency_ms,
                    error=str(exc),
                )
                last_error = str(exc)

            _log_result(result, provider.spec.endpoint)

            if result.status in ("LIVE", "STALE"):
                return result

        return DataResult(
            value=None,
            status="UNAVAILABLE",
            data_type=self.data_type,
            source="chain_exhausted",
            fetched_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=0,
            error=last_error,
        )


def _log_result(result: DataResult, endpoint: str) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO data_source_log
                   (logged_at, source, endpoint, data_type, http_status,
                    latency_ms, ok, quality, error_message)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    result.fetched_at,
                    result.source,
                    endpoint,
                    result.data_type,
                    None,
                    result.latency_ms,
                    1 if result.status in ("LIVE", "STALE") else 0,
                    result.status,
                    result.error,
                ),
            )
    except Exception:
        pass  # never crash the app over logging
