from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from PySide6.QtWidgets import QApplication

from scripts.generate_social_qa_data import generate_social_qa_data
from scripts.social_operator_benchmark import run_benchmark
from src.ai.prompt_builder import build_email_draft_messages
from src.ai.result_schema import EmailDraftInput
from src.ai.writer_brain import build_writer_messages
from src.ai.writer_schema import DraftWritingInput
from src.campaign_service import CampaignService
from src.channels.readiness import list_channel_readiness
from src.db import Database
from src.gui.main_window import MainWindow
from src.ai.research_schema import RecipientBrief


SOCIAL_CHANNELS = ("instagram", "tiktok", "x", "vk")


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
    db = Database(tmp_path / "stage48.sqlite")
    db.initialize()
    db.set_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "delay_seconds": "0",
            "onboarding_completed": "true",
            "execution_mode_instagram": "manual_assist",
            "execution_mode_tiktok": "manual_assist",
            "execution_mode_x": "manual_assist",
            "execution_mode_vk": "manual_assist",
        }
    )
    return CampaignService(db, mailer=FakeMailer(), sleep_fn=lambda _: None, export_dir=tmp_path / "exports")


def add_social_lead(service: CampaignService, campaign_id: int, channel: str, index: int = 1) -> int:
    handle = f"qa_{channel}_{index:03d}"
    urls = {
        "instagram": f"https://www.instagram.com/{handle}/",
        "tiktok": f"https://www.tiktok.com/@{handle}",
        "x": f"https://x.com/{handle}",
        "vk": f"https://vk.com/{handle}",
    }
    result = service.add_contact_rows(
        campaign_id,
        [
            {
                "channel": channel,
                "handle": handle,
                "profile_url": urls[channel],
                "name": "Creator",
                "company": "QA Studio",
                "topic": "safe social outreach",
                "website": "https://example.com",
                "social_profile": urls[channel],
                "generated_message": "Привет! Короткий safe Manual Assist текст.",
                "status": "approved",
            }
        ],
        source="stage48",
    )
    assert result.imported_count == 1, result.errors
    contact = service.contacts(campaign_id)[0]
    service.db.update_contact(
        int(contact["id"]),
        {
            "status": "approved",
            "ai_generated": 1,
            "ai_confidence": 0.78,
            "research_brief_json": '{"recipient_type":"creator","source_basis":["row_data"]}',
            "enrichment_status": "success",
            "lead_status": "Warm",
        },
    )
    return int(contact["id"])


def test_channel_readiness_matrix_includes_active_and_future_channels() -> None:
    rows = list_channel_readiness(has_email_profile=False, has_telegram_token=False, has_telegram_chat_id=False)
    by_channel = {row.channel_id: row for row in rows}

    assert set(by_channel) == {"email", "telegram", "instagram", "tiktok", "x", "vk", "whatsapp", "viber"}
    assert by_channel["email"].current_status == "Full-ready, credentials pending"
    assert by_channel["telegram"].current_status == "Full-ready, live credentials pending"
    assert by_channel["instagram"].current_status == "Manual Assist Full"
    assert by_channel["tiktok"].manual_assist_readiness == "full"
    assert by_channel["whatsapp"].current_status == "Future slot"


@pytest.mark.parametrize("channel", SOCIAL_CHANNELS)
def test_social_manual_assist_full_flow_has_no_autosend(tmp_path: Path, channel: str) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_social_lead(service, campaign_id, channel)

    action = service.prepare_manual_assist(contact_id)
    copied = service.operator_copy_message(
        int(service.start_outreach_session(campaign_id)["session"]["id"]),
        contact_id,
    )
    count = service.mark_manual_assist_sent([contact_id])

    assert action.channel == channel
    assert action.profile_url.startswith("https://")
    assert action.copy_text
    assert copied
    assert count == 1
    assert service.db.get_contact(contact_id)["status"] == "sent"
    assert service.mailer.sent == []
    assert service.db.fetch_one("SELECT * FROM job_queue WHERE contact_id = ?", (contact_id,)) is None
    log = service.db.fetch_one("SELECT * FROM send_logs WHERE contact_id = ? AND action = 'manual_assist_mark_sent'", (contact_id,))
    assert log is not None
    assert log["channel"] == channel


