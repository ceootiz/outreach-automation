from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from PySide6.QtWidgets import QApplication

from scripts.social_operator_benchmark import run_benchmark
from src.campaign_service import CampaignService
from src.channels.connectors import API_PENDING, FUTURE_SUPPORT, MANUAL_ASSIST_STATE
from src.channels.profile_urls import PROFILE_NOT_FOUND, profile_url_for
from src.db import Database
from src.gui.main_window import MainWindow


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
    db = Database(tmp_path / "stage49.sqlite")
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


def add_lead(service: CampaignService, campaign_id: int, channel: str, index: int = 1) -> int:
    handle = f"stage49_{channel}_{index:03d}"
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
                "email": f"{channel}-{index}@channel.local",
                "handle": handle,
                "profile_url": urls[channel],
                "name": "Stage 4.9 Lead",
                "company": "Creator QA Studio",
                "topic": "safe social outreach",
                "social_profile": urls[channel],
                "generated_message": "Привет! Короткий manual-assist черновик без скрытой отправки.",
                "status": "approved",
            }
        ],
        source="stage49",
    )
    assert result.imported_count == 1, result.errors
    contact_id = int(service.contacts(campaign_id)[0]["id"])
    service.db.update_contact(
        contact_id,
        {
            "ai_generated": 1,
            "ai_confidence": 0.82,
            "research_brief_json": '{"recipient_type":"creator","source_basis":["row_data"]}',
            "lead_status": "Warm",
        },
    )
    return contact_id


def test_connector_slots_expose_human_connection_states(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    slots = {slot["channel_id"]: slot for slot in service.connector_slots()}

    assert set(slots) == {"email", "telegram", "instagram", "tiktok", "x", "vk", "whatsapp", "viber"}
    assert slots["instagram"]["connection_state"] == MANUAL_ASSIST_STATE
    assert slots["tiktok"]["connection_state"] == MANUAL_ASSIST_STATE
    assert slots["x"]["connection_state"] == API_PENDING
    assert slots["vk"]["connection_state"] == API_PENDING
    assert slots["whatsapp"]["connection_state"] == FUTURE_SUPPORT
    assert "Помощник" in " ".join(slots["instagram"]["recommended_workflow"])
    assert slots["instagram"]["credential_state"] == "No credentials required for Manual Assist"


def test_profile_url_engine_constructs_safe_social_urls() -> None:
    assert profile_url_for("instagram", handle="@creator").url == "https://www.instagram.com/creator/"
    assert profile_url_for("tiktok", handle="creator").url == "https://www.tiktok.com/@creator"
    assert profile_url_for("x", handle="creator").url == "https://x.com/creator"
    assert profile_url_for("vk", external_id="12345").url == "https://vk.com/id12345"
    missing = profile_url_for("instagram")
    assert missing.display_text == PROFILE_NOT_FOUND
    assert not missing.ok


@pytest.mark.parametrize("channel", SOCIAL_CHANNELS)
def test_channel_cockpit_manual_assist_flow_and_exports(tmp_path: Path, channel: str) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_lead(service, campaign_id, channel)

    snapshot = service.channel_cockpit_snapshot(campaign_id, channel)
    action = snapshot["manual_action"]
    assert snapshot["slot"]["connection_state"] in {MANUAL_ASSIST_STATE, API_PENDING}
    assert action["profile_url"].startswith("https://")
    assert action["copy_text"]
    assert snapshot["autosend"] is False

    count = service.mark_manual_assist_sent([contact_id])
    csv_export = service.export_channel_session(campaign_id, channel, format="csv")
    json_export = service.export_channel_session(campaign_id, channel, format="json")

    assert count == 1
    assert Path(csv_export["path"]).exists()
    assert Path(json_export["path"]).exists()
    assert csv_export["clipboard_summary"].endswith("autosend off")
    assert service.mailer.sent == []
    assert service.db.fetch_one("SELECT * FROM job_queue WHERE contact_id = ?", (contact_id,)) is None


def test_smart_channel_recommendations_are_advisory_only(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    instagram_id = add_lead(service, campaign_id, "instagram")
    recommendation = service.recommend_channel_for_contact(instagram_id)

    assert recommendation["channel_id"] == "instagram"
    assert recommendation["execution_mode"] == "manual_assist"
    assert recommendation["autosend"] is False


def test_global_search_recent_and_fuzzy_history(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_lead(service, campaign_id, "vk")
    service.add_reply(contact_id, "Stage49 fuzzy reply marker", reply_status="maybe_later")
    service.schedule_followup(contact_id, days_from_now=3, note="Stage49 followup marker")

    results = service.global_search("Stage49 marker", campaign_id=campaign_id, limit=20)
    assert {row["result_type"] for row in results} & {"reply", "followup"}
    assert service.recent_searches()[0] == "Stage49 marker"


def test_social_benchmark_includes_cockpit_and_fast_actions(tmp_path: Path) -> None:
    rows = run_benchmark(per_channel=25, db_path=str(tmp_path / "stage49_benchmark.sqlite"), reset=True)
    metrics = {str(row["operation"]): row for row in rows}

    assert "open cockpit" in metrics
    assert float(metrics["open cockpit"]["average_ms"]) < 150
    assert float(metrics["copy message"]["average_ms"]) < 100
    assert float(metrics["mark sent"]["average_ms"]) < 250


def test_focus_mode_and_channel_cockpit_ui_are_clickable(qapp: QApplication, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    for channel in SOCIAL_CHANNELS:
        add_lead(service, campaign_id, channel)
    window = MainWindow(service)
    window.show()
    qapp.processEvents()

    try:
        window.set_active_campaign_id(campaign_id)
        session = window.outreach_session_view
        session.start_session()
        qapp.processEvents()
        assert session.focus_mode_toggle.objectName() == "sessionFocusModeToggle"
        session.focus_mode_toggle.setChecked(True)
        qapp.processEvents()
        assert not session.filters_widget.isVisible()
        session.focus_mode_toggle.setChecked(False)
        qapp.processEvents()
        assert session.tiktok_filter.objectName() == "sessionTikTokOnly"
        assert session.x_filter.objectName() == "sessionXOnly"
        assert session.vk_filter.objectName() == "sessionVKOnly"

        cockpit = window.channel_cockpit_view
        assert cockpit.channel_selector.count() >= 8
        for channel in SOCIAL_CHANNELS:
            cockpit.channel_selector.setCurrentIndex(cockpit.channel_selector.findData(channel))
            cockpit.refresh()
            assert cockpit.workflow_table.rowCount() >= 3
            assert cockpit.copy_button.isEnabled()
            assert cockpit.export_csv_button.isEnabled()
        search = window.global_search_view
        search.search_input.setText("Creator QA")
        search.run_search()
        assert search.results_table.rowCount() >= 1
        assert search.recent_selector.count() >= 2
    finally:
        window.campaign_view.shutdown()
        window.settings_view.shutdown()
        window.close()
