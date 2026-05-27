from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from .db import Database
from .logger_setup import redact_secret
from .state_machine import transition_contact


JOB_TYPES = {
    "generate_message",
    "ai_generate_draft",
    "ai_research_contact",
    "ai_write_from_brief",
    "ai_dual_brain_generate",
    "enrich_contact",
    "enrich_bulk_contacts",
    "ai_research_from_enrichment",
    "ai_generate_reply",
    "ai_summarize_reply",
    "ai_followup_suggestion",
    "ai_stage_suggestion",
    "ai_score_draft",
    "email_sync",
    "telegram_sync",
    "dry_run_send",
    "live_send",
    "export_report",
    "followup_reminder",
}
JOB_STATUSES = {
    "pending",
    "queued",
    "running",
    "paused",
    "completed",
    "failed",
    "cancelled",
}


@dataclass(slots=True)
class QueueResult:
    ok: bool
    job_id: int | None = None
    job_group_id: str | None = None
    count: int = 0
    error: str = ""


class QueueService:
    def __init__(self, db: Database):
        self.db = db

    def enqueue_job(
        self,
        job_type: str,
        campaign_id: int | None = None,
        contact_id: int | None = None,
        job_group_id: str | None = None,
        priority: int = 100,
        max_attempts: int = 3,
        payload: dict[str, Any] | None = None,
        status: str = "queued",
        channel: str = "email",
    ) -> QueueResult:
        if job_type not in JOB_TYPES:
            return QueueResult(False, error=f"Unknown job_type: {job_type}.")
        if status not in JOB_STATUSES:
            return QueueResult(False, error=f"Unknown job status: {status}.")

        group_id = job_group_id or str(uuid.uuid4())
        job_id = self.db.execute(
            """
            INSERT INTO job_queue (
                campaign_id, contact_id, job_group_id, channel, job_type, status,
                priority, max_attempts, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                campaign_id,
                contact_id,
                group_id,
                channel or "email",
                job_type,
                status,
                priority,
                max_attempts,
                json.dumps(payload or {}, ensure_ascii=False),
            ),
        )
        return QueueResult(True, job_id=job_id, job_group_id=group_id, count=1)

    def enqueue_generate_messages(self, campaign_id: int, channel: str | None = None) -> QueueResult:
        contacts = self._contacts_for_status(campaign_id, "new", channel)
        group_id = str(uuid.uuid4())
        count = 0
        errors: list[str] = []
        for contact in contacts:
            transition = transition_contact(self.db, contact["id"], "generation_queued")
            if not transition.ok:
                errors.append(transition.error)
                continue
            result = self.enqueue_job(
                "generate_message",
                campaign_id=campaign_id,
                contact_id=contact["id"],
                job_group_id=group_id,
                channel=str(contact.get("channel") or channel or "email"),
            )
            if result.ok:
                count += 1
            else:
                errors.append(result.error)
        return QueueResult(
            ok=not errors,
            job_group_id=group_id,
            count=count,
            error="; ".join(errors),
        )

    def enqueue_ai_generate_drafts(
        self,
        campaign_id: int,
        *,
        contact_ids: list[int] | None = None,
        campaign_topic: str = "",
        tone: str = "friendly",
        max_count: int | None = None,
        channel: str | None = None,
        use_enrichment: bool = False,
    ) -> QueueResult:
        channel_clause = ""
        channel_params: list[Any] = []
        if channel:
            channel_clause = " AND channel = ?"
            channel_params.append(channel)
        if contact_ids:
            placeholders = ", ".join("?" for _ in contact_ids)
            contacts = self.db.fetch_all(
                f"""
                SELECT *
                FROM contacts
                WHERE campaign_id = ?
                  AND id IN ({placeholders})
                  AND status IN ('new', 'failed')
                  {channel_clause}
                ORDER BY id ASC
                """,
                [campaign_id, *contact_ids, *channel_params],
            )
        else:
            contacts = self.db.fetch_all(
                f"""
                SELECT *
                FROM contacts
                WHERE campaign_id = ?
                  AND status IN ('new', 'failed')
                  {channel_clause}
                ORDER BY id ASC
                """,
                [campaign_id, *channel_params],
            )
        if max_count is not None:
            contacts = contacts[: max(int(max_count), 0)]

        group_id = str(uuid.uuid4())
        count = 0
        errors: list[str] = []
        payload = {
            "campaign_topic": campaign_topic,
            "tone": tone,
            "channel": channel or "",
            "use_enrichment": bool(use_enrichment),
        }
        for contact in contacts:
            transition = transition_contact(self.db, contact["id"], "generation_queued")
            if not transition.ok:
                errors.append(transition.error)
                continue
            result = self.enqueue_job(
                "ai_generate_draft",
                campaign_id=campaign_id,
                contact_id=contact["id"],
                job_group_id=group_id,
                payload=payload,
                channel=str(contact.get("channel") or channel or "email"),
            )
            if result.ok:
                count += 1
            else:
                errors.append(result.error)
        return QueueResult(
            ok=not errors,
            job_group_id=group_id,
            count=count,
            error="; ".join(errors),
        )

    def enqueue_ai_dual_brain_drafts(
        self,
        campaign_id: int,
        *,
        contact_ids: list[int] | None = None,
        campaign_topic: str = "",
        tone: str = "friendly",
        max_count: int | None = None,
        channel: str | None = None,
        use_enrichment: bool = False,
    ) -> QueueResult:
        channel_clause = ""
        channel_params: list[Any] = []
        if channel:
            channel_clause = " AND channel = ?"
            channel_params.append(channel)
        if contact_ids:
            placeholders = ", ".join("?" for _ in contact_ids)
            contacts = self.db.fetch_all(
                f"""
                SELECT *
                FROM contacts
                WHERE campaign_id = ?
                  AND id IN ({placeholders})
                  AND status IN ('new', 'failed')
                  {channel_clause}
                ORDER BY id ASC
                """,
                [campaign_id, *contact_ids, *channel_params],
            )
        else:
            contacts = self.db.fetch_all(
                f"""
                SELECT *
                FROM contacts
                WHERE campaign_id = ?
                  AND status IN ('new', 'failed')
                  {channel_clause}
                ORDER BY id ASC
                """,
                [campaign_id, *channel_params],
            )
        if max_count is not None:
            contacts = contacts[: max(int(max_count), 0)]

        group_id = str(uuid.uuid4())
        count = 0
        errors: list[str] = []
        payload = {
            "campaign_topic": campaign_topic,
            "tone": tone,
            "channel": channel or "",
            "use_enrichment": bool(use_enrichment),
        }
        for contact in contacts:
            transition = transition_contact(self.db, contact["id"], "generation_queued")
            if not transition.ok:
                errors.append(transition.error)
                continue
            result = self.enqueue_job(
                "ai_dual_brain_generate",
                campaign_id=campaign_id,
                contact_id=contact["id"],
                job_group_id=group_id,
                payload=payload,
                channel=str(contact.get("channel") or channel or "email"),
            )
            if result.ok:
                count += 1
            else:
                errors.append(result.error)
        return QueueResult(ok=not errors, job_group_id=group_id, count=count, error="; ".join(errors))

    def enqueue_enrich_contacts(
        self,
        campaign_id: int,
        *,
        contact_ids: list[int] | None = None,
        max_count: int | None = None,
        channel: str | None = None,
        force_refresh: bool = False,
    ) -> QueueResult:
        channel_clause = ""
        channel_params: list[Any] = []
        if channel:
            channel_clause = " AND channel = ?"
            channel_params.append(channel)
        if contact_ids:
            placeholders = ", ".join("?" for _ in contact_ids)
            contacts = self.db.fetch_all(
                f"""
                SELECT *
                FROM contacts
                WHERE campaign_id = ?
                  AND id IN ({placeholders})
                  {channel_clause}
                ORDER BY id ASC
                """,
                [campaign_id, *contact_ids, *channel_params],
            )
        else:
            contacts = self.db.fetch_all(
                f"""
                SELECT *
                FROM contacts
                WHERE campaign_id = ?
                  {channel_clause}
                ORDER BY id ASC
                """,
                [campaign_id, *channel_params],
            )
        if max_count is not None:
            contacts = contacts[: max(int(max_count), 0)]

        group_id = str(uuid.uuid4())
        count = 0
        errors: list[str] = []
        for contact in contacts:
            result = self.enqueue_job(
                "enrich_contact",
                campaign_id=campaign_id,
                contact_id=contact["id"],
                job_group_id=group_id,
                payload={"force_refresh": bool(force_refresh)},
                channel=str(contact.get("channel") or channel or "email"),
            )
            if result.ok:
                count += 1
            else:
                errors.append(result.error)
        return QueueResult(ok=not errors, job_group_id=group_id, count=count, error="; ".join(errors))

    def enqueue_ai_research_contact(
        self,
        campaign_id: int,
        contact_id: int,
        campaign_topic: str,
        channel: str = "email",
    ) -> QueueResult:
        return self.enqueue_job(
            "ai_research_contact",
            campaign_id=campaign_id,
            contact_id=contact_id,
            payload={"campaign_topic": campaign_topic},
            channel=channel,
        )

    def enqueue_ai_write_from_brief(
        self,
        campaign_id: int,
        contact_id: int,
        campaign_topic: str,
        tone: str = "friendly",
        channel: str = "email",
    ) -> QueueResult:
        return self.enqueue_job(
            "ai_write_from_brief",
            campaign_id=campaign_id,
            contact_id=contact_id,
            payload={"campaign_topic": campaign_topic, "tone": tone},
            channel=channel,
        )

    def enqueue_bulk_send(
        self,
        campaign_id: int,
        mode: str,
        confirm_live_send: bool = False,
        channel: str | None = None,
    ) -> QueueResult:
        if mode not in {"dry_run", "live"}:
            return QueueResult(False, error="mode must be dry_run or live.")

        contacts = self._contacts_for_status(campaign_id, "approved", channel)
        group_id = str(uuid.uuid4())
        count = 0
        errors: list[str] = []
        job_type = "dry_run_send" if mode == "dry_run" else "live_send"
        for contact in contacts:
            transition = transition_contact(self.db, contact["id"], "queued")
            if not transition.ok:
                errors.append(transition.error)
                continue
            result = self.enqueue_job(
                job_type,
                campaign_id=campaign_id,
                contact_id=contact["id"],
                job_group_id=group_id,
                payload={
                    "mode": mode,
                    "confirm_live_send": confirm_live_send,
                    "channel": str(contact.get("channel") or channel or "email"),
                },
                channel=str(contact.get("channel") or channel or "email"),
            )
            if result.ok:
                count += 1
            else:
                errors.append(result.error)
        return QueueResult(
            ok=not errors,
            job_group_id=group_id,
            count=count,
            error="; ".join(errors),
        )

    def enqueue_export_report(self, campaign_id: int) -> QueueResult:
        return self.enqueue_job(
            "export_report",
            campaign_id=campaign_id,
            contact_id=None,
            payload={"campaign_id": campaign_id},
        )

    def enqueue_email_sync(self, campaign_id: int, account_id: str = "", limit: int = 25) -> QueueResult:
        return self.enqueue_job(
            "email_sync",
            campaign_id=campaign_id,
            payload={"account_id": account_id, "limit": limit},
            channel="email",
        )

    def enqueue_telegram_sync(self, campaign_id: int, account_id: str = "telegram_bot", limit: int = 50) -> QueueResult:
        return self.enqueue_job(
            "telegram_sync",
            campaign_id=campaign_id,
            payload={"account_id": account_id, "limit": limit},
            channel="telegram",
        )

    def enqueue_ai_score_draft(self, campaign_id: int, contact_id: int, channel: str = "email") -> QueueResult:
        return self.enqueue_job(
            "ai_score_draft",
            campaign_id=campaign_id,
            contact_id=contact_id,
            payload={"contact_id": contact_id},
            channel=channel,
        )

    def enqueue_ai_generate_reply(
        self,
        campaign_id: int,
        contact_id: int,
        reply_text: str,
        channel: str = "email",
    ) -> QueueResult:
        return self.enqueue_job(
            "ai_generate_reply",
            campaign_id=campaign_id,
            contact_id=contact_id,
            payload={"reply_text": reply_text},
            channel=channel,
        )

    def enqueue_ai_summarize_reply(
        self,
        campaign_id: int,
        contact_id: int,
        thread_id: int,
        channel: str = "email",
    ) -> QueueResult:
        return self.enqueue_job(
            "ai_summarize_reply",
            campaign_id=campaign_id,
            contact_id=contact_id,
            payload={"thread_id": thread_id},
            channel=channel,
        )

    def enqueue_ai_followup_suggestion(
        self,
        campaign_id: int,
        contact_id: int,
        thread_id: int | None = None,
        channel: str = "email",
    ) -> QueueResult:
        return self.enqueue_job(
            "ai_followup_suggestion",
            campaign_id=campaign_id,
            contact_id=contact_id,
            payload={"thread_id": thread_id},
            channel=channel,
        )

    def enqueue_ai_stage_suggestion(
        self,
        campaign_id: int,
        contact_id: int,
        thread_id: int | None = None,
        channel: str = "email",
    ) -> QueueResult:
        return self.enqueue_job(
            "ai_stage_suggestion",
            campaign_id=campaign_id,
            contact_id=contact_id,
            payload={"thread_id": thread_id},
            channel=channel,
        )

    def enqueue_followup_reminder(
        self,
        campaign_id: int,
        contact_id: int,
        followup_id: int | None = None,
        channel: str = "email",
    ) -> QueueResult:
        return self.enqueue_job(
            "followup_reminder",
            campaign_id=campaign_id,
            contact_id=contact_id,
            payload={"followup_id": followup_id},
            channel=channel,
        )

    def _contacts_for_status(
        self,
        campaign_id: int,
        status: str,
        channel: str | None = None,
    ) -> list[dict[str, Any]]:
        if channel:
            return self.db.fetch_all(
                """
                SELECT *
                FROM contacts
                WHERE campaign_id = ?
                  AND status = ?
                  AND channel = ?
                ORDER BY id DESC
                """,
                (campaign_id, status, channel),
            )
        return self.db.list_contacts(campaign_id, status=status)

    def fetch_next_job(self) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM job_queue
                WHERE status IN ('pending', 'queued')
                  AND attempts < max_attempts
                ORDER BY priority ASC, created_at ASC, id ASC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            job = dict(row)
            conn.execute(
                """
                UPDATE job_queue
                SET status = 'running',
                    attempts = attempts + 1,
                    started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                    updated_at = CURRENT_TIMESTAMP,
                    progress_percent = CASE
                        WHEN progress_percent < 1 THEN 1
                        ELSE progress_percent
                    END
                WHERE id = ?
                """,
                (job["id"],),
            )
        job["status"] = "running"
        job["attempts"] = int(job["attempts"]) + 1
        return job

    def recover_interrupted_jobs(self, campaign_id: int | None = None) -> int:
        params: list[Any] = []
        query = "SELECT * FROM job_queue WHERE status = 'running'"
        if campaign_id is not None:
            query += " AND campaign_id = ?"
            params.append(campaign_id)
        rows = self.db.fetch_all(query, params)
        if not rows:
            return 0

        recovered = 0
        for job in rows:
            job_id = int(job["id"])
            self.db.execute(
                """
                UPDATE job_queue
                SET status = 'queued',
                    progress_percent = 0,
                    last_error = 'Recovered interrupted job after restart.',
                    started_at = NULL,
                    updated_at = CURRENT_TIMESTAMP,
                    attempts = CASE WHEN attempts > 0 THEN attempts - 1 ELSE attempts END
                WHERE id = ?
                """,
                (job_id,),
            )
            contact_id = job.get("contact_id")
            if contact_id:
                job_type = str(job.get("job_type") or "")
                contact = self.db.get_contact(int(contact_id))
                status = str(contact.get("status") or "") if contact else ""
                if job_type in {
                    "generate_message",
                    "ai_generate_draft",
                    "ai_research_contact",
                    "ai_write_from_brief",
                    "ai_dual_brain_generate",
                    "enrich_contact",
                    "ai_research_from_enrichment",
                    "ai_score_draft",
                } and status in {"generating", "generation_queued"}:
                    self.db.update_contact(int(contact_id), {"status": "generation_queued"})
                elif job_type in {"dry_run_send", "live_send"} and status in {"sending", "queued"}:
                    self.db.update_contact(int(contact_id), {"status": "queued"})
            recovered += 1
        return recovered

    def update_job_progress(self, job_id: int, progress_percent: int) -> None:
        progress = max(0, min(int(progress_percent), 100))
        self.db.execute(
            """
            UPDATE job_queue
            SET progress_percent = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (progress, job_id),
        )

    def complete_job(self, job_id: int) -> None:
        self.db.execute(
            """
            UPDATE job_queue
            SET status = 'completed',
                progress_percent = 100,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                last_error = NULL
            WHERE id = ?
            """,
            (job_id,),
        )

    def fail_job(self, job_id: int, error: str) -> None:
        self.db.execute(
            """
            UPDATE job_queue
            SET status = 'failed',
                last_error = ?,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (redact_secret(error), job_id),
        )

    def cancel_job(self, job_id: int, reason: str = "Cancelled by operator") -> QueueResult:
        job = self.db.fetch_one("SELECT * FROM job_queue WHERE id = ?", (job_id,))
        if not job:
            return QueueResult(False, job_id=job_id, error=f"Job {job_id} not found.")
        if job.get("contact_id"):
            contact = self.db.get_contact(int(job["contact_id"]))
            if contact and contact.get("status") in {"queued", "approved"}:
                transition_contact(self.db, int(job["contact_id"]), "cancelled", last_error=reason)
        self.db.execute(
            """
            UPDATE job_queue
            SET status = 'cancelled',
                last_error = ?,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (redact_secret(reason), job_id),
        )
        return QueueResult(True, job_id=job_id, count=1)

    def retry_failed_job(self, job_id: int) -> QueueResult:
        job = self.db.fetch_one("SELECT * FROM job_queue WHERE id = ?", (job_id,))
        if not job:
            return QueueResult(False, job_id=job_id, error=f"Job {job_id} not found.")
        if job["status"] != "failed":
            return QueueResult(False, job_id=job_id, error="Only failed jobs can be retried.")
        if job.get("contact_id") and job["job_type"] in {"dry_run_send", "live_send"}:
            transition = transition_contact(self.db, int(job["contact_id"]), "queued")
            if not transition.ok:
                return QueueResult(False, job_id=job_id, error=transition.error)
        if job.get("contact_id") and job["job_type"] in {"generate_message", "ai_generate_draft"}:
            transition = transition_contact(self.db, int(job["contact_id"]), "generation_queued")
            if not transition.ok:
                return QueueResult(False, job_id=job_id, error=transition.error)
        self.db.execute(
            """
            UPDATE job_queue
            SET status = 'queued',
                progress_percent = 0,
                last_error = NULL,
                started_at = NULL,
                completed_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (job_id,),
        )
        return QueueResult(True, job_id=job_id, count=1)

    def retry_failed_jobs(self, campaign_id: int | None = None) -> QueueResult:
        params: list[Any] = []
        query = "SELECT id FROM job_queue WHERE status = 'failed'"
        if campaign_id is not None:
            query += " AND campaign_id = ?"
            params.append(campaign_id)
        rows = self.db.fetch_all(query, params)
        count = 0
        errors: list[str] = []
        for row in rows:
            result = self.retry_failed_job(int(row["id"]))
            if result.ok:
                count += 1
            else:
                errors.append(result.error)
        return QueueResult(ok=not errors, count=count, error="; ".join(errors))

    def get_queue_stats(self, campaign_id: int | None = None) -> dict[str, int]:
        stats = {status: 0 for status in JOB_STATUSES}
        query = "SELECT status, COUNT(*) AS count FROM job_queue"
        params: list[Any] = []
        if campaign_id is not None:
            query += " WHERE campaign_id = ?"
            params.append(campaign_id)
        query += " GROUP BY status"
        for row in self.db.fetch_all(query, params):
            stats[row["status"]] = int(row["count"])
        return stats

    def list_recent_jobs(
        self,
        campaign_id: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT job_queue.*, contacts.email
            FROM job_queue
            LEFT JOIN contacts ON contacts.id = job_queue.contact_id
        """
        params: list[Any] = []
        if campaign_id is not None:
            query += " WHERE job_queue.campaign_id = ?"
            params.append(campaign_id)
        query += " ORDER BY job_queue.updated_at DESC, job_queue.id DESC LIMIT ?"
        params.append(limit)
        return self.db.fetch_all(query, params)

    def clear_completed_jobs(self, campaign_id: int | None = None) -> int:
        query = "DELETE FROM job_queue WHERE status = 'completed'"
        params: list[Any] = []
        if campaign_id is not None:
            query += " AND campaign_id = ?"
            params.append(campaign_id)
        return self.db.execute(query, params)

    @staticmethod
    def payload(job: dict[str, Any]) -> dict[str, Any]:
        raw = job.get("payload_json") or "{}"
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}
