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
from src.intelligence import ConversationAI


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def check_connection(self, **kwargs):
        return SimpleNamespace(ok=True, message="ok")


def make_service(tmp_path: Path) -> CampaignService:
    db = Database(tmp_path / "stage33.sqlite")
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


def add_contact(
    service: CampaignService,
    campaign_id: int,
    *,
    channel: str = "email",
    status: str = "new",
) -> int:
    row = {
        "channel": channel,
        "email": "lead@example.com" if channel == "email" else "",
        "external_id": "1001" if channel == "telegram" else "",
        "handle": "@lead" if channel != "email" else "",
        "name": "Lead",
        "company": "Acme",
        "topic": "partnership",
        "subject": "Hello",
        "generated_message": "Hello Lead, quick partnership idea.",
        "status": status,
    }
    result = service.add_contact_rows(campaign_id, [row])
    assert result.imported_count == 1
    contact = service.db.fetch_one("SELECT * FROM contacts ORDER BY id DESC LIMIT 1")
    assert contact is not None
    return int(contact["id"])


def test_thread_creation_and_manual_reply_intelligence(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_contact(service, campaign_id)

    thread = service.conversation_thread(contact_id)
    assert thread["contact_id"] == contact_id
    assert thread["lead_status"] == "New"

    result = service.add_manual_reply_to_conversation(
        contact_id,
        "Интересно, пришлите цены и медиакит.",
        reply_status="interested",
    )

    updated = service.conversation_thread(contact_id)
    messages = service.conversation_messages(int(updated["id"]))
    suggestions = service.db.fetch_all("SELECT * FROM ai_reply_suggestions WHERE contact_id = ?", (contact_id,))

    assert result["analysis"].intent == "pricing_request"
    assert updated["lead_status"] == "Interested"
    assert updated["unread_state"] == "unread"
    assert any(row["direction"] == "inbound" for row in messages)
    assert suggestions and suggestions[0]["short_reply"]
    assert service.mailer.sent == []


def test_lead_status_changes_and_followup_suggestions_are_manual_only(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_contact(service, campaign_id)

    status = service.change_lead_status(contact_id, "Negotiating")
    suggestion = service.suggest_followup_for_contact(contact_id)
    metrics = service.conversation_metrics(campaign_id)

    assert status == "Negotiating"
    assert suggestion["recommendation"]
    assert metrics["lead_statuses"]["Negotiating"] == 1
    assert metrics["followup_suggestions"] == 1
    assert service.mailer.sent == []


def test_ai_summary_and_queue_jobs_do_not_autosend(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_contact(service, campaign_id)
    reply = service.add_manual_reply_to_conversation(contact_id, "Давайте вернемся позже.", reply_status="maybe_later")
    thread_id = int(reply["thread"]["id"])

    summary_job = service.enqueue_ai_summarize_reply(contact_id)
    followup_job = service.enqueue_ai_followup_suggestion(contact_id)
    QueueJobProcessor(service).process_available()

    thread = service.conversation_thread(contact_id)
    logs = service.db.fetch_all(
        "SELECT action, status FROM send_logs WHERE action IN ('ai_summarize_reply', 'ai_followup_suggestion')"
    )

    assert summary_job.count == 1
    assert followup_job.count == 1
    assert thread["summary"]
    assert service.conversation_messages(thread_id)
    assert {row["action"] for row in logs} == {"ai_summarize_reply", "ai_followup_suggestion"}
    assert service.mailer.sent == []


def test_channel_aware_ai_reply_behavior_and_no_recipient_rewrite(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_contact(service, campaign_id, channel="telegram", status="approved")
    contact = service.db.get_contact(contact_id)
    assert contact is not None

    ai = ConversationAI()
    telegram_suggestion = ai.suggest_replies(contact, "Интересно, пришлите детали.", channel="telegram")
    email_contact = dict(contact, channel="email", email="sender-is-not-recipient@example.com")
    email_suggestion = ai.suggest_replies(email_contact, "Интересно, пришлите детали.", channel="email")

    service.save_telegram_settings(bot_token="123456:stage33-token")
    service.save_settings(
        {
            "active_channel": "telegram",
            "send_mode": "live",
            "safe_mode": "true",
            "allowed_test_recipient": "999",
        }
    )
    summary = service.send_approved(campaign_id, confirm_live_send=True)

    assert len(telegram_suggestion.short_reply) <= len(email_suggestion.formal_reply)
    assert "allowed_test_recipient=999" in summary.errors[0]
    assert "telegram_chat_id=1001" in summary.errors[0]
    assert service.mailer.sent == []


def test_inbox_ui_and_doctor_hooks_are_wired() -> None:
    main_window_source = Path("src/gui/main_window.py").read_text(encoding="utf-8")
    views_source = Path("src/gui/intelligence_views.py").read_text(encoding="utf-8")
    doctor_source = Path("scripts/ui_clickability_doctor.py").read_text(encoding="utf-8")

    assert "UnifiedInboxView" in main_window_source
    assert '"inbox"' in main_window_source
    assert "Входящие" in main_window_source
    assert "unifiedInboxView" in views_source
    assert "inboxConversationList" in views_source
    assert "conversationThreadTable" in views_source
    assert "replyComposerInput" in views_source
    assert "inboxSuggestReplyButton" in views_source
    assert "inboxSuggestFollowupButton" in views_source
    assert "Unified inbox sidebar item exists" in doctor_source
