from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from PySide6.QtWidgets import QApplication, QLineEdit

from src.ai import AIConnectionCheckResult, AIProviderError, AIService, EmailDraftInput, EmailDraftResult
from src.ai.prompt_builder import build_email_draft_messages
from src.ai.result_schema import parse_email_draft_result
from src.background_worker import QueueJobProcessor
from src.campaign_service import CampaignService
from src.credential_store import load_ai_api_key
from src.db import Database
from src.gui.main_window import MainWindow


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def check_connection(self, **kwargs):
        return SimpleNamespace(ok=False, message="No Gmail in AI tests")


class FakeAIProvider:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.inputs: list[EmailDraftInput] = []

    def generate_email_draft(self, input_data: EmailDraftInput) -> EmailDraftResult:
        self.inputs.append(input_data)
        if self.fail:
            raise AIProviderError("AI provider failed safely")
        return EmailDraftResult(
            subject=f"Черновик для {input_data.company or input_data.email}",
            body=f"Здравствуйте! По теме: {input_data.campaign_topic}.",
            personalization_notes="Использованы данные строки",
            confidence=0.82,
            warnings=[] if input_data.company else ["Мало данных для персонализации."],
        )

    def check_connection(self) -> AIConnectionCheckResult:
        return AIConnectionCheckResult(True, "AI test ok")


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
    db = Database(tmp_path / "ai.sqlite")
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
    provider = ai_provider or FakeAIProvider()
    ai_service = AIService(provider_factory=lambda _provider, _model: provider)
    return CampaignService(
        db,
        mailer=FakeMailer(),
        ai_draft_service=ai_service,
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )


def add_contact(db: Database, campaign_id: int, email: str = "lead@example.com") -> int:
    return db.add_contact(
        {
            "campaign_id": campaign_id,
            "email": email,
            "name": "Анна",
            "company": "Example Co",
            "website": "https://example.com",
            "social_profile": "https://linkedin.com/company/example",
            "topic": "маркетинг",
            "subject": "",
            "base_message": "",
            "generated_message": "",
            "status": "new",
        }
    )


def test_manual_mode_still_uses_existing_generate_queue(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    add_contact(service.db, campaign_id)

    result = service.enqueue_generate_messages(campaign_id)

    assert result.count == 1
    jobs = service.recent_jobs(campaign_id)
    assert jobs[0]["job_type"] == "generate_message"


def test_ai_mode_controls_and_settings_are_visible(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path))
    window.show()
    qapp.processEvents()

    assert window.campaign_view.manual_mode_button.text() == "Ручной"
    assert window.campaign_view.ai_mode_button.text() == "AI Assist"
    assert window.campaign_view.ai_topic_input.placeholderText().startswith("Например")
    assert window.campaign_view.ai_generate_button.text() == "Сгенерировать черновики"
    assert window.settings_view.ai_provider.findData("openai") >= 0
    assert window.settings_view.ai_api_key.echoMode() == QLineEdit.EchoMode.Password

    window.campaign_view.shutdown()
    window.settings_view.shutdown()
    window.close()


