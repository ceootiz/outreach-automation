from __future__ import annotations

from typing import Protocol

from .result_schema import EnrichmentResult


class BaseEnricher(Protocol):
    def enrich(self, contact: dict) -> EnrichmentResult:
        ...
