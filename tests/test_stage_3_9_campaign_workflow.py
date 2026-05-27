from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from PySide6.QtWidgets import QApplication, QMessageBox

from src.campaign_service import CampaignService
from src.channels.execution import DRY_RUN, MANUAL_ASSIST
from src.db import Database
from src.gui.intelligence_views import NewCampaignWizard
from src.gui.main_window import MainWindow
from src.presets import get_preset, load_presets


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
    monkeypatch.setenv("OPENAI_RESEARCH_API_KEY", "")
    monkeypatch.setenv("OPENAI_WRITER_API_KEY", "")


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def make_service(tmp_path: Path) -> CampaignService:
    db = Database(tmp_path / "stage39.sqlite")
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


def add_contact(service: CampaignService, campaign_id: int, email: str = "lead@example.com", status: str = "new") -> int:
    result = service.add_contact_rows(
        campaign_id,
        [
            {
                "email": email,
                "subject": "Hello",
                "generated_message": "Здравствуйте! Тестовый текст.",
                "status": status,
            }
        ],
        source="stage39",
    )
    assert result.imported_count == 1, result.errors
    row = service.db.fetch_one("SELECT * FROM contacts WHERE campaign_id = ? AND email = ?", (campaign_id, email))
    assert row is not None
    if status != row["status"]:
        service.db.update_contact(int(row["id"]), {"status": status})
    return int(row["id"])


def test_preset_registry_contains_operator_workflows() -> None:
    presets = {preset.preset_id: preset for preset in load_presets()}

    assert set(presets) == {
        "b2b_email_outreach",
        "influencer_collaboration",
        "telegram_outreach",
        "partnership_intro",
        "affiliate_proposal",
    }
    assert presets["b2b_email_outreach"].recommended_channel == "email"
    assert presets["influencer_collaboration"].recommended_execution_mode == MANUAL_ASSIST
    assert "Manual Assist" in " ".join(presets["influencer_collaboration"].warnings)
    assert get_preset("telegram_outreach").recommended_channel == "telegram"


def test_apply_preset_sets_safe_defaults_without_autosend(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()

    result = service.apply_campaign_preset("influencer_collaboration", campaign_id=campaign_id)
    settings = service.settings()

    assert result["autosend"] is False
    assert settings["active_channel"] == "instagram"
    assert service.execution_mode("instagram") == MANUAL_ASSIST
    assert settings["work_mode"] == "ai_assist"
    assert settings["send_mode"] == "dry_run"
    assert settings["ai_tone"] == "friendly"
    assert service.mailer.sent == []


def test_campaign_validation_and_health_score(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()

    validation = service.campaign_validation(campaign_id, preset_id="b2b_email_outreach")
    assert any(check["id"] == "recipients" and check["status"] == "error" for check in validation["checks"])
    assert service.campaign_health(campaign_id)["score"] < 80

    add_contact(service, campaign_id)
    improved = service.campaign_validation(campaign_id, preset_id="b2b_email_outreach")
    assert any(check["id"] == "recipients" and check["status"] == "ok" for check in improved["checks"])
    assert service.campaign_health(campaign_id)["label"] in {"Needs attention", "Healthy"}


def test_smart_warnings_cover_channel_and_bulk_safety(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.apply_campaign_preset("influencer_collaboration", campaign_id=campaign_id)
    service.set_execution_mode("instagram", DRY_RUN)

    warnings = service.smart_warnings(campaign_id, channel="instagram", execution_mode=DRY_RUN)

    assert any("Manual Assist" in warning for warning in warnings)

    service.save_settings({"active_channel": "email", "send_mode": "live"})
    for index in range(26):
        add_contact(service, campaign_id, email=f"bulk-{index}@example.com", status="approved")

    bulk_warnings = service.smart_warnings(campaign_id, channel="email", send_mode="live")

    assert any("без dry-run" in warning for warning in bulk_warnings)


def test_quick_start_creates_safe_campaign_without_queue_or_send(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    result = service.quick_start_campaign("quick_telegram_campaign")
    campaign_id = int(result["campaign_id"])

    assert result["autosend"] is False
    assert service.settings()["active_channel"] == "telegram"
    assert service.settings()["send_mode"] == "dry_run"
    assert service.db.fetch_one("SELECT * FROM job_queue WHERE campaign_id = ?", (campaign_id,)) is None
    assert service.mailer.sent == []


def test_archive_and_duplicate_campaign_are_review_safe(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    add_contact(service, campaign_id, status="approved")

    duplicate_id = service.duplicate_campaign(campaign_id)
    duplicate_contacts = service.contacts(duplicate_id)

    assert duplicate_id != campaign_id
    assert len(duplicate_contacts) == 1
    assert duplicate_contacts[0]["status"] == "new"
    assert service.mailer.sent == []

    service.archive_campaign(campaign_id)
    archived = service.db.fetch_one("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    assert archived is not None
    assert archived["status"] == "archived"


def test_operator_dashboard_and_wizard_widgets_exist(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(tmp_path)
    window = MainWindow(service)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    try:
        dashboard = window.campaign_dashboard_view
        dashboard.refresh()

        assert dashboard.preset_selector.count() >= 5
        assert dashboard.new_campaign_button.isEnabled()
        assert dashboard.quick_email_button.isEnabled()
        assert dashboard.quick_telegram_button.isEnabled()
        assert dashboard.quick_ai_button.isEnabled()
        assert dashboard.validation_table.objectName() == "campaignValidationTable"
        assert dashboard.health_badge.objectName() == "campaignHealthBadge"
        assert dashboard.operator_cards["risk_alerts"].objectName() == "operatorDashboard_risk_alerts"

        wizard = NewCampaignWizard(service)
        try:
            assert wizard.preset_selector.objectName() == "wizardPresetSelector"
            assert wizard.channel_selector.count() >= 6
            assert wizard.execution_selector.count() >= 1
            wizard.next_step()
            assert wizard.step_index == 1
            wizard.previous_step()
            assert wizard.step_index == 0
            wizard.create_campaign()
            assert wizard.created_campaign_id is not None
        finally:
            wizard.close()
    finally:
        window.campaign_view.shutdown()
        window.settings_view.shutdown()
        window.close()
