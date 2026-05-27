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
        raise AssertionError("Dashboard recovery tests must not send email")


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
    service = CampaignService(
        db,
        mailer=FakeMailer(),
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )
    campaign_id = service.default_campaign_id()
    for index in range(3):
        service.add_contact_row(
            campaign_id,
            {
                "email": f"recovery{index}@example.com",
                "subject": f"Тема {index}",
                "generated_message": f"Сообщение {index}",
                "name": "Test",
                "company": "Example",
                "topic": "Recovery",
            },
        )
    return service


def test_dashboard_recovery_keeps_queue_secondary(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    assert campaign.queue_card.objectName() == "queueStatusFooter"
    assert campaign.queue_card.maximumHeight() <= 48
    assert campaign.progress_bar.objectName() == "compactQueueProgress"
    assert campaign.refresh_queue_button.text() == "Обновить"
    assert campaign.retry_failed_button.text() == "Повторить"
    assert campaign.clear_completed_button.text() == "Очистить"


def test_dashboard_cards_are_removed_from_main_flow(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    assert campaign.findChild(type(campaign.queue_card), "bottomHowToCard") is None
    assert campaign.findChild(type(campaign.queue_card), "bottomStatsCard") is None
    assert campaign.findChild(type(campaign.queue_card), "bottomActionsCard") is None
    assert campaign.findChild(type(campaign.queue_card), "bottomActionBar") is campaign.action_bar


def test_action_bar_hierarchy_replaces_cards(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    assert campaign.quick_generate_button.text() == "Подготовить сообщения"
    assert campaign.quick_generate_button.objectName() == "primaryButton"
    assert campaign.quick_approve_button.objectName() == "softButton"
    assert campaign.quick_send_button.objectName() == "softButton"
    assert campaign.quick_export_button.objectName() == "textButton"
    assert "получателей" in campaign.action_summary_label.text()


def test_main_table_is_dominant_and_no_giant_queue_dashboard(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    assert campaign.recipient_preview_table.minimumHeight() >= 240
    assert campaign.recipient_preview_table.minimumHeight() > campaign.queue_card.maximumHeight() * 5
    assert campaign.queue_stat_labels == {}


def test_old_clutter_labels_do_not_return(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    texts = "\n".join(
        [label.text() for label in window.findChildren(type(window.campaign_view.current_job_label))]
        + [button.text() for button in window.findChildren(type(window.campaign_view.refresh_queue_button))]
    )

    for old_label in (
        "Что делать сейчас",
        "Что уже готово",
        "Главное действие",
        "Статус отправки",
        "Процесс отправки",
        "Очередь задач",
        "Повторить ошибки",
        "Очистить завершенные",
        "Повторить неудачные",
        "Очистить историю задач",
    ):
        assert old_label not in texts
