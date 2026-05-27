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

from scripts.generate_operator_qa_data import generate_operator_qa_data
from scripts.operator_throughput_benchmark import run_benchmark
from src.campaign_service import CampaignService
from src.db import Database
from src.gui.main_window import MainWindow
from src.operator import HIGH_VOLUME_MODE, ReviewQueueFilters


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


def make_service(db_path: Path, tmp_path: Path) -> CampaignService:
    db = Database(db_path)
    db.initialize()
    db.set_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "delay_seconds": "0",
            "onboarding_completed": "true",
            "active_channel": "instagram",
            "execution_mode_instagram": "manual_assist",
            "operator_mode": "high_volume",
        }
    )
    return CampaignService(db, mailer=FakeMailer(), sleep_fn=lambda _: None, export_dir=tmp_path / "exports")


def generate_service(tmp_path: Path, count: int = 100) -> tuple[CampaignService, int]:
    db_path = tmp_path / "stage47.sqlite"
    result = generate_operator_qa_data(count=count, reset=True, db_path=str(db_path))
    service = make_service(db_path, tmp_path)
    return service, int(result["campaign_id"])


def test_qa_data_generation_creates_100_safe_demo_leads(tmp_path: Path) -> None:
    service, campaign_id = generate_service(tmp_path, count=100)
    contacts = service.contacts(campaign_id)

    assert len(contacts) == 100
    assert {contact["channel"] for contact in contacts} == {"email", "telegram", "instagram", "x", "tiktok", "vk"}
    assert all("example.invalid" in contact["email"] or contact["email"].endswith("@channel.local") for contact in contacts)
    assert all(contact["ai_notes"] == "QA/demo dataset. No real recipient." for contact in contacts)
    assert service.mailer.sent == []


def test_100_lead_session_load_batching_and_quick_filters(tmp_path: Path) -> None:
    service, campaign_id = generate_service(tmp_path, count=100)
    snapshot = service.start_outreach_session(campaign_id, mode=HIGH_VOLUME_MODE)

    assert snapshot["total"] == 100
    assert snapshot["autosend"] is False

    ai_sorted = service.operator_review_queue(campaign_id, ReviewQueueFilters(order_by="ai_confidence"))
    assert float(ai_sorted[0]["contact"]["ai_confidence"] or 0) >= float(ai_sorted[-1]["contact"]["ai_confidence"] or 0)

    manual = service.operator_review_queue(campaign_id, ReviewQueueFilters(manual_assist=True))
    assert manual
    assert all(item["contact"]["channel"] in {"instagram", "x", "tiktok", "vk"} for item in manual)

    needs_review = service.operator_review_queue(campaign_id, ReviewQueueFilters(needs_review=True))
    assert needs_review
    assert all(item["contact"]["status"] == "pending_review" for item in needs_review)

    low_confidence = service.operator_review_queue(campaign_id, ReviewQueueFilters(low_confidence=True))
    assert low_confidence
    assert all(float(item["contact"]["ai_confidence"] or 0) < 0.45 for item in low_confidence)


def test_hotkeys_do_not_fire_while_editing_and_space_advances(qapp: QApplication, tmp_path: Path) -> None:
    service, campaign_id = generate_service(tmp_path, count=100)
    window = MainWindow(service)
    window.show()
    qapp.processEvents()

    try:
        window.set_active_campaign_id(campaign_id)
        session = window.outreach_session_view
        session.start_session()
        qapp.processEvents()
        first_contact = session.current_contact_id

        session.draft_editor.setFocus()
        QTest.keyClick(session.draft_editor, Qt.Key.Key_N)
        qapp.processEvents()
        assert session.current_contact_id == first_contact
        assert "n" in session.draft_editor.toPlainText().lower()

        session.draft_editor.clearFocus()
        QTest.keyClick(session, Qt.Key.Key_Space)
        qapp.processEvents()
        assert session.current_contact_id != first_contact
    finally:
        window.campaign_view.shutdown()
        window.settings_view.shutdown()
        window.close()


def test_copy_mark_sent_variant_and_session_recovery(tmp_path: Path) -> None:
    service, campaign_id = generate_service(tmp_path, count=100)
    snapshot = service.start_outreach_session(campaign_id, mode=HIGH_VOLUME_MODE)
    session_id = int(snapshot["session"]["id"])
    contact_id = int(snapshot["current"]["contact"]["id"])

    variant_text = service.operator_select_variant(session_id, contact_id, "friendly")
    service.operator_save_draft_state(session_id, contact_id, variant_text + " Recovery note.")
    restored_before_send = CampaignService(service.db, mailer=FakeMailer(), sleep_fn=lambda _: None, export_dir=tmp_path / "exports2")
    restored_before_snapshot = restored_before_send.restore_outreach_session(campaign_id)
    assert restored_before_snapshot is not None
    assert restored_before_snapshot["session"]["draft_variant"] == "friendly"
    assert "Recovery note" in restored_before_snapshot["session"]["unsaved_draft"]

    copied = service.operator_copy_message(session_id, contact_id)
    next_snapshot = service.operator_mark_manually_sent(session_id, contact_id)

    assert "Recovery note" in copied
    assert next_snapshot["autosend"] is False
    assert service.mailer.sent == []
    assert service.db.get_contact(contact_id)["status"] == "sent"

    restored = CampaignService(service.db, mailer=FakeMailer(), sleep_fn=lambda _: None, export_dir=tmp_path / "exports2")
    restored_snapshot = restored.restore_outreach_session(campaign_id)
    assert restored_snapshot is not None
    assert int(restored_snapshot["session"]["id"]) == session_id


def test_operator_throughput_benchmark_reports_latency(tmp_path: Path) -> None:
    rows = run_benchmark(count=100, db_path=str(tmp_path / "benchmark.sqlite"), reset=True)
    metrics = {str(row["operation"]): row for row in rows}

    assert {"load 100 leads", "next lead", "copy message", "filter high priority", "search", "session restore", "mark sent"} <= set(metrics)
    assert float(metrics["next lead"]["average_ms"]) < 150
    assert float(metrics["copy message"]["average_ms"]) < 100
    assert float(metrics["session restore"]["average_ms"]) < 500