def test_global_search_covers_social_history(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_social_lead(service, campaign_id, "instagram")
    service.add_reply(contact_id, "QA reply searchable marker from social history.", reply_status="maybe_later")
    service.schedule_followup(contact_id, days_from_now=4, note="QA follow-up searchable marker")
    service.prepare_manual_assist(contact_id)
    service.db.execute(
        """
        INSERT INTO ai_metrics (contact_id, campaign_id, warnings, confidence, personalization_quality)
        VALUES (?, ?, ?, 0.8, 'medium')
        """,
        (contact_id, campaign_id, "QA AI warning searchable marker"),
    )

    results = service.global_search("searchable marker", campaign_id=campaign_id, limit=30)
    result_types = {row["result_type"] for row in results}

    assert {"reply", "followup", "ai_metric"} <= result_types
    assert any(row["channel"] == "instagram" for row in results)
    assert service.operator_global_search(campaign_id, "QA Studio")


def test_social_qa_data_and_benchmark_are_safe(tmp_path: Path) -> None:
    db_path = tmp_path / "social.sqlite"
    result = generate_social_qa_data(per_channel=25, reset=True, db_path=str(db_path))
    db = Database(db_path)
    db.initialize()
    service = CampaignService(db, mailer=FakeMailer(), sleep_fn=lambda _: None, export_dir=tmp_path / "exports")
    contacts = service.contacts(int(result["campaign_id"]))

    assert result["count"] == 100
    assert {contact["channel"] for contact in contacts} == set(SOCIAL_CHANNELS)
    assert all(contact["email"].endswith("@channel.local") for contact in contacts)

    rows = run_benchmark(per_channel=25, db_path=str(tmp_path / "social_benchmark.sqlite"), reset=True)
    metrics = {str(row["operation"]): row for row in rows}

    assert float(metrics["next lead"]["average_ms"]) < 150
    assert float(metrics["copy message"]["average_ms"]) < 100
    assert float(metrics["mark sent"]["average_ms"]) < 250
    assert float(metrics["search"]["average_ms"]) < 300


def test_social_ai_prompt_rules_block_fake_familiarity() -> None:
    simple_messages = build_email_draft_messages(
        EmailDraftInput(
            contact_id=None,
            email="",
            name="Creator",
            company="",
            website="https://example.com",
            social_profile="https://www.instagram.com/qa_creator/",
            note="No profile content was fetched.",
            campaign_topic="Предложить сотрудничество по рекламе",
            tone="friendly",
            channel="instagram",
            execution_mode="manual_assist",
        )
    )
    brief = RecipientBrief(
        recipient_type="creator",
        likely_context="Данных мало.",
        positioning_angle="Аккуратно предложить формат сотрудничества.",
        message_hooks=["бережный первый контакт"],
        do_not_claim=["Не утверждать, что профиль изучен"],
        personalization_strength="low",
        confidence=0.35,
        warnings=["Недостаточно данных для персонализации"],
        source_basis=["row_data"],
    )
    writer_messages = build_writer_messages(
        DraftWritingInput(
            contact_id=None,
            campaign_topic="Предложить сотрудничество по рекламе",
            channel="tiktok",
            tone="friendly",
            email="",
            name="Creator",
            company="",
            website="",
            social_profile="https://www.tiktok.com/@qa_creator",
            note="",
            recipient_brief=brief,
            execution_mode="manual_assist",
        )
    )
    prompt_text = "\n".join(message["content"] for message in [*simple_messages, *writer_messages])

    assert "Subject должен быть пустой строкой" in prompt_text
    assert "без fake familiarity" in prompt_text
    assert "friendly but not cringe" in prompt_text
    assert "я изучил ваш профиль" in prompt_text
    assert "AI creates drafts only" in prompt_text or "Ты пишешь только черновик" in prompt_text


def test_ui_exposes_readiness_search_and_social_operator_flow(qapp: QApplication, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    add_social_lead(service, campaign_id, "instagram")
    window = MainWindow(service)
    window.show()
    qapp.processEvents()

    try:
        labels = "\n".join(button.text() for button in window.intelligence_sidebar_buttons)
        assert "Готовность каналов" in labels
        assert "Поиск" in labels
        assert window.channel_readiness_view.table.rowCount() >= 8

        window.global_search_view.search_input.setText("QA Studio")
        window.global_search_view.run_search()
        assert window.global_search_view.results_table.rowCount() >= 1

        session = window.outreach_session_view
        session.manual_assist_filter.setChecked(True)
        session.start_session()
        qapp.processEvents()
        assert session.current_session_id is not None
        assert session.copy_button.isEnabled()
        assert session.open_profile_button.isEnabled()
        assert session.mark_sent_button.isEnabled()
    finally:
        window.campaign_view.shutdown()
        window.settings_view.shutdown()
        window.close()
