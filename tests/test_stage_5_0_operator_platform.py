from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from scripts.perf_benchmark import run_benchmark
from src.campaign_service import CampaignService
from src.db import Database
from src.gui.main_window import MainWindow
from src.gui.operator_platform import CommandPaletteDialog
from src.operator import HIGH_VOLUME_MODE, ReviewQueueFilters
from src.performance import CacheManager, preload_window, recommended_batch_size, virtual_page


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
    db = Database(tmp_path / "stage50.sqlite")
    db.initialize()
    db.set_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "delay_seconds": "0",
            "onboarding_completed": "true",
            "operator_mode": "high_volume",
            "execution_mode_instagram": "manual_assist",
            "execution_mode_tiktok": "manual_assist",
            "execution_mode_x": "manual_assist",
            "execution_mode_vk": "manual_assist",
        }
    )
    return CampaignService(db, mailer=FakeMailer(), sleep_fn=lambda _: None, export_dir=tmp_path / "exports")


def sample_rows(count: int = 120) -> list[dict[str, object]]:
    channels = ["email", "telegram", "instagram", "x", "tiktok", "vk"]
    rows: list[dict[str, object]] = []
    for index in range(count):
        channel = channels[index % len(channels)]
        rows.append(
            {
                "channel": channel,
                "email": f"stage50-{index:04d}@example.invalid" if channel == "email" else "",
                "handle": f"stage50_{channel}_{index:04d}" if channel != "email" else "",
                "external_id": f"stage50-chat-{index:04d}" if channel == "telegram" else "",
                "profile_url": f"https://example.com/{channel}/stage50-{index:04d}" if channel not in {"email", "telegram"} else "",
                "name": f"Stage50 Lead {index}",
                "company": f"Stage50 Company {index % 12}",
                "topic": "operator platform QA",
                "generated_message": "Stage 5.0 synthetic operator draft. Manual/human workflow only.",
                "status": "pending_review" if index % 3 else "approved",
            }
        )
    return rows


def test_performance_primitives_are_conservative() -> None:
    cache = CacheManager(default_ttl_seconds=30, max_items=2)
    cache.set("a", {"value": 1})
    cache.set("b", {"value": 2})
    cache.set("c", {"value": 3})

    assert cache.get("a") is None
    assert cache.get("c") == {"value": 3}
    assert virtual_page(25_000, offset=24_900, limit=500).pages == 50
    assert recommended_batch_size(25_000).virtualized is True
    assert preload_window(25_000, 500, page_size=250, radius=1) == [(250, 250), (500, 250), (750, 250)]


