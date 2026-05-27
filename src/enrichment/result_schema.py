from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


ENRICHMENT_STATUSES = {"success", "partial", "failed", "blocked", "skipped"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_confidence(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


@dataclass(slots=True)
class EnrichmentResult:
    status: str = "skipped"
    source_urls: list[str] = field(default_factory=list)
    domain: str = ""
    title: str = ""
    description: str = ""
    public_summary: str = ""
    likely_category: str = ""
    signals: list[str] = field(default_factory=list)
    source_basis: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fetched_at: str = field(default_factory=utc_now_iso)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        status = self.status if self.status in ENRICHMENT_STATUSES else "failed"
        return {
            "status": status,
            "source_urls": self.source_urls[:8],
            "domain": self.domain,
            "title": self.title,
            "description": self.description,
            "public_summary": self.public_summary,
            "likely_category": self.likely_category,
            "signals": self.signals[:12],
            "source_basis": self.source_basis[:8],
            "warnings": self.warnings[:12],
            "fetched_at": self.fetched_at,
            "confidence": normalize_confidence(self.confidence),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


def parse_enrichment_result(raw: str | dict[str, Any] | EnrichmentResult | None) -> EnrichmentResult:
    if isinstance(raw, EnrichmentResult):
        return raw
    if not raw:
        return EnrichmentResult()
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return EnrichmentResult(status="failed", warnings=["Enrichment JSON поврежден."])
    elif isinstance(raw, dict):
        data = raw
    else:
        return EnrichmentResult(status="failed", warnings=["Enrichment result имеет неизвестный формат."])

    status = str(data.get("status") or "failed").strip().lower()
    if status not in ENRICHMENT_STATUSES:
        status = "failed"
    return EnrichmentResult(
        status=status,
        source_urls=_string_list(data.get("source_urls"))[:8],
        domain=str(data.get("domain") or "").strip().lower(),
        title=str(data.get("title") or "").strip()[:300],
        description=str(data.get("description") or "").strip()[:700],
        public_summary=str(data.get("public_summary") or "").strip()[:2500],
        likely_category=str(data.get("likely_category") or "").strip()[:160],
        signals=_string_list(data.get("signals"))[:12],
        source_basis=_string_list(data.get("source_basis"))[:8],
        warnings=_string_list(data.get("warnings"))[:12],
        fetched_at=str(data.get("fetched_at") or utc_now_iso()).strip(),
        confidence=normalize_confidence(data.get("confidence")),
    )
