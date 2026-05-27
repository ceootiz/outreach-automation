from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from src.ai import AIConnectionCheckResult, AIService, EmailDraftInput, EmailDraftResult
from src.ai.dual_brain_service import DualBrainService
from src.ai.research_schema import RecipientBrief, RecipientResearchInput
from src.ai.writer_schema import DraftWritingInput, WriterDraft, WriterValidationError
from src.background_worker import QueueJobProcessor
from src.campaign_service import CampaignService
from src.channels.execution import MANUAL_ASSIST
from src.db import Database
from src.inbox import EmailReplyMessage


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.checks: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def check_connection(self, **kwargs):
        self.checks.append({**kwargs, "password": "***" if kwargs.get("password") else ""})
        if not kwargs.get("password"):
            return SimpleNamespace(ok=False, message="Введите и сохраните App Password")
        return SimpleNamespace(ok=True, message="Connected. No email was sent.")


class FakeSimpleAIProvider:
    def __init__(self) -> None:
        self.inputs: list[EmailDraftInput] = []

    def generate_email_draft(self, input_data: EmailDraftInput) -> EmailDraftResult:
        self.inputs.append(input_data)
        return EmailDraftResult(
            subject="Controlled draft",
            body="Здравствуйте! Это безопасный controlled QA draft.",
            personalization_notes="No external facts.",
            confidence=0.78,
            warnings=[],
        )

    def check_connection(self) -> AIConnectionCheckResult:
        return AIConnectionCheckResult(True, "fake AI ok")


class FakeResearchBrain:
    def research_contact(self, input_data: RecipientResearchInput) -> RecipientBrief:
        weak = not any([input_data.company, input_data.website, input_data.note, input_data.social_profile])
        return RecipientBrief(
            recipient_type="unknown" if weak else "company",
            likely_context="Only row data was used.",
            positioning_angle="Offer a cautious collaboration conversation.",
            message_hooks=["campaign topic relevance"],
            do_not_claim=["do not claim browsing"],
            personalization_strength="low" if weak else "medium",
            confidence=0.35 if weak else 0.76,
            warnings=["Недостаточно данных"] if weak else [],
            source_basis=["row_data"],
        )

    def check_connection(self) -> AIConnectionCheckResult:
        return AIConnectionCheckResult(True, "research ok")


class FakeWriterBrain:
    def write_draft(self, input_data: DraftWritingInput) -> WriterDraft:
        return WriterDraft(
            subject="" if input_data.channel != "email" else "QA outreach",
            body="Здравствуйте! Предлагаю аккуратно обсудить сотрудничество. Без автоматической отправки.",
            why_this_angle=input_data.recipient_brief.positioning_angle,
            warnings=input_data.recipient_brief.warnings,
            confidence=0.82,
        )

    def check_connection(self) -> AIConnectionCheckResult:
        return AIConnectionCheckResult(True, "writer ok")


class MalformedWriterBrain:
    def write_draft(self, input_data: DraftWritingInput) -> WriterDraft:
        raise WriterValidationError("Writer Brain returned invalid JSON. password=stage40-secret")

    def check_connection(self) -> AIConnectionCheckResult:
        return AIConnectionCheckResult(False, "writer bad")


class FakeEmailClient:
    def __init__(self, messages: list[EmailReplyMessage]) -> None:
        self.messages = messages
        self.calls: list[dict[str, object]] = []

    def fetch_since(self, *, username: str, password: str, last_uid: str = "", limit: int = 25):
        self.calls.append({"username": username, "password": "***", "last_uid": last_uid, "limit": limit})
        assert password
        return self.messages


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_RESEARCH_API_KEY", "")
    monkeypatch.setenv("OPENAI_WRITER_API_KEY", "")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")


