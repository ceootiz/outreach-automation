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
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox

from src.campaign_service import CampaignService
from src.db import Database
from src.gui.main_window import MainWindow


class FakeMailer:
    def send_email(self, **kwargs) -> None:
        raise AssertionError("Clickability tests must not send email")

    def check_connection(self, **kwargs):
        return SimpleNamespace(ok=False, message="Введите и сохраните App Password")


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch: pytest.MonkeyPatch, qapp: QApplication, tmp_path: Path):
    os.environ["OUTREACH_AUTOMATION_APP_DIR"] = str(tmp_path / "app-data")

    def record(_parent, _title: str, _text: str, *args, **kwargs):
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", record)
    monkeypatch.setattr(QMessageBox, "warning", record)
    monkeypatch.setattr(QMessageBox, "critical", record)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )
    yield
    for widget in QApplication.topLevelWidgets():
        campaign_view = getattr(widget, "campaign_view", None)
        if campaign_view is not None:
            campaign_view.shutdown()
        settings_view = getattr(widget, "settings_view", None)
        if settings_view is not None:
            settings_view.shutdown()
        widget.close()
        widget.deleteLater()
    qapp.processEvents()


def make_service(tmp_path: Path) -> CampaignService:
    db = Database(tmp_path / "outreach.sqlite")
    db.initialize()
    db.set_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "delay_seconds": "0",
            "sender_email": "",
            "allowed_test_recipient": "",
            "onboarding_completed": "true",
        }
    )
    return CampaignService(
        db,
        mailer=FakeMailer(),
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )


def show_window(qapp: QApplication, tmp_path: Path) -> MainWindow:
    window = MainWindow(make_service(tmp_path))
    window.show()
    qapp.processEvents()
    return window


