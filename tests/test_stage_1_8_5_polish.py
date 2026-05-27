from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.campaign_service import CampaignService
from src.db import Database
from src.gui.main_window import MainWindow


class FakeMailer:
    def send_email(self, **kwargs) -> None:
        raise AssertionError("Polish tests must not send email")


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
        widget.close()
        widget.deleteLater()
    qapp.processEvents()


def make_service(tmp_path: Path, contacts: int = 0) -> CampaignService:
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
    service = CampaignService(
        db,
        mailer=FakeMailer(),
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )
    campaign_id = service.default_campaign_id()
    for index in range(contacts):
        service.add_contact_row(
            campaign_id,
            {
                "email": f"polish{index}@example.com",
                "subject": f"Тема {index}",
                "generated_message": f"Сообщение {index}",
                "name": "Test",
                "company": "Example",
                "topic": "Polish",
            },
        )
    return service


def test_button_hierarchy_and_disabled_state(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path, contacts=1))
    campaign = window.campaign_view

    assert campaign.quick_generate_button.objectName() == "primaryButton"
    assert campaign.quick_approve_button.objectName() == "softButton"
    assert campaign.quick_send_button.objectName() == "softButton"
    assert campaign.quick_export_button.objectName() == "textButton"
    assert campaign.cancel_current_button.objectName() == "ghostButton"

    campaign._set_busy(True, "Подготавливаем сообщения…")
    assert not campaign.quick_generate_button.isEnabled()
    assert not campaign.loading_label.isHidden()
    assert campaign.loading_label.text() == "Подготавливаем сообщения…"

    campaign._set_busy(False)
    assert campaign.quick_generate_button.isEnabled()
    assert not campaign.loading_label.isVisible()


def test_empty_states_and_queue_health_exist(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path, contacts=0))

    assert not window.contacts_view.empty_state.isHidden()
    assert window.contacts_view.empty_icon_label.text() == "✉"
    assert window.contacts_view.empty_add_button.text() == "+ Добавить строку"
    assert window.contacts_view.empty_import_button.text() == "Загрузить Excel"

    assert window.campaign_view.current_job_label.text() == "Процесс: нет задач"
    assert window.campaign_view.queue_health_label.text() == "Ошибок нет"


def test_keyboard_shortcuts_registered(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path, contacts=1))

    assert window.save_shortcut.objectName() == "saveChangesShortcut"
    assert window.paste_shortcut.objectName() == "pasteRowsShortcut"
    assert window.delete_shortcut.objectName() == "deleteRowsShortcut"
    assert window.enter_shortcut.objectName() == "editRowShortcut"


def test_table_and_sidebar_interaction_polish(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path, contacts=2))

    assert window.sidebar_buttons[0].isChecked()
    assert window.contacts_view.table.hasMouseTracking()
    assert window.contacts_view.table.selectionBehavior().name == "SelectRows"
    assert window.contacts_view.table.verticalHeader().defaultSectionSize() <= 40


def test_settings_safe_state_cards(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(tmp_path / "app-data"))
    window = MainWindow(make_service(tmp_path, contacts=0))

    assert window.settings_view.gmail_state_label.text() == "Почта пока не подключена"
    assert window.settings_view.send_mode_state_label.text().startswith("Безопасный тестовый режим")

    window.settings_view._set_send_mode("live")
    assert window.settings_view.send_mode_state_label.text().startswith("Боевой режим")
