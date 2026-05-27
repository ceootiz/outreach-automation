from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from src.background_worker import QueueJobProcessor
from src.campaign_service import CampaignService
from src.db import Database
from src.gui.main_window import MainWindow
from src.gui.settings_view import SettingsView
from src.gui.template_view import TemplateView
from src.gui.i18n import status_to_ru
from src.mailer import GmailSMTPMailer


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def cleanup_qt_widgets(qapp: QApplication):
    yield
    for widget in QApplication.topLevelWidgets():
        campaign_view = getattr(widget, "campaign_view", None)
        if campaign_view is not None:
            campaign_view.shutdown()
        settings_view = getattr(widget, "settings_view", None)
        if settings_view is not None:
            settings_view.shutdown()
        if isinstance(widget, SettingsView):
            widget.shutdown()
        widget.close()
        widget.deleteLater()
    qapp.processEvents()


@pytest.fixture()
def quiet_message_boxes(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = []

    def record(_parent, title: str, text: str, *args, **kwargs):
        messages.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", record)
    monkeypatch.setattr(QMessageBox, "warning", record)
    monkeypatch.setattr(QMessageBox, "critical", record)
    return messages


def make_service(tmp_path: Path, mailer: FakeMailer | None = None) -> CampaignService:
    db = Database(tmp_path / "outreach.sqlite")
    db.initialize()
    db.set_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "25",
            "delay_seconds": "0",
            "sender_email": "",
            "allowed_test_recipient": "",
        }
    )
    return CampaignService(
        db,
        mailer=mailer or FakeMailer(),
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )


def add_contact(
    service: CampaignService,
    campaign_id: int,
    email: str,
    status: str,
) -> int:
    contact_id = service.db.add_contact(
        {
            "campaign_id": campaign_id,
            "email": email,
            "name": "UI QA",
            "company": "Example Co",
            "topic": "Stage 1.6.2",
            "subject": "Hello {{company}}",
            "base_message": "Message for {{name}}",
            "status": "new",
        }
    )
    service.db.update_contact(
        contact_id,
        {
            "status": status,
            "generated_message": "Generated message",
        },
    )
    return contact_id


