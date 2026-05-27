from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QThread, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..background_worker import QueueJobProcessor, QueueWorker
from ..campaign_service import CampaignService
from ..channels import get_channel, list_channels
from ..channels.execution import (
    DRY_RUN,
    MANUAL_ASSIST,
    OFFICIAL_API,
    EXECUTION_MODE_LABELS,
    risk_label,
)
from ..config import IMPORTS_DIR, as_int
from ..excel_importer import is_valid_email
from ..models import CONTACT_STATUSES
from ..platform_actions import open_external_url
from ..queue_service import QueueResult
from .i18n import STATUS_LABELS_RU, status_from_ru, status_to_ru, user_safe_error
from .task_runner import BackgroundWorker
from .theme import (
    COLORS,
    card,
    compact_table_style,
    helper_text,
    section_title,
    set_button_kind,
)


def build_live_send_confirmation_message(
    count: int,
    recipients: list[str],
    sender_email: str = "",
    mode: str = "live",
    channel_display: str = "Email",
    sender_label: str = "",
    warnings: list[str] | None = None,
) -> str:
    recipient_lines = "\n".join(f"- {email}" for email in recipients[:5])
    if not recipient_lines:
        recipient_lines = "- Нет подтвержденных получателей"
    extra = ""
    if count > len(recipients):
        extra = f"\n...и еще {count - len(recipients)}"
    sender_line = (sender_label or sender_email).strip() or "не указан"
    mode_line = "Боевой режим" if mode == "live" else "Тестовый режим"
    intro = (
        "Вы собираетесь отправить реальные сообщения через Telegram Bot API."
        if channel_display == "Telegram"
        else "Вы собираетесь отправить реальные письма через Gmail."
    )
    warning_block = ""
    if warnings:
        warning_lines = "\n".join(f"- {warning}" for warning in warnings[:5])
        warning_block = f"\n\nПредупреждения:\n{warning_lines}"
    return (
        f"{intro}\n\n"
        f"Канал: {channel_display}\n"
        f"Режим: {mode_line}\n"
        f"Будет отправлено: {count} сообщение(я)\n"
        f"От: {sender_line}\n"
        f"Кому:\n{recipient_lines}{extra}{warning_block}\n\n"
        "Продолжить?"
    )


PREVIEW_COLUMNS = [
    ("select", "✓"),
    ("email", "Email"),
    ("subject", "Тема письма"),
    ("generated_message", "Сообщение"),
    ("name", "Имя"),
    ("company", "Компания"),
    ("topic", "Заметка"),
    ("status", "Статус"),
    ("last_error", "Ошибка"),
    ("website", "Сайт"),
    ("social_profile", "Соцсеть / профиль"),
    ("ai_badge", "AI"),
    ("enrichment_status", "Данные"),
    ("channel", "Канал"),
    ("handle", "Профиль / username"),
    ("profile_url", "URL профиля"),
    ("external_id", "ID / chat"),
]

PREVIEW_EDITABLE_COLUMNS = {
    "email",
    "subject",
    "generated_message",
    "name",
    "company",
    "topic",
    "website",
    "social_profile",
    "channel",
    "handle",
    "profile_url",
    "external_id",
    "status",
}


