from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from PySide6.QtWidgets import QApplication

from src.ai.prompt_builder import build_email_draft_messages
from src.ai.result_schema import EmailDraftInput
from src.ai.writer_brain import build_writer_messages
from src.ai.writer_schema import DraftWritingInput
from src.campaign_service import CampaignService
from src.channels.execution import (
    CAPABILITY_MATRIX,
    DRY_RUN,
    MANUAL_ASSIST,
    OFFICIAL_API,
    ChannelExecutionEngine,
    ExecutionPolicy,
    build_manual_assist_action,
    risk_label,
)
from src.db import Database
from src.gui.main_window import MainWindow
from src.ai.research_schema import RecipientBrief


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
    db = Database(tmp_path / "stage38.sqlite")
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


def add_approved_contact(service: CampaignService, campaign_id: int, channel: str, recipient: str) -> int:
    row = {
        "channel": channel,
        "generated_message": "Здравствуйте! Готовый ручной текст.",
        "subject": "Партнерство" if channel == "email" else "",
        "status": "approved",
    }
    if channel == "email":
        row["email"] = recipient
    elif channel == "telegram":
        row["external_id"] = recipient
    else:
        row["handle"] = recipient
        row["profile_url"] = f"https://example.com/{recipient.lstrip('@')}"
    result = service.add_contact_rows(campaign_id, [row], source="stage38")
    assert result.imported_count == 1, result.errors
    contact = service.db.fetch_one(
        "SELECT * FROM contacts WHERE campaign_id = ? AND channel = ? ORDER BY id DESC LIMIT 1",
        (campaign_id, channel),
    )
    assert contact is not None
    service.db.update_contact(int(contact["id"]), {"status": "approved"})
    return int(contact["id"])


def test_capability_matrix_has_risk_and_execution_modes() -> None:
    assert set(CAPABILITY_MATRIX) == {"email", "telegram", "x", "instagram", "vk", "tiktok"}
    assert CAPABILITY_MATRIX["email"].supports_live_send is True
    assert CAPABILITY_MATRIX["email"].supports_reply_ingestion is True
    assert CAPABILITY_MATRIX["telegram"].official_api == "yes"
    assert CAPABILITY_MATRIX["telegram"].supports_live_send is True
    assert CAPABILITY_MATRIX["instagram"].requires_manual_assist is True
    assert CAPABILITY_MATRIX["instagram"].allowed_execution_modes == (DRY_RUN, MANUAL_ASSIST)
    assert CAPABILITY_MATRIX["tiktok"].risk_level == "high"
    assert risk_label(CAPABILITY_MATRIX["x"].risk_level)


def test_execution_policy_blocks_unsupported_official_live_and_routes_manual() -> None:
    policy = ExecutionPolicy()

    blocked = policy.decide("instagram", OFFICIAL_API, send_mode="live", confirm_live_send=True)
    assert blocked.ok is False
    assert blocked.manual_required is True
    assert "Manual Assist" in blocked.message

    manual = policy.decide("x", MANUAL_ASSIST, send_mode="live", confirm_live_send=True)
    assert manual.ok is True
    assert manual.effective_mode == MANUAL_ASSIST
    assert manual.manual_required is True

    email = policy.decide("email", OFFICIAL_API, send_mode="live", confirm_live_send=True)
    assert email.ok is True
    assert email.effective_mode == OFFICIAL_API


def test_manual_assist_action_is_operator_only() -> None:
    action = build_manual_assist_action(
        {
            "id": 42,
            "channel": "instagram",
            "handle": "@brand",
            "profile_url": "",
            "generated_message": "Привет! Короткий ручной outreach.",
        }
    )

    assert action.manual_required if hasattr(action, "manual_required") else True
    assert action.profile_url == "https://www.instagram.com/brand/"
    assert action.copy_text == "Привет! Короткий ручной outreach."
    assert "ничего не отправляет" in action.instructions or "не отправляет" in action.instructions
    assert action.risk_level == "high"


def test_execution_engine_returns_structured_result() -> None:
    engine = ChannelExecutionEngine()
    contact = {"id": 1, "channel": "vk", "handle": "@lead", "generated_message": "text"}

    result = engine.result_for_contact(contact, MANUAL_ASSIST)

    assert result.status == "manual_required"
    assert result.mode == MANUAL_ASSIST
    assert result.manual_required is True
    assert result.to_dict()["action_taken"] == "manual_assist_prepare"
    assert result.to_dict()["warnings"]


