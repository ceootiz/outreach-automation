from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from PySide6.QtWidgets import QApplication

from src.ai import AIConnectionCheckResult
from src.ai.dual_brain_service import DualBrainService
from src.ai.research_brain import build_research_messages
from src.ai.research_schema import RecipientBrief, RecipientResearchInput
from src.ai.writer_brain import build_writer_messages
from src.ai.writer_schema import DraftWritingInput, WriterDraft
from src.background_worker import QueueJobProcessor
from src.campaign_service import CampaignService
from src.db import Database
from src.enrichment import EnrichmentService
from src.enrichment.domain_analyzer import candidate_website_url
from src.enrichment.web_enricher import FetchResponse, WebEnricher
from src.gui.main_window import MainWindow


class FakeHttpClient:
    def __init__(self, responses: dict[str, FetchResponse | Exception | str]):
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url: str, *, timeout: int = 8, user_agent: str = "") -> FetchResponse:
        self.calls.append(url)
        value = self.responses.get(url)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, FetchResponse):
            return value
        if isinstance(value, str):
            return FetchResponse(url=url, status_code=200, text=value, content_type="text/html")
        return FetchResponse(url=url, status_code=404, text="", content_type="text/plain")


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def check_connection(self, **kwargs):
        return SimpleNamespace(ok=False, message="No live Gmail in enrichment tests")


class FakeResearchBrain:
    def __init__(self) -> None:
        self.inputs: list[RecipientResearchInput] = []

    def research_contact(self, input_data: RecipientResearchInput) -> RecipientBrief:
        self.inputs.append(input_data)
        enrichment = input_data.enrichment_result or {}
        has_public_data = enrichment.get("status") in {"success", "partial"}
        return RecipientBrief(
            recipient_type="company" if has_public_data else "unknown",
            likely_context="Использованы только данные строки и разрешенные публичные данные сайта.",
            positioning_angle="Предложить сотрудничество без утверждений о личном изучении сайта.",
            message_hooks=["публичное позиционирование"] if has_public_data else ["нейтральный outreach"],
            do_not_claim=["не писать, что сайт был изучен вручную"],
            personalization_strength="medium" if has_public_data else "low",
            confidence=0.72 if has_public_data else 0.35,
            warnings=list(enrichment.get("warnings") or []),
            source_basis=["row_data", "website_public_data"] if has_public_data else ["row_data"],
        )

    def check_connection(self) -> AIConnectionCheckResult:
        return AIConnectionCheckResult(True, "Research ok")


class FakeWriterBrain:
    def __init__(self) -> None:
        self.inputs: list[DraftWritingInput] = []

    def write_draft(self, input_data: DraftWritingInput) -> WriterDraft:
        self.inputs.append(input_data)
        return WriterDraft(
            subject="Сотрудничество по рекламе" if input_data.channel == "email" else "",
            body="Здравствуйте! Предлагаю аккуратно обсудить сотрудничество по рекламе.",
            why_this_angle=input_data.recipient_brief.positioning_angle,
            warnings=input_data.recipient_brief.warnings,
            confidence=0.8,
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


def html_response(url: str, html: str) -> FetchResponse:
    return FetchResponse(url=url, status_code=200, text=html, content_type="text/html")


def make_service(tmp_path: Path, http_client: FakeHttpClient, research: FakeResearchBrain, writer: FakeWriterBrain) -> CampaignService:
    db = Database(tmp_path / "stage37.sqlite")
    db.initialize()
    db.set_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "25",
            "delay_seconds": "0",
            "onboarding_completed": "true",
            "ai_generation_mode": "dual_brain",
            "ai_research_provider": "openai",
            "ai_research_model": "research-test-model",
            "ai_writer_provider": "openai",
            "ai_writer_model": "writer-test-model",
            "ai_max_drafts_per_batch": "25",
            "web_enrichment_enabled": "true",
            "web_enrichment_max_pages": "2",
            "web_enrichment_timeout_seconds": "4",
            "web_enrichment_cache_ttl_days": "7",
            "web_enrichment_respect_robots": "true",
        }
    )
    return CampaignService(
        db,
        mailer=FakeMailer(),
        dual_brain_service=DualBrainService(
            research_factory=lambda _provider, _model: research,
            writer_factory=lambda _provider, _model: writer,
        ),
        enrichment_service=EnrichmentService(
            db,
            WebEnricher(http_client=http_client, max_pages=2, timeout_seconds=4),
        ),
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )


