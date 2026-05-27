from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")

from src.campaign_service import CampaignService
from src.credential_store import (
    delete_profile_password,
    get_gmail_credential_status,
    load_profile_password,
    save_gmail_app_password,
)
from src.db import Database
from src.gmail_profile_service import GmailProfileService


class CapturingMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def check_connection(self, **kwargs):
        return type("Result", (), {"ok": True, "message": "Connected. No email was sent."})()


@pytest.fixture(autouse=True)
def isolated_app_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(tmp_path / "app-data"))
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)


def make_service(tmp_path: Path, mailer: CapturingMailer | None = None) -> CampaignService:
    db = Database(tmp_path / "profiles.sqlite")
    db.initialize()
    db.set_settings(
        {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": "587",
            "sender_email": "",
            "send_mode": "live",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "25",
            "delay_seconds": "0",
            "allowed_test_recipient": "",
            "onboarding_completed": "true",
        }
    )
    return CampaignService(
        db,
        mailer=mailer or CapturingMailer(),
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )


def add_approved_contact(db: Database, campaign_id: int, email: str) -> int:
    contact_id = db.add_contact(
        {
            "campaign_id": campaign_id,
            "email": email,
            "name": "Lead",
            "company": "Example",
            "topic": "Profiles",
            "subject": "Hello",
            "base_message": "Body",
            "generated_message": "Body",
            "status": "approved",
        }
    )
    db.update_contact(contact_id, {"status": "approved", "generated_message": "Body"})
    return contact_id


def test_create_profile_stores_email_but_not_password_in_sqlite(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    secret = "profile-secret-password"

    profile = service.create_gmail_profile("Основной", "Sender@Gmail.com", secret)

    rows = service.db.fetch_all("SELECT * FROM gmail_profiles")
    assert len(rows) == 1
    assert rows[0]["email"] == "sender@gmail.com"
    assert rows[0]["profile_name"] == "Основной"
    assert secret.encode() not in service.db.path.read_bytes()
    assert load_profile_password(profile["id"], "sender@gmail.com") == secret


def test_list_set_active_and_only_one_profile_active(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    first = service.create_gmail_profile("Первый", "first@gmail.com", "first-pass")
    second = service.create_gmail_profile("Второй", "second@gmail.com", "second-pass")

    service.set_active_gmail_profile(int(first["id"]))
    assert service.active_sender_email() == "first@gmail.com"
    service.set_active_gmail_profile(int(second["id"]))

    profiles = service.list_gmail_profiles()
    active = [profile for profile in profiles if int(profile["is_active"]) == 1]
    assert len(active) == 1
    assert active[0]["email"] == "second@gmail.com"


def test_delete_profile_removes_profile_credential(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    profile = service.create_gmail_profile("Delete me", "delete@gmail.com", "delete-pass")

    assert load_profile_password(profile["id"], "delete@gmail.com") == "delete-pass"
    service.delete_gmail_profile(int(profile["id"]))

    assert service.list_gmail_profiles() == []
    assert load_profile_password(profile["id"], "delete@gmail.com") == ""
    assert not get_gmail_credential_status("delete@gmail.com").has_password


def test_migrate_legacy_single_gmail_credential(tmp_path: Path) -> None:
    db = Database(tmp_path / "migration.sqlite")
    db.initialize()
    db.set_setting("sender_email", "legacy@gmail.com")
    save_gmail_app_password("legacy@gmail.com", "legacy-pass")

    service = GmailProfileService(db, mailer=CapturingMailer())
    migrated = service.migrate_legacy_credentials_if_needed()

    assert migrated is not None
    assert migrated["profile_name"] == "Основной"
    assert migrated["email"] == "legacy@gmail.com"
    assert int(migrated["is_active"]) == 1
    assert load_profile_password(migrated["id"], "legacy@gmail.com") == "legacy-pass"


def test_active_profile_email_used_as_sender_and_contact_email_as_recipient(tmp_path: Path) -> None:
    mailer = CapturingMailer()
    service = make_service(tmp_path, mailer=mailer)
    campaign_id = service.default_campaign_id()
    service.create_gmail_profile("Main", "sender-one@gmail.com", "sender-one-pass")
    service.db.set_setting("allowed_test_recipient", "lead@example.com")
    add_approved_contact(service.db, campaign_id, "lead@example.com")

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert summary.sent == 1
    assert mailer.sent[0]["sender_email"] == "sender-one@gmail.com"
    assert mailer.sent[0]["recipient_email"] == "lead@example.com"
    assert mailer.sent[0]["password"] == "sender-one-pass"


def test_allowed_test_recipient_blocks_but_does_not_rewrite_with_profiles(tmp_path: Path) -> None:
    mailer = CapturingMailer()
    service = make_service(tmp_path, mailer=mailer)
    campaign_id = service.default_campaign_id()
    service.create_gmail_profile("Main", "sender@gmail.com", "sender-pass")
    service.db.set_setting("allowed_test_recipient", "owned@example.com")
    add_approved_contact(service.db, campaign_id, "lead@example.com")

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert summary.sent == 0
    assert summary.blocked_by_guardrail
    assert mailer.sent == []
    assert "recipient_email=lead@example.com" in summary.errors[0]
    assert "allowed_test_recipient=owned@example.com" in summary.errors[0]


def test_no_sender_to_sender_regression_with_active_profile(tmp_path: Path) -> None:
    mailer = CapturingMailer()
    service = make_service(tmp_path, mailer=mailer)
    campaign_id = service.default_campaign_id()
    service.create_gmail_profile("Blackwasser", "blackwasser51@gmail.com", "profile-pass")
    service.db.set_setting("allowed_test_recipient", "blackwasser@yandex.ru")
    add_approved_contact(service.db, campaign_id, "blackwasser@yandex.ru")

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert summary.sent == 1
    assert mailer.sent[0]["sender_email"] == "blackwasser51@gmail.com"
    assert mailer.sent[0]["recipient_email"] == "blackwasser@yandex.ru"
    assert mailer.sent[0]["recipient_email"] != mailer.sent[0]["sender_email"]


def test_settings_and_main_ui_expose_gmail_profile_controls() -> None:
    settings_source = Path("src/gui/settings_view.py").read_text(encoding="utf-8")
    campaign_source = Path("src/gui/campaign_view.py").read_text(encoding="utf-8")

    assert "settingsGmailProfileList" in settings_source
    assert "settingsGmailProfileNameInput" in settings_source
    assert "Добавить профиль" in settings_source
    assert "Удалить" in settings_source
    assert "Сделать активным" in settings_source
    assert "campaignSenderSelectorButton" in campaign_source
    assert "Выбрать отправителя" in campaign_source
    assert "campaign.sender_selector" in campaign_source


def test_profile_password_not_exported_or_logged(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    secret = "never-export-this-password"
    campaign_id = service.default_campaign_id()
    service.create_gmail_profile("Secure", "secure@gmail.com", secret)
    add_approved_contact(service.db, campaign_id, "lead@example.com")

    report = service.export_report(campaign_id)
    logs = service.db.fetch_all("SELECT * FROM send_logs")

    assert secret.encode() not in service.db.path.read_bytes()
    assert secret.encode() not in report.read_bytes()
    assert all(secret not in str(value) for row in logs for value in row.values())
    assert get_gmail_credential_status("secure@gmail.com").has_password


def test_profile_delete_helper_tolerates_missing_credentials() -> None:
    delete_profile_password(999999, "missing@example.com")