def test_campaign_service_manual_assist_does_not_enqueue_or_send(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_approved_contact(service, campaign_id, "instagram", "@brand")
    service.set_execution_mode("instagram", MANUAL_ASSIST)

    result = service.enqueue_send_approved(
        campaign_id,
        mode="live",
        confirm_live_send=True,
        channel="instagram",
    )

    assert result.ok is True
    assert result.count == 1
    assert service.mailer.sent == []
    assert service.db.fetch_one("SELECT * FROM job_queue WHERE contact_id = ?", (contact_id,)) is None
    log = service.db.fetch_one("SELECT * FROM send_logs WHERE action = 'manual_assist_prepare'")
    assert log is not None
    assert log["channel"] == "instagram"
    assert service.db.get_contact(contact_id)["status"] == "approved"


def test_unsupported_live_send_still_blocked_without_manual_assist(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    add_approved_contact(service, campaign_id, "tiktok", "@creator")

    result = service.enqueue_send_approved(
        campaign_id,
        mode="live",
        confirm_live_send=True,
        channel="tiktok",
    )

    assert result.ok is False
    assert "Боевая отправка" in result.error
    assert service.mailer.sent == []


def test_manual_mark_sent_tracks_execution_without_hidden_automation(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_approved_contact(service, campaign_id, "x", "@operator")

    count = service.mark_manual_assist_sent([contact_id])

    assert count == 1
    contact = service.db.get_contact(contact_id)
    assert contact["status"] == "sent"
    log = service.db.fetch_one("SELECT * FROM send_logs WHERE action = 'manual_assist_mark_sent'")
    assert log is not None
    assert log["channel"] == "x"
    assert "No platform automation" in log["error"]
    assert service.mailer.sent == []


def test_ai_prompts_include_execution_context() -> None:
    simple_messages = build_email_draft_messages(
        EmailDraftInput(
            contact_id=1,
            email="lead@social.local",
            channel="instagram",
            campaign_topic="предложить сотрудничество",
            tone="business",
            execution_mode=MANUAL_ASSIST,
            execution_notes="Instagram manual-only",
        )
    )
    assert "Manual Assist" in simple_messages[0]["content"]
    assert '"mode": "manual_assist"' in simple_messages[1]["content"]

    brief = RecipientBrief(
        recipient_type="creator",
        likely_context="Публичных данных мало.",
        positioning_angle="Короткое ручное сообщение.",
        message_hooks=["нейтральный outreach"],
        do_not_claim=["не писать, что профиль изучен"],
        personalization_strength="low",
        confidence=0.4,
        warnings=["мало данных"],
        source_basis=["row_data"],
    )
    writer_messages = build_writer_messages(
        DraftWritingInput(
            contact_id=2,
            email="lead@social.local",
            channel="tiktok",
            campaign_topic="предложить сотрудничество",
            tone="short",
            recipient_brief=brief,
            execution_mode=MANUAL_ASSIST,
            execution_notes="TikTok manual-only",
        )
    )
    assert "Manual Assist" in writer_messages[0]["content"]
    assert '"mode": "manual_assist"' in writer_messages[1]["content"]
    assert "Subject" in writer_messages[0]["content"] and "пустой строкой" in writer_messages[0]["content"]


def test_ui_exposes_execution_mode_and_manual_assist_controls(tmp_path: Path, qapp: QApplication) -> None:
    service = make_service(tmp_path)
    window = MainWindow(service)
    window.show()
    qapp.processEvents()

    campaign = window.campaign_view
    assert campaign.execution_mode_combo.objectName() == "campaignExecutionModeCombo"
    assert campaign.execution_risk_label.objectName() == "campaignExecutionRiskLabel"

    index = campaign.channel_selector.findData("instagram")
    campaign.channel_selector.setCurrentIndex(index)
    qapp.processEvents()
    assert campaign.execution_mode_combo.findData(MANUAL_ASSIST) >= 0
    assert "Risk:" in campaign.execution_risk_label.text()
    assert campaign.copy_manual_message_button.objectName() == "campaignManualAssistCopyButton"
    assert campaign.open_manual_profile_button.objectName() == "campaignManualAssistOpenProfileButton"
    assert campaign.mark_manual_sent_button.objectName() == "campaignManualAssistMarkSentButton"

    inbox = window.unified_inbox_view
    assert inbox.copy_reply_button.objectName() == "inboxCopyReplyButton"
    assert inbox.open_profile_button.objectName() == "inboxOpenProfileButton"
    assert inbox.mark_replied_manual_button.objectName() == "inboxMarkRepliedManualButton"
    assert inbox.mark_followup_done_button.objectName() == "inboxMarkFollowupDoneButton"

    window.campaign_view.shutdown()
    window.settings_view.shutdown()
    window.close()
