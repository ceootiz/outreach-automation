from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from src.background_worker import QueueJobProcessor
from src.campaign_service import CampaignService
from src.db import Database
from src.inbox import EmailReplyMessage, TelegramReplyMessage, TelegramSyncClient


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def check_connection(self, **kwargs):
        return SimpleNamespace(ok=True, message="ok")


class FakeEmailClient:
    def __init__(self, messages: list[EmailReplyMessage]) -> None:
        self.messages = messages
        self.calls: list[dict[str, object]] = []

    def fetch_since(self, *, username: str, password: str, last_uid: str = "", limit: int = 25):
        self.calls.append({"username": username, "password": "***", "last_uid": last_uid, "limit": limit})
        assert password
        return self.messages


class FakeTelegramHttp:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def post_form(self, url: str, data: dict[str, object], *, secrets=None):
        self.calls.append({"url": url, "data": data, "secrets": ["***" if secrets else ""]})
        return {
            "ok": True,
            "result": [
                {
                    "update_id": 77,
                    "message": {
                        "message_id": 12,
                        "date": 1710000000,
                        "text": "Интересно, пришлите детали.",
                        "chat": {"id": 1001, "username": "lead_chat"},
                        "from": {"id": 1001, "first_name": "Lead", "username": "lead_chat"},
                    },
                }
            ],
        }


def make_service(tmp_path: Path) -> CampaignService:
    os.environ["OUTREACH_AUTOMATION_APP_DIR"] = str(tmp_path / "appdata")
    db = Database(tmp_path / "stage34.sqlite")
    db.initialize()
    db.set_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "delay_seconds": "0",
            "onboarding_completed": "true",
            "email_sync_enabled": "true",
            "telegram_sync_enabled": "true",
            "inbox_sync_mode": "manual",
        }
    )
    return CampaignService(db, mailer=FakeMailer(), sleep_fn=lambda _: None, export_dir=tmp_path / "exports")


def add_email_contact(service: CampaignService, campaign_id: int, email: str = "lead@example.com") -> int:
    result = service.add_contact_rows(
        campaign_id,
        [
            {
                "email": email,
                "name": "Lead",
                "company": "Acme",
                "subject": "Partnership",
                "generated_message": "Hello Lead",
                "status": "sent",
            }
        ],
    )
    assert result.imported_count == 1
    return int(service.db.fetch_one("SELECT id FROM contacts WHERE email = ?", (email,))["id"])


def test_email_imap_read_only_sync_ingests_reply_and_checkpoint(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_email_contact(service, campaign_id)
    service.create_gmail_profile("Main", "sender@example.com", "app-password")
    message = EmailReplyMessage(
        imap_uid="42",
        remote_message_id="msg-42@example.com",
        sender_email="lead@example.com",
        sender_name="Lead",
        subject="Re: Partnership",
        body="Интересно, пришлите цены.",
        in_reply_to="sent-message-id",
    )

    result = service.sync_email_replies(campaign_id, client=FakeEmailClient([message]))

    thread = service.conversation_thread(contact_id)
    messages = service.conversation_messages(int(thread["id"]))
    state = service.inbox_sync_state("email", "sender@example.com")
    queued = service.db.fetch_all("SELECT job_type FROM job_queue WHERE contact_id = ?", (contact_id,))

    assert result.ok is True
    assert result.imported_count == 1
    assert state["last_synced_uid"] == "42"
    assert thread["suggested_lead_status"] == "Interested"
    assert thread["lead_status"] == "New"
    assert any(row["remote_message_id"] == "msg-42@example.com" for row in messages)
    assert {row["job_type"] for row in queued} >= {"ai_summarize_reply", "ai_stage_suggestion"}
    assert service.mailer.sent == []


def test_email_sync_is_idempotent_and_does_not_duplicate_replies(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    add_email_contact(service, campaign_id)
    message = EmailReplyMessage(
        imap_uid="43",
        remote_message_id="msg-43@example.com",
        sender_email="lead@example.com",
        sender_name="Lead",
        subject="Re: Partnership",
        body="Ок, вернемся позже.",
    )

    first = service.inbox.ingest_email_messages([message], campaign_id=campaign_id, account_id="sender@example.com")
    second = service.inbox.ingest_email_messages([message], campaign_id=campaign_id, account_id="sender@example.com")

    replies = service.db.fetch_all("SELECT * FROM replies")
    messages = service.db.fetch_all("SELECT * FROM conversation_messages WHERE remote_message_id = ?", ("msg-43@example.com",))
    assert first.imported_count == 1
    assert second.imported_count == 0
    assert second.skipped_count == 1
    assert len(replies) == 1
    assert len(messages) == 1


def test_telegram_polling_uses_getupdates_and_ingests_chat_reply(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.save_telegram_settings(bot_token="123456:stage34-token")
    client = TelegramSyncClient(http_client=FakeTelegramHttp())

    result = service.sync_telegram_replies(campaign_id, client=client)

    contact = service.db.fetch_one("SELECT * FROM contacts WHERE channel = 'telegram'")
    state = service.inbox_sync_state("telegram", "telegram_bot")
    messages = service.db.fetch_all("SELECT * FROM conversation_messages WHERE channel = 'telegram'")

    assert result.ok is True
    assert result.imported_count == 1
    assert contact["external_id"] == "1001"
    assert state["last_update_id"] == 77
    assert messages[0]["telegram_update_id"] == 77
    assert "stage34-token" not in str(service.db.recent_send_logs())
    assert service.mailer.sent == []


def test_queue_processes_sync_summary_jobs_without_autosend(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_email_contact(service, campaign_id)
    message = EmailReplyMessage(
        imap_uid="44",
        remote_message_id="msg-44@example.com",
        sender_email="lead@example.com",
        sender_name="Lead",
        subject="Re: Partnership",
        body="Да, интересно.",
    )
    service.inbox.ingest_email_messages([message], campaign_id=campaign_id, account_id="sender@example.com")

    QueueJobProcessor(service).process_available()

    thread = service.conversation_thread(contact_id)
    logs = service.db.fetch_all(
        "SELECT action FROM send_logs WHERE action IN ('ai_summarize_reply', 'ai_stage_suggestion')"
    )
    assert thread["summary"]
    assert {row["action"] for row in logs} == {"ai_summarize_reply", "ai_stage_suggestion"}
    assert service.db.get_contact(contact_id)["lead_status"] == "New"
    assert service.mailer.sent == []


def test_sync_settings_and_ui_hooks_are_wired() -> None:
    settings_source = Path("src/gui/settings_view.py").read_text(encoding="utf-8")
    inbox_source = Path("src/gui/intelligence_views.py").read_text(encoding="utf-8")
    main_source = Path("src/gui/main_window.py").read_text(encoding="utf-8")
    doctor_source = Path("scripts/ui_clickability_doctor.py").read_text(encoding="utf-8")

    assert "settingsInboxSyncMode" in settings_source
    assert "settingsEmailSyncNowButton" in settings_source
    assert "settingsTelegramSyncNowButton" in settings_source
    assert "inboxBackgroundSyncTimer" in main_source
    assert "_maybe_enqueue_background_inbox_sync" in main_source
    assert "normalize_interval" in main_source
    assert "inboxSyncNowButton" in inbox_source
    assert "inboxRefreshButton" in inbox_source
    assert "inboxOpenConversationButton" in inbox_source
    assert "Inbox sync button enabled" in doctor_source
