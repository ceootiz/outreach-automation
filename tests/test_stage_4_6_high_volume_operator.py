from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from PySide6.QtWidgets import QApplication

from src.campaign_service import CampaignService
from src.db import Database
from src.gui.main_window import MainWindow
from src.operator import (
    HIGH_PRIORITY,
    HIGH_VOLUME_MODE,
    HOTKEY_ACTIONS,
    LeadPrioritizer,
    ReviewQueueFilters,
)


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def check_connection(self, **kwargs):
        return SimpleNamespace(ok=True, message="fake Gmail ok")


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def make_service(tmp_path: Path) -> CampaignService:
    db = Database(tmp_path / "stage46.sqlite")
    db.initialize()
    db.set_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "delay_seconds": "0",
            "onboarding_completed": "true",
            "active_channel": "instagram",
            "execution_mode_instagram": "manual_assist",
        }
    )
    return CampaignService(db, mailer=FakeMailer(), sleep_fn=lambda _: None, export_dir=tmp_path / "exports")


def add_lead(
    service: CampaignService,
    campaign_id: int,
    *,
    channel: str = "instagram",
    handle: str = "@creator",
    email: str = "",
    status: str = "pending_review",
    ai_confidence: float = 0.82,
    lead_status: str = "Warm",
) -> int:
    row = {
        "channel": channel,
        "email": email,
        "handle": handle,
        "profile_url": f"https://example.com/{handle.lstrip('@')}" if handle else "",
        "name": "Creator",
        "company": "Example Studio",
        "website": "https://example.com",
        "topic": "ads collaboration",
        "generated_message": "Здравствуйте! Предлагаю аккуратно обсудить рекламное сотрудничество.",
        "status": status,
    }
    if channel == "telegram":
        row["external_id"] = "1001"
    result = service.add_contact_rows(campaign_id, [row], source="stage46")
    assert result.imported_count == 1, result.errors
    contact = service.contacts(campaign_id)[0]
    service.db.update_contact(
        int(contact["id"]),
        {
            "status": status,
            "ai_generated": 1,
            "ai_confidence": ai_confidence,
            "research_confidence": 0.72,
            "enrichment_status": "success",
            "enrichment_confidence": 0.76,
            "lead_status": lead_status,
        },
    )
    return int(contact["id"])


def test_hotkey_map_contains_required_operator_actions() -> None:
    assert set(HOTKEY_ACTIONS) >= {"A", "R", "C", "O", "S", "N", "P", "F", "L", "1", "2", "3"}
    assert HOTKEY_ACTIONS["S"].action_id == "mark_manually_sent"
    assert HOTKEY_ACTIONS["C"].action_id == "copy_message"


def test_priority_engine_ranks_strong_and_weak_leads() -> None:
    prioritizer = LeadPrioritizer()

    strong = prioritizer.score_contact(
        {
            "channel": "email",
            "name": "Anna",
            "company": "Example Co",
            "website": "https://example.com",
            "topic": "partnership",
            "generated_message": "Ready",
            "ai_generated": 1,
            "ai_confidence": 0.9,
            "research_confidence": 0.8,
            "enrichment_status": "success",
            "enrichment_confidence": 0.8,
            "lead_status": "Interested",
        }
    )
    weak = prioritizer.score_contact({"channel": "instagram", "ai_generated": 1, "ai_confidence": 0.2, "last_error": "AI warning"})

    assert strong.label == HIGH_PRIORITY
    assert strong.score > weak.score
    assert weak.label in {"Medium Priority", "Low Priority"}


def test_session_workflow_records_manual_actions_without_autosend(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_lead(service, campaign_id)

    snapshot = service.start_outreach_session(campaign_id, mode=HIGH_VOLUME_MODE)
    session_id = int(snapshot["session"]["id"])

    text = service.operator_copy_message(session_id, contact_id)
    service.operator_approve_draft(session_id, contact_id)
    next_snapshot = service.operator_mark_manually_sent(session_id, contact_id)

    assert "сотрудничество" in text
    assert service.db.get_contact(contact_id)["status"] == "sent"
    assert service.mailer.sent == []
    assert service.db.fetch_one("SELECT * FROM job_queue WHERE contact_id = ?", (contact_id,)) is None
    assert next_snapshot["autosend"] is False
    actions = service.db.fetch_all("SELECT action FROM operator_session_events WHERE session_id = ?", (session_id,))
    assert {row["action"] for row in actions} >= {"copy_message", "approve_draft", "mark_manually_sent"}


def test_review_queue_filters_and_session_restore(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    warm_id = add_lead(service, campaign_id, handle="@warm", lead_status="Warm", ai_confidence=0.86)
    add_lead(service, campaign_id, handle="@cold", lead_status="New", ai_confidence=0.35)

    filters = ReviewQueueFilters(only_high_priority=True, only_warm=True)
    snapshot = service.start_outreach_session(campaign_id, mode=HIGH_VOLUME_MODE, filters=filters)
    session_id = int(snapshot["session"]["id"])

    assert snapshot["total"] == 1
    assert int(snapshot["current"]["contact"]["id"]) == warm_id

    restored_service = CampaignService(service.db, mailer=FakeMailer(), sleep_fn=lambda _: None, export_dir=tmp_path / "exports2")
    restored = restored_service.restore_outreach_session(campaign_id)

    assert restored is not None
    assert int(restored["session"]["id"]) == session_id
    assert restored["session"]["filters"]["only_high_priority"] is True
    assert int(restored["current"]["contact"]["id"]) == warm_id


def test_ai_feedback_and_rate_limit_are_operator_safe(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_lead(service, campaign_id)
    snapshot = service.start_outreach_session(campaign_id, mode=HIGH_VOLUME_MODE)
    session_id = int(snapshot["session"]["id"])

    feedback_id = service.operator_save_ai_feedback(session_id, contact_id, "generic", "too broad")
    service.db.log_send(contact_id, campaign_id, "live_send", "sent", "controlled fake", channel="email")
    rate_state = service.operator_rate_limit_state(campaign_id, channel="instagram")

    assert feedback_id > 0
    assert service.db.fetch_one("SELECT * FROM ai_feedback WHERE id = ?", (feedback_id,))["rating"] == "generic"
    assert rate_state["paused"] is True
    assert any("Daily limit" in warning for warning in rate_state["warnings"])
    assert service.mailer.sent == []


def test_ui_exposes_high_volume_session_controls(qapp: QApplication, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    add_lead(service, service.default_campaign_id())
    window = MainWindow(service)
    window.show()
    qapp.processEvents()

    try:
        labels = "\n".join(button.text() for button in window.intelligence_sidebar_buttons)
        assert "Outreach Session" in labels
        session = window.outreach_session_view
        assert session.mode_selector.objectName() == "operatorModeSelector"
        assert session.start_session_button.objectName() == "startOutreachSessionButton"
        assert session.copy_button.objectName() == "sessionCopyButton"
        assert session.open_profile_button.objectName() == "sessionOpenProfileButton"
        assert session.mark_sent_button.objectName() == "sessionMarkSentButton"
        assert session.hotkey_helper.objectName() == "sessionHotkeyHelperLabel"
        assert len(session.hotkey_shortcuts) >= 12
        session.start_session()
        qapp.processEvents()
        assert session.current_session_id is not None
        assert session.current_contact_id is not None
    finally:
        window.campaign_view.shutdown()
        window.settings_view.shutdown()
        window.close()
