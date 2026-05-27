from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..db import Database
from .contact_timeline_service import ContactTimelineService


class FollowUpService:
    def __init__(self, db: Database, timeline: ContactTimelineService | None = None):
        self.db = db
        self.timeline = timeline or ContactTimelineService(db)

    def schedule_followup(
        self,
        contact_id: int,
        *,
        due_at: str | None = None,
        days_from_now: int = 2,
        note: str = "",
    ) -> int:
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError("Contact not found")
        if due_at is None:
            due = datetime.now().replace(microsecond=0) + timedelta(days=max(days_from_now, 0))
            due_at = due.isoformat(sep=" ")
        followup_id = self.db.execute(
            """
            INSERT INTO followups (contact_id, campaign_id, due_at, status, note)
            VALUES (?, ?, ?, 'scheduled', ?)
            """,
            (contact_id, int(contact["campaign_id"]), due_at, note.strip()),
        )
        self.timeline.record_event(
            contact_id,
            "note_added",
            title="Follow-up scheduled",
            details=f"due_at={due_at}",
            metadata={"followup_id": followup_id},
        )
        return followup_id

    def due_followups(self, campaign_id: int | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        query = """
            SELECT followups.*, contacts.email, contacts.handle, contacts.external_id, contacts.channel
            FROM followups
            LEFT JOIN contacts ON contacts.id = followups.contact_id
            WHERE followups.status = 'scheduled'
              AND datetime(followups.due_at) <= datetime('now', 'localtime')
        """
        if campaign_id is not None:
            query += " AND followups.campaign_id = ?"
            params.append(campaign_id)
        query += " ORDER BY followups.due_at ASC, followups.id ASC"
        return self.db.fetch_all(query, params)

    def mark_done(self, followup_id: int) -> None:
        self.db.execute(
            """
            UPDATE followups
            SET status = 'done', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (followup_id,),
        )
