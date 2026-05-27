from __future__ import annotations

from typing import Any

from ..db import Database
from .search_index import compact_text, like_pattern, title_from_contact
from .search_result import SearchResult


class GlobalSearchService:
    def __init__(self, db: Database):
        self.db = db

    def search(
        self,
        query: str,
        *,
        campaign_id: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        needle = (query or "").strip()
        if not needle:
            return []
        results = self._run_loaders(needle, campaign_id=campaign_id, limit=limit)
        if len(results) < min(limit, 8):
            results.extend(self._token_fallback(needle, campaign_id=campaign_id, limit=limit - len(results)))
        return [result.to_dict() for result in self._dedupe(results)[:limit]]

    def _run_loaders(self, query: str, *, campaign_id: int | None, limit: int) -> list[SearchResult]:
        remaining = max(limit, 1)
        results: list[SearchResult] = []
        for loader in (
            self._contacts,
            self._campaigns,
            self._replies,
            self._messages,
            self._timeline,
            self._send_logs,
            self._followups,
            self._ai_metrics,
        ):
            if remaining <= 0:
                break
            batch = loader(query, campaign_id=campaign_id, limit=remaining)
            results.extend(batch)
            remaining = limit - len(results)
        return results[:limit]

    def _token_fallback(self, query: str, *, campaign_id: int | None, limit: int) -> list[SearchResult]:
        if limit <= 0:
            return []
        tokens = [token for token in query.replace("/", " ").replace("@", " ").split() if len(token) >= 3]
        if len(tokens) <= 1:
            return []
        results: list[SearchResult] = []
        remaining = limit
        for token in tokens[:4]:
            if remaining <= 0:
                break
            batch = self._run_loaders(token, campaign_id=campaign_id, limit=remaining)
            results.extend(batch)
            remaining = limit - len(results)
        return results

    @staticmethod
    def _dedupe(results: list[SearchResult]) -> list[SearchResult]:
        seen: set[tuple[str, int | None]] = set()
        deduped: list[SearchResult] = []
        for result in results:
            key = (result.result_type, result.object_id)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(result)
        return deduped

    def _contacts(self, query: str, *, campaign_id: int | None, limit: int) -> list[SearchResult]:
        pattern = like_pattern(query)
        where = """
            (contacts.email LIKE ? OR contacts.handle LIKE ? OR contacts.profile_url LIKE ?
             OR contacts.external_id LIKE ? OR contacts.name LIKE ? OR contacts.company LIKE ?
             OR contacts.topic LIKE ? OR contacts.website LIKE ? OR contacts.social_profile LIKE ?
             OR contacts.subject LIKE ? OR contacts.base_message LIKE ? OR contacts.generated_message LIKE ?
             OR contacts.ai_notes LIKE ? OR contacts.ai_warnings LIKE ? OR contacts.research_brief_json LIKE ?
             OR contacts.enrichment_result_json LIKE ? OR contacts.enrichment_warnings LIKE ?)
        """
        params: list[Any] = [pattern] * 17
        campaign_clause = ""
        if campaign_id is not None:
            campaign_clause = "AND contacts.campaign_id = ?"
            params.append(campaign_id)
        params.append(limit)
        rows = self.db.fetch_all(
            f"""
            SELECT contacts.*, campaigns.name AS campaign_name
            FROM contacts
            LEFT JOIN campaigns ON campaigns.id = contacts.campaign_id
            WHERE {where} {campaign_clause}
            ORDER BY contacts.updated_at DESC, contacts.id DESC
            LIMIT ?
            """,
            params,
        )
        return [
            SearchResult(
                result_type="contact",
                title=title_from_contact(row),
                snippet=compact_text(
                    row.get("campaign_name"),
                    row.get("email"),
                    row.get("handle"),
                    row.get("profile_url"),
                    row.get("company"),
                    row.get("generated_message"),
                ),
                channel=str(row.get("channel") or ""),
                campaign_id=int(row["campaign_id"]) if row.get("campaign_id") is not None else None,
                contact_id=int(row["id"]),
                object_id=int(row["id"]),
            )
            for row in rows
        ]

    def _campaigns(self, query: str, *, campaign_id: int | None, limit: int) -> list[SearchResult]:
        pattern = like_pattern(query)
        params: list[Any] = [pattern, pattern]
        campaign_clause = ""
        if campaign_id is not None:
            campaign_clause = "AND id = ?"
            params.append(campaign_id)
        params.append(limit)
        rows = self.db.fetch_all(
            f"""
            SELECT *
            FROM campaigns
            WHERE (name LIKE ? OR status LIKE ?) {campaign_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            params,
        )
        return [
            SearchResult(
                result_type="campaign",
                title=str(row.get("name") or "Campaign"),
                snippet=compact_text("Campaign", row.get("status"), row.get("created_at")),
                campaign_id=int(row["id"]),
                object_id=int(row["id"]),
            )
            for row in rows
        ]

    def _replies(self, query: str, *, campaign_id: int | None, limit: int) -> list[SearchResult]:
        pattern = like_pattern(query)
        params: list[Any] = [pattern, pattern, pattern]
        campaign_clause = ""
        if campaign_id is not None:
            campaign_clause = "AND replies.campaign_id = ?"
            params.append(campaign_id)
        params.append(limit)
        rows = self.db.fetch_all(
            f"""
            SELECT replies.*, contacts.channel, contacts.email, contacts.handle, campaigns.name AS campaign_name
            FROM replies
            LEFT JOIN contacts ON contacts.id = replies.contact_id
            LEFT JOIN campaigns ON campaigns.id = replies.campaign_id
            WHERE (replies.reply_text LIKE ? OR replies.ai_summary LIKE ? OR replies.suggested_next_action LIKE ?)
              {campaign_clause}
            ORDER BY replies.created_at DESC, replies.id DESC
            LIMIT ?
            """,
            params,
        )
        return [
            SearchResult(
                result_type="reply",
                title=compact_text("Reply", row.get("email"), row.get("handle"), limit=90),
                snippet=compact_text(row.get("campaign_name"), row.get("reply_status"), row.get("reply_text"), row.get("ai_summary")),
                channel=str(row.get("channel") or ""),
                campaign_id=int(row["campaign_id"]) if row.get("campaign_id") is not None else None,
                contact_id=int(row["contact_id"]) if row.get("contact_id") is not None else None,
                object_id=int(row["id"]),
            )
            for row in rows
        ]

    def _messages(self, query: str, *, campaign_id: int | None, limit: int) -> list[SearchResult]:
        pattern = like_pattern(query)
        params: list[Any] = [pattern, pattern, pattern, pattern]
        campaign_clause = ""
        if campaign_id is not None:
            campaign_clause = "AND conversation_messages.campaign_id = ?"
            params.append(campaign_id)
        params.append(limit)
        rows = self.db.fetch_all(
            f"""
            SELECT conversation_messages.*, campaigns.name AS campaign_name
            FROM conversation_messages
            LEFT JOIN campaigns ON campaigns.id = conversation_messages.campaign_id
            WHERE (conversation_messages.subject LIKE ? OR conversation_messages.body LIKE ?
                   OR conversation_messages.sender LIKE ? OR conversation_messages.metadata_json LIKE ?)
              {campaign_clause}
            ORDER BY conversation_messages.created_at DESC, conversation_messages.id DESC
            LIMIT ?
            """,
            params,
        )
        return [
            SearchResult(
                result_type="message",
                title=compact_text(row.get("direction"), row.get("message_type"), row.get("sender"), limit=90),
                snippet=compact_text(row.get("campaign_name"), row.get("subject"), row.get("body")),
                channel=str(row.get("channel") or ""),
                campaign_id=int(row["campaign_id"]) if row.get("campaign_id") is not None else None,
                contact_id=int(row["contact_id"]) if row.get("contact_id") is not None else None,
                object_id=int(row["id"]),
            )
            for row in rows
        ]

    def _timeline(self, query: str, *, campaign_id: int | None, limit: int) -> list[SearchResult]:
        pattern = like_pattern(query)
        params: list[Any] = [pattern, pattern, pattern]
        campaign_clause = ""
        if campaign_id is not None:
            campaign_clause = "AND contact_events.campaign_id = ?"
            params.append(campaign_id)
        params.append(limit)
        rows = self.db.fetch_all(
            f"""
            SELECT contact_events.*, contacts.channel, contacts.email, contacts.handle
            FROM contact_events
            LEFT JOIN contacts ON contacts.id = contact_events.contact_id
            WHERE (contact_events.title LIKE ? OR contact_events.details LIKE ? OR contact_events.metadata_json LIKE ?)
              {campaign_clause}
            ORDER BY contact_events.created_at DESC, contact_events.id DESC
            LIMIT ?
            """,
            params,
        )
        return [
            SearchResult(
                result_type="timeline",
                title=compact_text(row.get("title"), row.get("event_type"), limit=90),
                snippet=compact_text(row.get("email"), row.get("handle"), row.get("details")),
                channel=str(row.get("channel") or ""),
                campaign_id=int(row["campaign_id"]) if row.get("campaign_id") is not None else None,
                contact_id=int(row["contact_id"]) if row.get("contact_id") is not None else None,
                object_id=int(row["id"]),
            )
            for row in rows
        ]

    def _send_logs(self, query: str, *, campaign_id: int | None, limit: int) -> list[SearchResult]:
        pattern = like_pattern(query)
        params: list[Any] = [pattern, pattern, pattern, pattern]
        campaign_clause = ""
        if campaign_id is not None:
            campaign_clause = "AND send_logs.campaign_id = ?"
            params.append(campaign_id)
        params.append(limit)
        rows = self.db.fetch_all(
            f"""
            SELECT send_logs.*, campaigns.name AS campaign_name
            FROM send_logs
            LEFT JOIN campaigns ON campaigns.id = send_logs.campaign_id
            WHERE (send_logs.platform_recipient LIKE ? OR send_logs.action LIKE ?
                   OR send_logs.status LIKE ? OR send_logs.error LIKE ?)
              {campaign_clause}
            ORDER BY send_logs.created_at DESC, send_logs.id DESC
            LIMIT ?
            """,
            params,
        )
        return [
            SearchResult(
                result_type="send_log",
                title=compact_text(row.get("action"), row.get("status"), limit=90),
                snippet=compact_text(row.get("campaign_name"), row.get("platform_recipient"), row.get("error")),
                channel=str(row.get("channel") or ""),
                campaign_id=int(row["campaign_id"]) if row.get("campaign_id") is not None else None,
                contact_id=int(row["contact_id"]) if row.get("contact_id") is not None else None,
                object_id=int(row["id"]),
            )
            for row in rows
        ]

    def _followups(self, query: str, *, campaign_id: int | None, limit: int) -> list[SearchResult]:
        pattern = like_pattern(query)
        params: list[Any] = [pattern, pattern]
        campaign_clause = ""
        if campaign_id is not None:
            campaign_clause = "AND followups.campaign_id = ?"
            params.append(campaign_id)
        params.append(limit)
        rows = self.db.fetch_all(
            f"""
            SELECT followups.*, contacts.channel, contacts.email, contacts.handle
            FROM followups
            LEFT JOIN contacts ON contacts.id = followups.contact_id
            WHERE (followups.note LIKE ? OR followups.status LIKE ?) {campaign_clause}
            ORDER BY followups.due_at DESC, followups.id DESC
            LIMIT ?
            """,
            params,
        )
        return [
            SearchResult(
                result_type="followup",
                title=compact_text("Follow-up", row.get("status"), row.get("due_at"), limit=90),
                snippet=compact_text(row.get("email"), row.get("handle"), row.get("note")),
                channel=str(row.get("channel") or ""),
                campaign_id=int(row["campaign_id"]) if row.get("campaign_id") is not None else None,
                contact_id=int(row["contact_id"]) if row.get("contact_id") is not None else None,
                object_id=int(row["id"]),
            )
            for row in rows
        ]

    def _ai_metrics(self, query: str, *, campaign_id: int | None, limit: int) -> list[SearchResult]:
        pattern = like_pattern(query)
        params: list[Any] = [pattern, pattern, pattern]
        campaign_clause = ""
        if campaign_id is not None:
            campaign_clause = "AND ai_metrics.campaign_id = ?"
            params.append(campaign_id)
        params.append(limit)
        rows = self.db.fetch_all(
            f"""
            SELECT ai_metrics.*, contacts.channel, contacts.email, contacts.handle
            FROM ai_metrics
            LEFT JOIN contacts ON contacts.id = ai_metrics.contact_id
            WHERE (ai_metrics.spam_risk LIKE ? OR ai_metrics.personalization_quality LIKE ? OR ai_metrics.warnings LIKE ?)
              {campaign_clause}
            ORDER BY ai_metrics.created_at DESC, ai_metrics.id DESC
            LIMIT ?
            """,
            params,
        )
        return [
            SearchResult(
                result_type="ai_metric",
                title=compact_text("AI quality", row.get("spam_risk"), row.get("personalization_quality"), limit=90),
                snippet=compact_text(row.get("email"), row.get("handle"), row.get("warnings")),
                channel=str(row.get("channel") or ""),
                campaign_id=int(row["campaign_id"]) if row.get("campaign_id") is not None else None,
                contact_id=int(row["contact_id"]) if row.get("contact_id") is not None else None,
                object_id=int(row["id"]),
            )
            for row in rows
        ]
