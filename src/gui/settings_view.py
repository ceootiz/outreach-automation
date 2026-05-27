from __future__ import annotations

from typing import Any
from typing import Callable

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..campaign_service import CampaignService
from ..channels import get_channel, list_channels
from ..inbox.sync_scheduler import normalize_interval, normalize_sync_mode
from .i18n import user_safe_error
from .task_runner import BackgroundWorker
from .theme import COLORS, card, helper_text, section_title, set_button_kind


class SettingsView(QWidget):
    def __init__(self, service: CampaignService, refresh_callback: Callable[[], None]):
        super().__init__()
        self.service = service
        self.refresh_callback = refresh_callback
        self._loading = False
        self._jobs: list[tuple[QThread, BackgroundWorker]] = []
        self._task_success_handler: Callable[[Any], None] | None = None
        self.action_map: dict[str, dict[str, str]] = {}
        self._selected_profile_id: int | None = None

        self.profile_list = QListWidget()
        self.profile_list.setObjectName("settingsGmailProfileList")
        self.profile_list.setMinimumHeight(150)
        self.profile_list.currentItemChanged.connect(self._on_profile_selected)
        self.profile_name = QLineEdit()
        self.profile_name.setObjectName("settingsGmailProfileNameInput")
        self.profile_name.setPlaceholderText("Например: Основной")
        self.smtp_host = QLineEdit()
        self.smtp_host.setObjectName("settingsSmtpHostInput")
        self.smtp_port = QSpinBox()
        self.smtp_port.setObjectName("settingsSmtpPortInput")
        self.smtp_port.setRange(1, 65535)
        self.sender_email = QLineEdit()
        self.sender_email.setObjectName("settingsGmailAddressInput")
        self.sender_email.setPlaceholderText("you@gmail.com")
        self.app_password = QLineEdit()
        self.app_password.setObjectName("settingsAppPasswordInput")
        self.app_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.app_password.setPlaceholderText("Введите Gmail App Password")
        self.password_status = QLabel()
        self.password_status.setWordWrap(True)
        self.gmail_state_label = QLabel("Почта пока не подключена")
        self.gmail_state_label.setWordWrap(True)
        self.daily_limit = QSpinBox()
        self.daily_limit.setObjectName("settingsDailyLimitInput")
        self.daily_limit.setRange(0, 10000)
        self.delay_seconds = QSpinBox()
        self.delay_seconds.setObjectName("settingsDelaySecondsInput")
        self.delay_seconds.setRange(0, 3600)
        self.review_mode = QCheckBox("Ручное подтверждение перед отправкой")
        self.follow_up_days = QSpinBox()
        self.follow_up_days.setObjectName("settingsFollowUpDaysInput")
        self.follow_up_days.setRange(0, 365)
        self.safe_mode = QCheckBox("Безопасный режим")
        self.send_mode = QComboBox()
        self.send_mode.addItem("Тестовый режим", "dry_run")
        self.send_mode.addItem("Боевой режим", "live")
        self.send_mode.setVisible(False)
        self.send_mode.currentIndexChanged.connect(self._sync_mode_buttons)
        self.dry_run_mode_button = QPushButton("Тестовый режим")
        self.live_mode_button = QPushButton("Боевой режим")
        self.dry_run_mode_button.setCheckable(True)
        self.live_mode_button.setCheckable(True)
        self.dry_run_mode_button.clicked.connect(lambda: self._set_send_mode("dry_run"))
        self.live_mode_button.clicked.connect(lambda: self._set_send_mode("live"))
        self.real_send_confirm_required = QCheckBox("Требовать подтверждение перед боевой отправкой")
        self.allowed_test_recipient = QLineEdit()
        self.allowed_test_recipient.setObjectName("settingsAllowedTestRecipientInput")
        self.allowed_test_recipient.setPlaceholderText("например: ваш тестовый ящик")
        self.send_warning = QLabel(
            "Тестовый режим не отправляет реальные письма. Боевой режим отправляет письма через Gmail."
        )
        self.send_warning.setWordWrap(True)
        self.send_mode_state_label = QLabel("Безопасный тестовый режим")
        self.send_mode_state_label.setWordWrap(True)
        self.gmail_hint = QLabel("Добавьте несколько Gmail-профилей и выберите активный отправитель.")
        self.gmail_hint.setWordWrap(True)
        self.gmail_instruction_label = helper_text(
            "Как подключить Gmail?\n"
            "1. Включите 2FA в Google Account.\n"
            "2. Создайте App Password.\n"
            "3. Введите название профиля, Gmail address и App Password в этом окне.\n"
            "4. Нажмите «Сохранить профиль», затем «Проверить подключение Gmail»."
        )
        self.ai_provider = QComboBox()
        self.ai_provider.setObjectName("settingsAiProviderCombo")
        self.ai_provider.addItem("Off", "off")
        self.ai_provider.addItem("OpenAI", "openai")
        self.ai_model = QLineEdit()
        self.ai_model.setObjectName("settingsAiModelInput")
        self.ai_model.setPlaceholderText("gpt-4.1-mini")
        self.ai_api_key = QLineEdit()
        self.ai_api_key.setObjectName("settingsAiApiKeyInput")
        self.ai_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_api_key.setPlaceholderText("Введите OpenAI API key")
        self.ai_key_status = QLabel("AI key не сохранен")
        self.ai_key_status.setWordWrap(True)
        self.ai_max_drafts = QSpinBox()
        self.ai_max_drafts.setObjectName("settingsAiMaxDraftsInput")
        self.ai_max_drafts.setRange(1, 500)
        self.save_ai_button = QPushButton("Сохранить AI settings")
        self.check_ai_button = QPushButton("Test AI connection")
        set_button_kind(self.save_ai_button, "primary")
        set_button_kind(self.check_ai_button, "soft")
        self.save_ai_button.clicked.connect(self.save_ai_settings)
        self.check_ai_button.clicked.connect(self.check_ai_connection)

        self.research_brain_provider = QComboBox()
        self.research_brain_provider.setObjectName("settingsResearchBrainProviderCombo")
        self.research_brain_provider.addItem("Off", "off")
        self.research_brain_provider.addItem("OpenAI", "openai")
        self.research_brain_model = QLineEdit()
        self.research_brain_model.setObjectName("settingsResearchBrainModelInput")
        self.research_brain_model.setPlaceholderText("gpt-4.1-mini")
        self.research_brain_api_key = QLineEdit()
        self.research_brain_api_key.setObjectName("settingsResearchBrainApiKeyInput")
        self.research_brain_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.research_brain_api_key.setPlaceholderText("Research Brain API key")
        self.research_brain_status = QLabel("Research Brain key не сохранен")
        self.research_brain_status.setWordWrap(True)
        self.save_research_brain_button = QPushButton("Сохранить Research Brain")
        self.save_research_brain_button.setObjectName("settingsResearchBrainSaveButton")
        self.check_research_brain_button = QPushButton("Проверить Research Brain")
        self.check_research_brain_button.setObjectName("settingsResearchBrainTestButton")
        set_button_kind(self.save_research_brain_button, "soft")
        set_button_kind(self.check_research_brain_button, "soft")
        self.save_research_brain_button.clicked.connect(self.save_research_brain_settings)
        self.check_research_brain_button.clicked.connect(self.check_research_brain_connection)

        self.writer_brain_provider = QComboBox()
        self.writer_brain_provider.setObjectName("settingsWriterBrainProviderCombo")
        self.writer_brain_provider.addItem("Off", "off")
        self.writer_brain_provider.addItem("OpenAI", "openai")
        self.writer_brain_model = QLineEdit()
        self.writer_brain_model.setObjectName("settingsWriterBrainModelInput")
        self.writer_brain_model.setPlaceholderText("gpt-4.1-mini")
        self.writer_brain_api_key = QLineEdit()
        self.writer_brain_api_key.setObjectName("settingsWriterBrainApiKeyInput")
        self.writer_brain_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.writer_brain_api_key.setPlaceholderText("Writer Brain API key")
        self.writer_brain_status = QLabel("Writer Brain key не сохранен")
        self.writer_brain_status.setWordWrap(True)
        self.save_writer_brain_button = QPushButton("Сохранить Writer Brain")
        self.save_writer_brain_button.setObjectName("settingsWriterBrainSaveButton")
        self.check_writer_brain_button = QPushButton("Проверить Writer Brain")
        self.check_writer_brain_button.setObjectName("settingsWriterBrainTestButton")
        set_button_kind(self.save_writer_brain_button, "soft")
        set_button_kind(self.check_writer_brain_button, "soft")
        self.save_writer_brain_button.clicked.connect(self.save_writer_brain_settings)
        self.check_writer_brain_button.clicked.connect(self.check_writer_brain_connection)

        self.web_enrichment_max_contacts = QSpinBox()
        self.web_enrichment_max_contacts.setObjectName("settingsWebEnrichmentMaxContactsInput")
        self.web_enrichment_max_contacts.setRange(1, 500)
        self.web_enrichment_max_pages = QSpinBox()
        self.web_enrichment_max_pages.setObjectName("settingsWebEnrichmentMaxPagesInput")
        self.web_enrichment_max_pages.setRange(1, 3)
        self.web_enrichment_timeout = QSpinBox()
        self.web_enrichment_timeout.setObjectName("settingsWebEnrichmentTimeoutInput")
        self.web_enrichment_timeout.setRange(2, 20)
        self.web_enrichment_cache_ttl = QSpinBox()
        self.web_enrichment_cache_ttl.setObjectName("settingsWebEnrichmentCacheTtlInput")
        self.web_enrichment_cache_ttl.setRange(1, 60)
        self.web_enrichment_respect_robots = QCheckBox("Уважать robots.txt")
        self.web_enrichment_respect_robots.setObjectName("settingsWebEnrichmentRespectRobots")

        self.channel_token_inputs: dict[str, QLineEdit] = {}
        self.channel_check_buttons: dict[str, QPushButton] = {}
        self.telegram_token_input: QLineEdit | None = None
        self.telegram_default_chat_id_input: QLineEdit | None = None
        self.telegram_status_label: QLabel | None = None
        self.save_telegram_button: QPushButton | None = None
        self.email_sync_enabled = QCheckBox("Email reply sync")
        self.email_sync_enabled.setObjectName("settingsEmailSyncEnabled")
        self.telegram_sync_enabled = QCheckBox("Telegram reply sync")
        self.telegram_sync_enabled.setObjectName("settingsTelegramSyncEnabled")
        self.inbox_sync_mode = QComboBox()
        self.inbox_sync_mode.setObjectName("settingsInboxSyncMode")
        self.inbox_sync_mode.addItem("Off", "off")
        self.inbox_sync_mode.addItem("Manual sync", "manual")
        self.inbox_sync_mode.addItem("Background sync", "background")
        self.inbox_sync_interval = QSpinBox()
        self.inbox_sync_interval.setObjectName("settingsInboxSyncInterval")
        self.inbox_sync_interval.setRange(5, 1440)
        self.email_sync_now_button = QPushButton("Manual Email sync")
        self.email_sync_now_button.setObjectName("settingsEmailSyncNowButton")
        self.telegram_sync_now_button = QPushButton("Manual Telegram sync")
        self.telegram_sync_now_button.setObjectName("settingsTelegramSyncNowButton")
        set_button_kind(self.email_sync_now_button, "soft")
        set_button_kind(self.telegram_sync_now_button, "soft")
        self.email_sync_now_button.clicked.connect(self.sync_email_now)
        self.telegram_sync_now_button.clicked.connect(self.sync_telegram_now)
        self.email_sync_status_label = QLabel("Email sync: never")
        self.email_sync_status_label.setObjectName("settingsEmailSyncStatus")
        self.email_sync_status_label.setWordWrap(True)
        self.telegram_sync_status_label = QLabel("Telegram sync: never")
        self.telegram_sync_status_label.setObjectName("settingsTelegramSyncStatus")
        self.telegram_sync_status_label.setWordWrap(True)

        self.save_button = QPushButton("Сохранить настройки")
        self.add_profile_button = QPushButton("Добавить профиль")
        self.save_credentials_button = QPushButton("Сохранить профиль")
        self.delete_profile_button = QPushButton("Удалить")
        self.set_active_profile_button = QPushButton("Сделать активным")
        self.check_button = QPushButton("Проверить подключение Gmail")
        set_button_kind(self.save_button, "primary")
        set_button_kind(self.add_profile_button, "soft")
        set_button_kind(self.save_credentials_button, "primary")
        set_button_kind(self.delete_profile_button, "danger")
        set_button_kind(self.set_active_profile_button, "soft")
        set_button_kind(self.check_button, "soft")
        self.save_button.clicked.connect(lambda: self.save(show_message=True))
        self.add_profile_button.clicked.connect(self.add_profile)
        self.save_credentials_button.clicked.connect(self.save_gmail_credentials)
        self.delete_profile_button.clicked.connect(self.delete_selected_profile)
        self.set_active_profile_button.clicked.connect(self.set_selected_profile_active)
        self.check_button.clicked.connect(self.check_gmail_connection)
        self._register_action_map()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 6)
        layout.setSpacing(10)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_gmail_card())
        layout.addWidget(self._build_channels_card())
        layout.addWidget(self._build_inbox_sync_card())
        layout.addWidget(self._build_ai_card())
        layout.addWidget(self._build_send_mode_card())
        layout.addWidget(self._build_security_card())
        actions = QHBoxLayout()
        actions.addWidget(self.save_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)
        self._register_channel_action_map()

    def _register_action_map(self) -> None:
        """Developer-visible clickability map for Settings buttons and core inputs."""
        actions: list[tuple[str, QWidget, str, str]] = [
            ("settings.save", self.save_button, "save", "Сохранить обычные настройки"),
            ("settings.add_gmail_profile", self.add_profile_button, "add_profile", "Очистить форму для нового Gmail-профиля"),
            ("settings.save_gmail", self.save_credentials_button, "save_gmail_credentials", "Сохранить Gmail-профиль в защищенное хранилище"),
            ("settings.delete_gmail_profile", self.delete_profile_button, "delete_selected_profile", "Удалить Gmail-профиль и его пароль"),
            ("settings.set_active_gmail_profile", self.set_active_profile_button, "set_selected_profile_active", "Сделать выбранный Gmail-профиль активным"),
            ("settings.check_gmail", self.check_button, "check_gmail_connection", "Проверить SMTP login без отправки письма"),
            ("settings.save_ai", self.save_ai_button, "save_ai_settings", "Сохранить AI Assist настройки"),
            ("settings.check_ai", self.check_ai_button, "check_ai_connection", "Проверить AI provider без отправки писем"),
            ("settings.save_research_brain", self.save_research_brain_button, "save_research_brain_settings", "Сохранить Research Brain API key"),
            ("settings.check_research_brain", self.check_research_brain_button, "check_research_brain_connection", "Проверить Research Brain"),
            ("settings.save_writer_brain", self.save_writer_brain_button, "save_writer_brain_settings", "Сохранить Writer Brain API key"),
            ("settings.check_writer_brain", self.check_writer_brain_button, "check_writer_brain_connection", "Проверить Writer Brain"),
            ("settings.email_sync_now", self.email_sync_now_button, "sync_email_now", "Запустить read-only IMAP sync"),
            ("settings.telegram_sync_now", self.telegram_sync_now_button, "sync_telegram_now", "Запустить Telegram getUpdates sync"),
            ("settings.mode_dry_run", self.dry_run_mode_button, "_set_send_mode", "Выбрать тестовый режим"),
            ("settings.mode_live", self.live_mode_button, "_set_send_mode", "Выбрать боевой режим"),
        ]
        inputs: list[tuple[str, QWidget, str, str]] = [
            ("settings.gmail_profile_name", self.profile_name, "QLineEdit.setText", "Ввести название Gmail-профиля"),
            ("settings.gmail_address", self.sender_email, "QLineEdit.setText", "Ввести Gmail address"),
            ("settings.app_password", self.app_password, "QLineEdit.setText", "Ввести masked Gmail App Password"),
            ("settings.daily_limit", self.daily_limit, "QSpinBox.setValue", "Изменить дневной лимит"),
            ("settings.delay_seconds", self.delay_seconds, "QSpinBox.setValue", "Изменить задержку"),
            ("settings.allowed_test_recipient", self.allowed_test_recipient, "QLineEdit.setText", "Ввести разрешенного тестового получателя"),
            ("settings.safe_mode", self.safe_mode, "QCheckBox.setChecked", "Включить/выключить безопасный режим"),
            ("settings.real_send_confirm", self.real_send_confirm_required, "QCheckBox.setChecked", "Включить/выключить подтверждение боевой отправки"),
            ("settings.ai_provider", self.ai_provider, "QComboBox.setCurrentIndex", "Выбрать AI provider"),
            ("settings.ai_model", self.ai_model, "QLineEdit.setText", "Ввести AI model"),
            ("settings.ai_api_key", self.ai_api_key, "QLineEdit.setText", "Ввести masked OpenAI API key"),
            ("settings.ai_max_drafts", self.ai_max_drafts, "QSpinBox.setValue", "Изменить лимит AI-черновиков"),
            ("settings.research_brain_provider", self.research_brain_provider, "QComboBox.setCurrentIndex", "Выбрать Research Brain provider"),
            ("settings.research_brain_model", self.research_brain_model, "QLineEdit.setText", "Ввести Research Brain model"),
            ("settings.research_brain_api_key", self.research_brain_api_key, "QLineEdit.setText", "Ввести masked Research Brain API key"),
            ("settings.writer_brain_provider", self.writer_brain_provider, "QComboBox.setCurrentIndex", "Выбрать Writer Brain provider"),
            ("settings.writer_brain_model", self.writer_brain_model, "QLineEdit.setText", "Ввести Writer Brain model"),
            ("settings.writer_brain_api_key", self.writer_brain_api_key, "QLineEdit.setText", "Ввести masked Writer Brain API key"),
            ("settings.web_enrichment_max_contacts", self.web_enrichment_max_contacts, "QSpinBox.setValue", "Изменить максимум enrichment-контактов за раз"),
            ("settings.web_enrichment_max_pages", self.web_enrichment_max_pages, "QSpinBox.setValue", "Изменить максимум публичных страниц на контакт"),
            ("settings.web_enrichment_timeout", self.web_enrichment_timeout, "QSpinBox.setValue", "Изменить HTTP timeout enrichment"),
            ("settings.web_enrichment_cache_ttl", self.web_enrichment_cache_ttl, "QSpinBox.setValue", "Изменить TTL enrichment cache"),
            ("settings.web_enrichment_respect_robots", self.web_enrichment_respect_robots, "QCheckBox.setChecked", "Включить/выключить уважение robots.txt"),
            ("settings.email_sync_enabled", self.email_sync_enabled, "QCheckBox.setChecked", "Включить read-only Email sync"),
            ("settings.telegram_sync_enabled", self.telegram_sync_enabled, "QCheckBox.setChecked", "Включить Telegram polling sync"),
            ("settings.inbox_sync_mode", self.inbox_sync_mode, "QComboBox.setCurrentIndex", "Выбрать режим inbox sync"),
            ("settings.inbox_sync_interval", self.inbox_sync_interval, "QSpinBox.setValue", "Изменить интервал background sync"),
        ]
        self.action_map = {}
        for action_id, widget, slot_name, expected in actions + inputs:
            widget.setAccessibleName(action_id)
            widget.setProperty("actionId", action_id)
            widget.setProperty("connectedSlot", slot_name)
            widget.setProperty("expectedAction", expected)
            self.action_map[action_id] = {
                "objectName": widget.objectName(),
                "label": widget.text() if hasattr(widget, "text") else action_id,
                "slot": slot_name,
                "expected": expected,
            }

    def _build_header(self) -> QFrame:
        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        title = QLabel("Аккаунты и настройки")
        title.setObjectName("heroTitle")
        subtitle = QLabel("Подключите Gmail, выберите каналы и задайте безопасные лимиты.")
        subtitle.setObjectName("heroSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return frame

    def _register_channel_action_map(self) -> None:
        for channel_id, widget in self.channel_token_inputs.items():
            action_id = f"settings.channel_token.{channel_id}"
            widget.setAccessibleName(action_id)
            widget.setProperty("actionId", action_id)
            widget.setProperty("connectedSlot", "QLineEdit.setText")
            widget.setProperty("expectedAction", "Ввести API token для будущей official API-интеграции")
            self.action_map[action_id] = {
                "objectName": widget.objectName(),
                "label": get_channel(channel_id).display_name,
                "slot": "QLineEdit.setText",
                "expected": "Ввести API token для будущей official API-интеграции",
            }
        for channel_id, button in self.channel_check_buttons.items():
            action_id = f"settings.channel_check.{channel_id}"
            slot_name = "check_telegram_connection" if channel_id == "telegram" else "show_channel_limitations"
            button.setAccessibleName(action_id)
            button.setProperty("actionId", action_id)
            button.setProperty("connectedSlot", slot_name)
            button.setProperty("expectedAction", "Проверить Telegram Bot API" if channel_id == "telegram" else "Показать ограничения канала")
            self.action_map[action_id] = {
                "objectName": button.objectName(),
                "label": button.text(),
                "slot": slot_name,
                "expected": "Проверить Telegram Bot API" if channel_id == "telegram" else "Показать ограничения канала",
            }
        if self.telegram_default_chat_id_input is not None:
            action_id = "settings.telegram_default_chat_id"
            widget = self.telegram_default_chat_id_input
            widget.setAccessibleName(action_id)
            widget.setProperty("actionId", action_id)
            widget.setProperty("connectedSlot", "QLineEdit.setText")
            widget.setProperty("expectedAction", "Ввести Telegram chat_id для безопасного теста")
            self.action_map[action_id] = {
                "objectName": widget.objectName(),
                "label": "Telegram chat_id",
                "slot": "QLineEdit.setText",
                "expected": "Ввести Telegram chat_id для безопасного теста",
            }
        if self.save_telegram_button is not None:
            action_id = "settings.telegram_save"
            button = self.save_telegram_button
            button.setAccessibleName(action_id)
            button.setProperty("actionId", action_id)
            button.setProperty("connectedSlot", "save_telegram_settings")
            button.setProperty("expectedAction", "Сохранить Telegram Bot Token в защищенное хранилище")
            self.action_map[action_id] = {
                "objectName": button.objectName(),
                "label": button.text(),
                "slot": "save_telegram_settings",
                "expected": "Сохранить Telegram Bot Token в защищенное хранилище",
            }

    def show_channel_limitations(self, channel_id: str) -> None:
        channel = get_channel(channel_id)
        QMessageBox.information(
            self,
            channel.display_name,
            (
                f"{channel.display_name}\n\n"
                f"{channel.explain_limitations()}\n\n"
                "Stage 3.0: live-отправка отключена. Можно готовить сообщения, "
                "подтверждать их вручную и запускать dry-run."
            ),
        )

    def save_telegram_settings(self) -> None:
        token = self.telegram_token_input.text().strip() if self.telegram_token_input is not None else ""
        chat_id = (
            self.telegram_default_chat_id_input.text().strip()
            if self.telegram_default_chat_id_input is not None
            else ""
        )
        try:
            backend = self.service.save_telegram_settings(
                bot_token=token,
                default_test_chat_id=chat_id,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Telegram", user_safe_error(exc))
            return
        if self.telegram_token_input is not None:
            self.telegram_token_input.clear()
        QMessageBox.information(self, "Telegram", f"Настройки Telegram сохранены ({backend}).")
        self.refresh_callback()

    def check_telegram_connection(self) -> None:
        token = self.telegram_token_input.text().strip() if self.telegram_token_input is not None else ""
        self._run_task(
            lambda: self.service.check_telegram_connection(bot_token_override=token or None),
            self._show_telegram_check_result,
        )

    def _show_telegram_check_result(self, result) -> None:
        if self.telegram_status_label is None:
            return
        if result.ok:
            self.telegram_status_label.setText(user_safe_error(result.message))
            self.telegram_status_label.setStyleSheet(
                f"background: {COLORS['green_soft']}; color: {COLORS['green']}; "
                "border-radius: 12px; padding: 7px 10px; font-weight: 750;"
            )
            QMessageBox.information(self, "Telegram", user_safe_error(result.message))
        else:
            self.telegram_status_label.setText(user_safe_error(result.message))
            self.telegram_status_label.setStyleSheet(
                f"background: {COLORS['amber_soft']}; color: {COLORS['amber']}; "
                "border-radius: 12px; padding: 7px 10px; font-weight: 750;"
            )
            QMessageBox.warning(self, "Telegram", user_safe_error(result.message))
        self.refresh_callback()

    def _build_gmail_card(self) -> QFrame:
        self.gmail_card = card()
        self.gmail_card.setMinimumHeight(390)
        layout = QVBoxLayout(self.gmail_card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        title = section_title("Профили Gmail")
        hint = QLabel("Сохраните несколько отправителей один раз и выбирайте активный профиль перед рассылкой.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)

        profile_row = QHBoxLayout()
        profile_row.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(QLabel("Сохраненные профили"))
        left.addWidget(self.profile_list)
        profile_buttons = QHBoxLayout()
        profile_buttons.setSpacing(6)
        profile_buttons.addWidget(self.add_profile_button)
        profile_buttons.addWidget(self.delete_profile_button)
        left.addLayout(profile_buttons)

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.addRow("Название профиля", self.profile_name)
        form.addRow("Gmail address", self.sender_email)
        form.addRow("App Password", self.app_password)
        form.addRow("SMTP-сервер Gmail", self.smtp_host)
        form.addRow("SMTP-порт", self.smtp_port)
        form.addRow("Статус пароля", self.password_status)
        form_column = QVBoxLayout()
        form_column.setSpacing(8)
        form_column.addLayout(form)
        action_row = QHBoxLayout()
        action_row.addWidget(self.save_credentials_button)
        action_row.addWidget(self.set_active_profile_button)
        action_row.addWidget(self.check_button)
        action_row.addStretch(1)
        form_column.addLayout(action_row)
        profile_row.addLayout(left, 1)
        profile_row.addLayout(form_column, 2)

        instruction_box = QFrame()
        instruction_box.setObjectName("instructionBox")
        instruction_box.setStyleSheet(
            f"QFrame#instructionBox {{ background: {COLORS['surface_soft']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 14px; }}"
        )
        instruction_layout = QVBoxLayout(instruction_box)
        instruction_layout.setContentsMargins(12, 10, 12, 10)
        instruction_layout.addWidget(self.gmail_instruction_label)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.gmail_state_label)
        layout.addLayout(profile_row)
        layout.addWidget(instruction_box)
        return self.gmail_card

    def _build_channels_card(self) -> QFrame:
        frame = card()
        frame.setObjectName("settingsChannelsCard")
        frame.setMinimumHeight(300)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(section_title("Каналы"))
        layout.addWidget(
            helper_text(
                "Email уже работает через Gmail-профили. X, Instagram, Telegram, VK и TikTok "
                "в Stage 3.0 доступны как безопасная подготовка сообщений и dry-run без live-автоматизации."
            )
        )
        for channel in list_channels():
            if channel.channel_id == "email":
                continue
            row = QFrame()
            row.setObjectName(f"settingsChannelCard_{channel.channel_id}")
            row.setStyleSheet(
                f"background: {COLORS['surface_soft']}; border: 1px solid {COLORS['border_soft']}; "
                "border-radius: 14px;"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 9, 12, 9)
            row_layout.setSpacing(10)
            text_box = QVBoxLayout()
            text_box.setSpacing(3)
            title = QLabel(channel.display_name)
            title.setStyleSheet("font-weight: 800;")
            status_text = (
                "Статус: не подключено • Тип подключения: official Telegram Bot API"
                if channel.channel_id == "telegram"
                else "Статус: не подключено • Тип подключения: official API / manual review / disabled"
            )
            status = QLabel(status_text)
            status.setObjectName("muted")
            status.setWordWrap(True)
            limitations = QLabel(channel.explain_limitations())
            limitations.setObjectName("muted")
            limitations.setWordWrap(True)
            text_box.addWidget(title)
            text_box.addWidget(status)
            text_box.addWidget(limitations)

            token = QLineEdit()
            token.setObjectName(f"settingsChannelToken_{channel.channel_id}")
            token.setEchoMode(QLineEdit.EchoMode.Password)
            token.setPlaceholderText(
                "Telegram Bot Token"
                if channel.channel_id == "telegram"
                else "API token (optional, future official API)"
            )
            token.setMaximumWidth(230)
            button = QPushButton("Проверить подключение")
            button.setObjectName(f"settingsChannelCheck_{channel.channel_id}")
            set_button_kind(button, "soft")
            if channel.channel_id == "telegram":
                button.clicked.connect(self.check_telegram_connection)
            else:
                button.clicked.connect(lambda _checked=False, cid=channel.channel_id: self.show_channel_limitations(cid))
            self.channel_token_inputs[channel.channel_id] = token
            self.channel_check_buttons[channel.channel_id] = button

            row_layout.addLayout(text_box, 1)
            action_box = QVBoxLayout()
            action_box.setSpacing(6)
            action_box.addWidget(token)
            if channel.channel_id == "telegram":
                self.telegram_token_input = token
                chat_id = QLineEdit()
                chat_id.setObjectName("settingsTelegramDefaultChatIdInput")
                chat_id.setPlaceholderText("Default test chat_id (optional)")
                chat_id.setMaximumWidth(230)
                status_label = QLabel("Bot Token не сохранен")
                status_label.setObjectName("muted")
                status_label.setWordWrap(True)
                save_button = QPushButton("Сохранить Telegram")
                save_button.setObjectName("settingsTelegramSaveButton")
                set_button_kind(save_button, "primary")
                save_button.clicked.connect(self.save_telegram_settings)
                self.telegram_default_chat_id_input = chat_id
                self.telegram_status_label = status_label
                self.save_telegram_button = save_button
                action_box.addWidget(chat_id)
                action_box.addWidget(status_label)
                action_box.addWidget(save_button)
            action_box.addWidget(button)
            row_layout.addLayout(action_box)
            layout.addWidget(row)
        return frame

    def _build_inbox_sync_card(self) -> QFrame:
        frame = card()
        frame.setObjectName("settingsInboxSyncCard")
        frame.setMinimumHeight(230)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(section_title("Inbox Sync"))
        layout.addWidget(
            helper_text(
                "Read-only синхронизация ответов. Email использует IMAP только для чтения, "
                "Telegram использует getUpdates. Приложение не отправляет ответы автоматически."
            )
        )
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)
        form.addRow("Режим", self.inbox_sync_mode)
        form.addRow("Интервал background sync, мин", self.inbox_sync_interval)
        form.addRow("Email", self.email_sync_enabled)
        form.addRow("Telegram", self.telegram_sync_enabled)
        form.addRow("Email status", self.email_sync_status_label)
        form.addRow("Telegram status", self.telegram_sync_status_label)
        layout.addLayout(form)
        actions = QHBoxLayout()
        actions.addWidget(self.email_sync_now_button)
        actions.addWidget(self.telegram_sync_now_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        return frame

    def _build_ai_card(self) -> QFrame:
        self.ai_card = card()
        self.ai_card.setMinimumHeight(430)
        layout = QVBoxLayout(self.ai_card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)
        title = section_title("AI Assist")
        hint = helper_text(
            "AI Assist только готовит черновики. Research Brain анализирует получателя, Writer Brain пишет сообщение. "
            "Можно использовать один API key для обоих."
        )
        legacy_title = helper_text("Simple AI draft")
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)
        form.addRow("Provider", self.ai_provider)
        form.addRow("Model", self.ai_model)
        form.addRow("API Key", self.ai_api_key)
        form.addRow("Статус ключа", self.ai_key_status)
        form.addRow("Максимум черновиков за раз", self.ai_max_drafts)
        action_row = QHBoxLayout()
        action_row.addWidget(self.save_ai_button)
        action_row.addWidget(self.check_ai_button)
        action_row.addStretch(1)
        research_title = helper_text("Research Brain")
        research_form = QFormLayout()
        research_form.setHorizontalSpacing(18)
        research_form.setVerticalSpacing(8)
        research_form.addRow("Provider", self.research_brain_provider)
        research_form.addRow("Model", self.research_brain_model)
        research_form.addRow("API Key", self.research_brain_api_key)
        research_form.addRow("Статус", self.research_brain_status)
        research_actions = QHBoxLayout()
        research_actions.addWidget(self.save_research_brain_button)
        research_actions.addWidget(self.check_research_brain_button)
        research_actions.addStretch(1)
        writer_title = helper_text("Writer Brain")
        writer_form = QFormLayout()
        writer_form.setHorizontalSpacing(18)
        writer_form.setVerticalSpacing(8)
        writer_form.addRow("Provider", self.writer_brain_provider)
        writer_form.addRow("Model", self.writer_brain_model)
        writer_form.addRow("API Key", self.writer_brain_api_key)
        writer_form.addRow("Статус", self.writer_brain_status)
        writer_actions = QHBoxLayout()
        writer_actions.addWidget(self.save_writer_brain_button)
        writer_actions.addWidget(self.check_writer_brain_button)
        writer_actions.addStretch(1)
        enrichment_title = helper_text("Web Enrichment")
        enrichment_hint = helper_text(
            "Research Brain может безопасно использовать публичные страницы сайта: GET-only, без login, cookies, JS и captcha. "
            "Данные кешируются и всегда помечаются source_basis."
        )
        enrichment_form = QFormLayout()
        enrichment_form.setHorizontalSpacing(18)
        enrichment_form.setVerticalSpacing(8)
        enrichment_form.addRow("Максимум контактов за раз", self.web_enrichment_max_contacts)
        enrichment_form.addRow("Страниц на контакт", self.web_enrichment_max_pages)
        enrichment_form.addRow("HTTP timeout, сек", self.web_enrichment_timeout)
        enrichment_form.addRow("Cache TTL, дней", self.web_enrichment_cache_ttl)
        enrichment_form.addRow("Robots", self.web_enrichment_respect_robots)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(legacy_title)
        layout.addLayout(form)
        layout.addLayout(action_row)
        layout.addWidget(research_title)
        layout.addLayout(research_form)
        layout.addLayout(research_actions)
        layout.addWidget(writer_title)
        layout.addLayout(writer_form)
        layout.addLayout(writer_actions)
        layout.addWidget(enrichment_title)
        layout.addWidget(enrichment_hint)
        layout.addLayout(enrichment_form)
        return self.ai_card

    def _build_send_mode_card(self) -> QFrame:
        self.send_mode_card = card()
        self.send_mode_card.setMinimumHeight(170)
        layout = QVBoxLayout(self.send_mode_card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        title = section_title("Режим отправки")
        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        mode_row.addWidget(self.dry_run_mode_button)
        mode_row.addWidget(self.live_mode_button)
        mode_row.addStretch(1)
        dry_hint = QLabel("Тестовый режим: письма не отправляются, приложение только проверяет процесс.")
        dry_hint.setObjectName("muted")
        dry_hint.setWordWrap(True)
        live_hint = QLabel("Боевой режим: письма реально отправляются через Gmail после подтверждения.")
        live_hint.setObjectName("muted")
        live_hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addLayout(mode_row)
        layout.addWidget(self.send_mode_state_label)
        layout.addWidget(dry_hint)
        layout.addWidget(live_hint)
        layout.addWidget(self.send_mode)
        layout.addWidget(self.send_warning)
        return self.send_mode_card

    def _build_security_card(self) -> QFrame:
        self.security_card = card()
        self.security_card.setMinimumHeight(230)
        layout = QVBoxLayout(self.security_card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        title = section_title("Безопасность")
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)
        form.addRow("Дневной лимит", self.daily_limit)
        form.addRow("Задержка между письмами, сек", self.delay_seconds)
        form.addRow("Ручная проверка", self.review_mode)
        form.addRow("Повторное письмо через дней", self.follow_up_days)
        form.addRow("Безопасный режим", self.safe_mode)
        form.addRow("Подтверждение перед боевой отправкой", self.real_send_confirm_required)
        form.addRow("Разрешенный тестовый получатель (email или Telegram chat_id)", self.allowed_test_recipient)
        layout.addWidget(title)
        layout.addLayout(form)
        return self.security_card

    def refresh(self) -> None:
        if self._loading:
            return
        self._loading = True
        settings = self.service.settings()
        self.smtp_host.setText(settings.get("smtp_host", "smtp.gmail.com"))
        self.smtp_port.setValue(int(settings.get("smtp_port", "587") or 587))
        self.app_password.clear()
        provider_index = self.ai_provider.findData(settings.get("ai_provider", "off"))
        self.ai_provider.setCurrentIndex(max(provider_index, 0))
        self.ai_model.setText(settings.get("ai_model", "gpt-4.1-mini"))
        self.ai_api_key.clear()
        self.ai_max_drafts.setValue(int(settings.get("ai_max_drafts_per_batch", "25") or 25))
        research_index = self.research_brain_provider.findData(settings.get("ai_research_provider", "off"))
        self.research_brain_provider.setCurrentIndex(max(research_index, 0))
        self.research_brain_model.setText(settings.get("ai_research_model", "gpt-4.1-mini"))
        self.research_brain_api_key.clear()
        writer_index = self.writer_brain_provider.findData(settings.get("ai_writer_provider", "off"))
        self.writer_brain_provider.setCurrentIndex(max(writer_index, 0))
        self.writer_brain_model.setText(settings.get("ai_writer_model", "gpt-4.1-mini"))
        self.writer_brain_api_key.clear()
        self.web_enrichment_max_contacts.setValue(int(settings.get("web_enrichment_max_contacts_per_batch", "25") or 25))
        self.web_enrichment_max_pages.setValue(int(settings.get("web_enrichment_max_pages", "2") or 2))
        self.web_enrichment_timeout.setValue(int(settings.get("web_enrichment_timeout_seconds", "8") or 8))
        self.web_enrichment_cache_ttl.setValue(int(settings.get("web_enrichment_cache_ttl_days", "7") or 7))
        self.web_enrichment_respect_robots.setChecked(
            str(settings.get("web_enrichment_respect_robots", "true")).lower() == "true"
        )
        sync_mode = normalize_sync_mode(settings.get("inbox_sync_mode", "manual"))
        sync_index = self.inbox_sync_mode.findData(sync_mode)
        self.inbox_sync_mode.setCurrentIndex(max(sync_index, 0))
        self.inbox_sync_interval.setValue(normalize_interval(settings.get("inbox_sync_interval_minutes", "5")))
        self.email_sync_enabled.setChecked(settings.get("email_sync_enabled", "false").lower() == "true")
        self.telegram_sync_enabled.setChecked(settings.get("telegram_sync_enabled", "false").lower() == "true")
        self._refresh_sync_status_labels()
        ai_status = self.service.ai_credential_status("openai")
        if ai_status.has_password:
            source = "защищенном хранилище" if ai_status.source == "secure_storage" else ".env fallback"
            self.ai_key_status.setText(f"Сохранен в {source}")
            self.ai_api_key.setPlaceholderText("API key уже сохранен. Введите новый, чтобы заменить.")
        else:
            self.ai_key_status.setText("AI key не сохранен")
            self.ai_api_key.setPlaceholderText("Введите OpenAI API key")
        self._refresh_ai_brain_status_labels()
        self.daily_limit.setValue(int(settings.get("daily_send_limit", "25") or 25))
        self.delay_seconds.setValue(int(settings.get("delay_seconds", "5") or 5))
        self.review_mode.setChecked(settings.get("review_mode", "true").lower() == "true")
        self.follow_up_days.setValue(int(settings.get("follow_up_delay_days", "2") or 2))
        self.safe_mode.setChecked(settings.get("safe_mode", "true").lower() == "true")
        send_mode = settings.get("send_mode", "dry_run")
        index = self.send_mode.findData(send_mode if send_mode in {"dry_run", "live"} else "dry_run")
        self.send_mode.setCurrentIndex(max(index, 0))
        self.real_send_confirm_required.setChecked(
            settings.get("real_send_confirm_required", "true").lower() == "true"
        )
        self.allowed_test_recipient.setText(settings.get("allowed_test_recipient", ""))
        if self.telegram_token_input is not None:
            self.telegram_token_input.clear()
        if self.telegram_default_chat_id_input is not None:
            self.telegram_default_chat_id_input.setText(settings.get("telegram_default_test_chat_id", ""))
        if self.telegram_status_label is not None:
            telegram_status = self.service.telegram_credential_status()
            if telegram_status.has_password:
                source = "защищенном хранилище" if telegram_status.source == "secure_storage" else ".env fallback"
                self.telegram_status_label.setText(f"Bot Token сохранен в {source}")
                if self.telegram_token_input is not None:
                    self.telegram_token_input.setPlaceholderText("Bot Token уже сохранен. Введите новый, чтобы заменить.")
            else:
                self.telegram_status_label.setText("Bot Token не сохранен")
                if self.telegram_token_input is not None:
                    self.telegram_token_input.setPlaceholderText("Telegram Bot Token")
        selected_profile = self._populate_profiles(settings)
        if selected_profile:
            self.profile_name.setText(str(selected_profile.get("profile_name") or ""))
            self.sender_email.setText(str(selected_profile.get("email") or ""))
        else:
            self.profile_name.setText("")
            self.sender_email.setText(settings.get("sender_email", ""))
        credential_status = self.service.gmail_credential_status(self.sender_email.text().strip())
        if credential_status.has_password:
            source = (
                "защищенном хранилище"
                if credential_status.source == "secure_storage"
                else ".env fallback"
            )
            self.password_status.setText(f"Сохранен в {source}")
            self.app_password.setPlaceholderText("Пароль уже сохранен. Введите новый, чтобы заменить.")
        else:
            self.password_status.setText("Не сохранен")
            self.app_password.setPlaceholderText("Введите Gmail App Password")
        self._sync_mode_buttons()
        self._sync_status_cards()
        self._loading = False

    def _populate_profiles(self, settings: dict[str, str]) -> dict[str, Any] | None:
        profiles = self.service.list_gmail_profiles()
        active_id = settings.get("active_gmail_profile_id", "")
        preferred_id = self._selected_profile_id or (int(active_id) if str(active_id).isdigit() else None)
        selected_profile: dict[str, Any] | None = None
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        for profile in profiles:
            profile_id = int(profile["id"])
            active = int(profile.get("is_active") or 0) == 1
            password_state = "Подключен" if profile.get("has_password") else "Нет пароля"
            check_state = {
                "connected": "Проверен",
                "failed": "Ошибка",
            }.get(str(profile.get("last_check_status") or ""), "Не проверен")
            active_state = " • Активный" if active else ""
            item = QListWidgetItem(
                f"{profile.get('profile_name') or 'Gmail'}\n"
                f"{profile.get('email')} • {password_state} • {check_state}{active_state}"
            )
            item.setData(Qt.ItemDataRole.UserRole, profile_id)
            self.profile_list.addItem(item)
            if preferred_id == profile_id or (preferred_id is None and active):
                selected_profile = profile
                self.profile_list.setCurrentItem(item)
        self.profile_list.blockSignals(False)
        if selected_profile:
            self._selected_profile_id = int(selected_profile["id"])
        elif profiles:
            selected_profile = profiles[0]
            self._selected_profile_id = int(selected_profile["id"])
            self.profile_list.setCurrentRow(0)
        else:
            self._selected_profile_id = None
        return selected_profile

    def _on_profile_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if self._loading or current is None:
            return
        profile_id = int(current.data(Qt.ItemDataRole.UserRole))
        profile = self.service.gmail_profiles.get_profile(profile_id)
        if not profile:
            return
        self._selected_profile_id = profile_id
        self.profile_name.setText(str(profile.get("profile_name") or ""))
        self.sender_email.setText(str(profile.get("email") or ""))
        self.app_password.clear()
        if profile.get("has_password"):
            self.password_status.setText("Сохранен в защищенном хранилище")
            self.app_password.setPlaceholderText("Пароль уже сохранен. Введите новый, чтобы заменить.")
        else:
            self.password_status.setText("Не сохранен")
            self.app_password.setPlaceholderText("Введите Gmail App Password")
        self._sync_status_cards()

    def _set_send_mode(self, mode: str) -> None:
        index = self.send_mode.findData(mode)
        if index >= 0:
            self.send_mode.setCurrentIndex(index)
        self._sync_mode_buttons()

    def _sync_mode_buttons(self, *_args) -> None:
        mode = self.send_mode.currentData() or "dry_run"
        self.dry_run_mode_button.setChecked(mode == "dry_run")
        self.live_mode_button.setChecked(mode == "live")
        if mode == "live":
            self.dry_run_mode_button.setStyleSheet("")
            self.live_mode_button.setStyleSheet(
                f"background: {COLORS['amber_soft']}; color: {COLORS['amber']}; "
                "border-color: #F5D49B;"
            )
        else:
            self.live_mode_button.setStyleSheet("")
            self.dry_run_mode_button.setStyleSheet(
                f"background: {COLORS['green_soft']}; color: {COLORS['green']}; "
                "border-color: #CDEFD8;"
            )
        self._sync_status_cards()

    def _sync_status_cards(self) -> None:
        credential_status = self.service.gmail_credential_status(self.sender_email.text().strip())
        has_password = credential_status.has_password
        has_sender = bool(self.sender_email.text().strip())
        if has_password and has_sender:
            self.gmail_state_label.setText("Почта подключена")
            self.gmail_state_label.setStyleSheet(
                f"background: {COLORS['green_soft']}; color: {COLORS['green']}; "
                "border-radius: 12px; padding: 7px 10px; font-weight: 750;"
            )
        elif has_password:
            self.gmail_state_label.setText("Добавьте email отправителя")
            self.gmail_state_label.setStyleSheet(
                f"background: {COLORS['amber_soft']}; color: {COLORS['amber']}; "
                "border-radius: 12px; padding: 7px 10px; font-weight: 750;"
            )
        else:
            self.gmail_state_label.setText("Почта пока не подключена")
            self.gmail_state_label.setStyleSheet(
                f"background: {COLORS['amber_soft']}; color: {COLORS['amber']}; "
                "border-radius: 12px; padding: 7px 10px; font-weight: 750;"
            )

        mode = self.send_mode.currentData() or "dry_run"
        if mode == "live":
            self.send_mode_state_label.setText("Боевой режим: письма реально отправляются через Gmail")
            self.send_mode_state_label.setStyleSheet(
                f"background: {COLORS['amber_soft']}; color: {COLORS['amber']}; "
                "border-radius: 12px; padding: 7px 10px; font-weight: 750;"
            )
        else:
            self.send_mode_state_label.setText("Безопасный тестовый режим: реальные письма не отправляются")
            self.send_mode_state_label.setStyleSheet(
                f"background: {COLORS['green_soft']}; color: {COLORS['green']}; "
                "border-radius: 12px; padding: 7px 10px; font-weight: 750;"
            )

    def _settings_values(self) -> dict[str, str]:
        return {
            "smtp_host": self.smtp_host.text().strip() or "smtp.gmail.com",
            "smtp_port": str(self.smtp_port.value()),
            "sender_email": self.sender_email.text().strip(),
            "daily_send_limit": str(self.daily_limit.value()),
            "delay_seconds": str(self.delay_seconds.value()),
            "review_mode": "true" if self.review_mode.isChecked() else "false",
            "follow_up_delay_days": str(self.follow_up_days.value()),
            "safe_mode": "true" if self.safe_mode.isChecked() else "false",
            "send_mode": str(self.send_mode.currentData() or "dry_run"),
            "real_send_confirm_required": (
                "true" if self.real_send_confirm_required.isChecked() else "false"
            ),
            "allowed_test_recipient": self.allowed_test_recipient.text().strip(),
            "inbox_sync_mode": str(self.inbox_sync_mode.currentData() or "manual"),
            "inbox_sync_interval_minutes": str(self.inbox_sync_interval.value()),
            "email_sync_enabled": "true" if self.email_sync_enabled.isChecked() else "false",
            "telegram_sync_enabled": "true" if self.telegram_sync_enabled.isChecked() else "false",
            "web_enrichment_max_contacts_per_batch": str(self.web_enrichment_max_contacts.value()),
            "web_enrichment_max_pages": str(self.web_enrichment_max_pages.value()),
            "web_enrichment_timeout_seconds": str(self.web_enrichment_timeout.value()),
            "web_enrichment_cache_ttl_days": str(self.web_enrichment_cache_ttl.value()),
            "web_enrichment_respect_robots": "true" if self.web_enrichment_respect_robots.isChecked() else "false",
        }

    def save(self, show_message: bool = True) -> None:
        values = self._settings_values()
        try:
            self.service.save_settings(values)
        except Exception as exc:
            QMessageBox.critical(self, "Настройки", str(exc))
            return
        if show_message:
            QMessageBox.information(self, "Настройки", "Настройки сохранены.")
        self.refresh_callback()

    def add_profile(self) -> None:
        self._selected_profile_id = None
        self.profile_list.clearSelection()
        self.profile_name.clear()
        self.sender_email.clear()
        self.app_password.clear()
        self.password_status.setText("Новый профиль")
        self.gmail_state_label.setText("Введите Gmail address и App Password")
        self.profile_name.setFocus()

    def save_gmail_credentials(self) -> None:
        values = self._settings_values()
        password = self.app_password.text().strip()
        sender = values["sender_email"]
        name = self.profile_name.text().strip() or "Основной"
        try:
            self.service.save_settings(values)
            if self._selected_profile_id:
                profile = self.service.update_gmail_profile(
                    self._selected_profile_id,
                    name=name,
                    email=sender,
                    password=password or None,
                )
                backend_name = profile.get("credential_backend") or "secure storage"
                if int(profile.get("is_active") or 0):
                    self.service.set_active_gmail_profile(int(profile["id"]))
                self.app_password.clear()
                QMessageBox.information(
                    self,
                    "Gmail",
                    f"Профиль Gmail сохранен ({backend_name}).",
                )
            elif password:
                profile = self.service.create_gmail_profile(name, sender, password)
                self._selected_profile_id = int(profile["id"])
                backend_name = profile.get("credential_backend") or "secure storage"
                self.app_password.clear()
                QMessageBox.information(
                    self,
                    "Gmail",
                    f"Профиль Gmail сохранен ({backend_name}).",
                )
            elif not self.service.gmail_credential_status(sender).has_password:
                QMessageBox.warning(
                    self,
                    "Gmail",
                    "Введите Gmail App Password, чтобы создать профиль.",
                )
                return
            else:
                QMessageBox.information(self, "Gmail", "Gmail address сохранен.")
        except Exception as exc:
            QMessageBox.critical(self, "Gmail", user_safe_error(exc))
            return
        self.refresh_callback()

    def save_ai_settings(self) -> None:
        provider = str(self.ai_provider.currentData() or "off")
        model = self.ai_model.text().strip() or "gpt-4.1-mini"
        api_key = self.ai_api_key.text().strip()
        try:
            backend_name = self.service.save_ai_settings(
                provider=provider,
                model=model,
                api_key=api_key,
                max_drafts_per_batch=self.ai_max_drafts.value(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "AI Assist", user_safe_error(exc))
            return
        self.ai_api_key.clear()
        QMessageBox.information(self, "AI Assist", f"AI settings сохранены ({backend_name}).")
        self.refresh_callback()

    def check_ai_connection(self) -> None:
        provider = str(self.ai_provider.currentData() or "off")
        model = self.ai_model.text().strip() or "gpt-4.1-mini"
        api_key = self.ai_api_key.text().strip() or None
        self._run_task(
            lambda: self.service.check_ai_connection(
                provider=provider,
                model=model,
                api_key_override=api_key,
            ),
            self._show_ai_check_result,
        )

    def _show_ai_check_result(self, result) -> None:
        if result.ok:
            self.ai_key_status.setText("AI подключен")
            self.ai_key_status.setStyleSheet(
                f"background: {COLORS['green_soft']}; color: {COLORS['green']}; "
                "border-radius: 12px; padding: 7px 10px; font-weight: 750;"
            )
            QMessageBox.information(self, "AI Assist", user_safe_error(result.message))
        else:
            self.ai_key_status.setText(user_safe_error(result.message))
            self.ai_key_status.setStyleSheet(
                f"background: {COLORS['amber_soft']}; color: {COLORS['amber']}; "
                "border-radius: 12px; padding: 7px 10px; font-weight: 750;"
            )
            QMessageBox.warning(self, "AI Assist", user_safe_error(result.message))

    def save_research_brain_settings(self) -> None:
        self._save_ai_brain_settings(
            "research",
            self.research_brain_provider,
            self.research_brain_model,
            self.research_brain_api_key,
        )

    def save_writer_brain_settings(self) -> None:
        self._save_ai_brain_settings(
            "writer",
            self.writer_brain_provider,
            self.writer_brain_model,
            self.writer_brain_api_key,
        )

    def _save_ai_brain_settings(
        self,
        brain: str,
        provider_widget: QComboBox,
        model_widget: QLineEdit,
        api_key_widget: QLineEdit,
    ) -> None:
        provider = str(provider_widget.currentData() or "off")
        model = model_widget.text().strip() or "gpt-4.1-mini"
        api_key = api_key_widget.text().strip()
        try:
            backend_name = self.service.save_ai_brain_settings(
                brain,
                provider=provider,
                model=model,
                api_key=api_key,
            )
        except Exception as exc:
            QMessageBox.critical(self, "AI Assist", user_safe_error(exc))
            return
        api_key_widget.clear()
        self._refresh_ai_brain_status_labels()
        label = "Research Brain" if brain == "research" else "Writer Brain"
        QMessageBox.information(self, "AI Assist", f"{label} settings сохранены ({backend_name}).")
        self.refresh_callback()

    def check_research_brain_connection(self) -> None:
        self._check_ai_brain_connection(
            "research",
            self.research_brain_provider,
            self.research_brain_model,
            self.research_brain_api_key,
            self.research_brain_status,
        )

    def check_writer_brain_connection(self) -> None:
        self._check_ai_brain_connection(
            "writer",
            self.writer_brain_provider,
            self.writer_brain_model,
            self.writer_brain_api_key,
            self.writer_brain_status,
        )

    def _check_ai_brain_connection(
        self,
        brain: str,
        provider_widget: QComboBox,
        model_widget: QLineEdit,
        api_key_widget: QLineEdit,
        status_label: QLabel,
    ) -> None:
        provider = str(provider_widget.currentData() or "off")
        model = model_widget.text().strip() or "gpt-4.1-mini"
        api_key = api_key_widget.text().strip() or None
        self._run_task(
            lambda: self.service.check_ai_brain_connection(
                brain,
                provider=provider,
                model=model,
                api_key_override=api_key,
            ),
            lambda result: self._show_ai_brain_check_result(brain, status_label, result),
        )

    def _show_ai_brain_check_result(self, brain: str, status_label: QLabel, result) -> None:
        label = "Research Brain" if brain == "research" else "Writer Brain"
        if result.ok:
            status_label.setText(f"{label} подключен")
            status_label.setStyleSheet(
                f"background: {COLORS['green_soft']}; color: {COLORS['green']}; "
                "border-radius: 12px; padding: 7px 10px; font-weight: 750;"
            )
            QMessageBox.information(self, "AI Assist", user_safe_error(result.message))
        else:
            status_label.setText(user_safe_error(result.message))
            status_label.setStyleSheet(
                f"background: {COLORS['amber_soft']}; color: {COLORS['amber']}; "
                "border-radius: 12px; padding: 7px 10px; font-weight: 750;"
            )
            QMessageBox.warning(self, "AI Assist", user_safe_error(result.message))

    def delete_selected_profile(self) -> None:
        if not self._selected_profile_id:
            QMessageBox.information(self, "Gmail", "Выберите профиль для удаления.")
            return
        try:
            self.service.delete_gmail_profile(self._selected_profile_id)
        except Exception as exc:
            QMessageBox.critical(self, "Gmail", user_safe_error(exc))
            return
        self._selected_profile_id = None
        QMessageBox.information(self, "Gmail", "Профиль удален.")
        self.refresh_callback()

    def set_selected_profile_active(self) -> None:
        if not self._selected_profile_id:
            QMessageBox.information(self, "Gmail", "Выберите профиль отправителя.")
            return
        try:
            self.service.set_active_gmail_profile(self._selected_profile_id)
        except Exception as exc:
            QMessageBox.critical(self, "Gmail", user_safe_error(exc))
            return
        QMessageBox.information(self, "Gmail", "Активный отправитель выбран.")
        self.refresh_callback()

    def check_gmail_connection(self) -> None:
        try:
            self.service.save_settings(self._settings_values())
        except Exception as exc:
            QMessageBox.critical(self, "Проверка Gmail", user_safe_error(exc))
            return

        sender = self.sender_email.text().strip()
        password = self.app_password.text().strip() or None
        self._run_task(
            lambda: self.service.check_gmail_connection(
                sender_email=sender,
                app_password=password,
            ),
            self._show_check_result,
        )

    def sync_email_now(self) -> None:
        try:
            self.service.save_settings(self._settings_values())
        except Exception as exc:
            QMessageBox.critical(self, "Email sync", user_safe_error(exc))
            return
        self._run_task(
            lambda: self.service.sync_email_replies(self.service.default_campaign_id()),
            self._show_email_sync_result,
        )

    def sync_telegram_now(self) -> None:
        try:
            self.service.save_settings(self._settings_values())
        except Exception as exc:
            QMessageBox.critical(self, "Telegram sync", user_safe_error(exc))
            return
        self._run_task(
            lambda: self.service.sync_telegram_replies(self.service.default_campaign_id()),
            self._show_telegram_sync_result,
        )

    def _show_email_sync_result(self, result) -> None:
        self.email_sync_status_label.setText(user_safe_error(result.message))
        QMessageBox.information(self, "Email sync", user_safe_error(result.message))
        self.refresh_callback()

    def _show_telegram_sync_result(self, result) -> None:
        self.telegram_sync_status_label.setText(user_safe_error(result.message))
        QMessageBox.information(self, "Telegram sync", user_safe_error(result.message))
        self.refresh_callback()

    def _refresh_sync_status_labels(self) -> None:
        active_sender = self.service.active_sender_email()
        email_state = self.service.inbox_sync_state("email", active_sender)
        telegram_state = self.service.inbox_sync_state("telegram", "telegram_bot")
        self.email_sync_status_label.setText(
            f"Email sync: {email_state.get('status', 'never')} • "
            f"last={email_state.get('last_sync_at') or 'never'} • uid={email_state.get('last_synced_uid') or '-'}"
        )
        self.telegram_sync_status_label.setText(
            f"Telegram sync: {telegram_state.get('status', 'never')} • "
            f"last={telegram_state.get('last_sync_at') or 'never'} • update={telegram_state.get('last_update_id') or 0}"
        )

    def _refresh_ai_brain_status_labels(self) -> None:
        for brain_name, provider_widget, key_widget, status_label in (
            ("research", self.research_brain_provider, self.research_brain_api_key, self.research_brain_status),
            ("writer", self.writer_brain_provider, self.writer_brain_api_key, self.writer_brain_status),
        ):
            provider = str(provider_widget.currentData() or "openai")
            status = self.service.ai_brain_credential_status(brain_name, provider)
            label = "Research Brain" if brain_name == "research" else "Writer Brain"
            if status.has_password:
                source = "защищенном хранилище" if status.source == "secure_storage" else ".env fallback"
                status_label.setText(f"{label}: key сохранен в {source}")
                key_widget.setPlaceholderText("API key уже сохранен. Введите новый, чтобы заменить.")
            else:
                status_label.setText(f"{label}: key не сохранен")
                key_widget.setPlaceholderText(f"{label} API key")

    def _show_check_result(self, result) -> None:
        if result.ok:
            self.gmail_state_label.setText("Connected")
            self.gmail_state_label.setStyleSheet(
                f"background: {COLORS['green_soft']}; color: {COLORS['green']}; "
                "border-radius: 12px; padding: 7px 10px; font-weight: 750;"
            )
            QMessageBox.information(self, "Проверка Gmail", user_safe_error(result.message))
        else:
            self.gmail_state_label.setText(user_safe_error(result.message))
            self.gmail_state_label.setStyleSheet(
                f"background: {COLORS['amber_soft']}; color: {COLORS['amber']}; "
                "border-radius: 12px; padding: 7px 10px; font-weight: 750;"
            )
            QMessageBox.warning(self, "Проверка Gmail", user_safe_error(result.message))
        self.refresh_callback()

    def _run_task(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
    ) -> None:
        self.check_button.setEnabled(False)
        self.save_credentials_button.setEnabled(False)
        self.check_ai_button.setEnabled(False)
        self.save_ai_button.setEnabled(False)
        self.save_research_brain_button.setEnabled(False)
        self.check_research_brain_button.setEnabled(False)
        self.save_writer_brain_button.setEnabled(False)
        self.check_writer_brain_button.setEnabled(False)
        self.email_sync_now_button.setEnabled(False)
        self.telegram_sync_now_button.setEnabled(False)
        if self.save_telegram_button is not None:
            self.save_telegram_button.setEnabled(False)
        telegram_check = self.channel_check_buttons.get("telegram")
        if telegram_check is not None:
            telegram_check.setEnabled(False)
        self._task_success_handler = on_success
        thread = QThread(self)
        worker = BackgroundWorker(task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(self._handle_task_result)
        worker.error.connect(self._handle_task_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._finish_job(thread, worker))
        self._jobs.append((thread, worker))
        thread.start()

    def _handle_task_result(self, result: Any) -> None:
        if self._task_success_handler:
            self._task_success_handler(result)

    def _handle_task_error(self, message: str) -> None:
        QMessageBox.critical(self, "Проверка Gmail", user_safe_error(message))

    def _finish_job(self, thread: QThread, worker: BackgroundWorker) -> None:
        self._jobs = [job for job in self._jobs if job != (thread, worker)]
        if not self._jobs:
            self._task_success_handler = None
        self.check_button.setEnabled(True)
        self.save_credentials_button.setEnabled(True)
        self.check_ai_button.setEnabled(True)
        self.save_ai_button.setEnabled(True)
        self.save_research_brain_button.setEnabled(True)
        self.check_research_brain_button.setEnabled(True)
        self.save_writer_brain_button.setEnabled(True)
        self.check_writer_brain_button.setEnabled(True)
        self.email_sync_now_button.setEnabled(True)
        self.telegram_sync_now_button.setEnabled(True)
        if self.save_telegram_button is not None:
            self.save_telegram_button.setEnabled(True)
        telegram_check = self.channel_check_buttons.get("telegram")
        if telegram_check is not None:
            telegram_check.setEnabled(True)

    def shutdown(self) -> None:
        for thread, _worker in list(self._jobs):
            if thread.isRunning():
                thread.quit()
                thread.wait(3000)
