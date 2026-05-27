from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from src.ai import AIConnectionCheckResult, AIService, EmailDraftInput, EmailDraftResult
from src.background_worker import QueueJobProcessor
from src.campaign_service import CampaignService
from src.channels.telegram_channel import TelegramChannel
from src.db import Database
from src.http_client import HttpClientError
from src.inbox import EmailReplyMessage, TelegramReplyMessage


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.connection_checks: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def check_connection(self, **kwargs):
        self.connection_checks.append(kwargs)
        if not kwargs.get("password"):
            return SimpleNamespace(ok=False, message="Введите и сохраните App Password")
        return SimpleNamespace(ok=True, message="Connected. No email was sent.")


class FakeAIProvider:
    def __init__(self) -> None:
        self.inputs: list[EmailDraftInput] = []

    def generate_email_draft(self, input_data: EmailDraftInput) -> EmailDraftResult:
        self.inputs.append(input_data)
        return EmailDraftResult(
            subject="Аккуратное предложение",
            body=f"Здравствуйте! Коротко предлагаю обсудить: {input_data.campaign_topic}.",
            personalization_notes="Использованы только переданные данные.",
            confidence=0.81,
            warnings=[],
        )

    def check_connection(self) -> AIConnectionCheckResult:
        return AIConnectionCheckResult(True, "AI test connection ok")


class FakeEmailClient:
    def __init__(self, messages: list[EmailReplyMessage]) -> None:
        self.messages = messages
        self.calls: list[dict[str, object]] = []

    def fetch_since(self, *, username: str, password: str, last_uid: str = "", limit: int = 25):
        self.calls.append({"username": username, "password": "***", "last_uid": last_uid, "limit": limit})
        assert password
        return self.messages


class FakeTelegramHttp:
    def __init__(self, *, fail: bool = False, secret: str = "") -> None:
        self.fail = fail
        self.secret = secret
        self.gets: list[str] = []
        self.posts: list[tuple[str, dict[str, object]]] = []

    def get_json(self, url: str, *, secrets: list[str] | None = None):
        self.gets.append(url)
        if self.fail:
            raise HttpClientError(f"getMe failed for {self.secret}")
        return {"ok": True, "result": {"username": "stage35_bot", "first_name": "Stage 35"}}

    def post_form(self, url: str, data: dict[str, object], *, secrets: list[str] | None = None):
        self.posts.append((url, data))
        if self.fail:
            raise HttpClientError(f"sendMessage failed for {self.secret}")
        return {"ok": True, "result": {"message_id": 350}}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")


def make_service(tmp_path: Path, ai_provider: FakeAIProvider | None = None) -> CampaignService:
    db = Database(tmp_path / "stage35.sqlite")
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
            "ai_max_drafts_per_batch": "25",
            "email_sync_enabled": "true",
            "telegram_sync_enabled": "true",
            "inbox_sync_mode": "manual",
        }
    )
    provider = ai_provider or FakeAIProvider()
    ai_service = AIService(provider_factory=lambda _provider, _model: provider)
    return CampaignService(
        db,
        mailer=FakeMailer(),
        ai_draft_service=ai_service,
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )


def add_contact(
    service: CampaignService,
    campaign_id: int,
    *,
    email: str = "owned-recipient@example.com",
    channel: str = "email",
    external_id: str = "",
    status: str = "approved",
    message: str = "Controlled Stage 3.5 verification message.",
) -> int:
    contact_id = service.db.add_contact(
        {
            "campaign_id": campaign_id,
            "channel": channel,
            "email": email,
            "external_id": external_id,
            "handle": "@owned_test" if channel == "telegram" else "",
            "subject": "Stage 3.5 Verification",
            "base_message": message,
            "generated_message": message,
            "status": status,
        }
    )
    return int(contact_id)


def test_gmail_smtp_dry_run_then_live_uses_exact_profile_sender_and_contact_recipient(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.create_gmail_profile("Sender", "sender@example.com", "profile-password")
    contact_id = add_contact(service, campaign_id, email="owned-recipient@example.com")

    service.enqueue_send_approved(campaign_id, mode="dry_run", channel="email")
    QueueJobProcessor(service).process_available()

    assert service.mailer.sent == []
    assert service.db.get_contact(contact_id)["status"] == "dry_run_sent"

    service.approve_contacts([contact_id])
    service.save_settings(
        {
            "send_mode": "live",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "allowed_test_recipient": "owned-recipient@example.com",
        }
    )
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="email")
    QueueJobProcessor(service).process_available()

    contact = service.db.get_contact(contact_id)
    timeline = service.contact_timeline(contact_id)
    messages = service.conversation_messages(int(service.conversation_thread(contact_id)["id"]))
    assert len(service.mailer.sent) == 1
    assert service.mailer.sent[0]["sender_email"] == "sender@example.com"
    assert service.mailer.sent[0]["recipient_email"] == "owned-recipient@example.com"
    assert service.mailer.sent[0]["password"] == "profile-password"
    assert contact["status"] == "sent"
    assert contact["sent_at"]
    assert contact["follow_up_due_at"]
    assert any(event["event_type"] == "sent" for event in timeline)
    assert any(message["message_type"] == "sent" for message in messages)