def test_settings_email_controls_are_focusable_editable_and_connected(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = show_window(qapp, tmp_path)
    window.open_settings()
    settings = window.settings_view

    for field in (settings.sender_email, settings.app_password, settings.allowed_test_recipient):
        assert field.isEnabled()
        field.clear()
        field.setFocus()
        assert field.hasFocus()

    QTest.keyClicks(settings.sender_email, "clickable@example.com")
    QTest.keyClicks(settings.app_password, "safe-test-password")
    QTest.keyClicks(settings.allowed_test_recipient, "owned@example.com")

    assert settings.sender_email.text() == "clickable@example.com"
    assert settings.app_password.text() == "safe-test-password"
    assert settings.app_password.echoMode() == QLineEdit.EchoMode.Password
    assert settings.allowed_test_recipient.text() == "owned@example.com"

    assert settings.save_credentials_button.isEnabled()
    assert settings.check_button.isEnabled()
    assert settings.action_map["settings.save_gmail"]["slot"] == "save_gmail_credentials"
    assert settings.action_map["settings.check_gmail"]["slot"] == "check_gmail_connection"

    QTest.mouseClick(settings.save_credentials_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert settings.service.settings()["sender_email"] == "clickable@example.com"
    assert settings.app_password.text() == ""

    calls = {"gmail_check": 0}

    def fake_check(**kwargs):
        calls["gmail_check"] += 1
        return SimpleNamespace(ok=False, message="Введите и сохраните App Password")

    settings.service.check_gmail_connection = fake_check
    settings._run_task = lambda task, on_success: on_success(task())
    QTest.mouseClick(settings.check_button, Qt.MouseButton.LeftButton)
    assert calls["gmail_check"] == 1
    assert settings.gmail_state_label.text()


def test_settings_mode_limit_and_safety_controls_are_clickable(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = show_window(qapp, tmp_path)
    window.open_settings()
    settings = window.settings_view

    QTest.mouseClick(settings.live_mode_button, Qt.MouseButton.LeftButton)
    assert settings.send_mode.currentData() == "live"
    QTest.mouseClick(settings.dry_run_mode_button, Qt.MouseButton.LeftButton)
    assert settings.send_mode.currentData() == "dry_run"

    settings.daily_limit.setFocus()
    settings.daily_limit.setValue(7)
    settings.delay_seconds.setValue(3)
    settings.safe_mode.setChecked(False)
    settings.real_send_confirm_required.setChecked(False)
    settings.save(show_message=False)

    saved = settings.service.settings()
    assert saved["daily_send_limit"] == "7"
    assert saved["delay_seconds"] == "3"
    assert saved["safe_mode"] == "false"
    assert saved["real_send_confirm_required"] == "false"


def test_main_add_edit_save_and_delete_stay_on_main_page(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = show_window(qapp, tmp_path)
    campaign = window.campaign_view
    assert window.content_stack.currentIndex() == 0

    before_rows = campaign.recipient_preview_table.rowCount()
    QTest.mouseClick(campaign.add_row_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert window.content_stack.currentIndex() == 0
    assert campaign.recipient_preview_table.rowCount() == before_rows + 1
    row = campaign.recipient_preview_table.rowCount() - 1
    assert campaign.recipient_preview_table.item(row, 1).flags() & Qt.ItemFlag.ItemIsEditable

    campaign.recipient_preview_table.item(row, 1).setText("manual-main@example.com")
    campaign.recipient_preview_table.item(row, 2).setText("Тема")
    campaign.recipient_preview_table.item(row, 3).setText("Индивидуальное сообщение")
    QTest.mouseClick(campaign.save_changes_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    contacts = window.service.contacts(window.active_campaign_id())
    assert [contact["email"] for contact in contacts] == ["manual-main@example.com"]
    assert window.content_stack.currentIndex() == 0

    campaign.recipient_preview_table.selectRow(0)
    QTest.mouseClick(campaign.delete_selected_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert window.service.contacts(window.active_campaign_id()) == []
    assert window.content_stack.currentIndex() == 0


def test_main_actions_are_enabled_callable_and_do_not_teleport(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = show_window(qapp, tmp_path)
    campaign = window.campaign_view
    campaign._run_task = lambda _title, task, on_success, _message="": on_success(task())

    for action_id in (
        "campaign.generate_messages",
        "campaign.approve_selected",
        "campaign.send_approved",
        "campaign.export_report",
        "campaign.queue_refresh",
        "campaign.queue_cancel",
        "campaign.queue_retry",
        "campaign.queue_clear",
    ):
        assert action_id in campaign.action_map

    for button in (
        campaign.quick_generate_button,
        campaign.quick_approve_button,
        campaign.quick_send_button,
        campaign.quick_export_button,
        campaign.refresh_queue_button,
        campaign.cancel_current_button,
        campaign.retry_failed_button,
        campaign.clear_completed_button,
    ):
        assert button.isEnabled()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        qapp.processEvents()
        assert window.content_stack.currentIndex() == 0


def test_main_paste_button_persists_clipboard_rows_without_teleport(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = show_window(qapp, tmp_path)
    campaign = window.campaign_view

    QApplication.clipboard().setText("main-paste@example.com\tСообщение из буфера")
    QTest.mouseClick(campaign.paste_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    contacts = window.service.contacts(window.active_campaign_id())
    assert [contact["email"] for contact in contacts] == ["main-paste@example.com"]
    assert contacts[0]["base_message"] == "Сообщение из буфера"
    assert window.content_stack.currentIndex() == 0


def test_recipients_screen_controls_and_table_editing_work(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = show_window(qapp, tmp_path)
    window._select_page(1)
    contacts = window.contacts_view

    assert contacts.add_button.isEnabled()
    assert contacts.save_button.isEnabled()
    assert contacts.delete_button.isEnabled()
    assert contacts.action_map["contacts.add_row"]["slot"] == "add_empty_row"

    QTest.mouseClick(contacts.add_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert contacts.table.rowCount() == 1
    assert contacts.table.item(0, 1).flags() & Qt.ItemFlag.ItemIsEditable

    contacts.table.item(0, 1).setText("recipient-screen@example.com")
    contacts.table.item(0, 2).setText("Тема")
    contacts.table.item(0, 3).setText("Текст")
    QTest.mouseClick(contacts.save_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert window.service.contacts(window.active_campaign_id())[0]["email"] == "recipient-screen@example.com"

    contacts.search_input.setFocus()
    QTest.keyClicks(contacts.search_input, "recipient")
    assert contacts.search_input.text() == "recipient"
    contacts.status_filter.setCurrentIndex(0)
    contacts.table.selectRow(0)
    QTest.mouseClick(contacts.delete_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert window.service.contacts(window.active_campaign_id()) == []


def test_key_inputs_are_not_covered_by_obvious_sibling_overlay(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = show_window(qapp, tmp_path)
    window.open_settings()
    qapp.processEvents()

    for field in (
        window.settings_view.sender_email,
        window.settings_view.app_password,
        window.settings_view.allowed_test_recipient,
    ):
        center = field.mapTo(window, field.rect().center())
        top_widget = window.childAt(center)
        field.setFocus()
        assert field.hasFocus()
        if top_widget is not None:
            assert top_widget is field or field.isAncestorOf(top_widget)
