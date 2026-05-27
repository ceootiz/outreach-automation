from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .db import Database


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

ALLOWED_TRANSITIONS = {
    "new": {"generation_queued"},
    "generation_queued": {"generating"},
    "generating": {"pending_review", "failed"},
    "pending_review": {"approved"},
    "approved": {"queued", "cancelled"},
    "queued": {"sending", "cancelled"},
    "sending": {"sent", "dry_run_sent", "failed"},
    "failed": {"queued", "approved", "generation_queued"},
    "dry_run_sent": {"approved"},
    "sent": set(),
    "blacklisted": set(),
    "cancelled": set(),
}


@dataclass(slots=True)
class TransitionResult:
    ok: bool
    from_status: str
    to_status: str
    contact_id: int | None = None
    error: str = ""


def can_transition(from_status: str, to_status: str) -> bool:
    if from_status == to_status:
        return True
    if to_status == "blacklisted":
        return True
    if from_status == "blacklisted":
        return False
    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())


def get_allowed_transitions(from_status: str) -> set[str]:
    allowed = set(ALLOWED_TRANSITIONS.get(from_status, set()))
    if from_status != "blacklisted":
        allowed.add("blacklisted")
    allowed.add(from_status)
    return allowed


def transition_contact(
    db: Database,
    contact_id: int,
    to_status: str,
    last_error: str | None = None,
) -> TransitionResult:
    contact = db.get_contact(contact_id)
    if not contact:
        return TransitionResult(
            ok=False,
            from_status="",
            to_status=to_status,
            contact_id=contact_id,
            error=f"Contact {contact_id} not found.",
        )

    from_status = contact.get("status") or "new"
    if to_status not in CONTACT_STATUSES:
        return TransitionResult(
            ok=False,
            from_status=from_status,
            to_status=to_status,
            contact_id=contact_id,
            error=f"Unknown contact status: {to_status}.",
        )

    if not can_transition(from_status, to_status):
        return TransitionResult(
            ok=False,
            from_status=from_status,
            to_status=to_status,
            contact_id=contact_id,
            error=f"Invalid contact transition: {from_status} -> {to_status}.",
        )

    fields = {"status": to_status}
    if last_error is not None:
        fields["last_error"] = last_error
    db.update_contact(contact_id, fields)
    return TransitionResult(
        ok=True,
        from_status=from_status,
        to_status=to_status,
        contact_id=contact_id,
    )


def bulk_transition(
    db: Database,
    contact_ids: Iterable[int],
    to_status: str,
    last_error: str | None = None,
) -> list[TransitionResult]:
    return [
        transition_contact(db, contact_id, to_status, last_error=last_error)
        for contact_id in contact_ids
    ]