def test_safe_mode_missing_confirmation_mismatch_missing_recipient_and_daily_limit_block(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.create_gmail_profile("Sender", "sender@example.com", "profile-password")

    no_confirm_id = add_contact(service, campaign_id, email="confirm@example.com")
    service.save_settings(
        {
            "send_mode": "live",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "allowed_test_recipient": "confirm@example.com",
        }
    )
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=False, channel="email")
    QueueJobProcessor(service).process_available()
    assert service.mailer.sent == []
    assert service.db.get_contact(no_confirm_id)["status"] == "failed"

    mismatch_id = add_contact(service, campaign_id, email="mismatch@example.com")
    service.save_settings({"allowed_test_recipient": "allowed@example.com"})
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="email")
    QueueJobProcessor(service).process_available()
    mismatch_job = service.queue.list_recent_jobs(campaign_id)[0]
    assert service.mailer.sent == []
    assert service.db.get_contact(mismatch_id)["status"] == "failed"
    assert "allowed_test_recipient=allowed@example.com" in mismatch_job["last_error"]
    assert "recipient_email=mismatch@example.com" in mismatch_job["last_error"]

    missing_id = add_contact(service, campaign_id, email="")
    service.save_settings({"allowed_test_recipient": ""})
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="email")
    QueueJobProcessor(service).process_available()
    assert service.db.get_contact(missing_id)["status"] == "failed"
    assert service.mailer.sent == []

    first_id = add_contact(service, campaign_id, email="limit-one@example.com")
    second_id = add_contact(service, campaign_id, email="limit-two@example.com")
    service.save_settings({"allowed_test_recipient": "", "daily_send_limit": "1"})
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="email")
    QueueJobProcessor(service).process_available()
    assert len(service.mailer.sent) == 1
    assert service.mailer.sent[0]["recipient_email"] in {"limit-one@example.com", "limit-two@example.com"}
    assert {service.db.get_contact(first_id)["status"], service.db.get_contact(second_id)["status"]} == {"sent", "failed"}


def test_gmail_profile_switching_isolates_sender_credentials_without_rewriting_recipient(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    first = service.create_gmail_profile("Sender One", "sender-one@example.com", "password-one")
    second = service.create_gmail_profile("Sender Two", "sender-two@example.com", "password-two")

    first_contact = add_contact(service, campaign_id, email="first-owned@example.com")
    service.set_active_gmail_profile(int(first["id"]))
    service.save_settings(
        {"send_mode": "live", "allowed_test_recipient": "first-owned@example.com", "daily_send_limit": "2"}
    )
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="email")
    QueueJobProcessor(service).process_available()

    second_contact = add_contact(service, campaign_id, email="second-owned@example.com")
    service.set_active_gmail_profile(int(second["id"]))
    service.save_settings({"send_mode": "live", "allowed_test_recipient": "second-owned@example.com"})
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="email")
    QueueJobProcessor(service).process_available()

    assert service.mailer.sent[0]["sender_email"] == "sender-one@example.com"
    assert service.mailer.sent[0]["password"] == "password-one"
    assert service.mailer.sent[0]["recipient_email"] == "first-owned@example.com"
    assert service.mailer.sent[1]["sender_email"] == "sender-two@example.com"
    assert service.mailer.sent[1]["password"] == "password-two"
    assert service.mailer.sent[1]["recipient_email"] == "second-owned@example.com"
    assert service.db.get_contact(first_contact)["status"] == "sent"
    assert service.db.get_contact(second_contact)["status"] == "sent"


def test_telegram_dry_run_live_polling_and_safe_mode_guards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.save_telegram_settings(bot_token="123456:stage35-token", default_test_chat_id="1001")
    service.save_settings({"active_channel": "telegram", "send_mode": "dry_run"})
    contact_id = add_contact(
        service,
        campaign_id,
        channel="telegram",
        email="telegram-1001@example.local",
        external_id="1001",
    )
    fake_http = FakeTelegramHttp()
    monkeypatch.setattr("src.background_worker.TelegramChannel", lambda: TelegramChannel(http_client=fake_http))

    service.enqueue_send_approved(campaign_id, mode="dry_run", channel="telegram")
    QueueJobProcessor(service).process_available()
    assert fake_http.posts == []
    assert service.db.get_contact(contact_id)["status"] == "dry_run_sent"

    service.approve_contacts([contact_id])
    service.save_settings(
        {
            "send_mode": "live",
            "safe_mode": "true",
            "daily_send_limit": "1",
            "allowed_test_recipient": "1001",
        }
    )
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="telegram")
    QueueJobProcessor(service).process_available()
    assert len(fake_http.posts) == 1
    assert fake_http.posts[0][1]["chat_id"] == "1001"
    assert service.db.get_contact(contact_id)["status"] == "sent"

    reply = TelegramReplyMessage(
        update_id=3501,
        message_id=3501,
        chat_id="1001",
        sender_name="Owned Test",
        text="Получил, интересно.",
    )
    sync_result = service.inbox.ingest_telegram_updates([reply], campaign_id=campaign_id, account_id="telegram_bot")
    duplicate_result = service.inbox.ingest_telegram_updates([reply], campaign_id=campaign_id, account_id="telegram_bot")
    assert sync_result.imported_count == 1
    assert duplicate_result.imported_count == 0
    assert duplicate_result.skipped_count == 1

    blocked_id = add_contact(
        service,
        campaign_id,
        channel="telegram",
        email="telegram-2002@example.local",
        external_id="2002",
    )
    service.save_settings({"allowed_test_recipient": "1001"})
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="telegram")
    QueueJobProcessor(service).process_available()
    assert service.db.get_contact(blocked_id)["status"] == "failed"
    assert len(fake_http.posts) == 1


