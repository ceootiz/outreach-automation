from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CONTACT_STATUSES = {
    "new",
    "generation_queued",
    "generating",
    "pending_review",
    "approved",
    "queued",
    "sending",
    "dry_run_sent",
    "sent",
    "failed",
    "blacklisted",
    "cancelled",
}


@dataclass(slots=True)
class Campaign:
    id: int
    name: str
    created_at: str
    status: str


@dataclass(slots=True)
class Contact:
    id: int | None
    campaign_id: int
    email: str
    name: str = ""
    company: str = ""
    topic: str = ""
    website: str = ""
    social_profile: str = ""
    subject: str = ""
    base_message: str = ""
    generated_message: str = ""
    ai_generated: int = 0
    ai_confidence: float | None = None
    ai_notes: str = ""
    ai_warnings: str = ""
    status: str = "new"
    last_error: str = ""
    sent_at: str | None = None
    replied_at: str | None = None
    follow_up_due_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Contact":
        return cls(
            id=row.get("id"),
            campaign_id=row["campaign_id"],
            email=row.get("email") or "",
            name=row.get("name") or "",
            company=row.get("company") or "",
            topic=row.get("topic") or "",
            website=row.get("website") or "",
            social_profile=row.get("social_profile") or "",
            subject=row.get("subject") or "",
            base_message=row.get("base_message") or "",
            generated_message=row.get("generated_message") or "",
            ai_generated=int(row.get("ai_generated") or 0),
            ai_confidence=row.get("ai_confidence"),
            ai_notes=row.get("ai_notes") or "",
            ai_warnings=row.get("ai_warnings") or "",
            status=row.get("status") or "new",
            last_error=row.get("last_error") or "",
            sent_at=row.get("sent_at"),
            replied_at=row.get("replied_at"),
            follow_up_due_at=row.get("follow_up_due_at"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


@dataclass(slots=True)
class EmailTemplate:
    id: int | None
    name: str
    subject_template: str
    body_template: str
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class GeneratedEmail:
    subject: str
    body: str
