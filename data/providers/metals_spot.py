"""
Gold and Silver SPOT price provider.

Free, reliable, key-free XAU/USD and XAG/USD spot sources have not been
verified as of implementation. This provider returns UNAVAILABLE until a
source passes the full verification checklist:

    cost              ₹0
    requires_key      No
    rate_limit        sufficient for hourly polling
    data_license      permits personal non-commercial storage
    timestamp_quality exchange-grade
    reliability       high

When a verified source is found:
1. Add a concrete subclass of DataProvider below.
2. Update SPOT_CHAIN in get_spot_chain().
3. Document the verified source in the spec.
"""
from __future__ import annotations

from datetime import datetime, timezone

from data.providers.base import DataProvider, DataResult, ProviderSpec


class SpotUnavailableProvider(DataProvider):
    """Placeholder — no verified free spot source yet."""

    spec = ProviderSpec(
        name="spot_unverified",
        endpoint="N/A",
        cost="₹0",
        requires_key=False,
        rate_limit="N/A",
        resolution="N/A",
        historical_coverage="N/A",
        timestamp_quality="N/A",
        reliability="N/A",
        license="pending verification",
        storage_rights="pending verification",
        redistribution="pending verification",
        commercial_use="pending verification",
    )

    def fetch(self, asset: str, **kwargs) -> DataResult:
        return DataResult(
            value=None,
            status="UNAVAILABLE",
            data_type="SPOT",
            source=self.spec.name,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=0,
            error=(
                f"{asset} spot price: no verified free source. "
                "Add a verified provider to metals_spot.py to enable this."
            ),
        )


_SPOT_PROVIDER = SpotUnavailableProvider()


def get_spot_price(asset: str) -> DataResult:
    """Return spot price result. UNAVAILABLE until a source is verified."""
    return _SPOT_PROVIDER.fetch(asset=asset)
