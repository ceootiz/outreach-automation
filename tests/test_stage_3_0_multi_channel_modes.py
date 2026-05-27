from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from PySide6.QtWidgets import QApplication, QFrame

from src.ai import AIConnectionCheckResult, AIService, EmailDraftInput, EmailDraftResult
from src.ai.prompt_builder import build_email_draft_messages
from src.background_worker import QueueJobProcessor
from src.campaign_service import CampaignService
from src.channels import get_channel, list_channels
from src.db import Database
from src.gui.main_window import MainWindow


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def check_connection(self, **kwargs):
        return SimpleNamespace(ok=True, message="Gmail fake ok")


class FakeAIProvider:
    def __init__(self) -> None:
        self.inputs: list[EmailDraftInput] = []

    def generate_email_draft(self, input_data: EmailDraftInput) -> EmailDraftResult:
        self.inputs.append(input_data)
        return EmailDraftResult(
            subject="Email subject" if input_data.channel == "email" else "",
            body=f"Черновик для канала {input_data.channel}",
            personalization_notes="channel-aware",
            confidence=0.75,
            warnings=[],
        )

    def check_connection(self) -> AIConnectionCheckResult:
        return AIConnectionCheckResult(True, "AI fake ok")


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def make_service(tmp_path: Path, *, ai_provider: FakeAIProvider | None = None) -> CampaignService:
    db = Database(tmp_path / "stage3.sqlite")
    db.initialize()
    db.set_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "25",
            "delay_seconds": "0",
            "onboarding_completed": "true",
            "ai_provider": "openai",
            "ai_model": "gpt-4.1-mini",
        }
    )
    provider = ai_provider or FakeAIProvider()
    return CampaignService(
        db,
        mailer=FakeMailer(),
        ai_draft_service=AIService(provider_factory=lambda _provider, _model: provider),
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )


def add_approved_contact(
    service: CampaignService,
    campaign_id: int,
    channel: str,
    recipient: str,
) -> int:
    if channel == "email":
        row = {
            "channel": "email",
            "email": recipient,
            "subject": "Тема",
            "generated_message": "Сообщение",
            "status": "approved",
        }
    else:
        row = {
            "channel": channel,
            "handle": recipient,
            "generated_message": "Сообщение",
            "status": "approved",
        }
    result = service.add_contact_rows(campaign_id, [row], source="stage3-test")
    assert result.imported_count == 1, result.errors
    contact = service.db.fetch_one(
        "SELECT * FROM contacts WHERE campaign_id = ? AND channel = ? ORDER BY id DESC LIMIT 1",
        (campaign_id, channel),
    )
    assert contact is not None
    service.db.update_contact(int(contact["id"]), {"status": "approved"})
    return int(contact["id"])


def test_channel_registry_has_all_stage_3_channels() -> None:
    ids = {channel.channel_id for channel in list_channels()}
    assert ids == {"email", "x", "instagram", "telegram", "vk", "tiktok"}
    assert get_channel("email").supports_live_send is True
    for channel_id in ids - {"email", "telegram"}:
        channel = get_channel(channel_id)
        assert channel.supports_dry_run is True
        assert channel.supports_live_send is False
        assert channel.explain_limitations()
    assert get_channel("telegram").supports_live_send is True


def test_email_channel_still_dry_runs_and_keeps_recipient(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_approved_contact(service, campaign_id, "email", "lead@example.com")

    summary = service.send_approved(campaign_id)

    contact = service.db.get_contact(contact_id)
    log = service.db.fetch_one("SELECT * FROM send_logs WHERE action = 'dry_run_send'")
    assert summary.dry_run_sent == 1
    assert contact["status"] == "dry_run_sent"
    assert log["channel"] == "email"
    assert log["platform_recipient"] == "lead@example.com"
    assert service.mailer.sent == []


def test_non_email_live_send_blocked_by_default(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.save_settings({"active_channel": "x", "send_mode": "live"})
    add_approved_contact(service, campaign_id, "x", "@safe_profile")

    result = service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True, channel="x")

    assert result.ok is False
    assert result.count == 0
    assert "Боевая отправка" in result.error
    assert service.mailer.sent == []


def test_dry_run_works_for_all_channels(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    for channel in list_channels():
        recipient = "lead@example.com" if channel.channel_id == "email" else f"@{channel.channel_id}_profile"
        add_approved_contact(service, campaign_id, channel.channel_id, recipient)
        service.save_settings({"active_channel": channel.channel_id, "send_mode": "dry_run"})
        result = service.enqueue_send_approved(
            campaign_id,
            mode="dry_run",
            confirm_live_send=False,
            channel=channel.channel_id,
        )
        QueueJobProcessor(service).process_available()
        assert result.count == 1

    logs = service.db.fetch_all("SELECT channel, platform_recipient FROM send_logs WHERE action = 'dry_run_send'")
    assert {row["channel"] for row in logs} == {"email", "x", "instagram", "telegram", "vk", "tiktok"}
    assert service.mailer.sent == []


def test_ai_prompt_includes_channel_context_and_social_subject_is_empty(tmp_path: Path) -> None:
    input_data = EmailDraftInput(
        contact_id=1,
        email="x-abc@channel.local",
        channel="instagram",
        social_profile="https://instagram.com/example",
        campaign_topic="предложить сотрудничество",
        tone="business",
    )
    messages = build_email_draft_messages(input_data)
    assert "Instagram" in messages[0]["content"]
    assert "Subject должен быть пустой строкой" in messages[0]["content"]
    assert '"channel": "instagram"' in messages[1]["content"]

    fake_ai = FakeAIProvider()
    service = make_service(tmp_path, ai_provider=fake_ai)
    service.save_ai_settings(provider="openai", model="gpt-4.1-mini", api_key="stage3-safe-key")
    campaign_id = service.default_campaign_id()
    result = service.add_contact_rows(
        campaign_id,
        [
            {
                "channel": "instagram",
                "handle": "@brand",
                "generated_message": "",
                "status": "new",
            }
        ],
    )
    assert result.imported_count == 1
    contact_id = int(service.db.fetch_one("SELECT id FROM contacts WHERE channel = 'instagram'")["id"])

    queued = service.enqueue_ai_generate_drafts(
        campaign_id,
        contact_ids=[contact_id],
        campaign_topic="предложить сотрудничество",
        tone="business",
        channel="instagram",
    )
    QueueJobProcessor(service).process_available()
    contact = service.db.get_contact(contact_id)

    assert queued.count == 1
    assert fake_ai.inputs[0].channel == "instagram"
    assert contact["subject"] == ""
    assert contact["generated_message"]
    assert contact["status"] == "pending_review"
    assert service.mailer.sent == []


def test_non_email_channels_visible_in_ui_and_settings(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path))
    window.show()
    qapp.processEvents()

    selector_values = {
        window.campaign_view.channel_selector.itemData(index)
        for index in range(window.campaign_view.channel_selector.count())
    }
    assert {"email", "x", "instagram", "telegram", "vk", "tiktok"}.issubset(selector_values)
    assert window.tabs.tabText(3) == "Аккаунты и настройки"
    assert window.settings_view.findChild(QFrame, "settingsChannelCard_x") is not None
    for channel_id in ("x", "instagram", "telegram", "vk", "tiktok"):
        assert channel_id in window.settings_view.channel_token_inputs
        assert channel_id in window.settings_view.channel_check_buttons
        assert get_channel(channel_id).explain_limitations()

    window.campaign_view.shutdown()
    window.settings_view.shutdown()
    window.close()
