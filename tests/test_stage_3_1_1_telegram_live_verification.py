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
from src.db import Database
from src.http_client import HttpClientError


CONTROLLED_MESSAGE = "Controlled Stage 3.1.1 Telegram verification message."


class FakeMailer:
    def send_email(self, **kwargs) -> None:  # pragma: no cover - must not be used here
        raise AssertionError("Telegram verification tests must not send email")

    def check_connection(self, **kwargs):
        return SimpleNamespace(ok=False, message="Gmail not used")


class FakeTelegramHttp:
    def __init__(self, *, fail: bool = False, token_in_error: str = "") -> None:
        self.fail = fail
        self.token_in_error = token_in_error
        self.get_urls: list[str] = []
        self.posts: list[tuple[str, dict[str, object]]] = []

    def get_json(self, url: str, *, secrets: list[str] | None = None):
        self.get_urls.append(url)
        if self.fail:
            raise HttpClientError(f"getMe failed with {self.token_in_error or 'token'}")
        return {"ok": True, "result": {"username": "stage311_bot", "first_name": "Stage Bot"}}

    def post_form(self, url: str, data: dict[str, object], *, secrets: list[str] | None = None):
        self.posts.append((url, data))
        if self.fail:
            raise HttpClientError(f"sendMessage failed with {self.token_in_error or 'token'}")
        return {"ok": True, "result": {"message_id": 311}}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")


def make_service(tmp_path: Path) -> CampaignService:
    db = Database(tmp_path / "stage311.sqlite")
    db.initialize()
    db.set_settings(
        {
            "active_channel": "telegram",
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "delay_seconds": "0",
            "allowed_test_recipient": "",
            "onboarding_completed": "true",
        }
    )
    return CampaignService(
        db,
        mailer=FakeMailer(),
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )


def add_controlled_telegram_contact(
    service: CampaignService,
    campaign_id: int,
    *,
    chat_id: str = "1001",
    status: str = "approved",
) -> int:
    result = service.add_contact_rows(
        campaign_id,
        [
            {
                "channel": "telegram",
                "external_id": chat_id,
                "handle": "@owned_test",
                "generated_message": CONTROLLED_MESSAGE,
                "base_message": CONTROLLED_MESSAGE,
                "status": status,
            }
        ],
        source="stage-3.1.1-test",
    )
    assert result.imported_count == 1, result.errors
    contact = service.db.fetch_one(
        "SELECT * FROM contacts WHERE channel = 'telegram' ORDER BY id DESC LIMIT 1"
    )
    assert contact is not None
    service.db.update_contact(int(contact["id"]), {"status": status})
    return int(contact["id"])


def test_live_verification_preconditions_are_explicit(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    assert service.telegram_bot_token() == ""
    assert service.settings().get("telegram_default_test_chat_id", "") == ""

    service.save_telegram_settings(
        bot_token="123456:stage311-token",
        default_test_chat_id="1001",
    )

    assert bool(service.telegram_bot_token()) is True
    assert bool(service.settings().get("telegram_default_test_chat_id")) is True


def test_dry_run_no_send_message_http_and_logs_safe_recipient(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_controlled_telegram_contact(service, campaign_id)
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


def test_live_send_uses_exact_external_chat_id_and_message_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.save_telegram_settings(bot_token="123456:stage311-token")
    service.save_settings(
        {
            "send_mode": "live",
            "allowed_test_recipient": "1001",
            "safe_mode": "true",
            "daily_send_limit": "1",
        }
    )
    contact_id = add_controlled_telegram_contact(service, campaign_id, chat_id="1001")
    fake = FakeTelegramHttp()
    monkeypatch.setattr("src.background_worker.TelegramChannel", lambda: TelegramChannel(http_client=fake))

    result = service.enqueue_send_approved(
        campaign_id,
        mode="live",
        confirm_live_send=True,
        channel="telegram",
    )
    QueueJobProcessor(service).process_available()

    contact = service.db.get_contact(contact_id)
    job = service.queue.list_recent_jobs(campaign_id)[0]
    log = service.db.fetch_one("SELECT * FROM send_logs WHERE action = 'live_send'")
    assert result.count == 1
    assert len(fake.posts) == 1
    assert fake.posts[0][1]["chat_id"] == "1001"
    assert fake.posts[0][1]["text"] == CONTROLLED_MESSAGE
    assert contact["status"] == "sent"
    assert job["status"] == "completed"
    assert log["status"] == "sent"
    assert log["channel"] == "telegram"
    assert log["platform_recipient"] == "1001"


def test_safe_mode_mismatch_blocks_live_send_without_rewrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.save_telegram_settings(bot_token="123456:stage311-token")
    service.save_settings(
        {
            "send_mode": "live",
            "allowed_test_recipient": "9999",
            "safe_mode": "true",
            "daily_send_limit": "1",
        }
    )
    contact_id = add_controlled_telegram_contact(service, campaign_id, chat_id="1001")
    fake = FakeTelegramHttp()
    monkeypatch.setattr("src.background_worker.TelegramChannel", lambda: TelegramChannel(http_client=fake))

    service.enqueue_send_approved(
        campaign_id,
        mode="live",
        confirm_live_send=True,
        channel="telegram",
    )
    QueueJobProcessor(service).process_available()

    contact = service.db.get_contact(contact_id)
    job = service.queue.list_recent_jobs(campaign_id)[0]
    assert fake.posts == []
    assert contact["status"] == "failed"
    assert job["status"] == "failed"
    assert "allowed_test_recipient=9999" in job["last_error"]
    assert "telegram_chat_id=1001" in job["last_error"]


def test_telegram_token_not_leaked_when_live_http_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "123456:stage311-token"
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.save_telegram_settings(bot_token=token)
    service.save_settings(
        {
            "send_mode": "live",
            "allowed_test_recipient": "1001",
            "safe_mode": "true",
            "daily_send_limit": "1",
        }
    )
    add_controlled_telegram_contact(service, campaign_id, chat_id="1001")
    service.enqueue_send_approved(
        campaign_id,
        mode="live",
        confirm_live_send=True,
        channel="telegram",
    )
    fake = FakeTelegramHttp(fail=True, token_in_error=token)
    monkeypatch.setattr("src.background_worker.TelegramChannel", lambda: TelegramChannel(http_client=fake))

    QueueJobProcessor(service).process_available()

    job = service.queue.list_recent_jobs(campaign_id)[0]
    logs = service.db.fetch_all("SELECT * FROM send_logs")
    combined = " ".join(str(job.get("last_error") or "") for job in [job])
    combined += " " + " ".join(str(row.get("error") or "") for row in logs)
    assert token not in combined
