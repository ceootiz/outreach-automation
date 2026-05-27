from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from src.campaign_service import CampaignService
from src.db import Database
from src.logger_setup import setup_logging
from src.mailer import GmailSMTPMailer


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)


def make_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "outreach.sqlite")
    db.initialize()
    db.set_settings(
        {
            "sender_email": "sender@example.com",
            "daily_send_limit": "25",
            "delay_seconds": "0",
            "safe_mode": "true",
        }
    )
    return db


def add_approved_contact(db: Database, campaign_id: int, email: str = "owned@example.com") -> int:
    contact_id = db.add_contact(
        {
            "campaign_id": campaign_id,
            "email": email,
            "name": "Owned",
            "company": "Test Co",
            "topic": "Stage 1.3",
            "subject": "Test",
            "base_message": "Base",
            "status": "approved",
        }
    )
    db.update_contact(contact_id, {"generated_message": "Generated"})
    return contact_id


def test_default_send_mode_is_dry_run(tmp_path: Path) -> None:
    db = Database(tmp_path / "outreach.sqlite")
    db.initialize()

    assert db.get_settings()["send_mode"] == "dry_run"
    assert db.get_settings()["real_send_confirm_required"] == "true"


def test_dry_run_does_not_call_mailer_and_creates_log(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    contact_id = add_approved_contact(db, campaign_id)
    fake_mailer = FakeMailer()
    service = CampaignService(db, mailer=fake_mailer, sleep_fn=lambda _: None)

    summary = service.send_approved(campaign_id)

    contact = db.get_contact(contact_id)
    logs = db.fetch_all("SELECT * FROM send_logs WHERE action = 'dry_run_send'")
    assert summary.dry_run_sent == 1
    assert summary.sent == 0
    assert fake_mailer.sent == []
    assert contact["status"] == "dry_run_sent"
    assert logs


def test_live_send_blocked_without_confirm_when_required(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    add_approved_contact(db, campaign_id)
    db.set_settings({"send_mode": "live", "real_send_confirm_required": "true"})
    fake_mailer = FakeMailer()
    service = CampaignService(db, mailer=fake_mailer, sleep_fn=lambda _: None)

    summary = service.send_approved(campaign_id)

    assert summary.sent == 0
    assert summary.blocked_by_guardrail is True
    assert "explicitly confirms" in summary.errors[0]
    assert fake_mailer.sent == []


def test_live_send_blocked_when_allowed_test_recipient_mismatch(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    contact_id = add_approved_contact(db, campaign_id, "other@example.com")
    db.set_settings(
        {
            "send_mode": "live",
            "real_send_confirm_required": "true",
            "allowed_test_recipient": "owned@example.com",
        }
    )
    fake_mailer = FakeMailer()
    service = CampaignService(db, mailer=fake_mailer, sleep_fn=lambda _: None)

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert summary.sent == 0
    assert summary.blocked_by_guardrail is True
    assert "allowed_test_recipient" in summary.errors[0]
    assert fake_mailer.sent == []
    assert db.get_contact(contact_id)["status"] == "approved"


def test_live_send_allowed_for_allowed_recipient_with_confirm(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    contact_id = add_approved_contact(db, campaign_id, "owned@example.com")
    db.set_settings(
        {
            "send_mode": "live",
            "real_send_confirm_required": "true",
            "allowed_test_recipient": "owned@example.com",
            "daily_send_limit": "1",
        }
    )
    fake_mailer = FakeMailer()
    service = CampaignService(db, mailer=fake_mailer, sleep_fn=lambda _: None)

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert summary.sent == 1
    assert fake_mailer.sent[0]["recipient_email"] == "owned@example.com"
    assert db.get_contact(contact_id)["status"] == "sent"


def test_create_test_contact_script_creates_one_contact_without_sending(tmp_path: Path) -> None:
    db_path = tmp_path / "outreach.sqlite"
    env = os.environ.copy()
    env["OUTREACH_DB_PATH"] = str(db_path)

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "create_test_contact.py"), "owned@example.com"],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    db = Database(db_path)
    campaign = db.fetch_one("SELECT id FROM campaigns WHERE name = ?", ("Stage 1.3 Test Send",))
    assert campaign is not None
    contacts = db.list_contacts(int(campaign["id"]))
    logs = db.fetch_all("SELECT * FROM send_logs WHERE action = 'create_test_contact'")
    assert len(contacts) == 1
    assert contacts[0]["email"] == "owned@example.com"
    assert contacts[0]["status"] == "new"
    assert logs


def test_live_guardrail_result_and_logs_do_not_leak_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    secret = "stage-1-3-secret"
    log_file = tmp_path / "app.log"
    setup_logging(log_file)
    monkeypatch.setenv("GMAIL_APP_PASSWORD", secret)
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    add_approved_contact(db, campaign_id, "other@example.com")
    db.set_settings(
        {
            "send_mode": "live",
            "real_send_confirm_required": "true",
            "allowed_test_recipient": "owned@example.com",
        }
    )
    service = CampaignService(db, mailer=GmailSMTPMailer(), sleep_fn=lambda _: None)

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    for handler in service.logger.handlers:
        handler.flush()
    db_logs = "\n".join(str(row) for row in db.recent_send_logs(20))
    file_logs = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    result_text = "\n".join(summary.errors)
    assert secret not in result_text
    assert secret not in db_logs
    assert secret not in file_logs