def make_service(
    db_path: Path,
    *,
    mailer: FakeMailer | None = None,
    writer: object | None = None,
) -> CampaignService:
    db = Database(db_path)
    db.initialize()
    db.set_settings(
        {
            "active_channel": "email",
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "delay_seconds": "0",
            "follow_up_delay_days": "2",
            "allowed_test_recipient": "",
            "onboarding_completed": "true",
            "ai_provider": "openai",
            "ai_model": "gpt-4.1-mini",
            "ai_generation_mode": "dual_brain",
            "ai_research_provider": "openai",
            "ai_research_model": "research-qa",
            "ai_writer_provider": "openai",
            "ai_writer_model": "writer-qa",
            "ai_max_drafts_per_batch": "25",
            "email_sync_enabled": "true",
            "telegram_sync_enabled": "true",
            "inbox_sync_mode": "manual",
        }
    )
    simple_ai = FakeSimpleAIProvider()
    return CampaignService(
        db,
        mailer=mailer or FakeMailer(),
        ai_draft_service=AIService(provider_factory=lambda _provider, _model: simple_ai),
        dual_brain_service=DualBrainService(
            research_factory=lambda _provider, _model: FakeResearchBrain(),
            writer_factory=lambda _provider, _model: writer or FakeWriterBrain(),
        ),
        sleep_fn=lambda _: None,
        export_dir=db_path.parent / "exports",
    )


def add_email_contact(
    service: CampaignService,
    campaign_id: int,
    *,
    email: str = "owned-recipient@example.com",
    status: str = "new",
) -> int:
    contact_id = service.db.add_contact(
        {
            "campaign_id": campaign_id,
            "channel": "email",
            "email": email,
            "name": "QA Lead",
            "company": "QA Company",
            "subject": "QA",
            "base_message": "Controlled QA message.",
            "generated_message": "Controlled QA message.",
            "status": status,
        }
    )
    return int(contact_id)


def test_queue_restore_after_restart_recovers_interrupted_ai_job(tmp_path: Path) -> None:
    db_path = tmp_path / "stage40.sqlite"
    service = make_service(db_path)
    service.save_ai_brain_settings("research", provider="openai", model="research-qa", api_key="research-key")
    service.save_ai_brain_settings("writer", provider="openai", model="writer-qa", api_key="writer-key")
    campaign_id = service.default_campaign_id()
    contact_id = add_email_contact(service, campaign_id)

    queued = service.enqueue_ai_generate_drafts(
        campaign_id,
        contact_ids=[contact_id],
        campaign_topic="Предложить сотрудничество",
    )
    assert queued.count == 1
    running = service.queue.fetch_next_job()
    assert running is not None
    assert service.recent_jobs(campaign_id)[0]["status"] == "running"

    restarted = make_service(db_path)
    recovered_job = restarted.recent_jobs(campaign_id)[0]
    assert recovered_job["status"] == "queued"
    assert "Recovered interrupted job" in recovered_job["last_error"]

    QueueJobProcessor(restarted).process_available()
    contact = restarted.db.get_contact(contact_id)
    assert contact["status"] == "pending_review"
    assert contact["ai_generated"] == 1
    assert restarted.mailer.sent == []


def test_malformed_ai_output_fails_safely_without_autosend_or_secret_leak(tmp_path: Path) -> None:
    service = make_service(tmp_path / "malformed.sqlite", writer=MalformedWriterBrain())
    service.save_ai_brain_settings("research", provider="openai", model="research-qa", api_key="research-key")
    service.save_ai_brain_settings("writer", provider="openai", model="writer-qa", api_key="writer-key")
    campaign_id = service.default_campaign_id()
    contact_id = add_email_contact(service, campaign_id)

    service.enqueue_ai_generate_drafts(campaign_id, contact_ids=[contact_id], campaign_topic="QA topic")
    QueueJobProcessor(service).process_available()

    contact = service.db.get_contact(contact_id)
    job = service.recent_jobs(campaign_id)[0]
    assert contact["status"] == "failed"
    assert "Writer Brain returned invalid JSON" in contact["last_error"]
    assert "stage40-secret" not in contact["last_error"]
    assert "stage40-secret" not in job["last_error"]
    assert service.mailer.sent == []


def test_real_flow_guardrails_require_confirmation_safe_target_and_daily_limit(tmp_path: Path) -> None:
    mailer = FakeMailer()
    service = make_service(tmp_path / "guards.sqlite", mailer=mailer)
    campaign_id = service.default_campaign_id()
    service.create_gmail_profile("Sender", "sender@example.com", "profile-password")
    contact_id = add_email_contact(service, campaign_id, email="owned-recipient@example.com", status="approved")

    service.save_settings(
        {
            "send_mode": "live",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "allowed_test_recipient": "owned-recipient@example.com",
        }
    )
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=False, channel="email")
    QueueJobProcessor(service).process_available()
    assert mailer.sent == []

    service.db.update_contact(contact_id, {"status": "approved", "last_error": ""})
    service.save_settings({"allowed_test_recipient": "other-owned@example.com"})
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="email")
    QueueJobProcessor(service).process_available()
    assert mailer.sent == []
    assert "recipient_email=owned-recipient@example.com" in service.recent_jobs(campaign_id)[0]["last_error"]

    service.db.update_contact(contact_id, {"status": "approved", "last_error": ""})
    service.save_settings({"allowed_test_recipient": "owned-recipient@example.com"})
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="email")
    QueueJobProcessor(service).process_available()
    assert len(mailer.sent) == 1
    assert mailer.sent[0]["sender_email"] == "sender@example.com"
    assert mailer.sent[0]["recipient_email"] == "owned-recipient@example.com"


