from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot

from .campaign_service import CampaignService
from .channels import get_channel
from .channels.telegram_channel import TelegramChannel
from .config import as_bool, as_int
from .logger_setup import get_logger, redact_secret
from .mailer import MailerConfigError, MailerError
from .queue_service import QueueService
from .state_machine import transition_contact


ProgressCallback = Callable[[int, int, str], None]


class QueueJobProcessor:
    def __init__(self, service: CampaignService, queue: QueueService | None = None):
        self.service = service
        self.db = service.db
        self.queue = queue or service.queue
        self.logger = get_logger()

    def process_next_job(
        self,
        progress_callback: ProgressCallback | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> dict[str, Any] | None:
        job = self.queue.fetch_next_job()
        if not job:
            return None
        self.process_job(job, progress_callback=progress_callback, cancel_requested=cancel_requested)
        return job

    def process_available(
        self,
        progress_callback: ProgressCallback | None = None,
        cancel_requested: Callable[[], bool] | None = None,
        max_jobs: int | None = None,
    ) -> int:
        processed = 0
        while max_jobs is None or processed < max_jobs:
            job = self.process_next_job(
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
            if not job:
                break
            processed += 1
            if cancel_requested and cancel_requested():
                break
        return processed

    def process_job(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> None:
        job_id = int(job["id"])
        try:
            self._progress(job_id, 5, "running", progress_callback)
            if cancel_requested and cancel_requested():
                self.queue.cancel_job(job_id)
                return

            job_type = job["job_type"]
            if job_type == "generate_message":
                self._process_generate_message(job, progress_callback)
            elif job_type == "ai_generate_draft":
                self._process_ai_generate_draft(job, progress_callback)
            elif job_type == "ai_dual_brain_generate":
                self._process_ai_dual_brain_generate(job, progress_callback)
            elif job_type == "ai_research_contact":
                self._process_ai_research_contact(job, progress_callback)
            elif job_type == "ai_write_from_brief":
                self._process_ai_write_from_brief(job, progress_callback)
            elif job_type == "enrich_contact":
                self._process_enrich_contact(job, progress_callback)
            elif job_type == "ai_research_from_enrichment":
                self._process_ai_research_contact(job, progress_callback)
            elif job_type == "ai_score_draft":
                self._process_ai_score_draft(job, progress_callback)
            elif job_type == "ai_generate_reply":
                self._process_ai_generate_reply(job, progress_callback)
            elif job_type == "ai_summarize_reply":
                self._process_ai_summarize_reply(job, progress_callback)
            elif job_type == "ai_followup_suggestion":
                self._process_ai_followup_suggestion(job, progress_callback)
            elif job_type == "ai_stage_suggestion":
                self._process_ai_stage_suggestion(job, progress_callback)
            elif job_type == "email_sync":
                self._process_email_sync(job, progress_callback)
            elif job_type == "telegram_sync":
                self._process_telegram_sync(job, progress_callback)
            elif job_type == "followup_reminder":
                self._process_followup_reminder(job, progress_callback)
            elif job_type in {"dry_run_send", "live_send"}:
                self._process_send(job, progress_callback)
            elif job_type == "export_report":
                self._process_export_report(job, progress_callback)
            else:
                raise RuntimeError(f"Unsupported job type: {job_type}")

            self.queue.complete_job(job_id)
            self._progress(job_id, 100, "completed", progress_callback)
        except Exception as exc:
            error = redact_secret(exc)
            self.queue.fail_job(job_id, error)
            self.logger.error("Queue job %s failed: %s", job_id, error)
            if job.get("contact_id"):
                contact = self.db.get_contact(int(job["contact_id"]))
                if contact and contact.get("status") in {"sending", "generating"}:
                    transition_contact(self.db, int(job["contact_id"]), "failed", last_error=error)
                self.service.timeline.record_event(
                    int(job["contact_id"]),
                    "failed",
                    title="Queue job failed",
                    details=error,
                )

    def _process_generate_message(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        contact_id = int(job["contact_id"])
        to_generating = transition_contact(self.db, contact_id, "generating")
        if not to_generating.ok:
            raise RuntimeError(to_generating.error)

        self._progress(int(job["id"]), 30, "generating", progress_callback)
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise RuntimeError(f"Contact {contact_id} not found.")
        template = self.service.template()
        generated = self.service.ai_provider.generate_email(
            contact,
            template["subject_template"],
            template["body_template"],
        )
        self.db.update_contact(
            contact_id,
            {
                "subject": generated.subject,
                "generated_message": generated.body,
                "last_error": "",
            },
        )
        self._progress(int(job["id"]), 80, "pending review", progress_callback)
        to_pending = transition_contact(self.db, contact_id, "pending_review", last_error="")
        if not to_pending.ok:
            raise RuntimeError(to_pending.error)
        self.db.log_send(contact_id, job.get("campaign_id"), "generate_message", "ok", "")
        self.service.timeline.record_event(
            contact_id,
            "status_changed",
            title="Сообщение подготовлено",
            details="Template/manual generation completed. Human review required.",
        )

    def _process_ai_generate_draft(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        contact_id = int(job["contact_id"])
        to_generating = transition_contact(self.db, contact_id, "generating")
        if not to_generating.ok:
            raise RuntimeError(to_generating.error)

        self._progress(int(job["id"]), 25, "ai drafting", progress_callback)
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise RuntimeError(f"Contact {contact_id} not found.")
        payload = self.queue.payload(job)
        result = self.service.generate_ai_draft_for_contact(
            contact,
            campaign_topic=str(payload.get("campaign_topic") or ""),
            tone=str(payload.get("tone") or "friendly"),
        )
        self.db.update_contact(
            contact_id,
            {
                "subject": result.subject if str(contact.get("channel") or "email") == "email" else "",
                "generated_message": result.body,
                "base_message": result.body,
                "ai_generated": 1,
                "ai_confidence": result.confidence,
                "ai_notes": result.personalization_notes,
                "ai_warnings": json.dumps(result.warnings, ensure_ascii=False),
                "last_error": "",
            },
        )
        self._progress(int(job["id"]), 85, "pending review", progress_callback)
        to_pending = transition_contact(self.db, contact_id, "pending_review", last_error="")
        if not to_pending.ok:
            raise RuntimeError(to_pending.error)
        self.db.log_send(
            contact_id,
            job.get("campaign_id"),
            "ai_generate_draft",
            "pending_review",
            "AI draft created. Human review required.",
            channel=str(contact.get("channel") or job.get("channel") or "email"),
            platform_recipient=self.service.platform_recipient(contact),
        )
        self.service.timeline.record_event(
            contact_id,
            "ai_generated",
            title="AI draft generated",
            details="AI prepared a draft. Human review required.",
            metadata={"confidence": result.confidence},
        )
        self.service.ai_quality.score_contact_draft(contact_id)

    def _process_ai_dual_brain_generate(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        contact_id = int(job["contact_id"])
        to_generating = transition_contact(self.db, contact_id, "generating")
        if not to_generating.ok:
            raise RuntimeError(to_generating.error)

        self._progress(int(job["id"]), 15, "researching", progress_callback)
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise RuntimeError(f"Contact {contact_id} not found.")
        payload = self.queue.payload(job)
        if bool(payload.get("use_enrichment")):
            self._progress(int(job["id"]), 20, "enriching", progress_callback)
            self.service.enrich_contact_for_research(contact_id, enabled_override=True)
            contact = self.db.get_contact(contact_id)
            if not contact:
                raise RuntimeError(f"Contact {contact_id} not found after enrichment.")
        self._progress(int(job["id"]), 35, "researching", progress_callback)
        result = self.service.generate_dual_brain_draft_for_contact(
            contact,
            campaign_topic=str(payload.get("campaign_topic") or ""),
            tone=str(payload.get("tone") or "friendly"),
        )
        self._progress(int(job["id"]), 70, "writing", progress_callback)
        channel_id = str(contact.get("channel") or "email")
        warnings = list(result.brief.warnings) + list(result.draft.warnings)
        self.db.update_contact(
            contact_id,
            {
                "subject": result.draft.subject if channel_id == "email" else "",
                "generated_message": result.draft.body,
                "base_message": result.draft.body,
                "ai_generated": 1,
                "ai_confidence": result.draft.confidence,
                "ai_notes": result.draft.why_this_angle,
                "ai_warnings": json.dumps(warnings, ensure_ascii=False),
                "research_brief_json": json.dumps(result.brief.to_dict(), ensure_ascii=False),
                "research_confidence": result.brief.confidence,
                "research_warnings": json.dumps(result.brief.warnings, ensure_ascii=False),
                "research_status": result.brief.personalization_strength,
                "last_error": "",
            },
        )
        self._progress(int(job["id"]), 90, "pending review", progress_callback)
        to_pending = transition_contact(self.db, contact_id, "pending_review", last_error="")
        if not to_pending.ok:
            raise RuntimeError(to_pending.error)
        self.db.log_send(
            contact_id,
            job.get("campaign_id"),
            "ai_dual_brain_generate",
            "pending_review",
            "Research + Writer draft created. Human review required.",
            channel=channel_id,
            platform_recipient=self.service.platform_recipient(contact),
        )
        self.service.timeline.record_event(
            contact_id,
            "ai_generated",
            title="AI Research + Writer draft generated",
            details=(
                f"research={result.brief.personalization_strength}; "
                f"research_confidence={result.brief.confidence}; writer_confidence={result.draft.confidence}. "
                "Human review required."
            ),
            metadata={"research": result.brief.to_dict(), "writer_confidence": result.draft.confidence},
        )
        self.service.ai_quality.score_contact_draft(contact_id)
        self.service.record_dual_brain_metrics(
            contact_id,
            result=result,
        )

    def _process_ai_research_contact(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        contact_id = int(job["contact_id"])
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise RuntimeError(f"Contact {contact_id} not found.")
        payload = self.queue.payload(job)
        self._progress(int(job["id"]), 40, "researching", progress_callback)
        brief = self.service.research_contact_for_ai(
            contact,
            campaign_topic=str(payload.get("campaign_topic") or ""),
        )
        self.db.update_contact(
            contact_id,
            {
                "research_brief_json": json.dumps(brief.to_dict(), ensure_ascii=False),
                "research_confidence": brief.confidence,
                "research_warnings": json.dumps(brief.warnings, ensure_ascii=False),
                "research_status": brief.personalization_strength,
            },
        )
        self.db.log_send(
            contact_id,
            job.get("campaign_id"),
            "ai_research_contact",
            "ok",
            "Research brief saved. No draft sent.",
            channel=str(contact.get("channel") or job.get("channel") or "email"),
            platform_recipient=self.service.platform_recipient(contact),
        )

    def _process_enrich_contact(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        contact_id = int(job["contact_id"])
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise RuntimeError(f"Contact {contact_id} not found.")
        payload = self.queue.payload(job)
        self._progress(int(job["id"]), 40, "enriching", progress_callback)
        result = self.service.enrich_contact_for_research(
            contact_id,
            force_refresh=bool(payload.get("force_refresh")),
            enabled_override=True,
        )
        self._progress(int(job["id"]), 85, result.status, progress_callback)

    def _process_ai_write_from_brief(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        contact_id = int(job["contact_id"])
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise RuntimeError(f"Contact {contact_id} not found.")
        if str(contact.get("status") or "new") in {"new", "failed"}:
            queued = transition_contact(self.db, contact_id, "generation_queued")
            if not queued.ok:
                raise RuntimeError(queued.error)
            contact = self.db.get_contact(contact_id) or contact
        to_generating = transition_contact(self.db, contact_id, "generating")
        if not to_generating.ok:
            raise RuntimeError(to_generating.error)
        payload = self.queue.payload(job)
        self._progress(int(job["id"]), 35, "writing", progress_callback)
        draft = self.service.write_draft_from_existing_brief(
            contact,
            campaign_topic=str(payload.get("campaign_topic") or ""),
            tone=str(payload.get("tone") or "friendly"),
        )
        channel_id = str(contact.get("channel") or "email")
        self.db.update_contact(
            contact_id,
            {
                "subject": draft.subject if channel_id == "email" else "",
                "generated_message": draft.body,
                "base_message": draft.body,
                "ai_generated": 1,
                "ai_confidence": draft.confidence,
                "ai_notes": draft.why_this_angle,
                "ai_warnings": json.dumps(draft.warnings, ensure_ascii=False),
                "last_error": "",
            },
        )
        to_pending = transition_contact(self.db, contact_id, "pending_review", last_error="")
        if not to_pending.ok:
            raise RuntimeError(to_pending.error)
        self.db.log_send(
            contact_id,
            job.get("campaign_id"),
            "ai_write_from_brief",
            "pending_review",
            "Writer draft created from saved brief. Human review required.",
            channel=channel_id,
            platform_recipient=self.service.platform_recipient(contact),
        )

    def _process_ai_score_draft(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        contact_id = int(job["contact_id"])
        self._progress(int(job["id"]), 35, "ai scoring", progress_callback)
        score = self.service.score_contact_draft(contact_id)
        contact = self.db.get_contact(contact_id) or {}
        self.db.log_send(
            contact_id,
            job.get("campaign_id"),
            "ai_score_draft",
            "ok",
            f"spam={score.spam_risk}; personalization={score.personalization_quality}",
            channel=str(contact.get("channel") or job.get("channel") or "email"),
            platform_recipient=self.service.platform_recipient(contact) if contact else "",
        )

    def _process_ai_generate_reply(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        contact_id = int(job["contact_id"])
        payload = self.queue.payload(job)
        reply_text = str(payload.get("reply_text") or "")
        self._progress(int(job["id"]), 40, "ai reply assist", progress_callback)
        suggestions = self.service.conversation_reply_suggestions(contact_id, reply_text)
        self.service.timeline.record_event(
            contact_id,
            "note_added",
            title="AI reply suggestions created",
            details=suggestions.summary,
        )
        self.db.log_send(
            contact_id,
            job.get("campaign_id"),
            "ai_generate_reply",
            "ok",
            "AI reply suggestions created. No auto-send.",
        )

    def _process_ai_summarize_reply(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        contact_id = int(job["contact_id"])
        payload = self.queue.payload(job)
        thread_id = int(payload.get("thread_id") or self.service.conversation_thread(contact_id)["id"])
        self._progress(int(job["id"]), 45, "ai conversation summary", progress_callback)
        self.service.summarize_conversation(thread_id)
        self.db.log_send(
            contact_id,
            job.get("campaign_id"),
            "ai_summarize_reply",
            "ok",
            "Conversation summarized. No auto-send.",
        )

    def _process_ai_followup_suggestion(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        contact_id = int(job["contact_id"])
        self._progress(int(job["id"]), 45, "ai follow-up suggestion", progress_callback)
        suggestion = self.service.suggest_followup_for_contact(contact_id)
        self.db.log_send(
            contact_id,
            job.get("campaign_id"),
            "ai_followup_suggestion",
            "ok",
            f"Follow-up suggestion created for {suggestion.get('due_at') or 'manual review'}. No auto-send.",
        )

    def _process_ai_stage_suggestion(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        contact_id = int(job["contact_id"])
        self._progress(int(job["id"]), 45, "ai stage suggestion", progress_callback)
        thread = self.service.conversation_thread(contact_id)
        suggested = str(thread.get("suggested_lead_status") or "")
        self.service.timeline.record_event(
            contact_id,
            "note_added",
            title="AI lead stage suggested",
            details=f"suggested={suggested or 'manual review'}; human confirmation required.",
        )
        self.db.log_send(
            contact_id,
            job.get("campaign_id"),
            "ai_stage_suggestion",
            "ok",
            "Lead stage suggestion recorded. No automatic stage change.",
        )

    def _process_email_sync(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        campaign_id = int(job["campaign_id"])
        payload = self.queue.payload(job)
        self._progress(int(job["id"]), 35, "email inbox sync", progress_callback)
        result = self.service.sync_email_replies(campaign_id, limit=int(payload.get("limit") or 25))
        if not result.ok:
            raise RuntimeError(result.message)
        self._progress(int(job["id"]), 85, "email inbox synced", progress_callback)

    def _process_telegram_sync(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        campaign_id = int(job["campaign_id"])
        payload = self.queue.payload(job)
        self._progress(int(job["id"]), 35, "telegram inbox sync", progress_callback)
        result = self.service.sync_telegram_replies(campaign_id, limit=int(payload.get("limit") or 50))
        if not result.ok:
            raise RuntimeError(result.message)
        self._progress(int(job["id"]), 85, "telegram inbox synced", progress_callback)

    def _process_followup_reminder(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        contact_id = int(job["contact_id"])
        self._progress(int(job["id"]), 50, "follow-up reminder", progress_callback)
        self.service.timeline.record_event(
            contact_id,
            "note_added",
            title="Follow-up reminder",
            details="Manual follow-up reminder queued. No message was sent.",
        )
        self.db.log_send(
            contact_id,
            job.get("campaign_id"),
            "followup_reminder",
            "ok",
            "Manual follow-up reminder. No auto-send.",
        )

    def _process_send(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        contact_id = int(job["contact_id"])
        campaign_id = int(job["campaign_id"])
        job_type = job["job_type"]
        payload = self.queue.payload(job)
        mode = "dry_run" if job_type == "dry_run_send" else "live"
        channel_id = str(job.get("channel") or payload.get("channel") or "email").strip().lower()
        settings = self.service.settings()
        daily_limit = as_int(settings.get("daily_send_limit"), 25)
        safe_mode = as_bool(settings.get("safe_mode"), True)
        real_send_confirm_required = as_bool(settings.get("real_send_confirm_required"), True)
        allowed_test_recipient = (settings.get("allowed_test_recipient") or "").strip()
        follow_up_days = max(as_int(settings.get("follow_up_delay_days"), 2), 0)

        to_sending = transition_contact(self.db, contact_id, "sending")
        if not to_sending.ok:
            raise RuntimeError(to_sending.error)
        self._progress(int(job["id"]), 25, "sending", progress_callback)

        contact = self.db.get_contact(contact_id)
        if not contact:
            raise RuntimeError(f"Contact {contact_id} not found.")
        contact_channel_id = str(contact.get("channel") or channel_id or "email").strip().lower()
        channel = get_channel(contact_channel_id)
        platform_recipient = self.service.validate_channel_recipient(contact)

        if self.service.blacklist.is_blocked(contact["email"]):
            transition_contact(self.db, contact_id, "blacklisted", last_error="Email is in blacklist")
            self.db.log_send(
                contact_id,
                campaign_id,
                job_type,
                "blacklisted",
                "Email is in blacklist",
                channel=channel.channel_id,
                platform_recipient=platform_recipient,
            )
            raise RuntimeError("Email is in blacklist")

        if mode == "dry_run":
            transition = transition_contact(self.db, contact_id, "dry_run_sent", last_error="")
            if not transition.ok:
                raise RuntimeError(transition.error)
            self.db.log_send(
                contact_id,
                campaign_id,
                "dry_run_send",
                "dry_run_sent",
                (
                    f"Dry-run only. No live message was sent. recipient_email={platform_recipient}"
                    if channel.channel_id == "email"
                    else f"Dry-run only. No live message was sent. platform_recipient={platform_recipient}"
                ),
                channel=channel.channel_id,
                platform_recipient=platform_recipient,
            )
            self.service.timeline.record_event(
                contact_id,
                "dry_run",
                title="Dry-run выполнен",
                details=f"channel={channel.channel_id}; recipient={platform_recipient}",
            )
            self.service.conversations.add_message(
                contact_id,
                direction="outbound",
                subject=str(contact.get("subject") or ""),
                body=str(contact.get("generated_message") or contact.get("base_message") or ""),
                message_type="dry_run",
                status="dry_run_sent",
                metadata={"recipient": platform_recipient, "channel": channel.channel_id, "job_id": int(job["id"])},
            )
            return

        if channel.channel_id == "telegram" and not self.service.telegram_bot_token():
            raise RuntimeError("Telegram live send blocked: сохраните Bot Token в Аккаунты и настройки → Telegram.")

        if not channel.supports_live_send:
            raise RuntimeError(channel.live_disabled_message)

        if real_send_confirm_required and not bool(payload.get("confirm_live_send")):
            raise RuntimeError("Live send is blocked until the operator explicitly confirms.")

        live_recipient = self.service.validate_live_recipient(
            contact,
            safe_mode=safe_mode,
            allowed_test_recipient=allowed_test_recipient,
        )

        if safe_mode and daily_limit <= 0:
            raise RuntimeError("Safe mode requires daily_send_limit greater than 0.")

        rate_state = self.service.rate_limiter.state(daily_limit)
        if not rate_state.allowed:
            raise RuntimeError(
                "Daily send limit reached. "
                f"Remaining today: {rate_state.remaining}/{rate_state.daily_limit} "
                f"(sent today: {rate_state.sent_today}/{rate_state.daily_limit})."
            )

        try:
            if channel.channel_id == "telegram":
                TelegramChannel().send_message(
                    bot_token=self.service.telegram_bot_token(),
                    chat_id=live_recipient,
                    text=contact.get("generated_message") or contact.get("base_message") or "",
                )
            else:
                self.service.mailer.send_email(
                    host=settings.get("smtp_host", "smtp.gmail.com"),
                    port=as_int(settings.get("smtp_port"), 587),
                    sender_email=self.service.active_sender_email(),
                    recipient_email=live_recipient,
                    subject=contact.get("subject") or "",
                    body=contact.get("generated_message") or contact.get("base_message") or "",
                    password=self.service.active_sender_password() or None,
                )
        except (MailerConfigError, MailerError):
            raise

        sent_at = datetime.now().replace(microsecond=0)
        follow_up_due_at = sent_at + timedelta(days=follow_up_days)
        transition = transition_contact(self.db, contact_id, "sent", last_error="")
        if not transition.ok:
            raise RuntimeError(transition.error)
        self.db.update_contact(
            contact_id,
            {
                "sent_at": sent_at.isoformat(sep=" "),
                "follow_up_due_at": follow_up_due_at.isoformat(sep=" "),
            },
        )
        self.db.log_send(
            contact_id,
            campaign_id,
            "live_send",
            "sent",
            (
                f"telegram_chat_id={live_recipient}"
                if channel.channel_id == "telegram"
                else f"recipient_email={live_recipient}"
            ),
            channel=channel.channel_id,
            platform_recipient=live_recipient,
        )
        self.service.timeline.record_event(
            contact_id,
            "sent",
            title="Отправлено",
            details=f"channel={channel.channel_id}; recipient={live_recipient}",
        )
        self.service.conversations.add_message(
            contact_id,
            direction="outbound",
            subject=str(contact.get("subject") or ""),
            body=str(contact.get("generated_message") or contact.get("base_message") or ""),
            message_type="sent",
            status="sent",
            metadata={"recipient": live_recipient, "channel": channel.channel_id, "job_id": int(job["id"])},
        )
        self.service.followups.schedule_followup(
            contact_id,
            due_at=follow_up_due_at.isoformat(sep=" "),
            note="Suggested after successful send. Manual confirmation required.",
        )

    def _process_export_report(
        self,
        job: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> None:
        campaign_id = int(job["campaign_id"])
        self._progress(int(job["id"]), 40, "exporting", progress_callback)
        report_path = self.service.export_report(campaign_id)
        self.db.log_send(None, campaign_id, "export_report_job", "ok", report_path.name)

    def _progress(
        self,
        job_id: int,
        percent: int,
        message: str,
        callback: ProgressCallback | None,
    ) -> None:
        self.queue.update_job_progress(job_id, percent)
        if callback:
            callback(job_id, percent, message)


class QueueWorker(QObject):
    worker_started = Signal()
    worker_stopped = Signal()
    job_started = Signal(dict)
    job_progress = Signal(int, int, str)
    job_completed = Signal(dict)
    job_failed = Signal(dict, str)
    queue_updated = Signal()

    def __init__(self, processor: QueueJobProcessor):
        super().__init__()
        self.processor = processor
        self._stop_requested = False
        self._pause_requested = False
        self._cancel_requested = False

    @Slot()
    def run(self) -> None:
        self.worker_started.emit()
        try:
            while not self._stop_requested:
                if self._pause_requested:
                    break
                job = self.processor.queue.fetch_next_job()
                if not job:
                    break
                self.job_started.emit(job)
                before_status = job.get("status")
                try:
                    self.processor.process_job(
                        job,
                        progress_callback=self.job_progress.emit,
                        cancel_requested=lambda: self._cancel_requested,
                    )
                except Exception as exc:  # defensive: processor already catches expected errors
                    error = redact_secret(exc)
                    self.processor.queue.fail_job(int(job["id"]), error)
                    self.job_failed.emit(job, error)
                refreshed = self.processor.db.fetch_one("SELECT * FROM job_queue WHERE id = ?", (job["id"],))
                if refreshed and refreshed.get("status") == "failed":
                    self.job_failed.emit(refreshed, refreshed.get("last_error") or "")
                else:
                    self.job_completed.emit(refreshed or job)
                self.queue_updated.emit()
                if self._cancel_requested and before_status == "running":
                    break
        finally:
            self.worker_stopped.emit()

    @Slot()
    def stop(self) -> None:
        self._stop_requested = True

    @Slot()
    def pause(self) -> None:
        self._pause_requested = True

    @Slot()
    def cancel_current(self) -> None:
        self._cancel_requested = True
