from __future__ import annotations

import json
from typing import Any

from ..db import Database
from ..logger_setup import redact_secret
from .contact_timeline_service import ContactTimelineService
from .conversation_ai import ConversationAI, ConversationReplySuggestions
from .reply_service import ReplyService


LEAD_STATUSES = {
    "New",
    "Contacted",
    "Warm",
    "Interested",
    "Negotiating",
    "Closed",
    "Lost",
}


class ConversationService:
    def __init__(
        self,
        db: Database,
        timeline: ContactTimelineService | None = None,
        replies: ReplyService | None = None,
        conversation_ai: ConversationAI | None = None,
    ):
        self.db = db
        self.timeline = timeline or ContactTimelineService(db)
        self.replies = replies or ReplyService(db, self.timeline)
        self.ai = conversation_ai or ConversationAI()

    def get_or_create_thread(self, contact_id: int) -> dict[str, Any]:
        thread = self.thread_for_contact(contact_id)
        if thread:
            return thread
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError("Contact not found")
        thread_id = self.db.execute(
            """
            INSERT INTO conversation_threads (
                campaign_id, contact_id, channel, lead_status, unread_state
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(contact["campaign_id"]),
                contact_id,
                str(contact.get("channel") or "email"),
                str(contact.get("lead_status") or "New"),
                str(contact.get("unread_state") or "read"),
            ),
        )
        self.timeline.record_event(
            contact_id,
            "note_added",
            title="Conversation thread created",
            details="Conversation timeline initialized.",
            metadata={"thread_id": thread_id},
        )
        created = self.thread_for_contact(contact_id)
        if not created:
            raise RuntimeError("Conversation thread was not created")
        return created

    def thread_for_contact(self, contact_id: int) -> dict[str, Any] | None:
        return self.db.fetch_one(
            """
            SELECT conversation_threads.*, contacts.email, contacts.handle,
                   contacts.external_id, contacts.name, contacts.company
            FROM conversation_threads
            LEFT JOIN contacts ON contacts.id = conversation_threads.contact_id
            WHERE conversation_threads.contact_id = ?
            """,
            (contact_id,),
        )

    def list_inbox(
        self,
        campaign_id: int | None = None,
        *,
        channel: str | None = None,
        lead_status: str | None = None,
        unread: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        query = """
            SELECT conversation_threads.*, contacts.email, contacts.handle,
                   contacts.external_id, contacts.name, contacts.company,
                   contacts.subject, contacts.generated_message
            FROM conversation_threads
            LEFT JOIN contacts ON contacts.id = conversation_threads.contact_id
            WHERE 1 = 1
        """
        if campaign_id is not None:
            query += " AND conversation_threads.campaign_id = ?"
            params.append(campaign_id)
        if channel and channel != "all":
            query += " AND conversation_threads.channel = ?"
            params.append(channel)
        if lead_status and lead_status != "all":
            query += " AND conversation_threads.lead_status = ?"
            params.append(lead_status)
        if unread and unread != "all":
            query += " AND conversation_threads.unread_state = ?"
            params.append(unread)
        if search:
            pattern = f"%{search.strip()}%"
            query += """
                AND (
                    contacts.email LIKE ? OR contacts.handle LIKE ? OR contacts.external_id LIKE ?
                    OR contacts.name LIKE ? OR contacts.company LIKE ?
                    OR conversation_threads.summary LIKE ?
                )
            """
            params.extend([pattern] * 6)
        query += " ORDER BY conversation_threads.last_activity_at DESC, conversation_threads.id DESC LIMIT ?"
        params.append(limit)
        return self.db.fetch_all(query, params)

    def messages_for_thread(self, thread_id: int) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT *
            FROM conversation_messages
            WHERE thread_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (thread_id,),
        )

    def add_message(
        self,
        contact_id: int,
        *,
        direction: str,
        body: str,
        subject: str = "",
        message_type: str = "reply",
        status: str = "new",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError("Contact not found")
        thread = self.get_or_create_thread(contact_id)
        message_id = self.db.execute(
            """
            INSERT INTO conversation_messages (
                thread_id, contact_id, campaign_id, channel, direction,
                message_type, subject, body, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(thread["id"]),
                contact_id,
                int(contact["campaign_id"]),
                str(contact.get("channel") or "email"),
                direction,
                message_type,
                redact_secret(subject.strip()),
                redact_secret(body.strip()),
                status,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        self._touch_thread(int(thread["id"]), unread_state="unread" if direction == "inbound" else None)
        return message_id

    def ingest_manual_reply(
        self,
        contact_id: int,
        reply_text: str,
        *,
        reply_status: str = "no_response",
    ) -> dict[str, Any]:
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError("Contact not found")
        safe_reply = redact_secret(reply_text.strip())
        if not safe_reply:
            raise ValueError("Reply text is required")

        thread = self.get_or_create_thread(contact_id)
        reply_id = self.replies.add_reply(contact_id, safe_reply, reply_status=reply_status)
        message_id = self.add_message(
            contact_id,
            direction="inbound",
            body=safe_reply,
            message_type="reply",
            status=reply_status,
            metadata={"reply_id": reply_id},
        )
        analysis = self.ai.analyze_reply(contact, safe_reply, channel=str(contact.get("channel") or "email"))
        suggestions = self.ai.suggest_replies(contact, safe_reply, channel=str(contact.get("channel") or "email"))
        self._save_suggestions(int(thread["id"]), contact, suggestions, reply_id=reply_id)
        self.change_lead_status(contact_id, analysis.lead_status)
        self.db.update_contact(contact_id, {"unread_state": "unread"})
        self._update_thread_analysis(int(thread["id"]), analysis)
        self.timeline.record_event(
            contact_id,
            "reply_added",
            title="Reply added to conversation",
            details=analysis.summary,
            metadata={"reply_id": reply_id, "message_id": message_id, "intent": analysis.intent},
        )
        return {
            "thread": self.thread_for_contact(contact_id) or thread,
            "reply_id": reply_id,
            "message_id": message_id,
            "analysis": analysis,
            "suggestions": suggestions,
        }

    def change_lead_status(self, contact_id: int, lead_status: str) -> str:
        normalized = self.normalize_lead_status(lead_status)
        thread = self.get_or_create_thread(contact_id)
        old_status = str(thread.get("lead_status") or "New")
        self.db.update_contact(contact_id, {"lead_status": normalized})
        self.db.execute(
            """
            UPDATE conversation_threads
            SET lead_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (normalized, int(thread["id"])),
        )
        if old_status != normalized:
            self.timeline.record_event(
                contact_id,
                "status_changed",
                title="Lead status changed",
                details=f"{old_status} -> {normalized}",
                metadata={"lead_status": normalized},
            )
        return normalized

    def mark_thread_read(self, thread_id: int) -> None:
        thread = self.db.fetch_one("SELECT * FROM conversation_threads WHERE id = ?", (thread_id,))
        if not thread:
            return
        self.db.execute(
            """
            UPDATE conversation_threads
            SET unread_state = 'read', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (thread_id,),
        )
        self.db.update_contact(int(thread["contact_id"]), {"unread_state": "read"})

    def summarize_thread(self, thread_id: int) -> dict[str, Any]:
        thread = self.db.fetch_one("SELECT * FROM conversation_threads WHERE id = ?", (thread_id,))
        if not thread:
            raise ValueError("Conversation thread not found")
        messages = self.messages_for_thread(thread_id)
        inbound = [row for row in messages if row.get("direction") == "inbound"]
        latest = inbound[-1] if inbound else (messages[-1] if messages else {})
        contact = self.db.get_contact(int(thread["contact_id"])) or {}
        analysis = self.ai.analyze_reply(
            contact,
            str(latest.get("body") or "Conversation has no replies yet."),
            channel=str(thread.get("channel") or contact.get("channel") or "email"),
        )
        self._update_thread_analysis(thread_id, analysis)
        self.timeline.record_event(
            int(thread["contact_id"]),
            "note_added",
            title="Conversation summarized",
            details=analysis.summary,
            metadata={"thread_id": thread_id, "intent": analysis.intent},
        )
        return self.thread_for_contact(int(thread["contact_id"])) or {}

    def suggest_replies(self, contact_id: int, reply_text: str) -> ConversationReplySuggestions:
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError("Contact not found")
        thread = self.get_or_create_thread(contact_id)
        suggestions = self.ai.suggest_replies(
            contact,
            reply_text,
            channel=str(contact.get("channel") or "email"),
        )
        self._save_suggestions(int(thread["id"]), contact, suggestions)
        self.timeline.record_event(
            contact_id,
            "note_added",
            title="AI reply suggestions created",
            details=suggestions.summary,
            metadata={"thread_id": int(thread["id"]), "intent": suggestions.intent},
        )
        return suggestions

    def suggest_followup(self, contact_id: int) -> dict[str, Any]:
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError("Contact not found")
        thread = self.get_or_create_thread(contact_id)
        latest_reply = self.db.fetch_one(
            """
            SELECT reply_text
            FROM replies
            WHERE contact_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (contact_id,),
        )
        analysis = self.ai.analyze_reply(
            contact,
            str((latest_reply or {}).get("reply_text") or ""),
            channel=str(contact.get("channel") or "email"),
        )
        due_at = self.ai.suggested_due_at(analysis)
        suggestion_id = self.db.execute(
            """
            INSERT INTO followup_suggestions (
                thread_id, contact_id, campaign_id, suggested_due_at, tone,
                reason, recommendation, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'suggested')
            """,
            (
                int(thread["id"]),
                contact_id,
                int(contact["campaign_id"]),
                due_at,
                analysis.followup_tone,
                analysis.summary,
                analysis.recommended_next_action,
            ),
        )
        self.timeline.record_event(
            contact_id,
            "note_added",
            title="AI follow-up suggested",
            details=analysis.recommended_next_action,
            metadata={"followup_suggestion_id": suggestion_id, "due_at": due_at},
        )
        return {
            "id": suggestion_id,
            "due_at": due_at,
            "tone": analysis.followup_tone,
            "reason": analysis.summary,
            "recommendation": analysis.recommended_next_action,
        }

    def latest_suggestions(self, contact_id: int, limit: int = 5) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT *
            FROM ai_reply_suggestions
            WHERE contact_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (contact_id, limit),
        )

    def conversation_metrics(self, campaign_id: int) -> dict[str, Any]:
        rows = self.db.fetch_all(
            """
            SELECT lead_status, COUNT(*) AS count
            FROM conversation_threads
            WHERE campaign_id = ?
            GROUP BY lead_status
            """,
            (campaign_id,),
        )
        unread = self.db.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM conversation_threads
            WHERE campaign_id = ? AND unread_state = 'unread'
            """,
            (campaign_id,),
        )
        followups = self.db.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM followup_suggestions
            WHERE campaign_id = ? AND status = 'suggested'
            """,
            (campaign_id,),
        )
        return {
            "lead_statuses": {row["lead_status"]: int(row["count"]) for row in rows},
            "unread": int((unread or {}).get("count") or 0),
            "followup_suggestions": int((followups or {}).get("count") or 0),
        }

    def search(self, term: str, campaign_id: int | None = None) -> dict[str, list[dict[str, Any]]]:
        query = term.strip()
        if not query:
            return {"contacts": [], "conversations": [], "replies": [], "notes": []}
        contacts = self.db.list_contacts(campaign_id or self.db.get_default_campaign_id(), search=query)
        conversations = self.list_inbox(campaign_id, search=query)
        replies = self.db.fetch_all(
            """
            SELECT replies.*, contacts.email, contacts.handle, contacts.external_id
            FROM replies
            LEFT JOIN contacts ON contacts.id = replies.contact_id
            WHERE replies.reply_text LIKE ? OR replies.ai_summary LIKE ?
            ORDER BY replies.created_at DESC
            LIMIT 50
            """,
            (f"%{query}%", f"%{query}%"),
        )
        notes = self.db.fetch_all(
            """
            SELECT contact_events.*, contacts.email, contacts.handle, contacts.external_id
            FROM contact_events
            LEFT JOIN contacts ON contacts.id = contact_events.contact_id
            WHERE contact_events.title LIKE ? OR contact_events.details LIKE ?
            ORDER BY contact_events.created_at DESC
            LIMIT 50
            """,
            (f"%{query}%", f"%{query}%"),
        )
        return {
            "contacts": contacts,
            "conversations": conversations,
            "replies": replies,
            "notes": notes,
        }

    def _save_suggestions(
        self,
        thread_id: int,
        contact: dict[str, Any],
        suggestions: ConversationReplySuggestions,
        *,
        reply_id: int | None = None,
    ) -> int:
        return self.db.execute(
            """
            INSERT INTO ai_reply_suggestions (
                thread_id, contact_id, campaign_id, reply_id, channel,
                summary, intent, sentiment, urgency, recommended_next_action,
                short_reply, friendly_reply, formal_reply
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                int(contact["id"]),
                int(contact["campaign_id"]),
                reply_id,
                str(contact.get("channel") or "email"),
                redact_secret(suggestions.summary),
                suggestions.intent,
                suggestions.sentiment,
                suggestions.urgency,
                redact_secret(suggestions.recommended_next_action),
                redact_secret(suggestions.short_reply),
                redact_secret(suggestions.friendly_reply),
                redact_secret(suggestions.formal_reply),
            ),
        )

    def _update_thread_analysis(self, thread_id: int, analysis) -> None:
        self.db.execute(
            """
            UPDATE conversation_threads
            SET summary = ?, intent = ?, sentiment = ?, urgency = ?,
                recommended_next_action = ?, unread_state = 'unread',
                last_activity_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                redact_secret(analysis.summary),
                analysis.intent,
                analysis.sentiment,
                analysis.urgency,
                redact_secret(analysis.recommended_next_action),
                thread_id,
            ),
        )

    def _touch_thread(self, thread_id: int, unread_state: str | None = None) -> None:
        unread_sql = ", unread_state = ?" if unread_state else ""
        params: list[Any] = []
        if unread_state:
            params.append(unread_state)
        params.append(thread_id)
        self.db.execute(
            f"""
            UPDATE conversation_threads
            SET last_activity_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
                {unread_sql}
            WHERE id = ?
            """,
            params,
        )

    @staticmethod
    def normalize_lead_status(lead_status: str) -> str:
        normalized = (lead_status or "New").strip()
        aliases = {
            "new": "New",
            "contacted": "Contacted",
            "warm": "Warm",
            "interested": "Interested",
            "negotiating": "Negotiating",
            "closed": "Closed",
            "lost": "Lost",
        }
        normalized = aliases.get(normalized.lower(), normalized)
        if normalized not in LEAD_STATUSES:
            return "New"
        return normalized
