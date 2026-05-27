from __future__ import annotations

from email import message_from_string
from pathlib import Path

import pytest

from src.background_worker import QueueJobProcessor
from src.campaign_service import CampaignService
from src.db import Database
from src.gui.campaign_view import build_live_send_confirmation_message
from src.mailer import GmailSMTPMailer, MailerConfigError


class CapturingMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)


def make_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "routing.sqlite")
    db.initialize()
    db.set_settings(
        {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": "587",
            "sender_email": "sender@example.com",
            "send_mode": "live",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "25",
            "delay_seconds": "0",
            "allowed_test_recipient": "",
        }
    )
    return db


def add_contact(
    db: Database,
    campaign_id: int,
    email: str,
    status: str = "approved",
) -> int:
    contact_id = db.add_contact(
        {
            "campaign_id": campaign_id,
            "email": email,
            "name": "Lead",
            "company": "Example",
            "topic": "Routing",
            "subject": "Hello",
            "base_message": "Body",
            "generated_message": "Body",
            "status": status,
        }
    )
    db.update_contact(contact_id, {"status": status, "generated_message": "Body"})
    return contact_id


def test_mailer_uses_recipient_email_for_header_and_smtp_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    smtp_calls: dict[str, object] = {}

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            smtp_calls["host"] = host
            smtp_calls["port"] = port
            smtp_calls["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def starttls(self) -> None:
            smtp_calls["starttls"] = True

        def login(self, sender_email: str, password: str) -> None:
            smtp_calls["login_sender"] = sender_email
            smtp_calls["login_password"] = password

        def sendmail(self, from_addr: str, to_addrs: list[str], message: str) -> None:
            smtp_calls["from_addr"] = from_addr
            smtp_calls["to_addrs"] = to_addrs
            smtp_calls["message"] = message

        def send_message(self, message) -> None:  # pragma: no cover - must not be used
            raise AssertionError("send_message must not be used for live sends")

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    mailer = GmailSMTPMailer(password_getter=lambda sender: "app-password")
    mailer.send_email(
        host="smtp.gmail.com",
        port=587,
        sender_email="blackwasser51@gmail.com",
        recipient_email="blackwasser@yandex.ru",
        subject="Routing check",
        body="Body",
    )

    parsed = message_from_string(str(smtp_calls["message"]))
    assert parsed["From"] == "blackwasser51@gmail.com"
    assert parsed["To"] == "blackwasser@yandex.ru"
    assert smtp_calls["login_sender"] == "blackwasser51@gmail.com"
    assert smtp_calls["from_addr"] == "blackwasser51@gmail.com"
    assert smtp_calls["to_addrs"] == ["blackwasser@yandex.ru"]
    assert smtp_calls["to_addrs"] != ["blackwasser51@gmail.com"]


def test_mailer_blocks_missing_recipient_before_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    smtp_called = {"value": False}

    class FakeSMTP:
        def __init__(self, *args, **kwargs) -> None:
            smtp_called["value"] = True

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    mailer = GmailSMTPMailer(password_getter=lambda sender: "app-password")

    with pytest.raises(MailerConfigError):
        mailer.send_email(
            host="smtp.gmail.com",
            port=587,
            sender_email="sender@example.com",
            recipient_email="",
            subject="Hello",
            body="Body",
        )

    assert smtp_called["value"] is False


def test_campaign_live_send_passes_contact_email_to_mailer(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    add_contact(db, campaign_id, "lead@example.com")
    db.set_settings({"allowed_test_recipient": "lead@example.com"})
    mailer = CapturingMailer()
    service = CampaignService(db, mailer=mailer, sleep_fn=lambda _: None)

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert summary.sent == 1
    assert mailer.sent[0]["sender_email"] == "sender@example.com"
    assert mailer.sent[0]["recipient_email"] == "lead@example.com"


def test_dry_run_log_contains_contact_email(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    db.set_setting("send_mode", "dry_run")
    add_contact(db, campaign_id, "dry@example.com")
    service = CampaignService(db, mailer=CapturingMailer(), sleep_fn=lambda _: None)

    summary = service.send_approved(campaign_id)

    assert summary.dry_run_sent == 1
    log = db.fetch_one("SELECT * FROM send_logs WHERE action = 'dry_run_send'")
    assert "recipient_email=dry@example.com" in log["error"]


def test_allowed_test_recipient_blocks_without_rewriting(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    add_contact(db, campaign_id, "lead@example.com")
    db.set_settings({"allowed_test_recipient": "owned@example.com"})
    mailer = CapturingMailer()
    service = CampaignService(db, mailer=mailer, sleep_fn=lambda _: None)

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert summary.sent == 0
    assert summary.blocked_by_guardrail is True
    assert mailer.sent == []
    assert "recipient_email=lead@example.com" in summary.errors[0]
    assert "allowed_test_recipient=owned@example.com" in summary.errors[0]


def test_allowed_test_recipient_does_not_rewrite_matching_recipient(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    add_contact(db, campaign_id, "owned@example.com")
    db.set_settings(
        {
            "sender_email": "sender@example.com",
            "allowed_test_recipient": "owned@example.com",
        }
    )
    mailer = CapturingMailer()
    service = CampaignService(db, mailer=mailer, sleep_fn=lambda _: None)

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert summary.sent == 1
    assert mailer.sent[0]["sender_email"] == "sender@example.com"
    assert mailer.sent[0]["recipient_email"] == "owned@example.com"


def test_queue_live_send_job_uses_contact_email(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    contact_id = add_contact(db, campaign_id, "queued@example.com")
    db.set_settings({"allowed_test_recipient": "queued@example.com"})
    mailer = CapturingMailer()
    service = CampaignService(db, mailer=mailer, sleep_fn=lambda _: None)

    result = service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True)
    QueueJobProcessor(service).process_available()

    assert result.count == 1
    job = service.queue.list_recent_jobs(campaign_id)[0]
    assert job["contact_id"] == contact_id
    assert job["status"] == "completed"
    assert mailer.sent[0]["recipient_email"] == "queued@example.com"


def test_queue_live_send_fails_when_recipient_missing(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    contact_id = add_contact(db, campaign_id, "")
    mailer = CapturingMailer()
    service = CampaignService(db, mailer=mailer, sleep_fn=lambda _: None)

    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True)
    QueueJobProcessor(service).process_available()

    job = service.queue.list_recent_jobs(campaign_id)[0]
    assert job["status"] == "failed"
    assert mailer.sent == []
    assert "Не удалось определить получателя" in job["last_error"]


def test_confirmation_dialog_text_separates_sender_and_recipients() -> None:
    message = build_live_send_confirmation_message(
        1,
        ["blackwasser@yandex.ru"],
        sender_email="blackwasser51@gmail.com",
        mode="live",
    )

    assert "Будет отправлено: 1" in message
    assert "От: blackwasser51@gmail.com" in message
    assert "Кому:" in message
    assert "blackwasser@yandex.ru" in message


def test_confirmation_implementation_has_no_fullscreen_overlay_flags() -> None:
    source = Path("src/gui/campaign_view.py").read_text(encoding="utf-8")

    assert "FullScreen" not in source
    assert "FramelessWindowHint" not in source
    assert "WindowStaysOnTopHint" not in source


def test_regression_blackwasser_sender_does_not_become_recipient(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    add_contact(db, campaign_id, "blackwasser@yandex.ru")
    db.set_settings(
        {
            "sender_email": "blackwasser51@gmail.com",
            "allowed_test_recipient": "blackwasser@yandex.ru",
        }
    )
    mailer = CapturingMailer()
    service = CampaignService(db, mailer=mailer, sleep_fn=lambda _: None)

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert summary.sent == 1
    assert mailer.sent[0]["sender_email"] == "blackwasser51@gmail.com"
    assert mailer.sent[0]["recipient_email"] == "blackwasser@yandex.ru"
    assert mailer.sent[0]["recipient_email"] != mailer.sent[0]["sender_email"]
