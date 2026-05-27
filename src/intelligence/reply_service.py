from __future__ import annotations

from datetime import datetime
from typing import Any

from ..db import Database
from ..logger_setup import redact_secret
from .contact_timeline_service import ContactTimelineService


REPLY_STATUSES = {
    "interested",
    "maybe_later",
    "not_interested",
    "no_response",
    "follow_up_needed",
    "closed",
}


class ReplyService:
    def __init__(self, db: Database, timeline: ContactTimelineService | None = None):
        self.db = db
        self.timeline = timeline or ContactTimelineService(db)

    def add_reply(
        self,
        contact_id: int,
        reply_text: str,
        *,
        reply_status: str = "no_response",
        ai_summary: str = "",
        suggested_next_action: str = "",
    ) -> int:
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError("Contact not found")
        status = self.normalize_status(reply_status)
        reply_id = self.db.execute(
            """
            INSERT INTO replies (
                contact_id, campaign_id, reply_text, reply_status,
                ai_summary, suggested_next_action
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                contact_id,
                int(contact["campaign_id"]),
                redact_secret(reply_text.strip()),
                status,
                redact_secret(ai_summary.strip()),
                redact_secret(suggested_next_action.strip()),
            ),
        )
        self.db.update_contact(
            contact_id,
            {"replied_at": datetime.now().replace(microsecond=0).isoformat(sep=" ")},
        )
        self.timeline.record_event(
            contact_id,
            "reply_added",
            title="Добавлен reply",
            details=f"status={status}",
            metadata={"reply_id": reply_id, "reply_status": status},
        )
        return reply_id

    def update_reply_status(self, reply_id: int, reply_status: str) -> None:
        status = self.normalize_status(reply_status)
        reply = self.db.fetch_one("SELECT * FROM replies WHERE id = ?", (reply_id,))
        if not reply:
            raise ValueError("Reply not found")
        self.db.execute(
            """
            UPDATE replies
            SET reply_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, reply_id),
        )
        self.timeline.record_event(
            int(reply["contact_id"]),
            "status_changed",
            title="Reply status updated",
            details=f"{reply.get('reply_status')} -> {status}",
            metadata={"reply_id": reply_id, "reply_status": status},
        )

    def list_replies(self, campaign_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if campaign_id is None:
            return self.db.fetch_all(
                """
                SELECT replies.*, contacts.email, contacts.handle, contacts.external_id, contacts.channel
                FROM replies
                LEFT JOIN contacts ON contacts.id = replies.contact_id
                ORDER BY replies.created_at DESC, replies.id DESC
                LIMIT ?
                """,
                (limit,),
            )
        return self.db.fetch_all(
            """
            SELECT replies.*, contacts.email, contacts.handle, contacts.external_id, contacts.channel
            FROM replies
            LEFT JOIN contacts ON contacts.id = replies.contact_id
            WHERE replies.campaign_id = ?
            ORDER BY replies.created_at DESC, replies.id DESC
            LIMIT ?
            """,
            (campaign_id, limit),
        )

    def replies_for_contact(self, contact_id: int) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT *
            FROM replies
            WHERE contact_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (contact_id,),
        )

    @staticmethod
    def normalize_status(reply_status: str) -> str:
        status = (reply_status or "no_response").strip().lower()
        if status not in REPLY_STATUSES:
            return "no_response"
        return status