def test_ai_api_key_stored_securely_not_in_sqlite(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    secret = "stage-2-openai-secret"

    backend = service.save_ai_settings(
        provider="openai",
        model="gpt-4.1-mini",
        api_key=secret,
        max_drafts_per_batch=12,
    )

    assert backend
    assert load_ai_api_key("openai") == secret
    assert service.db.get_settings()["ai_provider"] == "openai"
    assert service.db.get_settings()["ai_max_drafts_per_batch"] == "12"
    assert secret.encode() not in service.db.path.read_bytes()


def test_prompt_builder_and_result_parser_are_structured() -> None:
    input_data = EmailDraftInput(
        contact_id=1,
        email="lead@example.com",
        company="Example Co",
        campaign_topic="предложить сотрудничество",
        tone="business",
    )
    messages = build_email_draft_messages(input_data)
    result = parse_email_draft_result(
        {
            "subject": "Короткая тема",
            "body": "Текст письма",
            "personalization_notes": "Заметка",
            "confidence": 1.5,
            "warnings": ["warning"],
        }
    )

    assert messages[0]["role"] == "system"
    assert "Не выдумывай факты" in messages[0]["content"]
    assert '"campaign_topic"' in messages[1]["content"]
    assert result.confidence == 1.0
    assert result.warnings == ["warning"]


def test_ai_queue_generates_pending_review_drafts_and_never_sends(tmp_path: Path) -> None:
    fake_ai = FakeAIProvider()
    service = make_service(tmp_path, ai_provider=fake_ai)
    service.save_ai_settings(provider="openai", model="gpt-4.1-mini", api_key="safe-ai-key")
    campaign_id = service.default_campaign_id()
    contact_id = add_contact(service.db, campaign_id, "lead@example.com")

    result = service.enqueue_ai_generate_drafts(
        campaign_id,
        contact_ids=[contact_id],
        campaign_topic="предложить сотрудничество",
        tone="friendly",
    )
    QueueJobProcessor(service).process_available()
    contact = service.db.get_contact(contact_id)

    assert result.count == 1
    assert fake_ai.inputs[0].email == "lead@example.com"
    assert fake_ai.inputs[0].website == "https://example.com"
    assert contact["status"] == "pending_review"
    assert contact["subject"].startswith("Черновик")
    assert contact["generated_message"]
    assert contact["ai_generated"] == 1
    assert contact["ai_confidence"] == 0.82
    assert service.mailer.sent == []


def test_ai_never_auto_approves_or_sends(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.save_ai_settings(provider="openai", model="gpt-4.1-mini", api_key="safe-ai-key")
    campaign_id = service.default_campaign_id()
    contact_id = add_contact(service.db, campaign_id)

    service.enqueue_ai_generate_drafts(campaign_id, contact_ids=[contact_id], campaign_topic="тема")
    QueueJobProcessor(service).process_available()
    send_result = service.enqueue_send_approved(campaign_id, mode="dry_run")

    assert service.db.get_contact(contact_id)["status"] == "pending_review"
    assert send_result.count == 0
    assert service.mailer.sent == []


def test_ai_mode_without_api_key_is_blocked_but_manual_mode_works(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    add_contact(service.db, campaign_id)

    ai_result = service.enqueue_ai_generate_drafts(campaign_id, campaign_topic="тема")
    manual_result = service.enqueue_generate_messages(campaign_id)

    assert not ai_result.ok
    assert "API key" in ai_result.error
    assert manual_result.count == 1


def test_ai_failure_marks_contact_failed_safely(tmp_path: Path) -> None:
    service = make_service(tmp_path, ai_provider=FakeAIProvider(fail=True))
    service.save_ai_settings(provider="openai", model="gpt-4.1-mini", api_key="safe-ai-key")
    campaign_id = service.default_campaign_id()
    contact_id = add_contact(service.db, campaign_id)

    service.enqueue_ai_generate_drafts(campaign_id, contact_ids=[contact_id], campaign_topic="тема")
    QueueJobProcessor(service).process_available()
    contact = service.db.get_contact(contact_id)
    jobs = service.recent_jobs(campaign_id)

    assert contact["status"] == "failed"
    assert "AI provider failed safely" in contact["last_error"]
    assert jobs[0]["status"] == "failed"


def test_ai_key_not_leaked_to_logs_or_report(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    secret = "never-log-openai-secret"
    campaign_id = service.default_campaign_id()
    service.save_ai_settings(provider="openai", model="gpt-4.1-mini", api_key=secret)
    add_contact(service.db, campaign_id)

    report = service.export_report(campaign_id)
    logs = service.db.fetch_all("SELECT * FROM send_logs")

    assert secret.encode() not in service.db.path.read_bytes()
    assert secret.encode() not in report.read_bytes()
    assert all(secret not in str(value) for row in logs for value in row.values())
