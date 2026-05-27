from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from src.campaign_service import CampaignService
from src.db import Database
from src.gui.main_window import MainWindow


class FakeMailer:
    def send_email(self, **kwargs) -> None:
        raise AssertionError("Human UX tests must not send email")


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
                "email": f"human{index}@example.com",
                "subject": f"Тема {index}",
                "generated_message": f"Сообщение {index}",
                "name": "Test",
                "company": "Example",
                "topic": "UX",
            },
        )
    return service


def visible_texts(window: MainWindow) -> list[str]:
    labels = [label.text() for label in window.findChildren(QLabel)]
    buttons = [button.text() for button in window.findChildren(QPushButton)]
    return labels + buttons


def test_human_queue_and_action_labels_replace_technical_terms(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    texts = visible_texts(window)
    joined = "\n".join(texts)

    assert "Процесс: нет задач" in texts
    assert window.campaign_view.worker_status_label.text() == "Система: готова"
    assert window.campaign_view.current_contact_label.text() == "Сейчас обрабатывается: никто"
    assert "Повторить" in texts
    assert "Очистить" in texts

    for old_label in (
        "Очередь задач",
        "Процесс отправки",
        "Статус отправки",
        "Обработчик",
        "Текущая задача",
        "Текущий получатель",
        "Повторить ошибки",
        "Повторить неудачные",
        "Очистить завершенные",
        "Очистить историю задач",
        "Быстрые действия",
        "Состояние рассылки",
    ):
        assert old_label not in joined


def test_primary_action_has_clear_cta_and_secondary_actions(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    assert campaign.quick_generate_button.text() == "Подготовить сообщения"
    assert campaign.quick_generate_button.objectName() == "primaryButton"
    assert campaign.quick_approve_button.text() == "Подтвердить"
    assert campaign.quick_send_button.text() == "Тестовая отправка"
    assert campaign.quick_export_button.text() == "Отчет"
    assert campaign.quick_export_button.objectName() == "textButton"


def test_selected_rows_counter_updates_from_preview_table(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    assert campaign.preview_selected_label.text() == "• 0 выбрано"
    first_id_item = campaign.recipient_preview_table.item(0, 0)
    first_id_item.setCheckState(Qt.CheckState.Checked)
    qapp.processEvents()

    assert campaign.preview_selected_label.text() == "• 1 выбрано"
    assert len(campaign.selected_ids_for_action()) == 1


def test_feedback_messages_are_inline_and_callable(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(make_service(tmp_path))
    campaign = window.campaign_view

    campaign.show_feedback("Сообщения подготовлены.")
    assert campaign.feedback_label.text() == "Сообщения подготовлены."
    assert "background" in campaign.feedback_label.styleSheet()

    campaign.show_feedback("Нет задач для повтора.", "warning")
    assert campaign.feedback_label.text() == "Нет задач для повтора."
