"""
News provider via RSS feeds.

Sources are NOT hardcoded until verified against:
  - URL resolves and returns valid RSS/Atom
  - ToS permits personal non-commercial use
  - Rate limits acceptable for hourly polling
  - Timestamps present and parseable
  - No redistribution of full content required

VERIFIED_SOURCES below is initially empty.
Add entries after manual verification. The pipeline will work with zero
sources (returns empty list); the News Intelligence page will show
"No verified news sources configured."
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any

import feedparser

from data.providers.base import DataProvider, DataResult, ProviderSpec

# ── Verified RSS sources ──────────────────────────────────────────────────────
# Format: {"name": str, "url": str, "license_note": str}
# Add entries here after completing the verification checklist.
VERIFIED_SOURCES: list[dict[str, str]] = [
    # Example (uncomment after verifying ToS):
    # {
    #     "name": "World Gold Council RSS",
    #     "url": "https://www.gold.org/rss.xml",
    #     "license_note": "personal non-commercial use; verify before enabling",
    # },
]

RELEVANCE_KEYWORDS = {
    "gold", "silver", "xau", "xag", "comex", "mcx", "bullion",
    "metals", "inr", "precious", "commodity", "rupee",
}


class RSSNewsProvider(DataProvider):
    def __init__(self, name: str, url: str) -> None:
        self.spec = ProviderSpec(
            name=name,
            endpoint=url,
            cost="₹0",
            requires_key=False,
            rate_limit="verify per source",
            resolution="as published",
            historical_coverage="feed window only",
            timestamp_quality="as published",
            reliability="unknown",
            license="verify per source",
            storage_rights="verify per source",
            redistribution="verify per source",
            commercial_use="verify per source",
        )
        self._url = url

    def fetch(self, **kwargs) -> DataResult:
        t0 = time.monotonic()
        try:
            feed = feedparser.parse(self._url)
            latency_ms = int((time.monotonic() - t0) * 1000)
            if feed.bozo and not feed.entries:
                return self._result(None, "ERROR", "NEWS", latency_ms,
                                    str(feed.bozo_exception))
            items = []
            for entry in feed.entries:
                headline = entry.get("title", "").strip()
                if not headline:
                    continue
                published = entry.get("published", "")
                url = entry.get("link", "")
                content_hash = hashlib.sha256(
                    f"{headline}{self.spec.name}".encode()
                ).hexdigest()
                lower = headline.lower()
                relevant = any(kw in lower for kw in RELEVANCE_KEYWORDS)
                items.append({
                    "headline": headline,
                    "published_at": published,
                    "source_url": url,
                    "source": self.spec.name,
                    "content_hash": content_hash,
                    "relevant": relevant,
                })
            return self._result(items, "LIVE", "NEWS", latency_ms)
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            return self._result(None, "ERROR", "NEWS", latency_ms, str(exc))


def get_news() -> list[dict[str, Any]]:
    """Fetch from all verified sources; return deduplicated relevant items."""
    if not VERIFIED_SOURCES:
        return []

    seen_hashes: set[str] = set()
    all_items: list[dict] = []

    for src in VERIFIED_SOURCES:
        provider = RSSNewsProvider(src["name"], src["url"])
        result = provider.fetch()
        if result.status != "LIVE" or not result.value:
            continue
        for item in result.value:
            if item["content_hash"] not in seen_hashes and item["relevant"]:
                seen_hashes.add(item["content_hash"])
                item["fetched_at"] = datetime.now(timezone.utc).isoformat()
                all_items.append(item)

    return all_items