def test_generic_email_domains_are_skipped_without_public_fetch() -> None:
    url, warnings = candidate_website_url({"email": "person@gmail.com"})
    assert url == ""
    assert warnings

    fake_http = FakeHttpClient({})
    result = WebEnricher(http_client=fake_http).enrich({"email": "person@yandex.ru"})

    assert result.status == "skipped"
    assert fake_http.calls == []


def test_web_enricher_fetches_public_home_and_about_page() -> None:
    fake_http = FakeHttpClient(
        {
            "https://example.com/robots.txt": FetchResponse("https://example.com/robots.txt", 404, "", "text/plain"),
            "https://example.com/": html_response(
                "https://example.com/",
                """
                <html><head><title>Example Studio</title>
                <meta name="description" content="Creative advertising studio"></head>
                <body><h1>Example Studio</h1><p>We make media and brand campaigns.</p>
                <a href="/about">About</a></body></html>
                """,
            ),
            "https://example.com/about": html_response(
                "https://example.com/about",
                "<html><body><p>About Example Studio: marketing, media, and content partnerships.</p></body></html>",
            ),
        }
    )

    result = WebEnricher(http_client=fake_http, max_pages=2).enrich({"website": "https://example.com"})

    assert result.status == "success"
    assert "https://example.com/" in result.source_urls
    assert "https://example.com/about" in result.source_urls
    assert result.title == "Example Studio"
    assert "media" in result.public_summary.lower()
    assert result.source_basis == ["website_public_data"]
    assert fake_http.calls.count("https://example.com/robots.txt") == 1


def test_robots_block_is_respected() -> None:
    fake_http = FakeHttpClient(
        {
            "https://blocked.example/robots.txt": FetchResponse(
                "https://blocked.example/robots.txt",
                200,
                "User-agent: *\nDisallow: /",
                "text/plain",
            )
        }
    )

    result = WebEnricher(http_client=fake_http).enrich({"website": "https://blocked.example"})

    assert result.status == "blocked"
    assert "robots.txt запрещает" in " ".join(result.warnings)
    assert "https://blocked.example/" not in fake_http.calls


def test_enrichment_cache_prevents_duplicate_fetches(tmp_path: Path) -> None:
    db = Database(tmp_path / "cache.sqlite")
    db.initialize()
    fake_http = FakeHttpClient(
        {
            "https://cache.example/robots.txt": FetchResponse("https://cache.example/robots.txt", 404, "", "text/plain"),
            "https://cache.example/": html_response("https://cache.example/", "<title>Cached</title><p>Cached website text.</p>"),
        }
    )
    service = EnrichmentService(db, WebEnricher(http_client=fake_http))
    settings = {
        "enabled": True,
        "max_pages": 1,
        "timeout_seconds": 4,
        "cache_ttl_days": 7,
        "respect_robots": True,
    }

    first = service.enrich_contact({"website": "https://cache.example"}, settings=settings)
    calls_after_first = list(fake_http.calls)
    second = service.enrich_contact({"website": "https://cache.example"}, settings=settings)

    assert first.status == "success"
    assert second.status == "success"
    assert fake_http.calls == calls_after_first
    assert "cache" in " ".join(second.warnings).lower()


def test_failed_fetch_returns_warning_without_fake_claims() -> None:
    fake_http = FakeHttpClient(
        {
            "https://down.example/robots.txt": FetchResponse("https://down.example/robots.txt", 404, "", "text/plain"),
            "https://down.example/": RuntimeError("network down"),
        }
    )

    result = WebEnricher(http_client=fake_http).enrich({"website": "https://down.example"})

    assert result.status == "failed"
    assert any("Fetch failed" in warning for warning in result.warnings)
    assert result.public_summary == ""