def wait_for(qapp: QApplication, predicate, label: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for {label}")


def test_campaign_view_has_queue_panel_buttons(qapp: QApplication, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    window = MainWindow(service)

    assert window.campaign_view.worker_status_label.text().startswith("Система:")
    assert window.campaign_view.current_job_label.text().startswith("Процесс:")
    assert window.campaign_view.current_contact_label.text().startswith("Сейчас обрабатывается:")
    assert window.campaign_view.progress_bar.maximum() == 100

    button_texts = {
        window.campaign_view.refresh_queue_button.text(),
        window.campaign_view.cancel_current_button.text(),
        window.campaign_view.retry_failed_button.text(),
        window.campaign_view.clear_completed_button.text(),
    }
    assert {
        "Обновить",
        "Остановить",
        "Повторить",
        "Очистить",
    }.issubset(button_texts)


def test_settings_send_mode_and_allowed_recipient_persist(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service(tmp_path)
    monkeypatch.setenv("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(tmp_path / "app-data"))
    view = SettingsView(service, refresh_callback=lambda: None)
    view.refresh()

    assert view.send_mode.currentText() == "Тестовый режим"
    view.send_mode.setCurrentText("Боевой режим")
    view.allowed_test_recipient.setText("owned@example.com")
    view.daily_limit.setValue(1)
    view.safe_mode.setChecked(True)
    view.save(show_message=False)

    settings = service.settings()
    assert settings["send_mode"] == "live"
    assert settings["allowed_test_recipient"] == "owned@example.com"
    assert settings["daily_send_limit"] == "1"
    assert settings["safe_mode"] == "true"


def test_contacts_table_handles_queue_statuses(qapp: QApplication, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    for index, status in enumerate(["queued", "sending", "dry_run_sent"], start=1):
        add_contact(service, campaign_id, f"status{index}@example.com", status)
    window = MainWindow(service)

    rows = window.contacts_view.table.rowCount()
    statuses = {
        window.contacts_view.table.item(row, 7).text()
        for row in range(rows)
    }
    assert {status_to_ru("queued"), status_to_ru("sending"), status_to_ru("dry_run_sent")}.issubset(statuses)


def test_reapprove_action_works_from_ui_selection(
    qapp: QApplication,
    tmp_path: Path,
    quiet_message_boxes: list[tuple[str, str]],
) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_contact(service, campaign_id, "dryrun@example.com", "dry_run_sent")
    window = MainWindow(service)

    for row in range(window.contacts_view.table.rowCount()):
        if window.contacts_view.table.item(row, 0).text() == str(contact_id):
            window.contacts_view.table.selectRow(row)
            break

    window.campaign_view.reapprove_selected()

    assert service.db.get_contact(contact_id)["status"] == "approved"
    assert quiet_message_boxes[-1][0] == "Вернуть к отправке"


def test_template_preview_without_selection_is_safe(
    qapp: QApplication,
    tmp_path: Path,
    quiet_message_boxes: list[tuple[str, str]],
) -> None:
    service = make_service(tmp_path)
    view = TemplateView(service, selected_contact_ids=lambda: [], refresh_callback=lambda: None)

    view.preview()

    assert quiet_message_boxes[-1] == (
        "Предпросмотр",
        "Сначала выберите получателя во вкладке Получатели.",
    )


def test_gmail_check_without_password_returns_user_safe_message() -> None:
    mailer = GmailSMTPMailer(password_getter=lambda: "")

    result = mailer.check_connection(
        host="smtp.gmail.com",
        port=587,
        sender_email="sender@example.com",
    )

    assert not result.ok
    assert "Gmail app password is missing" in result.message
    assert "sender@example.com" not in result.message


def test_logs_view_loads_after_queue_actions(qapp: QApplication, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    contact_id = add_contact(service, campaign_id, "queue-log@example.com", "approved")

    result = service.enqueue_send_approved(campaign_id, mode="dry_run")
    assert result.count == 1
    QueueJobProcessor(service).process_available()

    window = MainWindow(service)
    window.logs_view.refresh()

    actions = {
        window.logs_view.table.item(row, 3).text()
        for row in range(window.logs_view.table.rowCount())
    }
    assert service.db.get_contact(contact_id)["status"] == "dry_run_sent"
    assert {"enqueue_send", "dry_run_send"}.issubset(actions)


def test_campaign_queue_buttons_drain_jobs_after_fast_followup_action(
    qapp: QApplication,
    tmp_path: Path,
    quiet_message_boxes: list[tuple[str, str]],
) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    for index in range(3):
        add_contact(service, campaign_id, f"fast{index}@example.com", "new")
    window = MainWindow(service)

    window.campaign_view.generate_messages()
    wait_for(
        qapp,
        lambda: {contact["status"] for contact in service.contacts(campaign_id)} == {"pending_review"},
        "queued generation jobs",
    )
    target = sorted(service.contacts(campaign_id), key=lambda contact: contact["email"])[0]

    window.refresh_all()
    for row in range(window.contacts_view.table.rowCount()):
        if window.contacts_view.table.item(row, 0).text() == str(target["id"]):
            window.contacts_view.table.selectRow(row)
            break
    window.campaign_view.approve_selected()

    window.campaign_view.send_approved()
    wait_for(
        qapp,
        lambda: service.db.get_contact(target["id"])["status"] == "dry_run_sent",
        "fast follow-up dry-run send",
    )
    wait_for(qapp, lambda: window.campaign_view._queue_thread is None, "queue worker stop")
    wait_for(qapp, lambda: not window.campaign_view._jobs, "campaign task cleanup")

    assert service.db.fetch_one(
        "SELECT id FROM send_logs WHERE action = 'dry_run_send' AND contact_id = ?",
        (target["id"],),
    )
    assert any(title == "Отправить подтвержденные" for title, _text in quiet_message_boxes)
    window.campaign_view.shutdown()
    window.settings_view.shutdown()
    window.close()
    qapp.processEvents()