def test_email_imap_ingestion_is_idempotent_and_does_not_mutate_server_or_autosend(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.create_gmail_profile("Sender", "sender@example.com", "profile-password")
    contact_id = add_contact(service, campaign_id, email="reply@example.com", status="sent")
    message = EmailReplyMessage(
        imap_uid="35",
        remote_message_id="stage35-message-id",
        sender_email="reply@example.com",
        sender_name="Reply",
        subject="Re: Stage 3.5 Verification",
        body="Интересно, пришлите детали.",
        in_reply_to="outbound-message-id",
    )
    client = FakeEmailClient([message])

    first = service.sync_email_replies(campaign_id, client=client)
    second = service.sync_email_replies(campaign_id, client=client)

    thread = service.conversation_thread(contact_id)
    replies = service.db.fetch_all("SELECT * FROM replies")
    messages = service.conversation_messages(int(thread["id"]))
    assert first.imported_count == 1
    assert second.imported_count == 0
    assert len(replies) == 1
    assert len([row for row in messages if row["remote_message_id"] == "stage35-message-id"]) == 1
    assert client.calls[0]["password"] == "***"
    assert service.mailer.sent == []
    assert thread["suggested_lead_status"] in {"Warm", "Interested"}
    assert thread["lead_status"] == "New"


def test_ai_draft_and_reply_intelligence_never_auto_approve_or_send(tmp_path: Path) -> None:
    provider = FakeAIProvider()
    service = make_service(tmp_path, provider)
    campaign_id = service.default_campaign_id()
    service.save_ai_settings(provider="openai", model="gpt-4.1-mini", api_key="stage35-ai-key")
    contact_id = add_contact(
        service,
        campaign_id,
        email="ai-owned@example.com",
        status="new",
        message="",
    )

    result = service.enqueue_ai_generate_drafts(
        campaign_id,
        contact_ids=[contact_id],
        campaign_topic="Предложить сотрудничество по рекламе",
        tone="business",
    )
    QueueJobProcessor(service).process_available()
    contact = service.db.get_contact(contact_id)
    assert result.count == 1
    assert contact["status"] == "pending_review"
    assert contact["status"] != "approved"
    assert int(contact["ai_generated"]) == 1
    assert service.mailer.sent == []

    service.add_manual_reply_to_conversation(contact_id, "Интересно, пришлите условия.", reply_status="interested")
    service.enqueue_ai_summarize_reply(contact_id)
    service.enqueue_ai_generate_reply(contact_id, "Интересно, пришлите условия.")
    service.enqueue_ai_followup_suggestion(contact_id)
    QueueJobProcessor(service).process_available()
    thread = service.conversation_thread(contact_id)
    logs = service.db.fetch_all("SELECT action FROM send_logs WHERE action LIKE 'ai_%'")
    assert thread["summary"]
    assert {"ai_summarize_reply", "ai_generate_reply", "ai_followup_suggestion"}.issubset(
        {row["action"] for row in logs}
    )
    assert service.mailer.sent == []
    assert service.db.get_contact(contact_id)["status"] == "pending_review"


def test_failure_paths_are_user_safe_and_do_not_leak_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    token = "123456:stage35-token"
    service.save_telegram_settings(bot_token=token)
    service.save_settings(
        {
            "active_channel": "telegram",
            "send_mode": "live",
            "safe_mode": "true",
            "daily_send_limit": "1",
            "allowed_test_recipient": "1001",
        }
    )
    add_contact(
        service,
        campaign_id,
        channel="telegram",
        email="telegram-fail@example.local",
        external_id="1001",
    )
    fake_http = FakeTelegramHttp(fail=True, secret=token)
    monkeypatch.setattr("src.background_worker.TelegramChannel", lambda: TelegramChannel(http_client=fake_http))

    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="telegram")
    QueueJobProcessor(service).process_available()

    combined = " ".join(str(job.get("last_error") or "") for job in service.queue.list_recent_jobs(campaign_id))
    combined += " " + " ".join(str(row.get("error") or "") for row in service.db.fetch_all("SELECT * FROM send_logs"))
    assert token not in combined
    assert service.mailer.sent == []
