from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..db import Database
from ..logger_setup import redact_secret
from .operator_metrics import OperatorSessionMetrics
from .review_queue import ReviewQueueFilters


PRECISION_MODE = "precision"
HIGH_VOLUME_MODE = "high_volume"
OPERATOR_MODES = {
    PRECISION_MODE: "Precision Mode",
    HIGH_VOLUME_MODE: "High Volume Mode",
}


@dataclass(frozen=True, slots=True)
class OperatorSessionState:
    id: int
    campaign_id: int
    mode: str
    current_contact_id: int | None = None
    review_index: int = 0
    filters: ReviewQueueFilters = field(default_factory=ReviewQueueFilters)
    draft_variant: str = ""
    unsaved_draft: str = ""
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "mode": self.mode,
            "current_contact_id": self.current_contact_id,
            "review_index": self.review_index,
            "filters": self.filters.to_dict(),
            "draft_variant": self.draft_variant,
            "unsaved_draft": self.unsaved_draft,
            "status": self.status,
        }


def normalize_operator_mode(mode: str | None) -> str:
    key = (mode or PRECISION_MODE).strip().lower()
    return key if key in OPERATOR_MODES else PRECISION_MODE


class OperatorSessionManager:
    def __init__(self, db: Database):
        self.db = db

    def start_session(
        self,
        campaign_id: int,
        *,
        mode: str = HIGH_VOLUME_MODE,
        filters: ReviewQueueFilters | None = None,
        current_contact_id: int | None = None,
    ) -> OperatorSessionState:
        selected_filters = filters or ReviewQueueFilters()
        session_id = self.db.execute(
            """
            INSERT INTO operator_sessions (
                campaign_id, mode, current_contact_id, review_index, filters_json, draft_variant, unsaved_draft, status
            ) VALUES (?, ?, ?, 0, ?, '', '', 'active')
            """,
            (
                campaign_id,
                normalize_operator_mode(mode),
                current_contact_id,
                json.dumps(selected_filters.to_dict(), ensure_ascii=False),
            ),
        )
        return self.restore_session(session_id=session_id) or OperatorSessionState(
            id=session_id,
            campaign_id=campaign_id,
            mode=normalize_operator_mode(mode),
            current_contact_id=current_contact_id,
            filters=selected_filters,
        )

    def restore_session(
        self,
        *,
        session_id: int | None = None,
        campaign_id: int | None = None,
    ) -> OperatorSessionState | None:
        if session_id:
            row = self.db.fetch_one("SELECT * FROM operator_sessions WHERE id = ?", (session_id,))
        elif campaign_id:
            row = self.db.fetch_one(
                """
                SELECT *
                FROM operator_sessions
                WHERE campaign_id = ? AND status = 'active'
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (campaign_id,),
            )
        else:
            row = self.db.fetch_one(
                """
                SELECT *
                FROM operator_sessions
                WHERE status = 'active'
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """
            )
        return self._row_to_state(row) if row else None

    def save_position(
        self,
        session_id: int,
        *,
        contact_id: int | None,
        review_index: int,
        filters: ReviewQueueFilters | None = None,
        draft_variant: str | None = None,
        unsaved_draft: str | None = None,
    ) -> None:
        assignments = ["current_contact_id = ?", "review_index = ?", "updated_at = CURRENT_TIMESTAMP"]
        params: list[Any] = [contact_id, max(review_index, 0)]
        if filters is not None:
            assignments.append("filters_json = ?")
            params.append(json.dumps(filters.to_dict(), ensure_ascii=False))
        if draft_variant is not None:
            assignments.append("draft_variant = ?")
            params.append(draft_variant)
        if unsaved_draft is not None:
            assignments.append("unsaved_draft = ?")
            params.append(redact_secret(unsaved_draft))
        params.append(session_id)
        self.db.execute(
            f"UPDATE operator_sessions SET {', '.join(assignments)} WHERE id = ?",
            params,
        )

    def close_session(self, session_id: int) -> None:
        self.db.execute(
            "UPDATE operator_sessions SET status = 'closed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )

    def record_action(
        self,
        session_id: int,
        contact_id: int | None,
        action: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        return self.db.execute(
            """
            INSERT INTO operator_session_events (
                session_id, contact_id, action, metadata_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                session_id,
                contact_id,
                action,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

    def save_feedback(
        self,
        *,
        contact_id: int,
        rating: str,
        note: str = "",
        session_id: int | None = None,
    ) -> int:
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError("Contact not found.")
        clean_rating = (rating or "").strip().lower()
        if clean_rating not in {"useful", "generic", "inaccurate", "too_aggressive", "weak_personalization"}:
            raise ValueError("Unsupported AI feedback rating.")
        return self.db.execute(
            """
            INSERT INTO ai_feedback (
                contact_id, campaign_id, session_id, rating, note
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                contact_id,
                int(contact["campaign_id"]),
                session_id,
                clean_rating,
                redact_secret(note),
            ),
        )

    def metrics(self, session_id: int) -> OperatorSessionMetrics:
        def count(actions: tuple[str, ...]) -> int:
            placeholders = ", ".join("?" for _ in actions)
            row = self.db.fetch_one(
                f"""
                SELECT COUNT(DISTINCT contact_id) AS count
                FROM operator_session_events
                WHERE session_id = ? AND action IN ({placeholders})
                  AND contact_id IS NOT NULL
                """,
                (session_id, *actions),
            )
            return int(row["count"] if row else 0)

        reviewed = count(("approve_draft", "copy_message", "mark_manually_sent"))
        copied = count(("copy_message",))
        sent = count(("mark_manually_sent",))
        skipped = count(("skip_lead",))
        accepted = count(("approve_draft", "mark_manually_sent"))
        replies = count(("reply_received",))
        followups = count(("follow_up", "followup_done"))
        ai_acceptance_rate = round(accepted / reviewed, 2) if reviewed else 0.0
        followup_conversion = round(followups / reviewed, 2) if reviewed else 0.0
        return OperatorSessionMetrics(
            reviewed_leads=reviewed,
            copied_messages=copied,
            manually_sent=sent,
            skipped_leads=skipped,
            replies_received=replies,
            ai_acceptance_rate=ai_acceptance_rate,
            avg_review_time_seconds=0.0,
            followup_conversion=followup_conversion,
        )

    @staticmethod
    def _row_to_state(row: dict[str, Any]) -> OperatorSessionState:
        try:
            filters_data = json.loads(row.get("filters_json") or "{}")
        except json.JSONDecodeError:
            filters_data = {}
        current = row.get("current_contact_id")
        return OperatorSessionState(
            id=int(row["id"]),
            campaign_id=int(row["campaign_id"]),
            mode=normalize_operator_mode(str(row.get("mode") or PRECISION_MODE)),
            current_contact_id=int(current) if current not in (None, "") else None,
            review_index=int(row.get("review_index") or 0),
            filters=ReviewQueueFilters.from_dict(filters_data),
            draft_variant=str(row.get("draft_variant") or ""),
            unsaved_draft=str(row.get("unsaved_draft") or ""),
            status=str(row.get("status") or "active"),
        )


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")
