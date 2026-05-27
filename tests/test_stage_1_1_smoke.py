from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from src.campaign_service import CampaignService
from src.db import Database
from src.logger_setup import setup_logging
from src.mailer import GmailSMTPMailer


def write_stage_1_1_workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "contacts"
    sheet.append(["email", "name", "company", "topic", "subject", "message"])
    sheet.append(
        [
            "stage11.alex@example.com",
            "Alex Smoke",
            "Acme Smoke",
            "creator tools",
            "Intro for {{company}}",
            "I noticed your work around {{topic}}.",
        ]
    )
    sheet.append(
        [
            "stage11.maria@example.com",
            "Maria Smoke",
            "Northwind Smoke",
            "B2B automation",
            "",
            "Could be useful for {{company}}.",
        ]
    )
    sheet.append(["not-an-email", "Broken Email", "Bad Co", "invalid", "Bad", "Bad"])
    sheet.append(["stage11.alex@example.com", "Alex Duplicate", "Acme Smoke", "duplicate", "Dup", "Dup"])
    sheet.append(["", "Empty Email", "No Mail Co", "missing", "Empty", "Empty"])
    workbook.save(path)


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)


def test_stage_1_1_service_smoke(tmp_path: Path) -> None:
    setup_logging(tmp_path / "app.log")
    db = Database(tmp_path / "outreach.sqlite")
    db.initialize()
    campaign_id = db.create_campaign("Stage 1.1 Smoke")
    service = CampaignService(
        db,
        mailer=GmailSMTPMailer(password_getter=lambda: ""),
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )
    service.save_settings(
        {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": "587",
            "sender_email": "stage11.sender@example.com",
            "daily_send_limit": "1",
            "delay_seconds": "0",
            "review_mode": "true",
            "follow_up_delay_days": "2",
            "safe_mode": "true",
            "send_mode": "live",
            "real_send_confirm_required": "false",
        }
    )
    workbook_path = tmp_path / "test_contacts_stage_1_1.xlsx"
    write_stage_1_1_workbook(workbook_path)

    import_result = service.import_file(workbook_path, campaign_id)
    assert import_result.imported_count == 2
    assert import_result.skipped_count == 3
    assert len(db.recent_import_errors(10)) == 3

    contacts = service.contacts(campaign_id)
    assert len(contacts) == 2
    assert {contact["status"] for contact in contacts} == {"new"}

    assert service.generate_messages(campaign_id) == 2
    contacts = service.contacts(campaign_id)
    assert all(contact["status"] == "pending_review" for contact in contacts)
    assert all(contact["generated_message"] for contact in contacts)

    edit_target = sorted(contacts, key=lambda contact: contact["email"])[0]
    service.update_contact(edit_target["id"], {"generated_message": "Manual Stage 1.1 edit body"})
    assert db.get_contact(edit_target["id"])["generated_message"] == "Manual Stage 1.1 edit body"

    assert service.approve_contacts([contact["id"] for contact in contacts]) == 2
    blacklist_target = sorted(contacts, key=lambda contact: contact["email"])[1]
    assert service.blacklist_contacts([blacklist_target["id"]], "Stage 1.1 smoke blacklist") == 1
    assert db.get_contact(blacklist_target["id"])["status"] == "blacklisted"

    missing_password_summary = service.send_approved(campaign_id, confirm_live_send=True)
    assert missing_password_summary.sent == 0
    assert missing_password_summary.failed == 0
    assert missing_password_summary.errors
    assert "Gmail app password is missing" in missing_password_summary.errors[0]
    assert db.get_contact(edit_target["id"])["status"] == "approved"

    limit_campaign_id = db.create_campaign("Stage 1.1 Limit Smoke")
    for email in ("stage11.limit.one@example.com", "stage11.limit.two@example.com"):
        contact_id = db.add_contact(
            {
                "campaign_id": limit_campaign_id,
                "email": email,
                "name": "Limit",
                "company": "Limit Co",
                "topic": "limits",
                "subject": "Limit smoke",
                "base_message": "Limit base",
                "status": "approved",
            }
        )
        db.update_contact(contact_id, {"generated_message": "Limit body"})

    fake_mailer = FakeMailer()
    limit_service = CampaignService(db, mailer=fake_mailer, sleep_fn=lambda _: None)
    limit_summary = limit_service.send_approved(limit_campaign_id, confirm_live_send=True)
    assert limit_summary.sent == 1
    assert limit_summary.blocked_by_limit is True
    assert len(fake_mailer.sent) == 1

    report_path = service.export_report(campaign_id)
    assert report_path.exists()
    assert report_path.name.startswith("contacts_export_")
    assert report_path.suffix == ".xlsx"

    assert db.recent_send_logs(20)
    assert db.recent_import_errors(20)
