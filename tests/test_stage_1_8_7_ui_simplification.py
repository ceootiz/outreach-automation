from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from src.campaign_service import CampaignService
from src.db import Database
from src.gui.main_window import MainWindow


class FakeMailer:
    def send_email(self, **kwargs) -> None:
        raise AssertionError("Simplification tests must not send email")


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


def make_service(tmp_path: Path, contacts: int = 4) -> CampaignService:
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
                "email": f"simple{index}@example.com",
                "subject": f"Тема {index}",
                "generated_message": f"Индивидуальное сообщение {index}",
                "name": "Test",
                "company": "Example",
                "topic": "Simple",
            },
        )
    return service


def visible_text(window: MainWindow) -> str:
    labels = [label.text() for label in window.findChildren(QLabel)]
    buttons = [button.text() for button in window.findChildren(QPushButton)]
    return "\n".join(labels + buttons)


def test_main_screen_is_action_workspace_not_dashboard(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path))
    text = visible_text(window)

    assert "Получатели" in text
    assert "Подготовить сообщения" in text
    assert "Что делать сейчас" not in text
    assert "Что уже готово" not in text
    assert "Главное действие" not in text
    assert "Статус отправки" not in text


def test_action_bar_exists_with_essential_actions(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    assert campaign.action_bar.objectName() == "bottomActionBar"
    assert campaign.quick_generate_button.text() == "Подготовить сообщения"
    assert campaign.quick_approve_button.text() == "Подтвердить"
    assert campaign.quick_send_button.text() == "Тестовая отправка"
    assert campaign.quick_export_button.text() == "Отчет"
    assert "тестовый режим" in campaign.action_summary_label.text()


def test_queue_dashboard_is_small_secondary_footer(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    assert campaign.queue_card.objectName() == "queueStatusFooter"
    assert campaign.queue_card.maximumHeight() <= 48
    assert campaign.queue_stat_labels == {}
    assert campaign.current_job_label.text() == "Процесс: нет задач"


def test_main_table_dominates_vertical_space(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    assert campaign.recipient_preview_table.minimumHeight() >= 240
    assert campaign.recipient_preview_table.minimumHeight() > campaign.action_bar.maximumHeight() * 3
    assert campaign.recipient_preview_table.minimumHeight() > campaign.queue_card.maximumHeight() * 5


def test_no_overlap_prone_tiny_main_screen_heights(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    assert campaign.queue_card.minimumHeight() >= 32
    assert campaign.action_bar.minimumHeight() >= 60
    for button in (
        campaign.quick_generate_button,
        campaign.quick_approve_button,
        campaign.quick_send_button,
        campaign.quick_export_button,
        campaign.refresh_queue_button,
    ):
        assert button.minimumHeight() >= 28


def test_main_screen_fits_macbook_targets(qapp: QApplication, tmp_path: Path) -> None:
    for width, height in ((1280, 800), (1440, 900)):
        window = MainWindow(make_service(tmp_path / f"{width}x{height}"))
        window.resize(width, height)
        window.show()
        qapp.processEvents()
        scroll = window.tabs.scrollWidget(0)
        assert scroll.verticalScrollBar().maximum() == 0
        assert scroll.horizontalScrollBar().maximum() == 0
        window.campaign_view.shutdown()
        window.close()
