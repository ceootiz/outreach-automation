from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..campaign_service import CampaignService
from .theme import card, helper_text, section_title, set_button_kind


class TemplateView(QWidget):
    def __init__(
        self,
        service: CampaignService,
        selected_contact_ids: Callable[[], list[int]],
        refresh_callback: Callable[[], None],
    ):
        super().__init__()
        self.service = service
        self.selected_contact_ids = selected_contact_ids
        self.refresh_callback = refresh_callback
        self._loading = False

        self.subject_template = QLineEdit()
        self.body_template = QTextEdit()
        self.body_template.setMinimumHeight(240)
        self.intro = QLabel("Шаблон нужен, если у получателей не заполнено индивидуальное сообщение.")
        self.intro.setObjectName("muted")
        self.intro.setWordWrap(True)
        self.variables_label = helper_text(
            "{{name}} — имя\n"
            "{{company}} — компания\n"
            "{{topic}} — заметка/ниша\n"
            "{{base_message}} — сообщение из строки"
        )

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.addRow("Шаблон темы", self.subject_template)
        form.addRow("Шаблон сообщения", self.body_template)

        self.explanation_card = card()
        explanation_layout = QVBoxLayout(self.explanation_card)
        explanation_layout.setContentsMargins(20, 18, 20, 18)
        explanation_layout.addWidget(
            helper_text("Шаблон нужен только если у получателя не заполнено индивидуальное сообщение.")
        )

        self.template_card = card()
        self.template_card.setMinimumHeight(360)
        card_layout = QVBoxLayout(self.template_card)
        card_layout.setContentsMargins(24, 22, 24, 24)
        card_layout.setSpacing(14)
        card_title = section_title("Шаблон по умолчанию")
        card_layout.addWidget(card_title)
        card_layout.addLayout(form)

        self.variables_card = card()
        variables_layout = QVBoxLayout(self.variables_card)
        variables_layout.setContentsMargins(20, 18, 20, 18)
        variables_layout.setSpacing(10)
        variables_layout.addWidget(section_title("Переменные"))
        variables_layout.addWidget(self.variables_label)

        self.save_button = QPushButton("Сохранить шаблон")
        self.preview_button = QPushButton("Предпросмотр выбранного получателя")
        set_button_kind(self.save_button, "primary")
        set_button_kind(self.preview_button, "soft")
        self.save_button.clicked.connect(self.save)
        self.preview_button.clicked.connect(self.preview)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(16)
        layout.addWidget(self._build_header())
        layout.addWidget(self.explanation_card)
        layout.addWidget(self.template_card)
        layout.addWidget(self.variables_card)
        actions = QHBoxLayout()
        actions.addWidget(self.save_button)
        actions.addWidget(self.preview_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)

    def _build_header(self) -> QFrame:
        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 22, 24, 22)
        title = QLabel("Шаблоны")
        title.setObjectName("heroTitle")
        subtitle = QLabel("Используйте шаблон только там, где у строки нет индивидуального текста.")
        subtitle.setObjectName("heroSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return frame

    def refresh(self) -> None:
        if self._loading:
            return
        self._loading = True
        template = self.service.template()
        self.subject_template.setText(template["subject_template"])
        self.body_template.setPlainText(template["body_template"])
        self._loading = False

    def save(self) -> None:
        try:
            self.service.save_template(
                self.subject_template.text(),
                self.body_template.toPlainText(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Шаблон", str(exc))
            return
        QMessageBox.information(self, "Шаблон", "Шаблон сохранен.")
        self.refresh_callback()

    def preview(self) -> None:
        ids = self.selected_contact_ids()
        if not ids:
            QMessageBox.information(
                self,
                "Предпросмотр",
                "Сначала выберите получателя во вкладке Получатели.",
            )
            return
        try:
            subject, body = self.service.preview_generated_email(ids[0])
        except Exception as exc:
            QMessageBox.critical(self, "Предпросмотр", str(exc))
            return
        message = QMessageBox(self)
        message.setWindowTitle("Предпросмотр")
        message.setText(f"Тема: {subject}")
        message.setDetailedText(body)
        message.exec()
