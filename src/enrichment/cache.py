from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ..db import Database
from .result_schema import EnrichmentResult, parse_enrichment_result


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


class EnrichmentCache:
    def __init__(self, db: Database):
        self.db = db

    def get(self, url: str, *, ttl_days: int = 7) -> EnrichmentResult | None:
        row = self.db.fetch_one(
            """
            SELECT *
            FROM enrichment_cache
            WHERE cache_key = ?
            LIMIT 1
            """,
            (self._cache_key(url),),
        )
        if not row:
            return None
        fetched_at = _parse_timestamp(str(row.get("fetched_at") or ""))
        if not fetched_at:
            return None
        if _utc_now() - fetched_at > timedelta(days=max(1, int(ttl_days or 7))):
            return None
        return parse_enrichment_result(row.get("result_json") or "{}")

    def save(self, url: str, result: EnrichmentResult, *, ttl_days: int = 7) -> None:
        data = result.to_dict()
        fetched_at = data.get("fetched_at") or _utc_now().isoformat()
        expires_at = (_utc_now() + timedelta(days=max(1, int(ttl_days or 7)))).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.db.execute(
            """
            INSERT INTO enrichment_cache (
                cache_key, url, domain, fetched_at, expires_at, status, title,
                description, public_summary, error, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                url = excluded.url,
                domain = excluded.domain,
                fetched_at = excluded.fetched_at,
                expires_at = excluded.expires_at,
                status = excluded.status,
                title = excluded.title,
                description = excluded.description,
                public_summary = excluded.public_summary,
                error = excluded.error,
                result_json = excluded.result_json
            """,
            (
                self._cache_key(url),
                url,
                result.domain,
                fetched_at,
                expires_at,
                result.status,
                result.title,
                result.description,
                result.public_summary,
                "; ".join(result.warnings),
                json.dumps(data, ensure_ascii=False),
            ),
        )

    @staticmethod
    def _cache_key(url: str) -> str:
        return (url or "").strip().lower().rstrip("/")
