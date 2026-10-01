"""DataProvider ABC and DataResult."""
from __future__ import annotations

import sqlite3
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