class CampaignView(QWidget):
    def __init__(
        self,
        service: CampaignService,
        active_campaign_id: Callable[[], int],
        set_active_campaign_id: Callable[[int], None],
        selected_contact_ids: Callable[[], list[int]],
        refresh_callback: Callable[[], None],
        add_row_callback: Callable[[], None] | None = None,
        paste_callback: Callable[[], None] | None = None,
        open_settings_callback: Callable[[], None] | None = None,
        delete_rows_callback: Callable[[], None] | None = None,
        save_rows_callback: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.service = service
        self.active_campaign_id = active_campaign_id
        self.set_active_campaign_id = set_active_campaign_id
        self.selected_contact_ids = selected_contact_ids
        self.refresh_callback = refresh_callback
        self.add_row_callback = add_row_callback
        self.paste_callback = paste_callback
        self.open_settings_callback = open_settings_callback
        self.delete_rows_callback = delete_rows_callback
        self.save_rows_callback = save_rows_callback
        self._jobs: list[tuple[QThread, BackgroundWorker]] = []
        self._queue_thread: QThread | None = None
        self._queue_worker: QueueWorker | None = None
        self._current_job_id: int | None = None
        self._current_job_type: str | None = None
        self._updating_preview = False
        self._task_success_handler: Callable[[Any], None] | None = None
        self._task_error_title = "Ошибка"
        self._shutting_down = False
        self.action_map: dict[str, dict[str, str]] = {}

        self.send_mode_label = QLabel("Тестовый режим: письма НЕ отправляются")
        self.send_mode_label.setObjectName("modeBadge")
        self.gmail_status_label = QLabel("● Почта не подключена")
        self.gmail_status_label.setObjectName("gmailStatus")
        self.active_sender_label = QLabel("Отправитель не выбран")
        self.active_sender_label.setObjectName("activeSenderLabel")
        self.active_sender_label.setWordWrap(True)
        self.sender_selector_button = QPushButton("Выбрать отправителя")
        self.sender_selector_button.setObjectName("campaignSenderSelectorButton")
        set_button_kind(self.sender_selector_button, "soft")
        self.sender_selector_button.clicked.connect(self.open_sender_selector)
        self.settings_shortcut_button = QPushButton("Настройки")
        set_button_kind(self.settings_shortcut_button, "soft")
        self.settings_shortcut_button.clicked.connect(self.open_settings)

        self.manual_mode_button = QPushButton("Ручной")
        self.ai_mode_button = QPushButton("AI Assist")
        self.manual_mode_button.setObjectName("campaignManualModeButton")
        self.ai_mode_button.setObjectName("campaignAiModeButton")
        self.manual_mode_button.setCheckable(True)
        self.ai_mode_button.setCheckable(True)
        set_button_kind(self.manual_mode_button, "soft")
        set_button_kind(self.ai_mode_button, "soft")
        self.manual_mode_button.clicked.connect(lambda: self._set_work_mode("manual"))
        self.ai_mode_button.clicked.connect(lambda: self._set_work_mode("ai_assist"))
        self.ai_topic_input = QLineEdit()
        self.ai_topic_input.setObjectName("campaignAiTopicInput")
        self.ai_topic_input.setPlaceholderText("Например: предложить сотрудничество по рекламе")
        self.ai_tone_combo = QComboBox()
        self.ai_tone_combo.setObjectName("campaignAiToneCombo")
        self.ai_tone_combo.addItem("Дружелюбный", "friendly")
        self.ai_tone_combo.addItem("Деловой", "business")
        self.ai_tone_combo.addItem("Короткий", "short")
        self.ai_tone_combo.addItem("Премиальный", "premium")
        self.ai_generation_mode_combo = QComboBox()
        self.ai_generation_mode_combo.setObjectName("campaignAiGenerationModeCombo")
        self.ai_generation_mode_combo.setAccessibleName("campaign.ai_generation_mode")
        self.ai_generation_mode_combo.setProperty("actionId", "campaign.ai_generation_mode")
        self.ai_generation_mode_combo.addItem("Simple AI draft", "simple")
        self.ai_generation_mode_combo.addItem("Research + Writer", "dual_brain")
        self.research_brain_status_label = QLabel("Research Brain: Off")
        self.research_brain_status_label.setObjectName("campaignResearchBrainStatus")
        self.research_brain_status_label.setWordWrap(True)
        self.writer_brain_status_label = QLabel("Writer Brain: Off")
        self.writer_brain_status_label.setObjectName("campaignWriterBrainStatus")
        self.writer_brain_status_label.setWordWrap(True)
        self.ai_drafts_only_checkbox = QCheckBox("Только черновики, без отправки")
        self.ai_drafts_only_checkbox.setObjectName("campaignAiDraftsOnlyCheckbox")
        self.ai_drafts_only_checkbox.setChecked(True)
        self.ai_drafts_only_checkbox.setEnabled(False)
        self.web_enrichment_checkbox = QCheckBox("Обогатить данные из сайта")
        self.web_enrichment_checkbox.setObjectName("campaignWebEnrichmentCheckbox")
        self.web_enrichment_checkbox.setToolTip("GET-only public pages, robots-aware, cached. Без login/JS/captcha.")
        self.enrich_contacts_button = QPushButton("Проверить данные получателей")
        self.enrich_contacts_button.setObjectName("campaignEnrichContactsButton")
        set_button_kind(self.enrich_contacts_button, "soft")
        self.enrich_contacts_button.clicked.connect(self.enrich_contacts)
        self.ai_generate_button = QPushButton("Сгенерировать черновики")
        self.ai_generate_button.setObjectName("campaignAiGenerateButton")
        set_button_kind(self.ai_generate_button, "primary")
        self.ai_generate_button.clicked.connect(self.generate_ai_drafts)
        self.ai_mode_panel: QFrame | None = None
        self.channel_selector = QComboBox()
        self.channel_selector.setObjectName("campaignChannelSelector")
        for channel in list_channels():
            self.channel_selector.addItem(channel.display_name, channel.channel_id)
        self.channel_selector.currentIndexChanged.connect(self._on_channel_changed)
        self.channel_notice_label = QLabel("")
        self.channel_notice_label.setObjectName("channelSafetyNotice")
        self.channel_notice_label.setWordWrap(True)
        self.execution_mode_combo = QComboBox()
        self.execution_mode_combo.setObjectName("campaignExecutionModeCombo")
        self.execution_mode_combo.setAccessibleName("campaign.execution_mode")
        self.execution_mode_combo.currentIndexChanged.connect(self._on_execution_mode_changed)
        self.execution_risk_label = QLabel("Risk: Low")
        self.execution_risk_label.setObjectName("campaignExecutionRiskLabel")
        self.execution_risk_label.setWordWrap(True)

        self.add_row_button = QPushButton("+ Добавить строку")
        self.paste_button = QPushButton("Вставить из буфера")
        self.import_button = QPushButton("Загрузить Excel/CSV")
        self.example_button = QPushButton("Скачать пример Excel")
        self.generate_button = QPushButton("Подготовить сообщения")
        self.approve_button = QPushButton("Подтвердить выбранные")
        self.reapprove_button = QPushButton("Вернуть к отправке")
        self.send_button = QPushButton("Отправить подтвержденные")
        self.followup_button = QPushButton("Показать повторные письма")
        self.export_button = QPushButton("Скачать отчет")
        self.quick_generate_button = QPushButton("Подготовить сообщения")
        self.quick_approve_button = QPushButton("Подтвердить")
        self.quick_send_button = QPushButton("Тестовая отправка")
        self.quick_export_button = QPushButton("Отчет")
        self.delete_selected_button = QPushButton("Удалить выбранные")
        self.save_changes_button = QPushButton("Сохранить изменения")
        set_button_kind(self.add_row_button, "primary")
        set_button_kind(self.paste_button, "soft")
        set_button_kind(self.import_button, "soft")
        set_button_kind(self.example_button, "soft")
        set_button_kind(self.generate_button, "soft")
        set_button_kind(self.approve_button, "soft")
        set_button_kind(self.reapprove_button, "soft")
        set_button_kind(self.send_button, "primary")
        set_button_kind(self.export_button, "soft")
        set_button_kind(self.quick_generate_button, "primary")
        set_button_kind(self.quick_approve_button, "soft")
        set_button_kind(self.quick_send_button, "soft")
        set_button_kind(self.quick_export_button, "text")
        set_button_kind(self.delete_selected_button, "danger")
        set_button_kind(self.save_changes_button, "soft")
        self.quick_generate_button.setMinimumHeight(34)
        self.quick_generate_button.setMaximumHeight(36)
        self.quick_approve_button.setMinimumHeight(32)
        self.quick_approve_button.setMaximumHeight(34)
        self.quick_send_button.setMinimumHeight(32)
        self.quick_send_button.setMaximumHeight(34)
        self.quick_export_button.setMinimumHeight(30)
        self.quick_export_button.setMaximumHeight(34)
        self.quick_generate_button.setMaximumWidth(210)
        self.quick_approve_button.setMaximumWidth(132)
        self.quick_send_button.setMaximumWidth(154)
        self.quick_export_button.setMaximumWidth(78)

        self.add_row_button.clicked.connect(self.add_row)
        self.paste_button.clicked.connect(self.paste_rows)
        self.import_button.clicked.connect(self.import_file)
        self.example_button.clicked.connect(self.download_example_excel)
        self.generate_button.clicked.connect(self.generate_messages)
        self.approve_button.clicked.connect(self.approve_selected)
        self.reapprove_button.clicked.connect(self.reapprove_selected)
        self.send_button.clicked.connect(self.send_approved)
        self.followup_button.clicked.connect(self.show_due_followups)
        self.export_button.clicked.connect(self.export_report)
        self.quick_generate_button.clicked.connect(self.generate_messages)
        self.quick_approve_button.clicked.connect(self.approve_selected)
        self.quick_send_button.clicked.connect(self.send_approved)
        self.quick_export_button.clicked.connect(self.export_report)
        self.delete_selected_button.clicked.connect(self.delete_rows)
        self.save_changes_button.clicked.connect(self.save_rows)

        self.stats_labels: dict[str, QLabel] = {}
        self.queue_stat_labels: dict[str, QLabel] = {}
        self.campaign_search_input = QLineEdit()
        self.campaign_search_input.setPlaceholderText("Поиск по email, имени, компании…")
        self.campaign_search_input.textChanged.connect(self._refresh_recipient_preview)
        self.preview_total_label = QLabel("0 получателей")
        self.preview_total_label.setObjectName("muted")
        self.preview_selected_label = QLabel("• 0 выбрано")
        self.preview_selected_label.setObjectName("muted")
        self.action_summary_label = QLabel("0 получателей • 0 подтверждено • тестовый режим")
        self.action_summary_label.setObjectName("muted")
        self.action_summary_label.setWordWrap(True)
        self.action_summary_label.setMinimumWidth(160)
        self.action_summary_label.setMaximumWidth(260)
        self.feedback_label = QLabel("Готово")
        self.feedback_label.setObjectName("muted")
        self.feedback_label.setWordWrap(False)
        self.feedback_label.setToolTip("Готово к работе")
        self.loading_label = QLabel("Нет активных действий")
        self.loading_label.setObjectName("muted")
        self.loading_label.setWordWrap(True)
        self.loading_label.setVisible(False)
        self.queue_health_label = QLabel("Ошибок нет")
        self.queue_health_label.setObjectName("queueTinyPill")
        self.queue_health_label.setWordWrap(True)
        self.queue_health_label.setMaximumHeight(22)
        self.recipient_preview_table = QTableWidget(0, len(PREVIEW_COLUMNS))
        self.recipient_preview_table.setObjectName("campaignRecipientPreviewTable")
        self.recipient_preview_table.setHorizontalHeaderLabels(
            [label for _, label in PREVIEW_COLUMNS]
        )
        compact_table_style(self.recipient_preview_table)
        self.recipient_preview_table.setMinimumWidth(0)
        self.recipient_preview_table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.recipient_preview_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.recipient_preview_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.recipient_preview_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.recipient_preview_table.itemChanged.connect(self._on_preview_item_changed)
        self.recipient_preview_table.itemSelectionChanged.connect(self.update_selected_counter)
        self.recipient_preview_table.setMinimumHeight(250)
        self.recipient_preview_table.setColumnWidth(0, 34)
        self.recipient_preview_table.setColumnWidth(1, 145)
        self.recipient_preview_table.setColumnWidth(2, 140)
        self.recipient_preview_table.setColumnWidth(3, 220)
        self.recipient_preview_table.setColumnWidth(4, 72)
        self.recipient_preview_table.setColumnWidth(5, 92)
        self.recipient_preview_table.setColumnWidth(6, 82)
        self.recipient_preview_table.setColumnWidth(7, 92)
        self.recipient_preview_table.setColumnWidth(8, 90)
        self.recipient_preview_table.setColumnWidth(9, 150)
        self.recipient_preview_table.setColumnWidth(10, 170)
        self.recipient_preview_table.setColumnWidth(11, 58)
        self.recipient_preview_table.setColumnWidth(12, 90)
        self.recipient_preview_table.setColumnWidth(13, 150)
        self.recipient_preview_table.setColumnWidth(14, 170)
        self.recipient_preview_table.setColumnWidth(15, 120)
        self.recipient_preview_table.setColumnWidth(16, 120)

        self.worker_status_label = QLabel("Система: готова")
        self.current_job_label = QLabel("Процесс: нет задач")
        self.current_contact_label = QLabel("Сейчас обрабатывается: никто")
        self.current_contact_label.setVisible(False)
        self.queue_stats_label = QLabel("Ожидает 0 • В работе 0 • Завершено 0 • Ошибки 0")
        self.eta_label = QLabel("Примерное время: позже")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("compactQueueProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.refresh_queue_button = QPushButton("Обновить")
        self.cancel_current_button = QPushButton("Остановить")
        self.retry_failed_button = QPushButton("Повторить")
        self.clear_completed_button = QPushButton("Очистить")
        set_button_kind(self.refresh_queue_button, "soft")
        set_button_kind(self.cancel_current_button, "ghost")
        set_button_kind(self.retry_failed_button, "text")
        set_button_kind(self.clear_completed_button, "text")
        self.refresh_queue_button.setMinimumHeight(28)
        self.refresh_queue_button.setMaximumHeight(30)
        self.refresh_queue_button.setMaximumWidth(92)
        self.cancel_current_button.setMinimumHeight(28)
        self.cancel_current_button.setMaximumHeight(30)
        self.cancel_current_button.setMaximumWidth(108)
        self.retry_failed_button.setMinimumHeight(28)
        self.retry_failed_button.setMaximumHeight(30)
        self.retry_failed_button.setMaximumWidth(84)
        self.clear_completed_button.setMinimumHeight(28)
        self.clear_completed_button.setMaximumHeight(30)
        self.clear_completed_button.setMaximumWidth(84)
        self.refresh_queue_button.clicked.connect(self.refresh_queue_panel)
        self.cancel_current_button.clicked.connect(self.cancel_current_job)
        self.retry_failed_button.clicked.connect(self.retry_failed_jobs)
        self.clear_completed_button.clicked.connect(self.clear_completed_jobs)

        self.manual_assist_panel: QFrame | None = None
        self.manual_assist_recipient_label = QLabel("Manual Assist: выберите получателя")
        self.manual_assist_recipient_label.setObjectName("campaignManualAssistRecipientLabel")
        self.manual_assist_recipient_label.setWordWrap(True)
        self.manual_assist_message_preview = QTextEdit()
        self.manual_assist_message_preview.setObjectName("campaignManualAssistMessagePreview")
        self.manual_assist_message_preview.setReadOnly(True)
        self.manual_assist_message_preview.setMinimumHeight(74)
        self.manual_assist_message_preview.setMaximumHeight(120)
        self.copy_manual_message_button = QPushButton("Скопировать сообщение")
        self.copy_manual_message_button.setObjectName("campaignManualAssistCopyButton")
        self.open_manual_profile_button = QPushButton("Открыть профиль")
        self.open_manual_profile_button.setObjectName("campaignManualAssistOpenProfileButton")
        self.mark_manual_sent_button = QPushButton("Отметить как отправлено вручную")
        self.mark_manual_sent_button.setObjectName("campaignManualAssistMarkSentButton")
        set_button_kind(self.copy_manual_message_button, "soft")
        set_button_kind(self.open_manual_profile_button, "soft")
        set_button_kind(self.mark_manual_sent_button, "primary")
        self.copy_manual_message_button.setObjectName("campaignManualAssistCopyButton")
        self.open_manual_profile_button.setObjectName("campaignManualAssistOpenProfileButton")
        self.mark_manual_sent_button.setObjectName("campaignManualAssistMarkSentButton")
        self.copy_manual_message_button.clicked.connect(self.copy_manual_message)
        self.open_manual_profile_button.clicked.connect(self.open_manual_profile)
        self.mark_manual_sent_button.clicked.connect(self.mark_manual_sent)
        self._manual_assist_contact_id: int | None = None
        self._manual_assist_profile_url = ""
        self._register_action_map()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 4)
        layout.setSpacing(6)
        layout.addWidget(self._build_header())
        layout.addLayout(self._build_workflow_steps())
        layout.addWidget(self._build_work_mode_panel())
        layout.addWidget(self._build_recipients_card(), 1)
        self.manual_assist_panel = self._build_manual_assist_panel()
        layout.addWidget(self.manual_assist_panel)
        self.action_bar = self._build_action_bar()
        layout.addWidget(self.action_bar)
        self.queue_card = self._build_queue_card()
        layout.addWidget(self.queue_card)

    def refresh(self) -> None:
        active_id = self.active_campaign_id()
        stats = self.service.stats(active_id)
        for key, label in self.stats_labels.items():
            label.setText(str(stats.get(key, 0)))
        settings = self.service.settings()
        send_mode = settings.get("send_mode", "dry_run")
        work_mode = settings.get("work_mode", "manual")
        channel_id = settings.get("active_channel", "email")
        selector_index = self.channel_selector.findData(channel_id)
        self.channel_selector.blockSignals(True)
        self.channel_selector.setCurrentIndex(max(selector_index, 0))
        self.channel_selector.blockSignals(False)
        self._sync_channel_notice()
        self._sync_execution_mode_options()
        self._sync_work_mode(work_mode)
        if not self.ai_topic_input.hasFocus():
            self.ai_topic_input.setText(settings.get("ai_campaign_topic", ""))
        tone_index = self.ai_tone_combo.findData(settings.get("ai_tone", "friendly"))
        self.ai_tone_combo.setCurrentIndex(max(tone_index, 0))
        mode_index = self.ai_generation_mode_combo.findData(settings.get("ai_generation_mode", "simple"))
        self.ai_generation_mode_combo.setCurrentIndex(max(mode_index, 0))
        self.web_enrichment_checkbox.setChecked(
            str(settings.get("web_enrichment_enabled", "false")).lower() == "true"
        )
        research_ready = self.service.ai_brain_credential_status(
            "research",
            settings.get("ai_research_provider", "off"),
        ).has_password
        writer_ready = self.service.ai_brain_credential_status(
            "writer",
            settings.get("ai_writer_provider", "off"),
        ).has_password
        self.research_brain_status_label.setText("Research Brain: готов" if research_ready else "Research Brain: нужен API key")
        self.writer_brain_status_label.setText("Writer Brain: готов" if writer_ready else "Writer Brain: нужен API key")
        active_sender = self.service.active_sender_email()
        self.active_sender_label.setText(
            f"Активный отправитель: {active_sender}" if active_sender else "Отправитель не выбран"
        )
        if send_mode == "live":
            self.send_mode_label.setText("Боевой режим: письма будут отправлены через Gmail")
            self.quick_send_button.setText("Отправить")
            self.send_mode_label.setStyleSheet(
                f"background: {COLORS['amber_soft']}; color: {COLORS['amber']}; "
                "border-radius: 14px; padding: 7px 12px; font-weight: 800;"
            )
        else:
            self.send_mode_label.setText("Тестовый режим: письма НЕ отправляются")
            self.quick_send_button.setText("Тестовая отправка")
            self.send_mode_label.setStyleSheet(
                f"background: {COLORS['green_soft']}; color: {COLORS['green']}; "
                "border-radius: 14px; padding: 7px 12px; font-weight: 800;"
            )
        if active_sender and self.service.gmail_credential_status(active_sender).has_password:
            self.gmail_status_label.setText("● Почта подключена")
            self.gmail_status_label.setStyleSheet(
                f"background: {COLORS['green_soft']}; color: {COLORS['green']}; "
                "border-radius: 14px; padding: 7px 12px; font-weight: 800;"
            )
        else:
            self.gmail_status_label.setText("● Почта не подключена")
            self.gmail_status_label.setStyleSheet(
                f"background: {COLORS['red_soft']}; color: {COLORS['red']}; "
                "border-radius: 14px; padding: 7px 12px; font-weight: 800;"
            )
        self.action_summary_label.setText(
            f"{stats.get('total', 0)} получателей • "
            f"{stats.get('approved', 0)} подтверждено • "
            f"{'боевой режим' if send_mode == 'live' else 'тестовый режим'}"
        )
        self._refresh_recipient_preview()
        self.refresh_queue_panel()

    def add_row(self) -> None:
        if self.add_row_callback:
            self.add_row_callback()

    def paste_rows(self) -> None:
        if self.paste_callback:
            self.paste_callback()

    def open_settings(self) -> None:
        if self.open_settings_callback:
            self.open_settings_callback()

    def delete_rows(self) -> None:
        if self.delete_rows_callback:
            self.delete_rows_callback()

    def save_rows(self) -> None:
        if self.save_rows_callback:
            self.save_rows_callback()
            self.show_feedback("Изменения сохранены.")

    def open_sender_selector(self) -> None:
        profiles = self.service.list_gmail_profiles()
        if not profiles:
            QMessageBox.information(
                self,
                "Выбрать отправителя",
                "Сначала добавьте Gmail-профиль во вкладке «Аккаунты и настройки».",
            )
            self.open_settings()
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Выбрать отправителя")
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = section_title("Gmail-профили")
        hint = helper_text("Выберите, с какого Gmail-аккаунта отправлять письма. Получатели останутся из таблицы.")
        profile_list = QListWidget()
        profile_list.setObjectName("campaignSenderProfileList")
        profile_list.setMinimumHeight(150)
        for profile in profiles:
            status = "Активный" if int(profile.get("is_active") or 0) else "Не активный"
            check = "Подключен" if profile.get("has_password") else "Нет пароля"
            item = QListWidgetItem(
                f"{profile.get('profile_name') or 'Gmail'}\n{profile.get('email')} • {status} • {check}"
            )
            item.setData(Qt.ItemDataRole.UserRole, int(profile["id"]))
            profile_list.addItem(item)
            if int(profile.get("is_active") or 0):
                profile_list.setCurrentItem(item)

        button_row = QHBoxLayout()
        make_active = QPushButton("Сделать активным")
        check_button = QPushButton("Проверить подключение")
        close_button = QPushButton("Закрыть")
        set_button_kind(make_active, "primary")
        set_button_kind(check_button, "soft")
        set_button_kind(close_button, "text")

        def selected_profile_id() -> int | None:
            item = profile_list.currentItem()
            return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

        def activate() -> None:
            profile_id = selected_profile_id()
            if profile_id is None:
                return
            self.service.set_active_gmail_profile(profile_id)
            self.show_feedback("Активный отправитель выбран.")
            dialog.accept()
            self.refresh_callback()

        def check_profile() -> None:
            profile_id = selected_profile_id()
            if profile_id is None:
                return
            result = self.service.check_gmail_profile_connection(profile_id)
            if result.ok:
                QMessageBox.information(dialog, "Проверка Gmail", user_safe_error(result.message))
            else:
                QMessageBox.warning(dialog, "Проверка Gmail", user_safe_error(result.message))
            self.refresh_callback()

        make_active.clicked.connect(activate)
        check_button.clicked.connect(check_profile)
        close_button.clicked.connect(dialog.reject)
        button_row.addWidget(make_active)
        button_row.addWidget(check_button)
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(profile_list)
        layout.addLayout(button_row)
        dialog.exec()

    def _register_action_map(self) -> None:
        """Developer-visible clickability map for smoke tests and QA diagnostics."""
        actions: list[tuple[str, QPushButton, str, str]] = [
            ("campaign.add_row", self.add_row_button, "add_row", "Добавить черновую строку на главной"),
            ("campaign.paste_rows", self.paste_button, "paste_rows", "Вставить получателей из буфера"),
            ("campaign.import_file", self.import_button, "import_file", "Открыть импорт Excel/CSV"),
            ("campaign.example_excel", self.example_button, "download_example_excel", "Создать пример Excel"),
            ("campaign.generate_messages", self.quick_generate_button, "generate_messages", "Поставить подготовку сообщений в очередь"),
            ("campaign.ai_generate_drafts", self.ai_generate_button, "generate_ai_drafts", "Сгенерировать AI-черновики без отправки"),
            ("campaign.enrich_contacts", self.enrich_contacts_button, "enrich_contacts", "Проверить публичные данные получателей"),
            ("campaign.approve_selected", self.quick_approve_button, "approve_selected", "Подтвердить выбранных получателей"),
            ("campaign.send_approved", self.quick_send_button, "send_approved", "Запустить тестовую/боевую отправку"),
            ("campaign.export_report", self.quick_export_button, "export_report", "Поставить экспорт отчета в очередь"),
            ("campaign.delete_selected", self.delete_selected_button, "delete_rows", "Удалить выбранные строки"),
            ("campaign.save_changes", self.save_changes_button, "save_rows", "Сохранить новые строки"),
            ("campaign.settings", self.settings_shortcut_button, "open_settings", "Открыть экран настроек"),
            ("campaign.sender_selector", self.sender_selector_button, "open_sender_selector", "Выбрать активный Gmail-профиль"),
            ("campaign.mode_manual", self.manual_mode_button, "_set_work_mode", "Работать без AI"),
            ("campaign.mode_ai_assist", self.ai_mode_button, "_set_work_mode", "Включить AI Assist для черновиков"),
            ("campaign.manual_assist_copy", self.copy_manual_message_button, "copy_manual_message", "Скопировать подготовленный manual-assist текст"),
            ("campaign.manual_assist_open_profile", self.open_manual_profile_button, "open_manual_profile", "Открыть профиль для ручной отправки"),
            ("campaign.manual_assist_mark_sent", self.mark_manual_sent_button, "mark_manual_sent", "Отметить ручную отправку"),
            ("campaign.queue_refresh", self.refresh_queue_button, "refresh_queue_panel", "Обновить статус процесса"),
            ("campaign.queue_cancel", self.cancel_current_button, "cancel_current_job", "Остановить текущую задачу"),
            ("campaign.queue_retry", self.retry_failed_button, "retry_failed_jobs", "Повторить неудачные задачи"),
            ("campaign.queue_clear", self.clear_completed_button, "clear_completed_jobs", "Очистить историю задач"),
        ]
        self.action_map = {}
        for action_id, button, slot_name, expected in actions:
            button.setAccessibleName(action_id)
            button.setProperty("actionId", action_id)
            button.setProperty("connectedSlot", slot_name)
            button.setProperty("expectedAction", expected)
            self.action_map[action_id] = {
                "objectName": button.objectName(),
                "label": button.text(),
                "slot": slot_name,
                "expected": expected,
            }
        self.channel_selector.setAccessibleName("campaign.channel_selector")
        self.channel_selector.setProperty("actionId", "campaign.channel_selector")
        self.channel_selector.setProperty("connectedSlot", "_on_channel_changed")
        self.channel_selector.setProperty("expectedAction", "Выбрать канал рассылки")
        self.action_map["campaign.channel_selector"] = {
            "objectName": self.channel_selector.objectName(),
            "label": "Канал",
            "slot": "_on_channel_changed",
            "expected": "Выбрать канал рассылки",
        }
        self.execution_mode_combo.setProperty("actionId", "campaign.execution_mode")
        self.execution_mode_combo.setProperty("connectedSlot", "_on_execution_mode_changed")
        self.execution_mode_combo.setProperty("expectedAction", "Выбрать dry-run / official API / Manual Assist")
        self.action_map["campaign.execution_mode"] = {
            "objectName": self.execution_mode_combo.objectName(),
            "label": "Как отправляем",
            "slot": "_on_execution_mode_changed",
            "expected": "Выбрать способ выполнения канала",
        }

    def add_empty_preview_row(self) -> None:
        self._updating_preview = True
        row_index = self.recipient_preview_table.rowCount()
        self.recipient_preview_table.insertRow(row_index)
        self._populate_preview_row(
            row_index,
            {
                "id": "",
                "channel": self.active_channel_id(),
                "email": "",
                "handle": "",
                "profile_url": "",
                "external_id": "",
                "subject": "",
                "generated_message": "",
                "base_message": "",
                "name": "",
                "company": "",
                "topic": "",
                "website": "",
                "social_profile": "",
                "status": "new",
                "last_error": "",
            },
        )
        self._updating_preview = False
        self.recipient_preview_table.selectRow(row_index)
        email_item = self.recipient_preview_table.item(row_index, 1)
        if email_item:
            self.recipient_preview_table.setCurrentItem(email_item)
            self.recipient_preview_table.editItem(email_item)
        self.update_selected_counter()
        channel = get_channel(self.active_channel_id())
        self.show_feedback(
            "Добавлена строка. Введите email, тему и сообщение."
            if channel.channel_id == "email"
            else f"Добавлена строка для {channel.display_name}. Укажите username/profile и сообщение."
        )

    def paste_rows_from_clipboard(self) -> None:
        from .contacts_table import ContactsTable

        text = QApplication.clipboard().text()
        rows = ContactsTable.parse_clipboard_rows(text)
        if not rows:
            QMessageBox.information(
                self,
                "Вставить из буфера",
                "В буфере нет строк с email и сообщением.",
            )
            self.show_feedback("В буфере нет строк с email и сообщением.", "warning")
            return
        result = self.service.add_contact_rows(
            self.active_campaign_id(),
            rows,
            source="campaign_clipboard",
        )
        message = f"Добавлено строк: {result.imported_count}\nПропущено: {result.skipped_count}"
        if result.errors:
            message += "\n\n" + "\n".join(result.errors[:10])
        QMessageBox.information(self, "Вставка завершена", message)
        self.show_feedback(
            f"Добавлено строк: {result.imported_count}."
            if result.imported_count
            else "Новые строки не добавлены.",
            "success" if result.imported_count else "warning",
        )
        self.refresh_callback()

    def save_preview_rows(self) -> None:
        rows_to_create: list[dict[str, str]] = []
        for row_index in range(self.recipient_preview_table.rowCount()):
            id_item = self.recipient_preview_table.item(row_index, 0)
            if id_item and id_item.data(Qt.ItemDataRole.UserRole):
                continue
            row = self._preview_row_to_contact(row_index)
            if any(value for key, value in row.items() if key not in {"status", "channel"}):
                rows_to_create.append(row)
        if not rows_to_create:
            QMessageBox.information(self, "Сохранить изменения", "Новых строк для сохранения нет.")
            self.show_feedback("Новых строк для сохранения нет.", "warning")
            return
        result = self.service.add_contact_rows(
            self.active_campaign_id(),
            rows_to_create,
            source="campaign_manual_table",
        )
        message = f"Сохранено строк: {result.imported_count}\nПропущено: {result.skipped_count}"
        if result.errors:
            message += "\n\n" + "\n".join(result.errors[:10])
        QMessageBox.information(self, "Сохранить изменения", message)
        self._updating_preview = True
        self.recipient_preview_table.setRowCount(0)
        self._updating_preview = False
        self.show_feedback(
            f"Сохранено строк: {result.imported_count}."
            if result.imported_count
            else "Строки не сохранены. Проверьте email.",
            "success" if result.imported_count else "warning",
        )
        self.refresh_callback()

    def delete_selected_preview_rows(self) -> None:
        selected_rows = sorted(
            {index.row() for index in self.recipient_preview_table.selectionModel().selectedRows()},
            reverse=True,
        )
        for row_index in range(self.recipient_preview_table.rowCount()):
            id_item = self.recipient_preview_table.item(row_index, 0)
            if id_item and id_item.checkState() == Qt.CheckState.Checked and row_index not in selected_rows:
                selected_rows.append(row_index)
        selected_rows = sorted(set(selected_rows), reverse=True)
        if not selected_rows:
            QMessageBox.information(self, "Удалить выбранные", "Выберите одну или несколько строк.")
            self.show_feedback("Сначала выберите строки.", "warning")
            return

        contact_ids: list[int] = []
        draft_deleted = 0
        for row_index in selected_rows:
            id_item = self.recipient_preview_table.item(row_index, 0)
            contact_id = id_item.data(Qt.ItemDataRole.UserRole) if id_item else None
            if contact_id:
                contact_ids.append(int(contact_id))
            else:
                self.recipient_preview_table.removeRow(row_index)
                draft_deleted += 1
        deleted = self.service.delete_contacts(contact_ids) if contact_ids else 0
        total = deleted + draft_deleted
        QMessageBox.information(self, "Удалить выбранные", f"Удалено строк: {total}")
        self.show_feedback(f"Удалено строк: {total}.")
        self.refresh_callback()

    def import_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Загрузить получателей",
            str(IMPORTS_DIR),
            "Excel/CSV (*.xlsx *.xlsm *.csv)",
        )
        if not file_path:
            return
        campaign_id = self.active_campaign_id()
        self._run_task(
            "Не удалось загрузить файл",
            lambda: self.service.import_file(Path(file_path), campaign_id),
            self._show_import_result,
            "Загружаем получателей…",
        )

    def _show_import_result(self, result) -> None:
        details = "\n".join(result.errors[:20])
        if len(result.errors) > 20:
            details += f"\n...и еще {len(result.errors) - 20}"
        QMessageBox.information(
            self,
            "Загрузка завершена",
            f"Добавлено получателей: {result.imported_count}\nПропущено строк: {result.skipped_count}"
            + (f"\n\nОшибки:\n{details}" if details else ""),
        )
        if result.skipped_count:
            self.show_feedback(
                f"Импортировано {result.imported_count}. Пропущено строк: {result.skipped_count}.",
                "warning",
            )
        else:
            self.show_feedback(f"Импортировано получателей: {result.imported_count}.")

    def download_example_excel(self) -> None:
        try:
            path = self.service.export_example_contacts_template()
        except Exception as exc:
            QMessageBox.critical(self, "Пример Excel", str(exc))
            self.show_feedback("Не удалось создать пример Excel.", "error")
            return
        QMessageBox.information(self, "Пример Excel", f"Файл создан:\n{path}")
        self.show_feedback("Пример Excel сохранен.")

    def generate_messages(self) -> None:
        if self._work_mode() == "ai_assist":
            self.generate_ai_drafts()
            return
        campaign_id = self.active_campaign_id()
        self._run_task(
            "Не удалось запустить подготовку",
            lambda: self.service.enqueue_generate_messages(campaign_id, channel=self.active_channel_id()),
            lambda result: self._show_enqueue_result(
                "Подготовить и проверить сообщения",
                result,
                "Писем отправлено на подготовку",
                "Сообщения готовятся. Проверьте их перед отправкой.",
            ),
            "Подготавливаем сообщения…",
        )

    def generate_ai_drafts(self) -> None:
        campaign_id = self.active_campaign_id()
        topic = self.ai_topic_input.text().strip()
        tone = str(self.ai_tone_combo.currentData() or "friendly")
        generation_mode = str(self.ai_generation_mode_combo.currentData() or "simple")
        use_enrichment = self.web_enrichment_checkbox.isChecked()
        selected_ids = self.selected_ids_for_action()
        contact_ids = selected_ids or None
        settings = self.service.settings()
        max_batch = max(as_int(settings.get("ai_max_drafts_per_batch"), 25), 1)
        candidate_count = self.service.ai_draft_candidate_count(campaign_id, contact_ids, channel=self.active_channel_id())
        confirm_ai_cost = False
        if candidate_count > max_batch:
            response = QMessageBox.question(
                self,
                "AI Assist",
                f"AI сгенерирует {candidate_count} писем. Это может стоить денег.\nПродолжить?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if response != QMessageBox.StandardButton.Yes:
                self.show_feedback("AI генерация отменена.")
                return
            confirm_ai_cost = True
        self.service.save_settings(
            {
                "ai_generation_mode": generation_mode,
                "web_enrichment_enabled": "true" if use_enrichment else "false",
            }
        )
        self._run_task(
            "Не удалось запустить AI Assist",
            lambda: self.service.enqueue_ai_generate_drafts(
                campaign_id,
                contact_ids=contact_ids,
                campaign_topic=topic,
                tone=tone,
                confirm_ai_cost=confirm_ai_cost,
                channel=self.active_channel_id(),
            ),
            lambda result: self._show_enqueue_result(
                "AI Assist",
                result,
                "Черновиков поставлено в очередь",
                "AI готовит черновики. Перед отправкой их нужно проверить и подтвердить.",
            ),
            "Генерируем AI-черновики…",
        )

    def enrich_contacts(self) -> None:
        campaign_id = self.active_campaign_id()
        selected_ids = self.selected_ids_for_action()
        self.service.save_settings(
            {"web_enrichment_enabled": "true" if self.web_enrichment_checkbox.isChecked() else "false"}
        )
        self._run_task(
            "Не удалось проверить публичные данные",
            lambda: self.service.enqueue_enrich_contacts(
                campaign_id,
                contact_ids=selected_ids or None,
                channel=self.active_channel_id(),
                force_refresh=False,
            ),
            lambda result: self._show_enqueue_result(
                "Проверить данные получателей",
                result,
                "Контактов поставлено на проверку",
                "Публичные данные будут проверены через безопасный GET-only enrichment.",
            ),
            "Проверяем публичные данные…",
        )

    def approve_selected(self) -> None:
        ids = self.selected_ids_for_action()
        if not ids:
            QMessageBox.information(self, "Подтвердить выбранные", "Выберите строки в таблице получателей.")
            self.show_feedback("Сначала выберите получателей.", "warning")
            return
        count = self.service.approve_contacts(ids)
        QMessageBox.information(self, "Подтвердить выбранные", f"Подтверждено строк: {count}")
        self.show_feedback(f"Подтверждено получателей: {count}.")
        self.refresh_callback()

    def reapprove_selected(self) -> None:
        ids = self.selected_ids_for_action()
        if not ids:
            QMessageBox.information(self, "Вернуть к отправке", "Выберите строки в таблице получателей.")
            self.show_feedback("Сначала выберите получателей.", "warning")
            return
        count = self.service.approve_contacts(ids)
        QMessageBox.information(self, "Вернуть к отправке", f"Вернуто к отправке: {count}")
        self.show_feedback(f"Вернуто к отправке: {count}.")
        self.refresh_callback()

    def send_approved(self) -> None:
        campaign_id = self.active_campaign_id()
        settings = self.service.settings()
        send_mode = (settings.get("send_mode") or "dry_run").strip().lower()
        execution_mode = str(self.execution_mode_combo.currentData() or self.service.execution_mode(self.active_channel_id()))
        self.service.set_execution_mode(self.active_channel_id(), execution_mode)
        warnings = self.service.smart_warnings(
            campaign_id,
            channel=self.active_channel_id(),
            execution_mode=execution_mode,
            send_mode=send_mode,
        )
        if warnings:
            self.show_feedback(warnings[0], "warning")
        if execution_mode == MANUAL_ASSIST:
            self.show_manual_assist_preview()
            return
        if execution_mode == DRY_RUN:
            send_mode = "dry_run"
        confirm_live_send = False
        if send_mode == "live" and settings.get("real_send_confirm_required", "true").lower() == "true":
            channel = get_channel(self.active_channel_id())
            count = self.service.approved_count(campaign_id, channel=channel.channel_id)
            recipients = self.service.approved_recipients(campaign_id, limit=5, channel=channel.channel_id)
            sender_label = (
                self.service.telegram_sender_label()
                if channel.channel_id == "telegram"
                else self.service.active_sender_email()
            )
            response = QMessageBox.question(
                self,
                "Подтвердите боевую отправку",
                build_live_send_confirmation_message(
                    count,
                    recipients,
                    sender_email=self.service.active_sender_email(),
                    mode=send_mode,
                    channel_display=channel.display_name,
                    sender_label=sender_label,
                    warnings=warnings,
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if response != QMessageBox.StandardButton.Yes:
                self.service.log_live_send_cancelled(campaign_id, count)
                self.show_feedback("Боевая отправка отменена.")
                self.refresh_callback()
                return
            confirm_live_send = True
        self._run_task(
            "Не удалось запустить отправку",
            lambda: self.service.enqueue_send_approved(
                campaign_id,
                mode=send_mode,
                confirm_live_send=confirm_live_send,
                channel=self.active_channel_id(),
            ),
            lambda result: self._show_enqueue_result(
                "Отправить подтвержденные",
                result,
                "Писем запущено в процесс",
                (
                    "Тестовая отправка запущена. Реальные письма не отправляются."
                    if send_mode == "dry_run"
                    else "Боевая отправка запущена через Gmail."
                ),
            ),
            "Запускаем отправку…",
        )

    def show_manual_assist_preview(self) -> None:
        campaign_id = self.active_campaign_id()
        selected_ids = self.selected_ids_for_action()
        try:
            contact = self.service.next_manual_assist_contact(
                campaign_id,
                channel=self.active_channel_id(),
                contact_ids=selected_ids or None,
            )
            if not contact:
                self.show_feedback("Нет подтвержденного получателя для Manual Assist.", "warning")
                return
            action = self.service.prepare_manual_assist(int(contact["id"]))
        except Exception as exc:
            self.show_feedback(user_safe_error(exc), "error")
            return
        self._manual_assist_contact_id = action.contact_id
        self._manual_assist_profile_url = action.profile_url
        self.manual_assist_recipient_label.setText(
            f"{action.channel}: {action.recipient or 'получатель не указан'} • {risk_label(action.risk_level)}"
        )
        self.manual_assist_message_preview.setPlainText(action.copy_text or action.message)
        if self.manual_assist_panel is not None:
            self.manual_assist_panel.setVisible(True)
        self.show_feedback("Manual Assist подготовлен: скопируйте текст и отправьте вручную.")

    def copy_manual_message(self) -> None:
        text = self.manual_assist_message_preview.toPlainText().strip()
        if not text:
            self.show_feedback("Нет подготовленного текста для копирования.", "warning")
            return
        QApplication.clipboard().setText(text)
        self.show_feedback("Сообщение скопировано. Отправка остается ручной.")

    def open_manual_profile(self) -> None:
        if not self._manual_assist_profile_url:
            self.show_feedback("Для этого контакта нет profile URL.", "warning")
            return
        open_external_url(self._manual_assist_profile_url)
        self.show_feedback("Профиль открыт. Отправка выполняется только оператором.")

    def mark_manual_sent(self) -> None:
        if not self._manual_assist_contact_id:
            self.show_feedback("Сначала подготовьте Manual Assist для контакта.", "warning")
            return
        count = self.service.mark_manual_assist_sent([self._manual_assist_contact_id])
        self.show_feedback(f"Отмечено вручную отправлено: {count}.")
        if self.manual_assist_panel is not None:
            self.manual_assist_panel.setVisible(False)
        self._manual_assist_contact_id = None
        self._manual_assist_profile_url = ""
        self.refresh_callback()

    def _show_enqueue_result(
        self,
        title: str,
        result: QueueResult,
        success_label: str,
        feedback_message: str | None = None,
    ) -> None:
        message = f"{success_label}: {result.count}"
        if result.error:
            message += f"\n\n{result.error}"
            self.show_feedback(result.error, "error")
        elif result.count:
            self.show_feedback(feedback_message or message)
        else:
            self.show_feedback("Нет задач для запуска.", "warning")
        QMessageBox.information(self, title, message)
        self.refresh_queue_panel()
        if result.count:
            self.start_queue_worker()

    def show_feedback(self, message: str, kind: str = "success") -> None:
        colors = {
            "success": (COLORS["green"], COLORS["green_soft"]),
            "warning": (COLORS["amber"], COLORS["amber_soft"]),
            "error": (COLORS["red"], COLORS["red_soft"]),
        }
        text_color, bg_color = colors.get(kind, colors["success"])
        self.feedback_label.setText(message)
        self.feedback_label.setToolTip(message)
        self.feedback_label.setStyleSheet(
            f"background: {bg_color}; color: {text_color}; border-radius: 12px; "
            "padding: 5px 10px; font-weight: 750;"
        )

    def set_loading_state(self, message: str, active: bool = True) -> None:
        self.loading_label.setText(message or "Нет активных действий")
        self.loading_label.setVisible(active)
        if active:
            self.loading_label.setStyleSheet(
                f"background: {COLORS['primary_soft']}; color: {COLORS['primary']}; "
                "border-radius: 10px; padding: 4px 9px; font-weight: 750;"
            )

    def update_progress(self, value: int) -> None:
        self.progress_bar.setValue(max(0, min(100, int(value))))

    def selected_ids_for_action(self) -> list[int]:
        ids = list(self.selected_contact_ids())
        ids.extend(self._selected_preview_contact_ids())
        return list(dict.fromkeys(ids))

    def _selected_preview_contact_ids(self) -> list[int]:
        ids: list[int] = []
        selected_rows = {
            index.row()
            for index in self.recipient_preview_table.selectionModel().selectedRows()
        }
        for row in range(self.recipient_preview_table.rowCount()):
            id_item = self.recipient_preview_table.item(row, 0)
            if not id_item:
                continue
            is_checked = id_item.checkState() == Qt.CheckState.Checked
            if row in selected_rows or is_checked:
                try:
                    ids.append(int(id_item.data(Qt.ItemDataRole.UserRole)))
                except (TypeError, ValueError):
                    try:
                        ids.append(int(id_item.text()))
                    except ValueError:
                        continue
        return ids

    def update_selected_counter(self) -> None:
        if self._updating_preview:
            return
        count = len(self.selected_ids_for_action())
        self.preview_selected_label.setText(f"• {count} выбрано")

    def _human_job_type(self, job_type: str | None) -> str:
        mapping = {
            "generate_message": "подготовка сообщений",
            "ai_generate_draft": "AI-черновик",
            "dry_run_send": "тестовая отправка",
            "live_send": "отправка через Gmail",
            "export_report": "создание отчета",
        }
        return mapping.get(job_type or "", "обработка")

    def _human_progress_message(self, message: str) -> str:
        normalized = message.strip().lower()
        if normalized == "sending":
            return "тестовая отправка" if self._current_job_type == "dry_run_send" else "отправка через Gmail"
        mapping = {
            "running": "запуск",
            "generating": "подготовка сообщений",
            "ai drafting": "AI готовит черновик",
            "pending review": "ожидает подтверждения",
            "exporting": "создание отчета",
            "completed": "завершено",
        }
        return mapping.get(normalized, message)

    def show_due_followups(self) -> None:
        due = self.service.due_followups(self.active_campaign_id())
        if not due:
            QMessageBox.information(self, "Повторные письма", "Сейчас нет получателей для повторного письма.")
            return

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            "\n".join(
                f"#{contact['id']} {contact['email']} | due {contact['follow_up_due_at']}"
                for contact in due
            )
        )
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Повторные письма")
        dialog.setText("Stage 1: фактическая автоотправка повторных писем пока не реализована.")
        dialog.layout().addWidget(text, 1, 0, 1, dialog.layout().columnCount())
        dialog.exec()

    def export_report(self) -> None:
        campaign_id = self.active_campaign_id()
        self._run_task(
            "Не удалось создать отчет",
            lambda: self.service.enqueue_export_report(campaign_id),
            lambda result: self._show_enqueue_result(
                "Скачать отчет",
                result,
                "Отчетов запущено",
                "Отчет готовится. После завершения он появится в exports.",
            ),
            "Готовим отчет…",
        )

    def refresh_queue_panel(self) -> None:
        stats = self.service.queue_stats(self.active_campaign_id())
        values = {
            "pending": stats.get("pending", 0) + stats.get("queued", 0),
            "running": stats.get("running", 0),
            "completed": stats.get("completed", 0),
            "failed": stats.get("failed", 0),
            "cancelled": stats.get("cancelled", 0),
        }
        self.queue_stats_label.setText(
            "Ожидает {pending} • В работе {running} • Завершено {completed} • "
            "Ошибки {failed}".format(**values)
        )
        for key, label in self.queue_stat_labels.items():
            label.setText(f"{label.property('labelText')} {values.get(key, 0)}")
        if values["failed"]:
            self.queue_health_label.setText(f"Есть неудачные задачи: {values['failed']}")
            self.queue_health_label.setStyleSheet(
                f"background: {COLORS['red_soft']}; color: {COLORS['red']}; "
                f"border: 1px solid {COLORS['border_soft']}; border-radius: 8px; "
                "padding: 2px 7px; font-size: 11px; font-weight: 720;"
            )
        else:
            self.queue_health_label.setText("Ошибок нет")
            self.queue_health_label.setStyleSheet(
                f"background: {COLORS['surface_soft']}; color: {COLORS['muted']}; "
                f"border: 1px solid {COLORS['border_soft']}; border-radius: 8px; "
                "padding: 2px 7px; font-size: 11px; font-weight: 720;"
            )

    def start_queue_worker(self) -> None:
        if self._shutting_down:
            return
        if self._queue_thread and self._queue_thread.isRunning():
            return
        if os.getenv("QT_QPA_PLATFORM", "").strip().lower() == "offscreen":
            self._process_queue_synchronously_for_smoke()
            return
        processor = QueueJobProcessor(self.service)
        self._queue_thread = QThread(self)
        self._queue_worker = QueueWorker(processor)
        self._queue_worker.moveToThread(self._queue_thread)
        self._queue_thread.started.connect(self._queue_worker.run)
        self._queue_worker.worker_started.connect(lambda: self.worker_status_label.setText("Система: работает"))
        self._queue_worker.worker_stopped.connect(lambda: self.worker_status_label.setText("Система: готова"))
        self._queue_worker.worker_stopped.connect(self._queue_thread.quit)
        self._queue_worker.queue_updated.connect(self.refresh_queue_panel)
        self._queue_worker.job_started.connect(self._on_queue_job_started)
        self._queue_worker.job_progress.connect(self._on_queue_job_progress)
        self._queue_worker.job_completed.connect(self._on_queue_job_done)
        self._queue_worker.job_failed.connect(lambda job, error: self._on_queue_job_done(job))
        self._queue_thread.finished.connect(self._on_queue_thread_finished)
        self._queue_thread.start()

    def _process_queue_synchronously_for_smoke(self) -> None:
        self.worker_status_label.setText("Система: работает")
        processor = QueueJobProcessor(self.service)

        def progress(job_id: int, percent: int, message: str) -> None:
            self._current_job_id = job_id
            job = self.service.db.fetch_one("SELECT job_type FROM job_queue WHERE id = ?", (job_id,))
            self._current_job_type = str(job.get("job_type") or "") if job else self._current_job_type
            self.update_progress(percent)
            self.current_job_label.setText(f"Процесс: {self._human_progress_message(message)}")

        processor.process_available(progress_callback=progress)
        self.worker_status_label.setText("Система: готова")
        self._queue_thread = None
        self._queue_worker = None
        self._current_job_id = None
        self._current_job_type = None
        self.current_job_label.setText("Процесс: нет задач")
        self.current_contact_label.setVisible(False)
        self.set_loading_state("", False)
        self.refresh_queue_panel()
        self.refresh_callback()

    def _on_queue_job_started(self, job: dict) -> None:
        self._current_job_id = int(job["id"])
        self._current_job_type = str(job.get("job_type") or "")
        contact_label = "никто"
        if job.get("contact_id"):
            contact = self.service.db.get_contact(int(job["contact_id"]))
            if contact:
                contact_label = contact["email"]
        self.current_job_label.setText(f"Процесс: {self._human_job_type(self._current_job_type)}")
        self.current_contact_label.setText(f"Сейчас обрабатывается: {contact_label}")
        self.current_contact_label.setVisible(contact_label != "никто")
        self.progress_bar.setValue(int(job.get("progress_percent") or 0))
        self.set_loading_state(f"{self._human_job_type(self._current_job_type).capitalize()}…", True)

    def _on_queue_job_progress(self, job_id: int, progress: int, message: str) -> None:
        self._current_job_id = job_id
        self.update_progress(progress)
        self.current_job_label.setText(f"Процесс: {self._human_progress_message(message)}")

    def _on_queue_job_done(self, job: dict) -> None:
        self.progress_bar.setValue(int(job.get("progress_percent") or 100))
        if job.get("status") == "failed":
            self.show_feedback(job.get("last_error") or "Задача завершилась ошибкой.", "error")
        else:
            self.show_feedback("Задача завершена.")
        self.refresh_callback()

    def _on_queue_thread_finished(self) -> None:
        self._queue_thread = None
        self._queue_worker = None
        self._current_job_id = None
        self._current_job_type = None
        self.current_job_label.setText("Процесс: нет задач")
        self.current_contact_label.setText("Сейчас обрабатывается: никто")
        self.current_contact_label.setVisible(False)
        self.set_loading_state("", False)
        QTimer.singleShot(0, self._after_queue_thread_finished)

    def _after_queue_thread_finished(self) -> None:
        if self._shutting_down:
            return
        self.refresh_queue_panel()
        stats = self.service.queue_stats(self.active_campaign_id())
        queued_count = stats.get("pending", 0) + stats.get("queued", 0)
        if queued_count:
            QTimer.singleShot(0, self.start_queue_worker)

    def cancel_current_job(self) -> None:
        if not self._current_job_id:
            QMessageBox.information(self, "Остановить", "Сейчас нет активной задачи.")
            self.show_feedback("Сейчас нет активной задачи.", "warning")
            return
        self.service.queue.cancel_job(self._current_job_id)
        if self._queue_worker:
            self._queue_worker.cancel_current()
        self.show_feedback("Задача остановлена.")
        self.refresh_queue_panel()

    def retry_failed_jobs(self) -> None:
        result = self.service.retry_failed_jobs(self.active_campaign_id())
        message = (
            f"Неудачные задачи снова запущены: {result.count}"
            if result.count
            else "Нет задач для повтора."
        )
        QMessageBox.information(self, "Повторить неудачные задачи", message)
        self.show_feedback(message, "warning" if not result.count else "success")
        self.refresh_queue_panel()
        if result.count:
            self.start_queue_worker()

    def clear_completed_jobs(self) -> None:
        count = self.service.clear_completed_jobs(self.active_campaign_id())
        QMessageBox.information(self, "Очистить историю задач", f"Очищено задач: {count}")
        self.show_feedback(f"История задач очищена: {count}.")
        self.refresh_queue_panel()

    def _run_task(
        self,
        error_title: str,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        loading_message: str = "Выполняем действие…",
    ) -> None:
        self._set_busy(True, loading_message)
        self._task_success_handler = on_success
        self._task_error_title = error_title
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
        self.show_feedback(message, "error")
        QMessageBox.critical(self, self._task_error_title, message)

    def _finish_job(self, thread: QThread, worker: BackgroundWorker) -> None:
        self._jobs = [job for job in self._jobs if job != (thread, worker)]
        if not self._jobs:
            self._task_success_handler = None
            self._task_error_title = "Ошибка"
        self._set_busy(False)
        self.refresh_callback()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.set_loading_state(message, busy)
        for button in (
            self.import_button,
            self.generate_button,
            self.approve_button,
            self.reapprove_button,
            self.send_button,
            self.followup_button,
            self.export_button,
            self.refresh_queue_button,
            self.cancel_current_button,
            self.retry_failed_button,
            self.clear_completed_button,
            self.add_row_button,
            self.paste_button,
            self.example_button,
            self.quick_generate_button,
            self.ai_generate_button,
            self.quick_approve_button,
            self.quick_send_button,
            self.quick_export_button,
            self.delete_selected_button,
            self.save_changes_button,
            self.manual_mode_button,
            self.ai_mode_button,
            self.copy_manual_message_button,
            self.open_manual_profile_button,
            self.mark_manual_sent_button,
        ):
            button.setEnabled(not busy)
        self.channel_selector.setEnabled(not busy)
        self.execution_mode_combo.setEnabled(not busy)

    def shutdown(self) -> None:
        self._shutting_down = True
        if self._queue_worker:
            self._queue_worker.stop()
        if self._queue_thread and self._queue_thread.isRunning():
            self._queue_thread.quit()
            self._queue_thread.wait(3000)
        for thread, _worker in list(self._jobs):
            if thread.isRunning():
                thread.quit()
                thread.wait(3000)

    def _build_header(self) -> QFrame:
        header = card()
        header.setMinimumHeight(68)
        header.setMaximumHeight(96)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)
        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        title = QLabel("Привет! 👋")
        title.setObjectName("heroTitle")
        title.setWordWrap(True)
        subtitle = QLabel("Отправляйте письма легко и безопасно.")
        subtitle.setObjectName("heroSubtitle")
        subtitle.setWordWrap(True)
        title_column.addWidget(title)
        title_column.addWidget(subtitle)
        layout.addLayout(title_column, 1)
        sender_column = QVBoxLayout()
        sender_column.setSpacing(4)
        self.active_sender_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 12px; font-weight: 720;"
        )
        self.sender_selector_button.setMinimumHeight(28)
        self.sender_selector_button.setMaximumHeight(30)
        sender_column.addWidget(self.active_sender_label)
        sender_column.addWidget(self.sender_selector_button)
        layout.addLayout(sender_column)
        self.gmail_status_label.setMinimumHeight(28)
        layout.addWidget(self.gmail_status_label)
        layout.addWidget(self.settings_shortcut_button)
        return header

    def _build_workflow_steps(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)
        self.workflow_cards: list[QFrame] = []
        steps = [
            ("1", "Добавьте получателей", "Импортируйте или введите вручную", True),
            ("2", "Проверьте и подтвердите", "Проверьте сообщения и подтвердите", False),
            ("3", "Отправьте письма", "Сначала тестовый режим", False),
        ]
        for index, (number, title, subtitle, active) in enumerate(steps):
            step_card = self._workflow_card(number, title, subtitle, active)
            self.workflow_cards.append(step_card)
            layout.addWidget(step_card, 1)
            if index < len(steps) - 1:
                arrow = QLabel("→")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow.setStyleSheet(f"color: {COLORS['muted_soft']}; font-size: 17px;")
                layout.addWidget(arrow)
        return layout

    def _workflow_card(self, number: str, title: str, subtitle: str, active: bool) -> QFrame:
        frame = card()
        frame.setMinimumHeight(52)
        frame.setMaximumHeight(60)
        if active:
            frame.setObjectName("activeWorkflowCard")
            frame.setStyleSheet(
                f"QFrame#activeWorkflowCard {{ background: {COLORS['primary_soft']}; "
                "border: 1px solid #C9DCFF; border-radius: 18px; }"
            )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        number_label = QLabel(number)
        number_label.setFixedSize(24, 24)
        number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        number_label.setStyleSheet(
            f"background: {COLORS['primary'] if active else COLORS['surface_soft']}; "
            f"color: {'white' if active else COLORS['muted']}; border-radius: 12px; font-weight: 900;"
        )
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; font-weight: 800;")
        title_label.setWordWrap(True)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("muted")
        subtitle_label.setWordWrap(True)
        subtitle_label.setStyleSheet(f"color: {COLORS['muted']}; font-size: 12px;")
        text_box.addWidget(title_label)
        text_box.addWidget(subtitle_label)
        layout.addWidget(number_label)
        layout.addLayout(text_box, 1)
        return frame

    def _build_work_mode_panel(self) -> QFrame:
        frame = self._quiet_card("workModePanel")
        frame.setMinimumHeight(58)
        frame.setMaximumHeight(220)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(8)
        label = QLabel("Режим работы")
        label.setObjectName("muted")
        top.addWidget(label)
        top.addWidget(self.manual_mode_button)
        top.addWidget(self.ai_mode_button)
        top.addSpacing(10)
        channel_label = QLabel("Канал")
        channel_label.setObjectName("muted")
        top.addWidget(channel_label)
        top.addWidget(self.channel_selector)
        top.addSpacing(10)
        execution_label = QLabel("Как отправляем")
        execution_label.setObjectName("muted")
        top.addWidget(execution_label)
        top.addWidget(self.execution_mode_combo)
        top.addStretch(1)
        ai_hint = QLabel("AI только готовит черновики. Отправка всегда требует подтверждения.")
        ai_hint.setObjectName("muted")
        ai_hint.setWordWrap(True)
        top.addWidget(ai_hint)
        layout.addLayout(top)
        layout.addWidget(self.execution_risk_label)
        layout.addWidget(self.channel_notice_label)

        self.ai_mode_panel = QFrame()
        ai_layout = QHBoxLayout(self.ai_mode_panel)
        ai_layout.setContentsMargins(0, 0, 0, 0)
        ai_layout.setSpacing(8)
        ai_layout.addWidget(QLabel("Тема рассылки"))
        ai_layout.addWidget(self.ai_topic_input, 1)
        ai_layout.addWidget(QLabel("Тон"))
        ai_layout.addWidget(self.ai_tone_combo)
        ai_layout.addWidget(QLabel("AI режим"))
        ai_layout.addWidget(self.ai_generation_mode_combo)
        ai_layout.addWidget(self.ai_drafts_only_checkbox)
        ai_layout.addWidget(self.web_enrichment_checkbox)
        ai_layout.addWidget(self.enrich_contacts_button)
        ai_layout.addWidget(self.ai_generate_button)
        layout.addWidget(self.ai_mode_panel)
        brain_row = QHBoxLayout()
        brain_row.setContentsMargins(0, 0, 0, 0)
        brain_row.setSpacing(8)
        brain_row.addWidget(self.research_brain_status_label)
        brain_row.addWidget(self.writer_brain_status_label)
        brain_row.addStretch(1)
        layout.addLayout(brain_row)
        return frame

    def _build_manual_assist_panel(self) -> QFrame:
        frame = self._quiet_card("manualAssistPanel")
        frame.setMinimumHeight(118)
        frame.setMaximumHeight(172)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 9, 12, 10)
        layout.setSpacing(6)
        top = QHBoxLayout()
        title = QLabel("Manual Assist")
        title.setStyleSheet(f"font-weight: 800; color: {COLORS['text']};")
        top.addWidget(title)
        top.addWidget(self.manual_assist_recipient_label, 1)
        top.addWidget(self.copy_manual_message_button)
        top.addWidget(self.open_manual_profile_button)
        top.addWidget(self.mark_manual_sent_button)
        layout.addLayout(top)
        layout.addWidget(self.manual_assist_message_preview)
        frame.setVisible(False)
        return frame

    def _work_mode(self) -> str:
        return "ai_assist" if self.ai_mode_button.isChecked() else "manual"

    def active_channel_id(self) -> str:
        return str(self.channel_selector.currentData() or "email")

    def _on_channel_changed(self) -> None:
        channel_id = self.active_channel_id()
        self.service.set_active_channel(channel_id)
        self._sync_execution_mode_options()
        self._sync_channel_notice()
        self._refresh_recipient_preview()
        self.show_feedback(f"Канал выбран: {get_channel(channel_id).display_name}.")

    def _sync_channel_notice(self) -> None:
        channel = get_channel(self.active_channel_id())
        capability = self.service.channel_capability(channel.channel_id)
        if channel.channel_id == "email":
            self.channel_notice_label.setVisible(False)
            self.quick_send_button.setToolTip("В тестовом режиме SMTP не вызывается. В боевом режиме отправляет через Gmail.")
        elif channel.channel_id == "telegram":
            self.channel_notice_label.setVisible(True)
            notice = (
                "Telegram использует только official Bot API. Для реальной отправки нужен chat_id, "
                "где бот имеет доступ. Dry-run остается безопасным режимом по умолчанию."
            )
        else:
            self.channel_notice_label.setVisible(True)
            notice = (
                f"{capability.limitation_text} Можно подготовить текст, открыть профиль и отметить ручную отправку."
            )
        if self.channel_notice_label.isVisible():
            self.channel_notice_label.setText(notice)
            self.channel_notice_label.setStyleSheet(
                f"background: {COLORS['amber_soft']}; color: {COLORS['amber']}; "
                f"border: 1px solid {COLORS['border_soft']}; border-radius: 12px; "
                "padding: 6px 10px; font-weight: 700;"
            )
        self.quick_send_button.setToolTip(channel.live_disabled_message)

    def _sync_execution_mode_options(self) -> None:
        channel_id = self.active_channel_id()
        current_mode = self.service.execution_mode(channel_id)
        options = self.service.execution_mode_options(channel_id)
        self.execution_mode_combo.blockSignals(True)
        self.execution_mode_combo.clear()
        for mode, label in options:
            self.execution_mode_combo.addItem(label, mode)
        index = self.execution_mode_combo.findData(current_mode)
        self.execution_mode_combo.setCurrentIndex(index if index >= 0 else 0)
        self.execution_mode_combo.blockSignals(False)
        capability = self.service.channel_capability(channel_id)
        self.execution_risk_label.setText(
            f"Ограничения канала / Risk: {risk_label(capability.risk_level)} • {capability.risk_explanation}"
        )
        self.execution_risk_label.setStyleSheet(
            f"color: {COLORS['muted']}; font-size: 12px; padding-left: 2px;"
        )
        if self.manual_assist_panel is not None:
            self.manual_assist_panel.setVisible(current_mode == MANUAL_ASSIST and self._manual_assist_contact_id is not None)

    def _on_execution_mode_changed(self) -> None:
        mode = str(self.execution_mode_combo.currentData() or DRY_RUN)
        normalized = self.service.set_execution_mode(self.active_channel_id(), mode)
        label = EXECUTION_MODE_LABELS.get(normalized, normalized)
        if self.manual_assist_panel is not None and normalized != MANUAL_ASSIST:
            self.manual_assist_panel.setVisible(False)
        self.show_feedback(f"Как отправляем: {label}.")

    def _set_work_mode(self, mode: str) -> None:
        normalized = "ai_assist" if mode == "ai_assist" else "manual"
        self.service.save_settings({"work_mode": normalized})
        self._sync_work_mode(normalized)
        self.show_feedback(
            "AI Assist включен: будут создаваться только черновики."
            if normalized == "ai_assist"
            else "Ручной режим включен."
        )

    def _sync_work_mode(self, mode: str) -> None:
        normalized = "ai_assist" if mode == "ai_assist" else "manual"
        self.manual_mode_button.setChecked(normalized == "manual")
        self.ai_mode_button.setChecked(normalized == "ai_assist")
        if self.ai_mode_panel is not None:
            self.ai_mode_panel.setVisible(normalized == "ai_assist")
        self.research_brain_status_label.setVisible(normalized == "ai_assist")
        self.writer_brain_status_label.setVisible(normalized == "ai_assist")
        self.quick_generate_button.setText(
            "Сгенерировать черновики" if normalized == "ai_assist" else "Подготовить сообщения"
        )

    def _build_recipients_card(self) -> QFrame:
        frame = card()
        frame.setMinimumHeight(405)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(7)
        title = section_title("Получатели")
        subtitle = helper_text("1 строка = 1 письмо.")
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for button in (
            self.add_row_button,
            self.paste_button,
            self.import_button,
            self.example_button,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        self.campaign_search_input.setMinimumWidth(190)
        self.campaign_search_input.setMaximumWidth(260)
        actions.addWidget(self.campaign_search_input)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.setContentsMargins(0, 2, 0, 0)
        footer.addWidget(self.preview_total_label)
        footer.addWidget(self.preview_selected_label)
        footer.addStretch(1)
        footer.addWidget(self.delete_selected_button)
        footer.addWidget(self.save_changes_button)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(actions)
        layout.addWidget(self.recipient_preview_table)
        layout.addLayout(footer)
        return frame

    def _quiet_card(self, object_name: str) -> QFrame:
        frame = card()
        frame.setObjectName(object_name)
        frame.setGraphicsEffect(None)
        frame.setStyleSheet(
            f"QFrame#{object_name} {{ background: {COLORS['surface']}; "
            f"border: 1px solid {COLORS['border_soft']}; border-radius: 16px; }}"
        )
        return frame

    def _build_action_bar(self) -> QFrame:
        frame = self._quiet_card("bottomActionBar")
        frame.setMinimumHeight(60)
        frame.setMaximumHeight(72)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(self.quick_generate_button)
        layout.addWidget(self.quick_approve_button)
        layout.addWidget(self.quick_send_button)
        layout.addWidget(self.quick_export_button)
        layout.addStretch(1)
        layout.addWidget(self.action_summary_label)
        return frame

    def _build_queue_card(self) -> QFrame:
        frame = self._quiet_card("queueStatusFooter")
        frame.setMinimumHeight(34)
        frame.setMaximumHeight(40)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 5, 12, 5)
        layout.setSpacing(6)
        self.worker_status_label.setWordWrap(True)
        self.current_job_label.setWordWrap(True)
        self.current_contact_label.setWordWrap(True)
        self.worker_status_label.setObjectName("muted")
        self.current_job_label.setObjectName("muted")
        layout.addWidget(self.current_job_label)
        self.progress_bar.setMaximumWidth(120)
        layout.addWidget(self.progress_bar)
        self.feedback_label.setMaximumWidth(170)
        layout.addWidget(self.feedback_label)
        layout.addStretch(1)
        layout.addWidget(self.refresh_queue_button)
        layout.addWidget(self.cancel_current_button)
        layout.addWidget(self.retry_failed_button)
        layout.addWidget(self.clear_completed_button)
        return frame

    def _refresh_recipient_preview(self) -> None:
        draft_rows = [] if self._updating_preview else self._preview_draft_rows()
        rows = self.service.contacts(
            self.active_campaign_id(),
            search=self.campaign_search_input.text().strip(),
        )
        self.preview_total_label.setText(f"Всего строк: {len(rows)}")
        rows = rows[:8]
        self._updating_preview = True
        self.recipient_preview_table.blockSignals(True)
        self.recipient_preview_table.setRowCount(0)
        self.recipient_preview_table.setRowCount(len(rows) + len(draft_rows))
        self.recipient_preview_table.setProperty("recipientPreviewTable", True)
        for row_index, contact in enumerate(rows):
            self._populate_preview_row(row_index, contact)
        for offset, contact in enumerate(draft_rows, start=len(rows)):
            self._populate_preview_row(offset, contact)
        self.recipient_preview_table.blockSignals(False)
        self._updating_preview = False
        self.update_selected_counter()

    def _preview_draft_rows(self) -> list[dict[str, str]]:
        drafts: list[dict[str, str]] = []
        for row_index in range(self.recipient_preview_table.rowCount()):
            id_item = self.recipient_preview_table.item(row_index, 0)
            if id_item and id_item.data(Qt.ItemDataRole.UserRole):
                continue
            row = self._preview_row_to_contact(row_index)
            if any(value for key, value in row.items() if key not in {"status", "channel"}):
                row["id"] = ""
                row["last_error"] = ""
                drafts.append(row)
        return drafts

    def _populate_preview_row(self, row_index: int, contact: dict[str, Any]) -> None:
        message = contact.get("generated_message") or contact.get("base_message") or ""
        channel_id = str(contact.get("channel") or "email")
        email_value = str(contact.get("email") or "")
        if channel_id != "email" and email_value.endswith("@channel.local"):
            email_value = ""
        research_status = str(contact.get("research_status") or "").strip()
        ai_badge = ""
        if int(contact.get("ai_generated") or 0):
            ai_badge = "AI"
            if research_status:
                ai_badge = f"AI · R:{research_status}"
        values = {
            "select": "",
            "email": email_value,
            "subject": contact.get("subject") or "",
            "generated_message": message or "Нет сообщения",
            "name": contact.get("name") or "",
            "company": contact.get("company") or "",
            "topic": contact.get("topic") or "",
            "status": status_to_ru(contact.get("status") or "new"),
            "last_error": contact.get("last_error") or "",
            "website": contact.get("website") or "",
            "social_profile": contact.get("social_profile") or "",
            "ai_badge": ai_badge,
            "enrichment_status": self._enrichment_status_label(
                str(contact.get("enrichment_status") or "not_checked")
            ),
            "channel": channel_id,
            "handle": contact.get("handle") or "",
            "profile_url": contact.get("profile_url") or "",
            "external_id": contact.get("external_id") or "",
        }
        contact_id = contact.get("id") or ""
        for column_index, (key, _) in enumerate(PREVIEW_COLUMNS):
            value = values.get(key, "")
            item = QTableWidgetItem(str(value))
            if key not in PREVIEW_EDITABLE_COLUMNS:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if key == "select":
                item.setData(Qt.ItemDataRole.UserRole, int(contact_id) if str(contact_id).strip() else 0)
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if key == "email" and item.text() and not is_valid_email(item.text()):
                item.setBackground(QColor(COLORS["red_soft"]))
                item.setForeground(QColor(COLORS["red"]))
            if key == "generated_message" and not message:
                item.setBackground(QColor(COLORS["amber_soft"]))
                item.setForeground(QColor(COLORS["amber"]))
            if key == "status":
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if key == "ai_badge" and item.text():
                item.setToolTip(
                    "AI Assist: черновик создан AI и требует ручной проверки.\n"
                    + str(contact.get("ai_notes") or "")
                    + ("\nWarnings: " + str(contact.get("ai_warnings") or "") if contact.get("ai_warnings") else "")
                    + ("\nResearch: " + str(contact.get("research_brief_json") or "") if contact.get("research_brief_json") else "")
                )
                item.setForeground(QColor(COLORS["primary"]))
                item.setBackground(QColor(COLORS["primary_soft"]))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if key == "enrichment_status":
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                status = str(contact.get("enrichment_status") or "not_checked")
                warnings = str(contact.get("enrichment_warnings") or "")
                if status in {"success", "partial"}:
                    item.setForeground(QColor(COLORS["green"]))
                    item.setBackground(QColor(COLORS["green_soft"]))
                elif status in {"failed", "blocked"}:
                    item.setForeground(QColor(COLORS["red"]))
                    item.setBackground(QColor(COLORS["red_soft"]))
                elif status == "skipped":
                    item.setForeground(QColor(COLORS["muted"]))
                    item.setBackground(QColor(COLORS["border_soft"]))
                if warnings or contact.get("enrichment_source_urls"):
                    item.setToolTip(
                        "Web enrichment\n"
                        f"Status: {status}\n"
                        f"Sources: {contact.get('enrichment_source_urls') or '-'}\n"
                        f"Warnings: {warnings or '-'}"
                    )
            self.recipient_preview_table.setItem(row_index, column_index, item)

    @staticmethod
    def _enrichment_status_label(status: str) -> str:
        return {
            "not_checked": "Не проверено",
            "success": "Найдено",
            "partial": "Частично",
            "failed": "Ошибка",
            "blocked": "Блок",
            "skipped": "Пропущено",
        }.get(status or "not_checked", "Не проверено")

    def _preview_row_to_contact(self, row_index: int) -> dict[str, str]:
        values: dict[str, str] = {}
        for column_index, (key, _) in enumerate(PREVIEW_COLUMNS):
            if key == "select":
                continue
            item = self.recipient_preview_table.item(row_index, column_index)
            values[key] = "" if item is None else item.text().strip()
        status = status_from_ru(values.get("status", "")) or "new"
        message = values.get("generated_message", "")
        if message == "Нет сообщения":
            message = ""
        return {
            "email": values.get("email", ""),
            "channel": values.get("channel", "") or self.active_channel_id(),
            "handle": values.get("handle", ""),
            "profile_url": values.get("profile_url", ""),
            "external_id": values.get("external_id", ""),
            "subject": values.get("subject", ""),
            "generated_message": message,
            "base_message": message,
            "name": values.get("name", ""),
            "company": values.get("company", ""),
            "topic": values.get("topic", ""),
            "website": values.get("website", ""),
            "social_profile": values.get("social_profile", ""),
            "status": status,
        }

    def _on_preview_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_preview:
            return
        self.update_selected_counter()
        key = PREVIEW_COLUMNS[item.column()][0]
        if key not in PREVIEW_EDITABLE_COLUMNS:
            return
        id_item = self.recipient_preview_table.item(item.row(), 0)
        contact_id = id_item.data(Qt.ItemDataRole.UserRole) if id_item else None
        if not contact_id:
            return
        value = item.text().strip()
        if key == "status":
            status = status_from_ru(value)
            if status not in CONTACT_STATUSES:
                QMessageBox.warning(
                    self,
                    "Неверный статус",
                    "Используйте один из статусов: "
                    + ", ".join(STATUS_LABELS_RU[status] for status in sorted(CONTACT_STATUSES)),
                )
                self.refresh_callback()
                return
            fields: dict[str, Any] = {"status": status}
        elif key == "generated_message":
            fields = {
                "generated_message": value,
                "base_message": value,
                "last_error": "" if value else "Нет сообщения. Можно заполнить вручную или использовать шаблон.",
            }
        elif key == "email":
            fields = {"email": value.strip().lower()}
        else:
            fields = {key: value}
        try:
            self.service.update_contact(int(contact_id), fields)
        except Exception as exc:
            QMessageBox.critical(self, "Не удалось сохранить", str(exc))
            self.refresh_callback()
