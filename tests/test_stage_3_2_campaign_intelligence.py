from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

import pytest

from src.background_worker import QueueJobProcessor
from src.campaign_service import CampaignService
from src.db import Database


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def check_connection(self, **kwargs):
        return SimpleNamespace(ok=True, message="ok")


def make_service(tmp_path: Path) -> CampaignService:
    db = Database(tmp_path / "stage32.sqlite")
    db.initialize()
    db.set_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "delay_seconds": "0",
            "onboarding_completed": "true",
        }
    )
    return CampaignService(db, mailer=FakeMailer(), sleep_fn=lambda _: None, export_dir=tmp_path / "exports")


def add_contact(service: CampaignService, campaign_id: int, *, status: str = "new") -> int:
    result = service.add_contact_rows(
        campaign_id,
        [
            {
                "email": "lead@example.com",
                "name": "Lead",
                "company": "Acme",
                "topic": "partnership",
                "subject": "Hello",
                "generated_message": "Hello Lead, quick partnership idea.",
                "status": status,
            }
        ],
    )
    assert result.imported_count == 1
    contact = service.db.fetch_one("SELECT * FROM contacts ORDER BY id DESC LIMIT 1")
    assert contact is not None
    return int(contact["id"])


def test_contact_timeline_records_core_events(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_contact(service, campaign_id)

    service.approve_contacts([contact_id])
    service.send_approved(campaign_id)

    event_types = [row["event_type"] for row in service.contact_timeline(contact_id)]
    assert "contact_created" in event_types
    assert "approved" in event_types
    assert "dry_run" in event_types


def test_reply_statuses_and_ai_reply_suggestions_are_manual_only(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_contact(service, campaign_id, status="sent")

    reply_id = service.add_reply(
        contact_id,
        "Интересно, пришлите цены и детали.",
        reply_status="interested",
    )
    suggestions = service.reply_suggestions(contact_id, "Интересно, пришлите цены и детали.")

    reply = service.db.fetch_one("SELECT * FROM replies WHERE id = ?", (reply_id,))
    assert reply["reply_status"] == "interested"
    assert "интерес" in reply["ai_summary"].lower()
    assert suggestions.short_reply
    assert service.mailer.sent == []


def test_ai_quality_scoring_and_metrics(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_contact(service, campaign_id, status="pending_review")
    service.db.update_contact(contact_id, {"ai_generated": 1, "ai_confidence": 0.82})

    score = service.score_contact_draft(contact_id)
    metrics = service.campaign_metrics(campaign_id)

    assert score.spam_risk == "low"
    assert score.personalization_quality in {"medium", "high"}
    assert metrics["ai_drafts"] == 1
    assert metrics["ai_confidence_average"] == 0.82
    assert service.db.fetch_one("SELECT * FROM ai_metrics WHERE contact_id = ?", (contact_id,)) is not None


def test_followup_scheduling_is_reminder_only(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_contact(service, campaign_id, status="sent")

    followup_id = service.schedule_followup(contact_id, due_at="2000-01-01 00:00:00", note="Manual reminder")
    result = service.enqueue_followup_reminder(contact_id, followup_id=followup_id)
    QueueJobProcessor(service).process_available()

    assert result.count == 1
    assert service.mailer.sent == []
    assert service.followups.due_followups(campaign_id)[0]["id"] == followup_id
    assert service.db.fetch_one("SELECT * FROM send_logs WHERE action = 'followup_reminder'") is not None


def test_live_guardrail_still_does_not_rewrite_telegram_recipient(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.save_telegram_settings(bot_token="123456:stage32-token")
    service.save_settings(
        {
            "active_channel": "telegram",
            "send_mode": "live",
            "safe_mode": "true",
            "allowed_test_recipient": "999",
        }
    )
    result = service.add_contact_rows(
        campaign_id,
        [
            {
                "channel": "telegram",
                "external_id": "1001",
                "generated_message": "Hello",
                "status": "approved",
            }
        ],
    )
    assert result.imported_count == 1

    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert summary.sent == 0
    assert summary.blocked_by_guardrail is True
    assert "allowed_test_recipient=999" in summary.errors[0]
    assert "telegram_chat_id=1001" in summary.errors[0]


def test_intelligence_ui_pages_are_wired_in_sidebar() -> None:
    main_window_source = Path("src/gui/main_window.py").read_text(encoding="utf-8")
    views_source = Path("src/gui/intelligence_views.py").read_text(encoding="utf-8")

    assert "CampaignDashboardView" in main_window_source
    assert "ReplyInboxView" in main_window_source
    assert "AIAssistIntelligenceView" in main_window_source
    assert "AnalyticsView" in main_window_source
    assert "intelligence_sidebar_buttons" in main_window_source
    assert "campaignTimelineTable" in views_source
    assert "addReplyButton" in views_source
    assert "aiScoreDraftButton" in views_source
    assert "analyticsRefreshButton" in views_source