def test_imap_ingestion_idempotency_and_no_autosend(tmp_path: Path) -> None:
    service = make_service(tmp_path / "imap.sqlite")
    campaign_id = service.default_campaign_id()
    service.create_gmail_profile("Sender", "sender@example.com", "profile-password")
    add_email_contact(service, campaign_id, email="lead@example.com", status="sent")
    message = EmailReplyMessage(
        imap_uid="401",
        remote_message_id="stage40-msg@example.com",
        sender_email="lead@example.com",
        sender_name="Lead",
        subject="Re: QA",
        body="Интересно, пришлите детали.",
    )

    first = service.sync_email_replies(campaign_id, client=FakeEmailClient([message]))
    second = service.sync_email_replies(campaign_id, client=FakeEmailClient([message]))

    assert first.imported_count == 1
    assert second.imported_count == 0
    assert second.skipped_count == 1
    assert len(service.db.fetch_all("SELECT * FROM replies")) == 1
    assert len(service.db.fetch_all("SELECT * FROM conversation_messages WHERE remote_message_id = ?", ("stage40-msg@example.com",))) == 1
    assert service.mailer.sent == []


def test_multi_profile_isolation_and_no_recipient_rewrite(tmp_path: Path) -> None:
    mailer = FakeMailer()
    service = make_service(tmp_path / "profiles.sqlite", mailer=mailer)
    campaign_id = service.default_campaign_id()
    first = service.create_gmail_profile("One", "one@example.com", "one-password")
    second = service.create_gmail_profile("Two", "two@example.com", "two-password")

    first_contact = add_email_contact(service, campaign_id, email="first-owned@example.com", status="approved")
    service.set_active_gmail_profile(int(first["id"]))
    service.save_settings({"send_mode": "live", "daily_send_limit": "2", "allowed_test_recipient": "first-owned@example.com"})
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="email")
    QueueJobProcessor(service).process_available()

    second_contact = add_email_contact(service, campaign_id, email="second-owned@example.com", status="approved")
    service.set_active_gmail_profile(int(second["id"]))
    service.save_settings({"allowed_test_recipient": "second-owned@example.com"})
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="email")
    QueueJobProcessor(service).process_available()

    assert service.db.get_contact(first_contact)["status"] == "sent"
    assert service.db.get_contact(second_contact)["status"] == "sent"
    assert mailer.sent[0]["sender_email"] == "one@example.com"
    assert mailer.sent[0]["recipient_email"] == "first-owned@example.com"
    assert mailer.sent[1]["sender_email"] == "two@example.com"
    assert mailer.sent[1]["recipient_email"] == "second-owned@example.com"


def test_manual_assist_flow_is_operator_only(tmp_path: Path) -> None:
    service = make_service(tmp_path / "manual.sqlite")
    campaign_id = service.default_campaign_id()
    result = service.add_contact_rows(
        campaign_id,
        [
            {
                "channel": "instagram",
                "handle": "@owned_creator",
                "profile_url": "https://www.instagram.com/owned_creator/",
                "generated_message": "Привет! Короткий manual-assist текст.",
                "status": "approved",
            }
        ],
    )
    assert result.imported_count == 1
    contact = service.contacts(campaign_id)[0]
    service.set_active_channel("instagram")
    service.set_execution_mode("instagram", MANUAL_ASSIST)

    prepared = service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="instagram")
    marked = service.mark_manual_assist_sent([int(contact["id"])])

    assert prepared.ok is True
    assert prepared.count == 1
    assert marked == 1
    assert service.mailer.sent == []
    logs = service.db.fetch_all("SELECT action, error FROM send_logs WHERE channel = 'instagram'")
    assert {row["action"] for row in logs} >= {"manual_assist_prepare", "manual_assist_mark_sent"}
    assert any("No platform automation" in row["error"] for row in logs)
