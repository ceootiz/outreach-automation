from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from PySide6.QtWidgets import QApplication, QLineEdit

from src.ai import AIConnectionCheckResult, AIService, EmailDraftInput, EmailDraftResult
from src.ai.dual_brain_service import DualBrainService
from src.ai.research_brain import build_research_messages
from src.ai.research_schema import RecipientBrief, RecipientResearchInput
from src.ai.writer_brain import build_writer_messages
from src.ai.writer_schema import DraftWritingInput, WriterDraft
from src.background_worker import QueueJobProcessor
from src.campaign_service import CampaignService
from src.credential_store import load_ai_brain_api_key
from src.db import Database
from src.gui.main_window import MainWindow


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def check_connection(self, **kwargs):
        return SimpleNamespace(ok=False, message="No Gmail in dual-brain tests")


class FakeSimpleAIProvider:
    def __init__(self) -> None:
        self.inputs: list[EmailDraftInput] = []

    def generate_email_draft(self, input_data: EmailDraftInput) -> EmailDraftResult:
        self.inputs.append(input_data)
        return EmailDraftResult(
            subject="Simple subject",
            body="Simple draft body",
            personalization_notes="simple",
            confidence=0.7,
            warnings=[],
        )

    def check_connection(self) -> AIConnectionCheckResult:
        return AIConnectionCheckResult(True, "ok")


class FakeResearchBrain:
    def __init__(self) -> None:
        self.inputs: list[RecipientResearchInput] = []

    def research_contact(self, input_data: RecipientResearchInput) -> RecipientBrief:
        self.inputs.append(input_data)
        low_data = not any([input_data.name, input_data.company, input_data.website, input_data.social_profile, input_data.note])
        return RecipientBrief(
            recipient_type="unknown" if low_data else "company",
            likely_context="Только данные строки, без web browsing.",
            positioning_angle="Аккуратно предложить сотрудничество по теме кампании.",
            message_hooks=["релевантность темы"],
            do_not_claim=["не утверждать, что сайт или профиль были изучены"],
            personalization_strength="low" if low_data else "medium",
            confidence=0.35 if low_data else 0.72,
            warnings=["Недостаточно данных"] if low_data else [],
            source_basis=["row_data"] if low_data else ["row_data", "user_note"],
        )

    def check_connection(self) -> AIConnectionCheckResult:
        return AIConnectionCheckResult(True, "Research ok")


class FakeWriterBrain:
    def __init__(self) -> None:
        self.inputs: list[DraftWritingInput] = []

    def write_draft(self, input_data: DraftWritingInput) -> WriterDraft:
        self.inputs.append(input_data)
        social = input_data.channel != "email"
        return WriterDraft(
            subject="" if social else "Сотрудничество по рекламе",
            body=f"Здравствуйте! По теме: {input_data.campaign_topic}. Предлагаю аккуратно обсудить формат.",
            why_this_angle=input_data.recipient_brief.positioning_angle,
            warnings=input_data.recipient_brief.warnings,
            confidence=0.81,
        )

    def check_connection(self) -> AIConnectionCheckResult:
        return AIConnectionCheckResult(True, "Writer ok")


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_RESEARCH_API_KEY", "")
    monkeypatch.setenv("OPENAI_WRITER_API_KEY", "")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def make_service(
    tmp_path: Path,
    *,
    research: FakeResearchBrain | None = None,
    writer: FakeWriterBrain | None = None,
    simple_ai: FakeSimpleAIProvider | None = None,
) -> CampaignService:
    db = Database(tmp_path / "dual_brain.sqlite")
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
            "ai_generation_mode": "dual_brain",
            "ai_research_provider": "openai",
            "ai_research_model": "research-test-model",
            "ai_writer_provider": "openai",
            "ai_writer_model": "writer-test-model",
            "ai_max_drafts_per_batch": "25",
        }
    )
    research_brain = research or FakeResearchBrain()
    writer_brain = writer or FakeWriterBrain()
    simple_provider = simple_ai or FakeSimpleAIProvider()
    return CampaignService(
        db,
        mailer=FakeMailer(),
        ai_draft_service=AIService(provider_factory=lambda _provider, _model: simple_provider),
        dual_brain_service=DualBrainService(
            research_factory=lambda _provider, _model: research_brain,
            writer_factory=lambda _provider, _model: writer_brain,
        ),
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )


