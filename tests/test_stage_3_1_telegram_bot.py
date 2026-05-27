from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from src.background_worker import QueueJobProcessor
from src.campaign_service import CampaignService
from src.channels.telegram_channel import TelegramChannel
from src.credential_store import load_telegram_bot_token
from src.db import Database
from src.http_client import HttpClientError


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def check_connection(self, **kwargs):
        return SimpleNamespace(ok=True, message="Gmail fake ok")


class FakeTelegramHttp:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.get_urls: list[str] = []
        self.posts: list[tuple[str, dict[str, object]]] = []

    def get_json(self, url: str, *, secrets: list[str] | None = None):
        self.get_urls.append(url)
        if self.fail:
            token = secrets[0] if secrets else "token"
            raise HttpClientError(f"Telegram failed with {token}")
        return {"ok": True, "result": {"username": "safe_bot", "first_name": "Safe Bot"}}

    def post_form(self, url: str, data: dict[str, object], *, secrets: list[str] | None = None):
        self.posts.append((url, data))
        if self.fail:
            token = secrets[0] if secrets else "token"
            raise HttpClientError(f"sendMessage failed with {token}")
        return {"ok": True, "result": {"message_id": 1}}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")


def make_service(tmp_path: Path) -> CampaignService:
    db = Database(tmp_path / "telegram.sqlite")
    db.initialize()
    db.set_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "25",
            "delay_seconds": "0",
            "onboarding_completed": "true",
        }
    )
    return CampaignService(
        db,
        mailer=FakeMailer(),
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )


def add_telegram_contact(
    service: CampaignService,
    campaign_id: int,
    *,
    chat_id: str = "1001",
    handle: str = "@safe_user",
    status: str = "approved",
) -> int:
    result = service.add_contact_rows(
        campaign_id,
        [
            {
                "channel": "telegram",
                "external_id": chat_id,
                "handle": handle,
                "generated_message": "Привет! Это безопасный тест.",
                "status": status,
            }
        ],
        source="telegram-test",
    )
    assert result.imported_count == 1, result.errors
    contact = service.db.fetch_one("SELECT * FROM contacts WHERE channel = 'telegram' ORDER BY id DESC LIMIT 1")
    assert contact is not None
    service.db.update_contact(int(contact["id"]), {"status": status})
    return int(contact["id"])


def test_telegram_token_stored_securely_not_in_sqlite(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    token = "123456:telegram-secret-token"

    backend = service.save_telegram_settings(bot_token=token, default_test_chat_id="1001")

    assert backend
    assert load_telegram_bot_token() == token
    assert service.db.get_settings()["telegram_default_test_chat_id"] == "1001"
    assert token.encode() not in service.db.path.read_bytes()


def test_telegram_check_connection_calls_get_me_with_fake_http() -> None:
    fake = FakeTelegramHttp()
    channel = TelegramChannel(http_client=fake)

    result = channel.check_connection({"bot_token": "123456:token"})

    assert result.ok is True
    assert "safe_bot" in result.message
    assert fake.get_urls[0].endswith("/getMe")


def test_telegram_send_message_calls_send_message_with_chat_id_and_text() -> None:
    fake = FakeTelegramHttp()
    channel = TelegramChannel(http_client=fake)

    result = channel.send_message(
        bot_token="123456:token",
        chat_id="1001",
        text="Hello",
    )

    assert result.ok is True
    assert fake.posts[0][0].endswith("/sendMessage")
    assert fake.posts[0][1]["chat_id"] == "1001"
    assert fake.posts[0][1]["text"] == "Hello"


def test_telegram_token_redacted_in_errors() -> None:
    fake = FakeTelegramHttp(fail=True)
    channel = TelegramChannel(http_client=fake)
    token = "123456:redact-me"

    result = channel.check_connection({"bot_token": token})

    assert result.ok is False
    assert token not in result.message


def test_telegram_live_send_blocked_without_chat_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.save_telegram_settings(bot_token="123456:token")
    service.save_settings({"active_channel": "telegram", "send_mode": "live"})
    add_telegram_contact(service, campaign_id, chat_id="", handle="@only_handle")
    fake = FakeTelegramHttp()
    monkeypatch.setattr("src.background_worker.TelegramChannel", lambda: TelegramChannel(http_client=fake))

    result = service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="telegram")
    QueueJobProcessor(service).process_available()
    job = service.queue.list_recent_jobs(campaign_id)[0]

    assert result.count == 1
    assert job["status"] == "failed"
    assert "chat_id" in job["last_error"]
    assert fake.posts == []


def test_telegram_safe_mode_allowed_recipient_blocks_mismatch(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.save_telegram_settings(bot_token="123456:token")
    service.save_settings(
        {
            "active_channel": "telegram",
            "send_mode": "live",
            "allowed_test_recipient": "9999",
            "safe_mode": "true",
        }
    )
    add_telegram_contact(service, campaign_id, chat_id="1001")

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert summary.sent == 0
    assert summary.blocked_by_guardrail is True
    assert "allowed_test_recipient=9999" in summary.errors[0]
    assert "telegram_chat_id=1001" in summary.errors[0]


def test_telegram_allowed_recipient_does_not_rewrite_chat_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.save_telegram_settings(bot_token="123456:token")
    service.save_settings(
        {
            "active_channel": "telegram",
            "send_mode": "live",
            "allowed_test_recipient": "1001",
            "safe_mode": "true",
        }
    )
    add_telegram_contact(service, campaign_id, chat_id="1001")
    fake = FakeTelegramHttp()
    monkeypatch.setattr("src.campaign_service.TelegramChannel", lambda: TelegramChannel(http_client=fake))

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert summary.sent == 1
    assert fake.posts[0][1]["chat_id"] == "1001"


def test_telegram_dry_run_does_not_call_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.save_settings({"active_channel": "telegram", "send_mode": "dry_run"})
    contact_id = add_telegram_contact(service, campaign_id, chat_id="1001")
    fake = FakeTelegramHttp()
    monkeypatch.setattr("src.background_worker.TelegramChannel", lambda: TelegramChannel(http_client=fake))

    result = service.enqueue_send_approved(campaign_id, mode="dry_run", channel="telegram")
    QueueJobProcessor(service).process_available()
    contact = service.db.get_contact(contact_id)
    log = service.db.fetch_one("SELECT * FROM send_logs WHERE action = 'dry_run_send'")

    assert result.count == 1
    assert contact["status"] == "dry_run_sent"
    assert log["channel"] == "telegram"
    assert log["platform_recipient"] == "1001"
    assert fake.posts == []


def test_email_channel_still_works_after_telegram_integration(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    result = service.add_contact_rows(
        campaign_id,
        [
            {
                "channel": "email",
                "email": "lead@example.com",
                "subject": "Тема",
                "generated_message": "Текст",
                "status": "approved",
            }
        ],
    )
    assert result.imported_count == 1
    service.save_settings({"active_channel": "email", "send_mode": "dry_run"})

    summary = service.send_approved(campaign_id)

    assert summary.dry_run_sent == 1
    assert service.mailer.sent == []
