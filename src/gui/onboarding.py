from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .theme import COLORS, card, helper_text, section_title, set_button_kind


class OnboardingDialog(QDialog):
    def __init__(self, mark_completed, parent=None):
        super().__init__(parent)
        self.mark_completed = mark_completed
        self.setWindowTitle("Добро пожаловать")
        self.setModal(True)
        self.setMinimumSize(520, 360)

        self.stack = QStackedWidget()
        for title, body in (
            (
                "Добро пожаловать 👋",
                "Gmail Рассылка помогает подготовить и безопасно проверить письма перед отправкой.",
            ),
            (
                "Что умеет приложение",
                "• Email live через Gmail\n• Telegram Bot API\n• Instagram, TikTok, X, VK через Помощник отправки\n• AI drafts, inbox и operator cockpit",
            ),
            (
                "Как подключить Gmail",
                "Создайте Gmail App Password и введите его во вкладке «Аккаунты и настройки».\nПароль хранится в защищенном хранилище и не пишется в логи.",
            ),
            (
                "Социальные каналы безопасны",
                "Социальные платформы не отправляются скрыто. Приложение готовит текст, открывает профиль, копирует сообщение и ждет ручного действия оператора.",
            ),
            (
                "Начинайте с тестового режима",
                "По умолчанию реальные отправки отключены. AI не отправляет и не подтверждает за вас; human review обязателен.",
            ),
        ):
            self.stack.addWidget(self._page(title, body))

        self.back_button = QPushButton("Назад")
        self.next_button = QPushButton("Далее")
        self.start_button = QPushButton("Начать работу")
        set_button_kind(self.back_button, "ghost")
        set_button_kind(self.next_button, "soft")
        set_button_kind(self.start_button, "primary")
        self.back_button.clicked.connect(self.back)
        self.next_button.clicked.connect(self.next)
        self.start_button.clicked.connect(self.finish)

        controls = QHBoxLayout()
        controls.addWidget(self.back_button)
        controls.addStretch(1)
        controls.addWidget(self.next_button)
        controls.addWidget(self.start_button)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)
        root.addWidget(self.stack)
        root.addLayout(controls)
        self._sync_buttons()

    def _page(self, title: str, body: str) -> QFrame:
        frame = card()
        frame.setGraphicsEffect(None)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        icon = QLabel("✉")
        icon.setFixedSize(46, 46)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background: {COLORS['primary_soft']}; color: {COLORS['primary']}; "
            "border-radius: 16px; font-size: 22px; font-weight: 900;"
        )
        text = helper_text(body)
        text.setStyleSheet(f"color: {COLORS['muted']}; font-size: 14px; line-height: 150%;")
        layout.addWidget(icon)
        layout.addWidget(section_title(title))
        layout.addWidget(text)
        layout.addStretch(1)
        return frame

    def back(self) -> None:
        self.stack.setCurrentIndex(max(0, self.stack.currentIndex() - 1))
        self._sync_buttons()

    def next(self) -> None:
        self.stack.setCurrentIndex(min(self.stack.count() - 1, self.stack.currentIndex() + 1))
        self._sync_buttons()

    def finish(self) -> None:
        self.mark_completed()
        self.accept()

    def _sync_buttons(self) -> None:
        is_first = self.stack.currentIndex() == 0
        is_last = self.stack.currentIndex() == self.stack.count() - 1
        self.back_button.setEnabled(not is_first)
        self.next_button.setVisible(not is_last)
        self.start_button.setVisible(is_last)