def add_email_contact(service: CampaignService, campaign_id: int, *, low_data: bool = False) -> int:
    return service.db.add_contact(
        {
            "campaign_id": campaign_id,
            "channel": "email",
            "email": "lead@example.com",
            "name": "" if low_data else "Анна",
            "company": "" if low_data else "Example Co",
            "website": "" if low_data else "https://example.com",
            "social_profile": "",
            "topic": "" if low_data else "интересуется рекламными интеграциями",
            "subject": "",
            "base_message": "",
            "generated_message": "",
            "status": "new",
        }
    )


def test_two_brain_keys_are_stored_separately_and_not_in_sqlite(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    research_secret = "stage36-research-key"
    writer_secret = "stage36-writer-key"

    service.save_ai_brain_settings("research", provider="openai", model="research-model", api_key=research_secret)
    service.save_ai_brain_settings("writer", provider="openai", model="writer-model", api_key=writer_secret)

    assert load_ai_brain_api_key("research", "openai") == research_secret
    assert load_ai_brain_api_key("writer", "openai") == writer_secret
    assert research_secret.encode() not in service.db.path.read_bytes()
    assert writer_secret.encode() not in service.db.path.read_bytes()

    shared = "stage36-shared-key"
    service.save_ai_brain_settings("research", provider="openai", model="research-model", api_key=shared)
    service.save_ai_brain_settings("writer", provider="openai", model="writer-model", api_key=shared)
    assert load_ai_brain_api_key("research", "openai") == shared
    assert load_ai_brain_api_key("writer", "openai") == shared


def test_research_and_writer_prompts_include_anti_hallucination_rules() -> None:
    research_input = RecipientResearchInput(
        contact_id=1,
        email="person@gmail.com",
        email_domain="gmail.com",
        campaign_topic="Предложить сотрудничество по рекламе",
    )
    research_messages = build_research_messages(research_input)
    assert "нет web enrichment" in research_messages[0]["content"]
    assert "Не выдумывай факты" in research_messages[0]["content"]
    assert "личных Gmail" in research_messages[0]["content"]

    brief = RecipientBrief(
        positioning_angle="Нейтрально предложить тестовый диалог.",
        do_not_claim=["не говорить, что сайт изучен"],
        personalization_strength="low",
        warnings=["Недостаточно данных"],
        source_basis=["row_data"],
    )
    writer_messages = build_writer_messages(
        DraftWritingInput(
            contact_id=1,
            email="person@gmail.com",
            channel="instagram",
            campaign_topic="Предложить сотрудничество по рекламе",
            tone="business",
            recipient_brief=brief,
        )
    )
    assert "Не добавляй факты" in writer_messages[0]["content"]
    assert "do_not_claim" in writer_messages[0]["content"]
    assert "subject" not in writer_messages[1]["content"].split("Формат ответа строго:", 1)[1].split("Входные данные:", 1)[0]


def test_dual_brain_flow_creates_pending_review_draft_and_never_sends(tmp_path: Path) -> None:
    research = FakeResearchBrain()
    writer = FakeWriterBrain()
    service = make_service(tmp_path, research=research, writer=writer)
    service.save_ai_brain_settings("research", provider="openai", model="research-test-model", api_key="r-key")
    service.save_ai_brain_settings("writer", provider="openai", model="writer-test-model", api_key="w-key")
    campaign_id = service.default_campaign_id()
    contact_id = add_email_contact(service, campaign_id)

    result = service.enqueue_ai_generate_drafts(
        campaign_id,
        contact_ids=[contact_id],
        campaign_topic="Предложить сотрудничество по рекламе",
        tone="business",
    )
    QueueJobProcessor(service).process_available()
    contact = service.db.get_contact(contact_id)

    assert result.ok
    assert result.count == 1
    assert service.recent_jobs(campaign_id)[0]["job_type"] == "ai_dual_brain_generate"
    assert research.inputs[0].email == "lead@example.com"
    assert writer.inputs[0].recipient_brief.positioning_angle
    assert contact["status"] == "pending_review"
    assert contact["subject"] == "Сотрудничество по рекламе"
    assert contact["generated_message"]
    assert int(contact["ai_generated"]) == 1
    assert contact["research_brief_json"]
    assert contact["research_status"] == "medium"
    assert service.enqueue_send_approved(campaign_id, mode="dry_run").count == 0
    assert service.mailer.sent == []


def test_low_data_contact_gets_research_warning(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.save_ai_brain_settings("research", provider="openai", model="research-test-model", api_key="r-key")
    service.save_ai_brain_settings("writer", provider="openai", model="writer-test-model", api_key="w-key")
    campaign_id = service.default_campaign_id()
    contact_id = add_email_contact(service, campaign_id, low_data=True)

    service.enqueue_ai_generate_drafts(campaign_id, contact_ids=[contact_id], campaign_topic="Предложить сотрудничество")
    QueueJobProcessor(service).process_available()
    contact = service.db.get_contact(contact_id)

    assert contact["status"] == "pending_review"
    assert contact["research_status"] == "low"
    assert "Недостаточно данных" in contact["research_warnings"]


def test_social_channel_dual_brain_draft_has_no_subject(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.save_ai_brain_settings("research", provider="openai", model="research-test-model", api_key="r-key")
    service.save_ai_brain_settings("writer", provider="openai", model="writer-test-model", api_key="w-key")
    campaign_id = service.default_campaign_id()
    add_result = service.add_contact_rows(
        campaign_id,
        [
            {
                "channel": "telegram",
                "external_id": "1001",
                "name": "Анна",
                "company": "Example Channel",
                "status": "new",
            }
        ],
    )
    assert add_result.imported_count == 1
    contact_id = int(service.db.fetch_one("SELECT id FROM contacts WHERE channel = 'telegram'")["id"])

    result = service.enqueue_ai_generate_drafts(
        campaign_id,
        contact_ids=[contact_id],
        campaign_topic="Предложить сотрудничество по рекламе",
        tone="short",
        channel="telegram",
    )
    QueueJobProcessor(service).process_available()
    contact = service.db.get_contact(contact_id)

    assert result.count == 1
    assert contact["channel"] == "telegram"
    assert contact["subject"] == ""
    assert contact["generated_message"]
    assert contact["status"] == "pending_review"
    assert service.mailer.sent == []


def test_simple_ai_mode_still_uses_old_provider_flow(tmp_path: Path) -> None:
    simple = FakeSimpleAIProvider()
    service = make_service(tmp_path, simple_ai=simple)
    service.save_ai_settings(provider="openai", model="gpt-4.1-mini", api_key="simple-key")
    service.save_settings({"ai_generation_mode": "simple"})
    campaign_id = service.default_campaign_id()
    contact_id = add_email_contact(service, campaign_id)

    result = service.enqueue_ai_generate_drafts(
        campaign_id,
        contact_ids=[contact_id],
        campaign_topic="Предложить сотрудничество",
    )
    QueueJobProcessor(service).process_available()
    contact = service.db.get_contact(contact_id)

    assert result.count == 1
    assert service.recent_jobs(campaign_id)[0]["job_type"] == "ai_generate_draft"
    assert simple.inputs[0].email == "lead@example.com"
    assert contact["subject"] == "Simple subject"
    assert contact["status"] == "pending_review"
    assert service.mailer.sent == []


def test_dual_brain_ui_controls_are_visible_and_masked(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path))
    window.show()
    qapp.processEvents()

    assert window.campaign_view.ai_generation_mode_combo.findData("dual_brain") >= 0
    assert window.settings_view.research_brain_provider.findData("openai") >= 0
    assert window.settings_view.writer_brain_provider.findData("openai") >= 0
    assert window.settings_view.research_brain_api_key.echoMode() == QLineEdit.EchoMode.Password
    assert window.settings_view.writer_brain_api_key.echoMode() == QLineEdit.EchoMode.Password
    assert window.settings_view.save_research_brain_button.isEnabled()
    assert window.settings_view.check_writer_brain_button.isEnabled()

    window.campaign_view.shutdown()
    window.settings_view.shutdown()
    window.close()