def test_massive_import_contacts_page_and_export(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    result = service.massive_import_rows(campaign_id, sample_rows(600), chunk_size=125, source="stage50")

    assert result["imported_count"] == 600
    assert result["chunks"] == 5
    page = service.contacts_page(campaign_id, offset=250, limit=100)
    assert page["page"]["total"] == 600
    assert len(page["items"]) == 100
    assert page["render_budget"]["virtualized"] is False

    export = service.export_operator_data(campaign_id, kind="leads", format="csv")
    assert Path(str(export["path"])).exists()
    assert export["autosend"] is False
    assert service.mailer.sent == []


def test_command_palette_and_session_state_are_safe(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.massive_import_rows(campaign_id, sample_rows(40), source="stage50")

    items = service.command_palette_items("Stage50 Company", campaign_id=campaign_id)
    assert items
    assert any(str(item["id"]).startswith("search:") for item in items)
    assert any(item["id"] == "action:start_session" for item in service.command_palette_items("", campaign_id=campaign_id))

    result = service.execute_command_palette_item("action:start_session", campaign_id=campaign_id)
    assert result["autosend"] is False
    assert result["snapshot"]["total"] == 40

    service.save_operator_ui_state(current_page_index=8, current_lead_id=123, scroll_position=450)
    restored = CampaignService(service.db, mailer=FakeMailer(), sleep_fn=lambda _: None, export_dir=tmp_path / "exports2")
    assert restored.restore_operator_ui_state()["current_lead_id"] == 123
    assert restored.restore_operator_ui_state()["scroll_position"] == 450
    assert restored.mailer.sent == []


def test_notification_center_task_monitor_and_analytics(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.massive_import_rows(campaign_id, sample_rows(12), source="stage50")
    contact_id = int(service.contacts(campaign_id)[0]["id"])
    session = service.start_outreach_session(campaign_id, mode=HIGH_VOLUME_MODE)
    session_id = int(session["session"]["id"])

    service.operator_copy_message(session_id, contact_id)
    service.operator_mark_manually_sent(session_id, contact_id)
    service.add_reply(contact_id, "Interested, please send details", reply_status="interested")
    service.schedule_followup(contact_id, days_from_now=2, note="Stage 5 follow-up")
    failed = service.queue.enqueue_job("ai_generate_draft", campaign_id=campaign_id, contact_id=contact_id, status="failed")
    service.db.execute("UPDATE job_queue SET last_error = ? WHERE id = ?", ("Stage 5 fake failure", failed.job_id))
    service.update_contact(contact_id, {"ai_warnings": "Low data warning"})

    notifications = service.notification_center(campaign_id)
    assert {row["type"] for row in notifications} >= {"reply", "follow_up", "queue_failure", "ai_warning"}
    monitor = service.background_task_monitor(campaign_id)
    assert monitor["queue_health"] == "Needs attention"
    assert monitor["by_status"]["failed"] == 1
    analytics = service.operator_analytics_summary(campaign_id)
    assert analytics["copied"] >= 1
    assert analytics["manually_sent"] >= 1


def test_main_window_command_palette_quick_review_and_new_panels(qapp: QApplication, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.massive_import_rows(campaign_id, sample_rows(60), source="stage50")
    window = MainWindow(service)
    window.show()
    qapp.processEvents()

    try:
        assert window.command_palette_shortcut.objectName() == "commandPaletteShortcut"
        labels = "\n".join(button.text() for button in window.intelligence_sidebar_buttons)
        assert "Уведомления" in labels
        assert "Задачи" in labels
        assert "Performance" in labels

        palette = CommandPaletteDialog(service, campaign_id, window)
        palette.input.setText("Stage50")
        qapp.processEvents()
        assert palette.table.rowCount() >= 1
        palette.table.selectRow(0)
        palette.run_selected()
        assert palette.result is not None
        assert palette.result.get("autosend") is False
        palette.close()

        session = window.outreach_session_view
        session.start_session()
        qapp.processEvents()
        assert session.quick_review_toggle.objectName() == "quickReviewModeToggle"
        session.quick_review_toggle.setChecked(True)
        qapp.processEvents()
        assert not session.filters_widget.isVisible()
        session.quick_review_toggle.setChecked(False)
        assert "J" in session.hotkey_shortcuts
        assert "K" in session.hotkey_shortcuts
        assert "E" in session.hotkey_shortcuts
        session.draft_editor.setFocus()
        current_contact = session.current_contact_id
        QTest.keyClick(session.draft_editor, Qt.Key.Key_J)
        qapp.processEvents()
        assert session.current_contact_id == current_contact
        session.draft_editor.clearFocus()
        QTest.keyClick(session, Qt.Key.Key_J)
        qapp.processEvents()
        assert session.current_contact_id != current_contact

        window.notification_center_view.refresh()
        assert window.notification_center_view.table.objectName() == "notificationCenterTable"
        window.background_task_monitor_view.refresh()
        assert window.background_task_monitor_view.table.objectName() == "taskMonitorTable"
        window.performance_platform_view.refresh()
        assert window.performance_platform_view.table.objectName() == "performanceSnapshotTable"
    finally:
        window.campaign_view.shutdown()
        window.settings_view.shutdown()
        window.close()


def test_search_cache_queue_recovery_and_no_autosend(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.massive_import_rows(campaign_id, sample_rows(80), source="stage50")

    first = service.global_search("Stage50 Company", campaign_id=campaign_id)
    second = service.global_search("Stage50 Company", campaign_id=campaign_id)
    assert first == second
    assert service.cache.stats()["items"] >= 1
    page = service.operator_review_queue_page(campaign_id, ReviewQueueFilters(manual_assist=True), offset=0, limit=20)
    assert page["page"]["limit"] == 20
    assert page["items"]

    service.queue.enqueue_job("ai_generate_draft", campaign_id=campaign_id, status="running")
    recovered = CampaignService(service.db, mailer=FakeMailer(), sleep_fn=lambda _: None, export_dir=tmp_path / "exports3")
    monitor = recovered.background_task_monitor(campaign_id)
    assert monitor["by_status"].get("queued", 0) >= 1
    assert service.mailer.sent == []
    assert recovered.mailer.sent == []


def test_perf_benchmark_reports_stage_5_operations(tmp_path: Path) -> None:
    rows = run_benchmark(count=200, db_path=str(tmp_path / "stage50_perf.sqlite"), reset=True)
    metrics = {str(row["operation"]): row for row in rows}

    expected = {"app startup", "massive import", "lead switching", "ai render", "inbox open", "search", "filter", "session restore", "queue latency", "contacts page"}
    assert expected <= set(metrics)
    assert float(metrics["lead switching"]["average_ms"]) < 150
    assert float(metrics["search"]["average_ms"]) < 300
    assert float(metrics["contacts page"]["average_ms"]) < 300
