from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from src.campaign_service import CampaignService
from src.db import Database
from src.gui.main_window import MainWindow
from src.gui.theme import COLORS


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
            "daily_send_limit": "25",
            "delay_seconds": "0",
            "sender_email": "",
            "allowed_test_recipient": "",
        }
    )
    return CampaignService(
        db,
        mailer=FakeMailer(),
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )


def test_sidebar_and_russian_navigation_exist(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path))

    assert window.sidebar is not None
    assert len(window.sidebar_buttons) == 5
    assert "Рассылка" in window.sidebar_buttons[0].text()
    assert "Получатели" in window.sidebar_buttons[1].text()
    assert window.mode_title.text() == "Тестовый режим"
    assert window.sidebar.styleSheet()


def test_campaign_has_onboarding_workflow_cards_and_queue_panel(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    assert campaign.findChildren(QPushButton)
    assert len(campaign.workflow_cards) == 3
    assert campaign.queue_card is not None
    assert campaign.progress_bar.maximum() == 100
    assert campaign.recipient_preview_table.columnCount() >= 9
    assert campaign.add_row_button.text() == "+ Добавить строку"
    assert campaign.send_mode_label.text().startswith("Тестовый режим")


def test_recipient_table_is_modern_russian_table_with_status_badges(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    campaign_id = service.default_campaign_id()
    service.db.add_contact(
        {
            "campaign_id": campaign_id,
            "email": "badge@example.com",
            "subject": "Тема",
            "generated_message": "Сообщение",
            "status": "approved",
        }
    )
    window = MainWindow(service)
    table = window.contacts_view.table

    assert table.objectName() == "recipientTable"
    assert table.horizontalHeaderItem(0).text() == "✓"
    assert table.horizontalHeaderItem(3).text() == "Сообщение"
    status_item = table.item(0, 7)
    assert status_item.text() == "Подтверждено"
    assert status_item.data(Qt.ItemDataRole.UserRole) == "status_badge"
    assert status_item.background().color().isValid()


def test_settings_cards_and_segmented_send_mode_exist(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    settings = window.settings_view

    assert settings.gmail_card is not None
    assert settings.send_mode_card is not None
    assert settings.security_card is not None
    assert settings.send_mode.currentText() == "Тестовый режим"
    assert settings.dry_run_mode_button.isChecked()
    settings.live_mode_button.click()
    assert settings.send_mode.currentData() == "live"


def test_theme_uses_light_apple_like_background() -> None:
    assert COLORS["bg"] == "#F6F7FB"
    assert COLORS["surface"] == "#FFFFFF"
