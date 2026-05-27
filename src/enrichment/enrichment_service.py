from __future__ import annotations

import json
from typing import Any

from ..config import as_bool, as_int
from ..db import Database
from .cache import EnrichmentCache
from .domain_analyzer import candidate_website_url
from .result_schema import EnrichmentResult
from .web_enricher import WebEnricher


class EnrichmentService:
    def __init__(self, db: Database, enricher: WebEnricher | None = None):
        self.db = db
        self.cache = EnrichmentCache(db)
        self.enricher = enricher

    def settings_from_app_settings(self, settings: dict[str, str]) -> dict[str, Any]:
        return {
            "enabled": as_bool(settings.get("web_enrichment_enabled"), False),
            "max_pages": max(1, min(as_int(settings.get("web_enrichment_max_pages"), 2), 3)),
            "timeout_seconds": max(2, min(as_int(settings.get("web_enrichment_timeout_seconds"), 8), 20)),
            "cache_ttl_days": max(1, min(as_int(settings.get("web_enrichment_cache_ttl_days"), 7), 60)),
            "respect_robots": as_bool(settings.get("web_enrichment_respect_robots"), True),
        }

    def enrich_contact(
        self,
        contact: dict[str, Any],
        *,
        settings: dict[str, Any],
        force_refresh: bool = False,
    ) -> EnrichmentResult:
        if not bool(settings.get("enabled", False)):
            return EnrichmentResult(status="skipped", warnings=["Web enrichment выключен."])

        url, warnings = candidate_website_url(contact)
        if not url:
            return EnrichmentResult(status="skipped", warnings=warnings)

        ttl_days = int(settings.get("cache_ttl_days") or 7)
        if not force_refresh:
            cached = self.cache.get(url, ttl_days=ttl_days)
            if cached is not None:
                cached.warnings.append("Использован cache enrichment.")
                return cached

        enricher = self.enricher or WebEnricher(
            max_pages=int(settings.get("max_pages") or 2),
            timeout_seconds=int(settings.get("timeout_seconds") or 8),
            respect_robots=bool(settings.get("respect_robots", True)),
        )
        result = enricher.enrich(contact)
        self.cache.save(url, result, ttl_days=ttl_days)
        return result

    def save_contact_result(self, contact_id: int, result: EnrichmentResult) -> None:
        self.db.update_contact(
            contact_id,
            {
                "enrichment_result_json": result.to_json(),
                "enrichment_status": result.status,
                "enrichment_source_urls": json.dumps(result.source_urls, ensure_ascii=False),
                "enrichment_warnings": json.dumps(result.warnings, ensure_ascii=False),
                "enrichment_confidence": result.confidence,
                "last_error": "" if result.status in {"success", "partial", "skipped"} else "; ".join(result.warnings),
            },
        )
