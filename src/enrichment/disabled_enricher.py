from __future__ import annotations

from .result_schema import EnrichmentResult


class DisabledEnricher:
    """Safe default when public web enrichment is disabled."""

    def enrich(self, contact: dict) -> EnrichmentResult:
        return EnrichmentResult(status="skipped", warnings=["Web enrichment disabled."])
