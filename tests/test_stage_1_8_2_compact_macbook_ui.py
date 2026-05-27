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
        raise AssertionError("Compact UI tests must not send email")


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


def make_service(tmp_path: Path, contacts: int = 3) -> CampaignService:
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
                "email": f"compact{index}@example.com",
                "subject": f"Тема {index}",
                "generated_message": f"Сообщение {index}",
                "name": "Test",
                "company": "Example",
                "topic": "Compact",
            },
        )
    return service


def test_window_default_and_minimum_fit_macbook_air(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path))

    assert window.size().width() <= 1360
    assert window.size().height() <= 850
    assert window.minimumWidth() <= 1180
    assert window.minimumHeight() <= 760
    assert window.sidebar_scroll.width() <= 245


def test_campaign_dashboard_fits_without_vertical_scroll_at_1280x800(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    window.resize(1280, 800)
    window.show()
    qapp.processEvents()

    campaign_scroll = window.tabs.scrollWidget(0)
    assert campaign_scroll.verticalScrollBar().maximum() == 0


def test_campaign_dashboard_fits_without_vertical_scroll_at_1440x900(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    window.resize(1440, 900)
    window.show()
    qapp.processEvents()

    campaign_scroll = window.tabs.scrollWidget(0)
    assert campaign_scroll.verticalScrollBar().maximum() == 0


def test_campaign_cards_and_table_are_compact(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    assert all(card.maximumHeight() <= 90 for card in campaign.workflow_cards)
    assert campaign.recipient_preview_table.minimumHeight() <= 300
    assert campaign.recipient_preview_table.minimumHeight() >= 240
    assert campaign.recipient_preview_table.verticalHeader().defaultSectionSize() <= 40
    assert campaign.add_row_button.minimumHeight() <= 36
    assert campaign.add_row_button.minimumHeight() >= 30
    assert campaign.queue_card.maximumHeight() <= 120
    assert campaign.queue_card is not None


def test_compact_russian_labels_remain(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path))

    assert "Рассылка" in window.sidebar_buttons[0].text()
    assert window.campaign_view.send_button.text() == "Отправить подтвержденные"
    assert window.campaign_view.campaign_search_input.placeholderText().startswith("Поиск")
    assert window.mode_title.text() == "Тестовый режим"
