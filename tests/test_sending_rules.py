from __future__ import annotations

from pathlib import Path

import pytest

from src.campaign_service import CampaignService
from src.db import Database
from src.mailer import GmailSMTPMailer, MailerSendError
from src.logger_setup import setup_logging


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)


def make_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.sqlite")
    db.initialize()
    db.set_settings(
        {
            "sender_email": "sender@example.com",
            "daily_send_limit": "25",
            "delay_seconds": "0",
            "follow_up_delay_days": "2",
            "send_mode": "live",
            "real_send_confirm_required": "false",
        }
    )
    return db


def add_approved_contact(db: Database, campaign_id: int, email: str = "lead@example.com") -> int:
    contact_id = db.add_contact(
        {
            "campaign_id": campaign_id,
            "email": email,
            "name": "Lead",
            "company": "Lead Co",
            "topic": "sales",
            "subject": "Hello",
            "base_message": "Base",
            "status": "approved",
        }
    )
    db.update_contact(contact_id, {"generated_message": "Generated body"})
    return contact_id


def test_blacklist_blocks_sending(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    contact_id = add_approved_contact(db, campaign_id, "blocked@example.com")
    fake_mailer = FakeMailer()
    service = CampaignService(db, mailer=fake_mailer, sleep_fn=lambda _: None)
    service.blacklist.add("blocked@example.com", "Do not contact")

    summary = service.send_approved(campaign_id, confirm_live_send=True)
    contact = db.get_contact(contact_id)

    assert summary.sent == 0
    assert summary.blacklisted == 1
    assert fake_mailer.sent == []
    assert contact["status"] == "blacklisted"


def test_rate_limiter_blocks_over_daily_limit(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    db.set_setting("daily_send_limit", "1")
    add_approved_contact(db, campaign_id, "next@example.com")
    db.log_send(None, campaign_id, "send_email", "sent", "")
    fake_mailer = FakeMailer()
    service = CampaignService(db, mailer=fake_mailer, sleep_fn=lambda _: None)

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert summary.sent == 0
    assert summary.blocked_by_limit is True
    assert fake_mailer.sent == []


def test_gmail_password_is_not_logged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret = "super-secret-app-password"
    log_file = tmp_path / "app.log"
    setup_logging(log_file)
    monkeypatch.setenv("GMAIL_APP_PASSWORD", secret)

    class BadSMTP:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def starttls(self) -> None:
            return None

        def login(self, sender_email: str, password: str) -> None:
            raise RuntimeError(f"auth failed for password={password}")

        def send_message(self, message) -> None:
            return None

    monkeypatch.setattr("smtplib.SMTP", BadSMTP)
    mailer = GmailSMTPMailer()

    with pytest.raises(MailerSendError) as exc_info:
        mailer.send_email(
            host="smtp.gmail.com",
            port=587,
            sender_email="sender@example.com",
            recipient_email="lead@example.com",
            subject="Hello",
            body="Body",
        )

    for handler in mailer.logger.handlers:
        handler.flush()

    assert secret not in str(exc_info.value)
    assert secret not in log_file.read_text(encoding="utf-8")
    assert "[REDACTED]" in log_file.read_text(encoding="utf-8")