def test_research_and_writer_prompts_use_enrichment_without_browsing_claims() -> None:
    research_input = RecipientResearchInput(
        contact_id=1,
        email="lead@example.com",
        email_domain="example.com",
        website="https://example.com",
        campaign_topic="Предложить сотрудничество по рекламе",
        enrichment_result={
            "status": "success",
            "source_urls": ["https://example.com/"],
            "public_summary": "Example Studio makes media and brand campaigns.",
            "source_basis": ["website_public_data"],
            "warnings": [],
        },
    )

    research_messages = build_research_messages(research_input)
    assert "website_public_data" in research_messages[0]["content"]
    assert "НЕ браузишь интернет" in research_messages[0]["content"]
    assert "Не утверждай, что ты лично проверил сайт" in research_messages[0]["content"]
    assert "Example Studio makes media" in research_messages[1]["content"]

    brief = RecipientBrief(
        recipient_type="company",
        likely_context="Публичные данные сайта говорят о brand campaigns.",
        positioning_angle="Аккуратно предложить рекламное сотрудничество.",
        source_basis=["row_data", "website_public_data"],
        confidence=0.7,
    )
    writer_messages = build_writer_messages(
        DraftWritingInput(
            contact_id=1,
            email="lead@example.com",
            channel="email",
            campaign_topic="Предложить сотрудничество по рекламе",
            tone="business",
            recipient_brief=brief,
        )
    )

    assert "нельзя писать" in writer_messages[0]["content"]
    assert "я изучил ваш сайт" in writer_messages[0]["content"]
    assert "website_public_data" in writer_messages[1]["content"]


def test_dual_brain_flow_enriches_before_research_and_stays_pending_review(tmp_path: Path) -> None:
    fake_http = FakeHttpClient(
        {
            "https://example.com/robots.txt": FetchResponse("https://example.com/robots.txt", 404, "", "text/plain"),
            "https://example.com/": html_response(
                "https://example.com/",
                "<title>Example Studio</title><p>Media partnerships and advertising campaigns.</p>",
            ),
        }
    )
    research = FakeResearchBrain()
    writer = FakeWriterBrain()
    service = make_service(tmp_path, fake_http, research, writer)
    service.save_ai_brain_settings("research", provider="openai", model="research-test-model", api_key="research-key")
    service.save_ai_brain_settings("writer", provider="openai", model="writer-test-model", api_key="writer-key")
    campaign_id = service.default_campaign_id()
    contact_id = service.db.add_contact(
        {
            "campaign_id": campaign_id,
            "channel": "email",
            "email": "lead@example.com",
            "name": "Анна",
            "company": "Example Studio",
            "website": "https://example.com",
            "topic": "интересуются рекламными интеграциями",
            "status": "new",
        }
    )

    result = service.enqueue_ai_generate_drafts(
        campaign_id,
        contact_ids=[contact_id],
        campaign_topic="Предложить сотрудничество по рекламе",
        tone="business",
        channel="email",
    )
    processed = QueueJobProcessor(service).process_available()
    contact = service.db.get_contact(contact_id)

    assert result.ok
    assert processed == 1
    assert research.inputs
    assert research.inputs[0].enrichment_result is not None
    assert research.inputs[0].enrichment_result["status"] == "success"
    assert contact["enrichment_status"] == "success"
    assert contact["status"] == "pending_review"
    assert contact["ai_generated"] == 1
    assert contact["sent_at"] is None
    assert service.mailer.sent == []


def test_stage_3_7_ui_controls_exist(qapp: QApplication, tmp_path: Path) -> None:
    db = Database(tmp_path / "ui.sqlite")
    db.initialize()
    service = CampaignService(db, mailer=FakeMailer(), sleep_fn=lambda _: None, export_dir=tmp_path / "exports")
    window = MainWindow(service)
    try:
        assert window.campaign_view.web_enrichment_checkbox.text() == "Обогатить данные из сайта"
        assert window.campaign_view.enrich_contacts_button.text() == "Проверить данные получателей"
        assert "campaign.enrich_contacts" in window.campaign_view.action_map
        assert window.settings_view.web_enrichment_max_contacts.maximum() == 500
        assert window.settings_view.web_enrichment_max_pages.maximum() == 3
        assert window.settings_view.web_enrichment_respect_robots.text() == "Уважать robots.txt"
    finally:
        window.campaign_view.shutdown()
        window.settings_view.shutdown()
        window.close()
