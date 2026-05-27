from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from PySide6.QtWidgets import QApplication, QMessageBox

from src.ai import AIConnectionCheckResult, AIProviderError, AIService, EmailDraftInput, EmailDraftResult
from src.ai.prompt_builder import build_email_draft_messages
from src.ai.result_schema import parse_email_draft_result
from src.background_worker import QueueJobProcessor
from src.campaign_service import CampaignService
from src.credential_store import load_ai_api_key
from src.db import Database
from src.gui.contacts_table import CONTACT_COLUMNS
from src.gui.settings_view import SettingsView


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def check_connection(self, **kwargs):
        return SimpleNamespace(ok=False, message="No Gmail in AI tests")


class QAProvider:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.inputs: list[EmailDraftInput] = []

    def generate_email_draft(self, input_data: EmailDraftInput) -> EmailDraftResult:
        self.inputs.append(input_data)
        if self.fail:
            raise AIProviderError("controlled AI failure")
        low_data = not any([input_data.name, input_data.company, input_data.website, input_data.note])
        return EmailDraftResult(
            subject="Сотрудничество по рекламе",
            body=(
                "Здравствуйте! Хотел бы аккуратно обсудить возможное сотрудничество "
                f"по теме: {input_data.campaign_topic}."
            ),
            personalization_notes="Использованы только данные строки получателя.",
            confidence=0.55 if low_data else 0.87,
            warnings=["Мало данных для персонализации."] if low_data else [],
        )

    def check_connection(self) -> AIConnectionCheckResult:
        return AIConnectionCheckResult(True, "AI test connection ok")


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


@pytest.fixture(autouse=True)
def no_dialogs(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)


def make_service(tmp_path: Path, provider: QAProvider | None = None) -> CampaignService:
    db = Database(tmp_path / "stage_2_1.sqlite")
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
            "ai_max_drafts_per_batch": "25",
        }
    )
    fake_provider = provider or QAProvider()
    ai_service = AIService(provider_factory=lambda _provider, _model: fake_provider)
    return CampaignService(
        db,
        mailer=FakeMailer(),
        ai_draft_service=ai_service,
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )


def add_contact(
    db: Database,
    campaign_id: int,
    *,
    email: str,
    company: str = "",
    topic: str = "",
    website: str = "",
    social_profile: str = "",
) -> int:
    return db.add_contact(
        {
            "campaign_id": campaign_id,
            "email": email,
            "name": "Test",
            "company": company,
            "topic": topic,
            "website": website,
            "social_profile": social_profile,
            "subject": "",
            "base_message": "",
            "generated_message": "",
            "status": "new",
        }
    )


def test_ai_connection_with_fake_provider(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.save_ai_settings(provider="openai", model="gpt-4.1-mini", api_key="stage-2-qa-key")

    result = service.check_ai_connection(provider="openai", model="gpt-4.1-mini")

    assert result.ok
    assert "ok" in result.message


def test_ai_key_persistence_ui_uses_secure_storage_not_sqlite(qapp: QApplication, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    view = SettingsView(service, refresh_callback=lambda: None)
    secret = "stage-2-1-secret-key"

    view.refresh()
    view.ai_provider.setCurrentIndex(view.ai_provider.findData("openai"))
    view.ai_model.setText("gpt-4.1-mini")
    view.ai_api_key.setText(secret)
    view.ai_max_drafts.setValue(9)
    view.save_ai_settings()
    view.refresh()

    assert service.settings()["ai_provider"] == "openai"
    assert service.settings()["ai_model"] == "gpt-4.1-mini"
    assert service.settings()["ai_max_drafts_per_batch"] == "9"
    assert load_ai_api_key("openai") == secret
    assert secret.encode() not in service.db.path.read_bytes()
    assert view.ai_api_key.text() == ""
    assert "Сохранен" in view.ai_key_status.text()
    view.shutdown()
    view.close()
    qapp.processEvents()


def test_ai_generation_blocked_when_no_key(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    add_contact(service.db, campaign_id, email="only@example.com")

    result = service.enqueue_ai_generate_drafts(campaign_id, campaign_topic="Предложить сотрудничество")

    assert not result.ok
    assert "API key" in result.error


def test_generated_drafts_pending_review_only_and_no_autosend(tmp_path: Path) -> None:
    provider = QAProvider()
    service = make_service(tmp_path, provider)
    service.save_ai_settings(provider="openai", model="gpt-4.1-mini", api_key="stage-2-qa-key")
    campaign_id = service.default_campaign_id()
    ids = [
        add_contact(service.db, campaign_id, email="email-only@example.com"),
        add_contact(service.db, campaign_id, email="company@example.com", company="Example Co", topic="медиа"),
        add_contact(
            service.db,
            campaign_id,
            email="full@example.com",
            company="Full Co",
            topic="реклама",
            website="https://example.com",
            social_profile="https://linkedin.com/company/example",
        ),
    ]

    result = service.enqueue_ai_generate_drafts(
        campaign_id,
        contact_ids=ids,
        campaign_topic="Предложить сотрудничество по рекламе",
        tone="business",
    )
    QueueJobProcessor(service).process_available()
    contacts = service.contacts(campaign_id)

    assert result.count == 3
    assert len(provider.inputs) == 3
    assert {contact["status"] for contact in contacts} == {"pending_review"}
    assert all(contact["subject"] and len(contact["subject"]) <= 90 for contact in contacts)
    assert all(contact["generated_message"] and len(contact["generated_message"]) <= 1200 for contact in contacts)
    assert all(int(contact["ai_generated"]) == 1 for contact in contacts)
    assert all(contact["ai_confidence"] is not None for contact in contacts)
    assert all(contact["ai_notes"] for contact in contacts)
    assert not any(contact["status"] == "approved" for contact in contacts)
    assert service.mailer.sent == []


def test_output_schema_validation_clamps_and_rejects_bad_json() -> None:
    parsed = parse_email_draft_result(
        '{"subject":"Тема","body":"Текст","personalization_notes":"","confidence":-4,"warnings":"мало данных"}'
    )

    assert parsed.confidence == 0.0
    assert parsed.warnings == ["мало данных"]
    with pytest.raises(ValueError):
        parse_email_draft_result("{not json")


def test_prompt_explicitly_prevents_fake_facts_and_spam_tone() -> None:
    messages = build_email_draft_messages(
        EmailDraftInput(
            contact_id=1,
            email="lead@example.com",
            campaign_topic="Предложить сотрудничество по рекламе",
            tone="business",
        )
    )
    system_prompt = messages[0]["content"]

    assert "Не выдумывай факты" in system_prompt
    assert "Используй только явно переданные данные" in system_prompt
    assert "Не говори, что изучил сайт/профиль" in system_prompt
    assert "массового спама" in system_prompt


def test_manual_mode_regression_still_uses_template_flow(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.db.set_setting("ai_provider", "off")
    campaign_id = service.default_campaign_id()
    add_contact(service.db, campaign_id, email="manual@example.com")

    result = service.enqueue_generate_messages(campaign_id)
    QueueJobProcessor(service).process_available()
    contact = service.contacts(campaign_id)[0]

    assert result.count == 1
    assert contact["status"] == "pending_review"
    assert contact["generated_message"]
    assert int(contact["ai_generated"]) == 0
    assert service.mailer.sent == []


def test_ai_badge_column_exists_for_review_ui() -> None:
    assert ("ai_badge", "AI") in CONTACT_COLUMNS
