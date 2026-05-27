from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QScrollArea

from src.campaign_service import CampaignService
from src.db import Database
from src.gui.main_window import MainWindow


class FakeMailer:
    def send_email(self, **kwargs) -> None:
        raise AssertionError("UI layout tests must not send email")


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


def test_every_page_is_wrapped_in_scroll_area(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path))

    for index in range(window.content_stack.count()):
        assert isinstance(window.content_stack.widget(index), QScrollArea)
    assert isinstance(window.sidebar_scroll, QScrollArea)


def test_campaign_layout_has_non_tiny_cards_and_search(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    assert window.sidebar is not None
    assert window.mode_card.minimumHeight() >= 68
    assert all(card.minimumHeight() >= 52 for card in campaign.workflow_cards)
    assert campaign.queue_card.minimumHeight() >= 32
    assert campaign.queue_card.maximumHeight() <= 48
    assert campaign.campaign_search_input.placeholderText().startswith("Поиск")
    assert campaign.recipient_preview_table.minimumHeight() >= 130
    assert campaign.recipient_preview_table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded


def test_recipients_table_layout_is_readable_and_has_empty_state(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    contacts = window.contacts_view

    assert not contacts.empty_state.isHidden()
    assert contacts.table.minimumHeight() >= 400
    assert contacts.table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert contacts.table.columnWidth(1) >= 180
    assert contacts.table.columnWidth(3) >= 280
    assert contacts.search_input.placeholderText().startswith("Поиск")


def test_settings_instruction_and_key_buttons_are_not_tiny(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    settings = window.settings_view

    assert settings.gmail_instruction_label.wordWrap()
    assert settings.gmail_card.minimumHeight() >= 240
    assert settings.security_card.minimumHeight() >= 220
    assert window.campaign_view.add_row_button.minimumHeight() >= 32
    assert window.contacts_view.add_button.minimumHeight() >= 32
    assert settings.save_button.minimumHeight() >= 32


def test_russian_labels_remain_visible_in_polished_layout(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))

    assert "Рассылка" in window.sidebar_buttons[0].text()
    assert window.campaign_view.settings_shortcut_button.text() == "Настройки"
    assert window.contacts_view.import_button.text() == "Загрузить Excel/CSV"
    assert window.settings_view.dry_run_mode_button.text() == "Тестовый режим"
