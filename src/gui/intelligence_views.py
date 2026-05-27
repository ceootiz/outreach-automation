from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..campaign_service import CampaignService
from ..intelligence import LEAD_STATUSES
from ..platform_actions import open_external_url
from .theme import COLORS, apply_table_style, card, helper_text, primary_button, secondary_button, set_button_kind


def _header(title: str, subtitle: str) -> QFrame:
    frame = card()
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    title_label = QLabel(title)
    title_label.setObjectName("heroTitle")
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("heroSubtitle")
    subtitle_label.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)
    return frame


def _metric_card(title: str, value: str) -> QFrame:
    frame = card()
    frame.setMinimumHeight(84)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    label = QLabel(title)
    label.setObjectName("muted")
    label.setWordWrap(True)
    number = QLabel(value)
    number.setStyleSheet("font-size: 24px; font-weight: 800;")
    layout.addWidget(label)
    layout.addWidget(number)
    return frame


class NewCampaignWizard(QDialog):
    def __init__(self, service: CampaignService, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("newCampaignWizard")
        self.setWindowTitle("Новая кампания")
        self.service = service
        self.created_campaign_id: int | None = None
        self.step_index = 0
        self.steps = (
            "1. Preset",
            "2. Канал",
            "3. Execution",
            "4. AI",
            "5. Получатели",
            "6. Проверка",
            "7. Draft launch",
        )

        self.step_label = QLabel()
        self.step_label.setObjectName("wizardStepLabel")
        self.step_label.setStyleSheet("font-size: 18px; font-weight: 800;")
        self.helper = helper_text("Выберите безопасный сценарий. Ничего не отправляется автоматически.")
        self.helper.setWordWrap(True)

        self.preset_selector = QComboBox()
        self.preset_selector.setObjectName("wizardPresetSelector")
        for preset in self.service.campaign_presets():
            self.preset_selector.addItem(preset.name, preset.preset_id)
        self.preset_selector.currentIndexChanged.connect(self._sync_from_preset)

        self.channel_selector = QComboBox()
        self.channel_selector.setObjectName("wizardChannelSelector")
        for channel_id, label in self.service.channel_options():
            self.channel_selector.addItem(label, channel_id)

        self.execution_selector = QComboBox()
        self.execution_selector.setObjectName("wizardExecutionModeSelector")
        self.channel_selector.currentIndexChanged.connect(self._sync_execution_options)

        self.ai_checkbox = QCheckBox("Включить AI drafts")
        self.ai_checkbox.setObjectName("wizardAiCheckbox")
        self.ai_checkbox.setChecked(True)

        self.validation_panel = helper_text("")
        self.validation_panel.setObjectName("wizardValidationPanel")
        self.validation_panel.setWordWrap(True)

        self.back_button = secondary_button("Назад")
        self.back_button.setObjectName("wizardBackButton")
        self.back_button.clicked.connect(self.previous_step)
        self.next_button = secondary_button("Далее")
        self.next_button.setObjectName("wizardNextButton")
        self.next_button.clicked.connect(self.next_step)
        self.create_button = primary_button("Создать кампанию")
        self.create_button.setObjectName("wizardCreateButton")
        self.create_button.clicked.connect(self.create_campaign)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        layout.addWidget(self.step_label)
        layout.addWidget(self.helper)

        form = card()
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(16, 14, 16, 14)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)
        for row, (label, widget) in enumerate(
            (
                ("Preset", self.preset_selector),
                ("Канал", self.channel_selector),
                ("Execution Mode", self.execution_selector),
                ("AI", self.ai_checkbox),
            )
        ):
            title = QLabel(label)
            title.setObjectName("muted")
            form_layout.addWidget(title, row, 0)
            form_layout.addWidget(widget, row, 1)
        layout.addWidget(form)
        layout.addWidget(self.validation_panel)

        actions = QHBoxLayout()
        actions.addWidget(self.back_button)
        actions.addWidget(self.next_button)
        actions.addStretch(1)
        actions.addWidget(self.create_button)
        layout.addLayout(actions)

        self._sync_from_preset()
        self._render_step()
        self.resize(560, 420)

    def _selected_preset(self):
        return self.service.campaign_preset(str(self.preset_selector.currentData() or "b2b_email_outreach"))

    def _sync_from_preset(self) -> None:
        preset = self._selected_preset()
        index = self.channel_selector.findData(preset.recommended_channel)
        self.channel_selector.setCurrentIndex(max(index, 0))
        self.ai_checkbox.setChecked(preset.ai_enabled)
        self._sync_execution_options()
        mode_index = self.execution_selector.findData(preset.recommended_execution_mode)
        self.execution_selector.setCurrentIndex(max(mode_index, 0))
        self.validation_panel.setText(
            f"{preset.description}\n\nWorkflow: "
            + " → ".join(preset.suggested_workflow[:4])
            + "\n\nHuman confirmation обязательна. Autosend: off."
        )

    def _sync_execution_options(self) -> None:
        channel_id = str(self.channel_selector.currentData() or "email")
        current = self.execution_selector.currentData()
        self.execution_selector.blockSignals(True)
        self.execution_selector.clear()
        for mode, label in self.service.execution_mode_options(channel_id):
            self.execution_selector.addItem(label, mode)
        index = self.execution_selector.findData(current)
        self.execution_selector.setCurrentIndex(max(index, 0))
        self.execution_selector.blockSignals(False)

    def _render_step(self) -> None:
        self.step_label.setText(self.steps[self.step_index])
        self.back_button.setEnabled(self.step_index > 0)
        self.next_button.setEnabled(self.step_index < len(self.steps) - 1)

    def next_step(self) -> None:
        self.step_index = min(self.step_index + 1, len(self.steps) - 1)
        self._render_step()

    def previous_step(self) -> None:
        self.step_index = max(self.step_index - 1, 0)
        self._render_step()

    def create_campaign(self) -> None:
        preset = self._selected_preset()
        self.created_campaign_id = self.service.create_campaign_from_preset(preset.preset_id)
        self.service.set_active_channel(str(self.channel_selector.currentData() or preset.recommended_channel))
        self.service.set_execution_mode(
            str(self.channel_selector.currentData() or preset.recommended_channel),
            str(self.execution_selector.currentData() or preset.recommended_execution_mode),
        )
        self.service.save_settings({"work_mode": "ai_assist" if self.ai_checkbox.isChecked() else "manual"})
        self.accept()


class CampaignDashboardView(QWidget):
    def __init__(
        self,
        service: CampaignService,
        campaign_id_getter: Callable[[], int],
        campaign_id_setter: Callable[[int], None] | None = None,
        refresh_callback: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.service = service
        self.campaign_id_getter = campaign_id_getter
        self.campaign_id_setter = campaign_id_setter
        self.refresh_callback = refresh_callback
        self.metric_cards: dict[str, QLabel] = {}
        self.operator_cards: dict[str, QLabel] = {}
        self.events_table = QTableWidget(0, 4)
        self.events_table.setObjectName("campaignTimelineTable")
        self.events_table.setHorizontalHeaderLabels(["Время", "Получатель", "Событие", "Детали"])
        apply_table_style(self.events_table)
        self.events_table.setMinimumHeight(240)
        self.events_table.setColumnWidth(0, 150)
        self.events_table.setColumnWidth(1, 190)
        self.events_table.setColumnWidth(2, 180)
        self.events_table.setColumnWidth(3, 360)

        self.refresh_button = secondary_button("Обновить")
        self.refresh_button.setObjectName("campaignDashboardRefreshButton")
        self.refresh_button.clicked.connect(self.refresh)

        self.preset_selector = QComboBox()
        self.preset_selector.setObjectName("campaignPresetSelector")
        for preset in self.service.campaign_presets():
            self.preset_selector.addItem(preset.name, preset.preset_id)

        self.new_campaign_button = primary_button("Новая кампания")
        self.new_campaign_button.setObjectName("newCampaignWizardButton")
        self.new_campaign_button.clicked.connect(self.open_new_campaign_wizard)
        self.apply_preset_button = secondary_button("Применить preset")
        self.apply_preset_button.setObjectName("applyPresetButton")
        self.apply_preset_button.clicked.connect(self.apply_selected_preset)
        self.quick_email_button = secondary_button("Quick Email Outreach")
        self.quick_email_button.setObjectName("quickEmailOutreachButton")
        self.quick_email_button.clicked.connect(lambda: self.run_quick_start("quick_email_outreach"))
        self.quick_telegram_button = secondary_button("Quick Telegram Campaign")
        self.quick_telegram_button.setObjectName("quickTelegramCampaignButton")
        self.quick_telegram_button.clicked.connect(lambda: self.run_quick_start("quick_telegram_campaign"))
        self.quick_ai_button = secondary_button("Quick AI Draft Generation")
        self.quick_ai_button.setObjectName("quickAiDraftButton")
        self.quick_ai_button.clicked.connect(lambda: self.run_quick_start("quick_ai_draft_generation"))
        self.archive_button = secondary_button("Архивировать")
        self.archive_button.setObjectName("archiveCampaignButton")
        self.archive_button.clicked.connect(self.archive_current_campaign)
        self.duplicate_button = secondary_button("Дублировать")
        self.duplicate_button.setObjectName("duplicateCampaignButton")
        self.duplicate_button.clicked.connect(self.duplicate_current_campaign)
        self.export_button = secondary_button("Экспорт отчета")
        self.export_button.setObjectName("exportCampaignReportButton")
        self.export_button.clicked.connect(self.export_campaign_report)

        self.health_badge = QLabel("Health: —")
        self.health_badge.setObjectName("campaignHealthBadge")
        self.health_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.health_badge.setMinimumHeight(30)

        self.smart_warnings_label = helper_text("Smart warnings: —")
        self.smart_warnings_label.setObjectName("campaignSmartWarningsLabel")
        self.smart_warnings_label.setWordWrap(True)

        self.validation_table = QTableWidget(0, 3)
        self.validation_table.setObjectName("campaignValidationTable")
        self.validation_table.setHorizontalHeaderLabels(["Проверка", "Статус", "Что делать"])
        self.validation_table.setMinimumHeight(190)
        self.validation_table.setColumnWidth(0, 190)
        self.validation_table.setColumnWidth(1, 105)
        self.validation_table.setColumnWidth(2, 420)
        apply_table_style(self.validation_table)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(_header("Кампании", "Operator workflow: preset, checklist и следующий безопасный шаг."))
        layout.addWidget(self._build_summary_card())
        layout.addWidget(self._build_operator_control_card())
        layout.addWidget(self._build_validation_card())
        layout.addWidget(self._build_operator_dashboard_card())
        layout.addWidget(self._build_metrics_grid())
        layout.addWidget(self._build_events_card(), 1)

    def _build_summary_card(self) -> QFrame:
        frame = card()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        self.campaign_name = QLabel("Кампания")
        self.campaign_name.setStyleSheet("font-size: 18px; font-weight: 800;")
        self.campaign_meta = QLabel("Канал • Отправитель • Статус")
        self.campaign_meta.setObjectName("muted")
        self.campaign_meta.setWordWrap(True)
        text_box = QVBoxLayout()
        text_box.addWidget(self.campaign_name)
        text_box.addWidget(self.campaign_meta)
        layout.addLayout(text_box, 1)
        layout.addWidget(self.refresh_button)
        return frame

    def _build_operator_control_card(self) -> QFrame:
        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = QLabel("Quick Start")
        title.setObjectName("dashboardTitle")
        subtitle = helper_text("Выберите preset или запустите безопасный сценарий. Live send не включается автоматически.")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        row = QHBoxLayout()
        row.addWidget(self.preset_selector, 1)
        row.addWidget(self.apply_preset_button)
        row.addWidget(self.new_campaign_button)
        layout.addLayout(row)

        quick = QHBoxLayout()
        quick.addWidget(self.quick_email_button)
        quick.addWidget(self.quick_telegram_button)
        quick.addWidget(self.quick_ai_button)
        quick.addStretch(1)
        layout.addLayout(quick)

        manage = QHBoxLayout()
        manage.addWidget(self.archive_button)
        manage.addWidget(self.duplicate_button)
        manage.addWidget(self.export_button)
        manage.addStretch(1)
        layout.addLayout(manage)
        return frame

    def _build_validation_card(self) -> QFrame:
        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 18)
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Launch checklist")
        title.setObjectName("dashboardTitle")
        subtitle = helper_text("Показывает, что готово, что безопасно, и что стоит исправить перед запуском.")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box, 1)
        top.addWidget(self.health_badge)
        layout.addLayout(top)
        layout.addWidget(self.validation_table)
        layout.addWidget(self.smart_warnings_label)
        return frame

    def _build_operator_dashboard_card(self) -> QFrame:
        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        title = QLabel("Operator dashboard")
        title.setObjectName("dashboardTitle")
        layout.addWidget(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        items = [
            ("active_campaigns", "Активные кампании"),
            ("drafts_pending_review", "Drafts на проверке"),
            ("replies_waiting", "Ответы ждут"),
            ("followup_reminders", "Follow-up reminders"),
            ("risk_alerts", "Risk alerts"),
            ("ai_warnings", "AI warnings"),
        ]
        for index, (key, title_text) in enumerate(items):
            metric = _metric_card(title_text, "0")
            value_label = metric.findChildren(QLabel)[1]
            value_label.setObjectName(f"operatorDashboard_{key}")
            self.operator_cards[key] = value_label
            grid.addWidget(metric, index // 3, index % 3)
        layout.addLayout(grid)
        return frame

    def _build_metrics_grid(self) -> QFrame:
        frame = card()
        grid = QGridLayout(frame)
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        items = [
            ("recipients", "Получателей"),
            ("ai_drafts", "Черновиков AI"),
            ("approved", "Подтверждено"),
            ("sent", "Отправлено"),
            ("dry_run", "Dry-run"),
            ("errors", "Ошибки"),
            ("replies", "Ответы"),
            ("ai_confidence_average", "AI confidence avg"),
        ]
        for index, (key, title) in enumerate(items):
            metric = _metric_card(title, "0")
            value_label = metric.findChildren(QLabel)[1]
            self.metric_cards[key] = value_label
            grid.addWidget(metric, index // 4, index % 4)
        return frame

    def _build_events_card(self) -> QFrame:
        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 18)
        title = QLabel("Contact timeline")
        title.setObjectName("dashboardTitle")
        layout.addWidget(title)
        layout.addWidget(self.events_table, 1)
        return frame

    def refresh(self) -> None:
        data = self.service.campaign_dashboard(self.campaign_id_getter())
        campaign = data["campaign"]
        metrics = data["metrics"]
        settings = self.service.settings()
        preset_id = settings.get("active_campaign_preset", "b2b_email_outreach")
        preset_index = self.preset_selector.findData(preset_id)
        self.preset_selector.blockSignals(True)
        self.preset_selector.setCurrentIndex(max(preset_index, 0))
        self.preset_selector.blockSignals(False)
        self.campaign_name.setText(str(campaign.get("name") or "Кампания"))
        channel = self.service.active_channel_id()
        sender = self.service.active_sender_email() or self.service.telegram_sender_label()
        health = self.service.campaign_health(self.campaign_id_getter(), preset_id=str(self.preset_selector.currentData() or ""))
        self.campaign_meta.setText(
            f"Канал: {channel} • Отправитель: {sender or 'не выбран'} • Статус: {campaign.get('status', 'active')} • Health: {health['label']}"
        )
        self._render_health(health)
        self._render_validation(health["validation"])
        self._render_operator_dashboard()
        for key, label in self.metric_cards.items():
            label.setText(str(metrics.get(key, 0)))
        rows = self.service.campaign_timeline(self.campaign_id_getter()) or data["recent_events"]
        self.events_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            recipient = row.get("email") or row.get("handle") or row.get("external_id") or ""
            values = [
                str(row.get("created_at") or ""),
                str(recipient),
                str(row.get("title") or row.get("event_type") or ""),
                str(row.get("details") or ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.events_table.setItem(row_index, column, item)

    def _render_health(self, health: dict[str, object]) -> None:
        label = str(health.get("label") or "Needs attention")
        score = int(health.get("score") or 0)
        self.health_badge.setText(f"{label} • {score}")
        color = COLORS["green"] if score >= 80 else COLORS["amber"] if score >= 55 else COLORS["red"]
        soft = COLORS["green_soft"] if score >= 80 else COLORS["amber_soft"] if score >= 55 else COLORS["red_soft"]
        self.health_badge.setStyleSheet(
            f"background: {soft}; color: {color}; border-radius: 12px; padding: 5px 10px; font-weight: 800;"
        )

    def _render_validation(self, validation: dict[str, object]) -> None:
        checks = list(validation.get("checks") or [])
        self.validation_table.setRowCount(len(checks))
        for row_index, row in enumerate(checks):
            values = [
                str(row.get("label") or ""),
                str(row.get("status") or ""),
                str(row.get("message") or ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.validation_table.setItem(row_index, column, item)
        warnings = self.service.smart_warnings(self.campaign_id_getter())
        if warnings:
            self.smart_warnings_label.setText("Smart warnings: " + " • ".join(warnings[:4]))
        else:
            self.smart_warnings_label.setText("Smart warnings: критичных предупреждений нет.")

    def _render_operator_dashboard(self) -> None:
        dashboard = self.service.operator_dashboard(self.campaign_id_getter())
        for key, label in self.operator_cards.items():
            label.setText(str(dashboard.get(key, 0)))

    def _finish_action(self, message: str) -> None:
        QMessageBox.information(self, "Кампании", message)
        if self.refresh_callback:
            self.refresh_callback()
        else:
            self.refresh()

    def apply_selected_preset(self) -> None:
        preset_id = str(self.preset_selector.currentData() or "b2b_email_outreach")
        result = self.service.apply_campaign_preset(preset_id, campaign_id=self.campaign_id_getter())
        self._finish_action(f"Preset применен: {result['preset']['name']}. Autosend выключен.")

    def open_new_campaign_wizard(self) -> None:
        dialog = NewCampaignWizard(self.service, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.created_campaign_id:
            if self.campaign_id_setter:
                self.campaign_id_setter(dialog.created_campaign_id)
            self._finish_action("Кампания создана. Проверьте checklist перед запуском drafts.")

    def run_quick_start(self, quick_start_id: str) -> None:
        result = self.service.quick_start_campaign(quick_start_id)
        if self.campaign_id_setter:
            self.campaign_id_setter(int(result["campaign_id"]))
        self._finish_action(f"{result['preset']['quick_start_label'] or result['preset']['name']} создан. Live send не включен.")

    def archive_current_campaign(self) -> None:
        self.service.archive_campaign(self.campaign_id_getter())
        self._finish_action("Кампания архивирована. Ничего не отправлялось.")

    def duplicate_current_campaign(self) -> None:
        new_campaign_id = self.service.duplicate_campaign(self.campaign_id_getter())
        if self.campaign_id_setter:
            self.campaign_id_setter(new_campaign_id)
        self._finish_action("Кампания дублирована как draft. Получатели требуют review.")

    def export_campaign_report(self) -> None:
        result = self.service.enqueue_export_report(self.campaign_id_getter())
        if result.ok:
            self._finish_action("Экспорт отчета поставлен в очередь.")
        else:
            QMessageBox.warning(self, "Экспорт отчета", result.error or "Не удалось поставить экспорт в очередь.")


class ChannelReadinessView(QWidget):
    def __init__(self, service: CampaignService):
        super().__init__()
        self.setObjectName("channelReadinessView")
        self.service = service
        self.refresh_button = secondary_button("Обновить")
        self.refresh_button.setObjectName("channelReadinessRefreshButton")
        self.refresh_button.clicked.connect(self.refresh)

        self.summary_label = helper_text("Статусы каналов показывают безопасную готовность: official API, Manual Assist и ограничения.")
        self.summary_label.setObjectName("channelReadinessSummary")
        self.summary_label.setWordWrap(True)

        self.table = QTableWidget(0, 6)
        self.table.setObjectName("channelReadinessTable")
        self.table.setHorizontalHeaderLabels(["Канал", "Статус", "Official API", "Manual Assist", "Ограничения", "Готовность"])
        self.table.setMinimumHeight(360)
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 190)
        self.table.setColumnWidth(2, 190)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(4, 360)
        self.table.setColumnWidth(5, 110)
        apply_table_style(self.table)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(_header("Готовность каналов", "Что умеет каждый канал, где нужен official API, и где безопасный путь — Помощник отправки."))
        top = QHBoxLayout()
        top.addWidget(self.summary_label, 1)
        top.addWidget(self.refresh_button)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        rows = self.service.channel_readiness_matrix()
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            limitations = (
                f"{row.get('risk_ui_label', '')}. {row.get('notes', '')}"
                + (
                    "\nНужно: " + ", ".join(row.get("missing_credentials") or [])
                    if row.get("missing_credentials")
                    else ""
                )
            )
            values = [
                row.get("display_name", ""),
                row.get("current_status", ""),
                row.get("official_api_live_send", ""),
                row.get("manual_assist_readiness", ""),
                limitations,
                f"{row.get('production_readiness_percent', 0)}%",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 5:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_index, col, item)


class GlobalSearchView(QWidget):
    def __init__(
        self,
        service: CampaignService,
        campaign_id_getter: Callable[[], int],
        campaign_id_setter: Callable[[int], None] | None = None,
        refresh_callback: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.setObjectName("globalSearchView")
        self.service = service
        self.campaign_id_getter = campaign_id_getter
        self.campaign_id_setter = campaign_id_setter
        self.refresh_callback = refresh_callback
        self.results: list[dict[str, object]] = []

        self.search_input = QLineEdit()
        self.search_input.setObjectName("globalSearchInput")
        self.search_input.setPlaceholderText("Поиск по контактам, кампаниям, сообщениям, replies, timeline, логам…")
        self.search_input.returnPressed.connect(self.run_search)
        self.search_button = primary_button("Найти")
        self.search_button.setObjectName("globalSearchButton")
        self.search_button.clicked.connect(self.run_search)
        self.open_button = secondary_button("Открыть результат")
        self.open_button.setObjectName("globalSearchOpenButton")
        self.open_button.clicked.connect(self.open_selected)
        self.recent_selector = QComboBox()
        self.recent_selector.setObjectName("globalSearchRecentSelector")
        self.recent_selector.currentIndexChanged.connect(self._use_recent_search)

        self.results_table = QTableWidget(0, 5)
        self.results_table.setObjectName("globalSearchResultsTable")
        self.results_table.setHorizontalHeaderLabels(["Тип", "Канал", "Кампания/контакт", "Фрагмент", "Действие"])
        self.results_table.setMinimumHeight(420)
        self.results_table.setColumnWidth(0, 110)
        self.results_table.setColumnWidth(1, 100)
        self.results_table.setColumnWidth(2, 220)
        self.results_table.setColumnWidth(3, 540)
        self.results_table.setColumnWidth(4, 100)
        apply_table_style(self.results_table)

        self.empty_label = helper_text("Введите запрос. Поиск не вызывает внешние API и не читает секреты.")
        self.empty_label.setObjectName("globalSearchEmptyState")
        self.empty_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(_header("Поиск", "Один спокойный поиск по истории: контакты, кампании, сообщения, replies, timeline, логи, AI и follow-ups."))
        row = QHBoxLayout()
        row.addWidget(self.search_input, 1)
        row.addWidget(self.recent_selector)
        row.addWidget(self.search_button)
        row.addWidget(self.open_button)
        layout.addLayout(row)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.results_table, 1)

    def refresh(self) -> None:
        self._refresh_recent_searches()
        if self.search_input.text().strip():
            self.run_search()

    def run_search(self) -> None:
        query = self.search_input.text().strip()
        self.results = self.service.global_search(query, campaign_id=None, limit=60)
        self._refresh_recent_searches()
        self.results_table.setRowCount(len(self.results))
        self.empty_label.setVisible(not bool(self.results))
        if not query:
            self.empty_label.setText("Введите запрос. Поиск не вызывает внешние API и не читает секреты.")
        elif not self.results:
            self.empty_label.setText("Ничего не найдено. Попробуйте email, handle, компанию, тему, reply или текст сообщения.")
        for row_index, result in enumerate(self.results):
            title = str(result.get("title") or "")
            campaign = result.get("campaign_id") or ""
            contact = result.get("contact_id") or ""
            values = [
                result.get("result_type", ""),
                result.get("channel", ""),
                f"{title}\nC:{campaign} • L:{contact}",
                result.get("snippet", ""),
                result.get("action", "open"),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                self.results_table.setItem(row_index, col, item)
        if self.results:
            self.results_table.selectRow(0)

    def _refresh_recent_searches(self) -> None:
        current = self.recent_selector.currentData()
        self.recent_selector.blockSignals(True)
        self.recent_selector.clear()
        self.recent_selector.addItem("Recent", "")
        for value in self.service.recent_searches():
            self.recent_selector.addItem(value, value)
        index = self.recent_selector.findData(current)
        self.recent_selector.setCurrentIndex(index if index >= 0 else 0)
        self.recent_selector.blockSignals(False)

    def _use_recent_search(self) -> None:
        value = str(self.recent_selector.currentData() or "")
        if not value:
            return
        self.search_input.setText(value)
        self.run_search()

    def open_selected(self) -> None:
        row = self.results_table.currentRow()
        if row < 0 or row >= len(self.results):
            self.empty_label.setText("Выберите результат для открытия.")
            self.empty_label.setVisible(True)
            return
        result = self.results[row]
        campaign_id = result.get("campaign_id")
        if campaign_id and self.campaign_id_setter:
            self.campaign_id_setter(int(campaign_id))
        if self.refresh_callback:
            self.refresh_callback()
        self.empty_label.setText("Результат выбран. Кампания/контекст обновлены без отправки сообщений.")
        self.empty_label.setVisible(True)


class ChannelCockpitView(QWidget):
    def __init__(self, service: CampaignService, campaign_id_getter: Callable[[], int], refresh_callback: Callable[[], None]):
        super().__init__()
        self.setObjectName("channelCockpitView")
        self.service = service
        self.campaign_id_getter = campaign_id_getter
        self.refresh_callback = refresh_callback
        self.snapshot: dict[str, object] = {}

        self.channel_selector = QComboBox()
        self.channel_selector.setObjectName("cockpitChannelSelector")
        for channel_id, label in [
            ("email", "Email"),
            ("telegram", "Telegram"),
            ("instagram", "Instagram"),
            ("tiktok", "TikTok"),
            ("x", "X"),
            ("vk", "VK"),
            ("whatsapp", "WhatsApp future"),
            ("viber", "Viber future"),
        ]:
            self.channel_selector.addItem(label, channel_id)
        self.channel_selector.currentIndexChanged.connect(self.refresh)

        self.state_label = QLabel("Connection: —")
        self.state_label.setObjectName("cockpitConnectionState")
        self.state_label.setStyleSheet("font-size: 18px; font-weight: 800;")
        self.capability_label = helper_text("Что умеет канал: —")
        self.capability_label.setObjectName("cockpitCapabilitySummary")
        self.capability_label.setWordWrap(True)
        self.limitation_label = helper_text("Ограничения канала: —")
        self.limitation_label.setObjectName("cockpitLimitations")
        self.limitation_label.setWordWrap(True)
        self.stats_label = helper_text("HUD: —")
        self.stats_label.setObjectName("cockpitSessionHud")
        self.stats_label.setWordWrap(True)
        self.recommendation_label = helper_text("Рекомендация: —")
        self.recommendation_label.setObjectName("cockpitRecommendationLabel")
        self.recommendation_label.setWordWrap(True)

        self.workflow_table = QTableWidget(0, 2)
        self.workflow_table.setObjectName("cockpitWorkflowChecklist")
        self.workflow_table.setHorizontalHeaderLabels(["Шаг", "Что делает оператор"])
        self.workflow_table.setMinimumHeight(170)
        self.workflow_table.setColumnWidth(0, 80)
        self.workflow_table.setColumnWidth(1, 520)
        apply_table_style(self.workflow_table)

        self.lead_label = helper_text("Текущий лид: —")
        self.lead_label.setObjectName("cockpitCurrentLead")
        self.lead_label.setWordWrap(True)
        self.message_preview = QTextEdit()
        self.message_preview.setObjectName("cockpitMessagePreview")
        self.message_preview.setMinimumHeight(170)
        self.message_preview.setPlaceholderText("Сообщение появится здесь. Отправка всегда вручную или через official API с подтверждением.")

        self.open_profile_button = secondary_button("Открыть профиль")
        self.open_profile_button.setObjectName("cockpitOpenProfileButton")
        self.open_profile_button.clicked.connect(self.open_profile)
        self.copy_button = primary_button("Скопировать")
        self.copy_button.setObjectName("cockpitCopyButton")
        self.copy_button.clicked.connect(self.copy_message)
        self.mark_sent_button = secondary_button("Отметить отправленным")
        self.mark_sent_button.setObjectName("cockpitMarkSentButton")
        self.mark_sent_button.clicked.connect(self.mark_sent)
        self.add_reply_button = secondary_button("Добавить reply")
        self.add_reply_button.setObjectName("cockpitAddReplyButton")
        self.add_reply_button.clicked.connect(self.add_reply)
        self.next_button = secondary_button("Следующий лид")
        self.next_button.setObjectName("cockpitNextLeadButton")
        self.next_button.clicked.connect(self.next_lead)
        self.export_csv_button = secondary_button("Экспорт CSV")
        self.export_csv_button.setObjectName("cockpitExportCsvButton")
        self.export_csv_button.clicked.connect(lambda: self.export_channel("csv"))
        self.export_json_button = secondary_button("Экспорт JSON")
        self.export_json_button.setObjectName("cockpitExportJsonButton")
        self.export_json_button.clicked.connect(lambda: self.export_channel("json"))
        self.copy_summary_button = secondary_button("Скопировать summary")
        self.copy_summary_button.setObjectName("cockpitCopySummaryButton")
        self.copy_summary_button.clicked.connect(self.copy_summary)

        self.feedback_label = helper_text("Cockpit готов. Никаких скрытых отправок.")
        self.feedback_label.setObjectName("cockpitFeedbackLabel")
        self.feedback_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(_header("Каналы", "Connector slots и operator cockpit: понятно, что подключено, что вручную, и что ограничено."))
        top = QHBoxLayout()
        top.addWidget(QLabel("Канал"))
        top.addWidget(self.channel_selector)
        top.addStretch(1)
        layout.addLayout(top)
        layout.addWidget(self._build_state_card())
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setObjectName("channelCockpitSplitter")
        body.addWidget(self._build_lead_card())
        body.addWidget(self._build_actions_card())
        body.setSizes([680, 280])
        layout.addWidget(body, 1)
        layout.addWidget(self.feedback_label)
        self.refresh()

    def _build_state_card(self) -> QFrame:
        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        layout.addWidget(self.state_label)
        layout.addWidget(self.capability_label)
        layout.addWidget(self.limitation_label)
        layout.addWidget(self.stats_label)
        layout.addWidget(self.recommendation_label)
        layout.addWidget(self.workflow_table)
        return frame

    def _build_lead_card(self) -> QFrame:
        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        title = QLabel("Operator focus")
        title.setObjectName("dashboardTitle")
        layout.addWidget(title)
        layout.addWidget(self.lead_label)
        layout.addWidget(self.message_preview, 1)
        return frame

    def _build_actions_card(self) -> QFrame:
        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(8)
        title = QLabel("Действия")
        title.setObjectName("dashboardTitle")
        layout.addWidget(title)
        for button in (
            self.open_profile_button,
            self.copy_button,
            self.mark_sent_button,
            self.add_reply_button,
            self.next_button,
            self.export_csv_button,
            self.export_json_button,
            self.copy_summary_button,
        ):
            layout.addWidget(button)
        layout.addStretch(1)
        return frame

    def _channel_id(self) -> str:
        return str(self.channel_selector.currentData() or "email")

    def refresh(self) -> None:
        self.snapshot = self.service.channel_cockpit_snapshot(self.campaign_id_getter(), self._channel_id())
        slot = dict(self.snapshot.get("slot") or {})
        self.state_label.setText(
            f"{slot.get('display_name', self._channel_id())}: {slot.get('connection_state', 'Not Configured')}"
        )
        self.capability_label.setText(
            f"Что умеет канал: {slot.get('capability_summary', '—')} • "
            f"Как отправляем: {slot.get('execution_mode_label', '—')}"
        )
        self.limitation_label.setText(
            f"Ограничения канала: {slot.get('risk_label', '—')}. {slot.get('limitations', '')}"
        )
        self.stats_label.setText(
            f"HUD: лидов {self.snapshot.get('contacts_count', 0)} • "
            f"copied {self.snapshot.get('copied', 0)} • "
            f"manual sent {self.snapshot.get('manual_sent', 0)} • "
            f"replies {self.snapshot.get('replies', 0)} • autosend off"
        )
        recommendation = dict(self.snapshot.get("recommendation") or {})
        self.recommendation_label.setText(
            "Рекомендация: "
            + (
                f"{recommendation.get('display_name')} — {recommendation.get('reason')}"
                if recommendation
                else "нет текущего лида для рекомендации"
            )
        )
        self._render_workflow(slot)
        self._render_lead()

    def _render_workflow(self, slot: dict[str, object]) -> None:
        workflow = list(slot.get("recommended_workflow") or [])
        self.workflow_table.setRowCount(len(workflow))
        for row_index, step in enumerate(workflow):
            self.workflow_table.setItem(row_index, 0, QTableWidgetItem(str(row_index + 1)))
            self.workflow_table.setItem(row_index, 1, QTableWidgetItem(str(step)))

    def _render_lead(self) -> None:
        contact = dict(self.snapshot.get("current_contact") or {})
        action = dict(self.snapshot.get("manual_action") or {})
        if not contact:
            self.lead_label.setText("Текущий лид: нет контактов для этого канала.")
            self.message_preview.setPlainText("")
            return
        recipient = contact.get("handle") or contact.get("profile_url") or contact.get("external_id") or contact.get("email") or "—"
        self.lead_label.setText(
            f"{recipient}\n"
            f"Статус: {contact.get('status') or 'new'} • Lead: {contact.get('lead_status') or 'New'}\n"
            f"Profile: {action.get('profile_url') or 'Профиль не найден'}"
        )
        self.message_preview.setPlainText(str(action.get("copy_text") or action.get("message") or ""))

    def _current_contact_id(self) -> int | None:
        contact = dict(self.snapshot.get("current_contact") or {})
        contact_id = int(contact.get("id") or 0)
        return contact_id or None

    def open_profile(self) -> None:
        action = dict(self.snapshot.get("manual_action") or {})
        url = str(action.get("profile_url") or "")
        if url:
            open_external_url(url)
            self.feedback_label.setText("Профиль открыт. Оператор действует вручную; скрытой отправки нет.")
        else:
            self.feedback_label.setText("Профиль не найден. Добавьте handle или profile URL.")

    def copy_message(self) -> None:
        text = self.message_preview.toPlainText().strip()
        QApplication.clipboard().setText(text)
        contact_id = self._current_contact_id()
        if contact_id:
            self.service.db.log_send(
                contact_id,
                self.campaign_id_getter(),
                "cockpit_copy_message",
                "manual_required",
                "Copied from channel cockpit. Nothing was sent.",
                channel=self._channel_id(),
            )
        self.feedback_label.setText("Скопировано. Отправка остается ручной/operator-confirmed.")

    def mark_sent(self) -> None:
        contact_id = self._current_contact_id()
        if not contact_id:
            self.feedback_label.setText("Нет лида для отметки.")
            return
        self.service.update_contact(contact_id, {"generated_message": self.message_preview.toPlainText().strip()})
        self.service.mark_manual_assist_sent([contact_id])
        self.feedback_label.setText("Отмечено отправленным вручную. No hidden automation.")
        self.refresh_callback()
        self.refresh()

    def add_reply(self) -> None:
        contact_id = self._current_contact_id()
        if not contact_id:
            self.feedback_label.setText("Нет лида для reply.")
            return
        self.service.add_reply(contact_id, "Manual reply placeholder from cockpit.", reply_status="no_response")
        self.feedback_label.setText("Reply placeholder добавлен вручную. AI/autoreply не запускались.")
        self.refresh_callback()
        self.refresh()

    def next_lead(self) -> None:
        self.feedback_label.setText("Следующий лид доступен в Outreach Session. Cockpit обновлен.")
        self.refresh()

    def export_channel(self, format: str) -> None:
        result = self.service.export_channel_session(self.campaign_id_getter(), self._channel_id(), format=format)
        self.feedback_label.setText(f"Экспорт готов: {result['path']}")

    def copy_summary(self) -> None:
        result = self.service.export_channel_session(self.campaign_id_getter(), self._channel_id(), format="csv")
        QApplication.clipboard().setText(str(result.get("clipboard_summary") or ""))
        self.feedback_label.setText("Summary скопирован в clipboard.")


class OutreachSessionView(QWidget):
    def __init__(self, service: CampaignService, campaign_id_getter: Callable[[], int], refresh_callback: Callable[[], None]):
        super().__init__()
        self.setObjectName("outreachSessionView")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.service = service
        self.campaign_id_getter = campaign_id_getter
        self.refresh_callback = refresh_callback
        self.current_session_id: int | None = None
        self.current_contact_id: int | None = None
        self.current_snapshot: dict[str, object] | None = None
        self._loading_draft = False

        self.mode_selector = QComboBox()
        self.mode_selector.setObjectName("operatorModeSelector")
        for mode, label in self.service.operator_mode_options():
            self.mode_selector.addItem(label, mode)
        self.mode_selector.currentIndexChanged.connect(self._persist_mode)

        self.batch_order_selector = QComboBox()
        self.batch_order_selector.setObjectName("sessionBatchOrderSelector")
        for value, label in [
            ("priority", "Порядок: Приоритет"),
            ("new", "Порядок: Новые"),
            ("ai_confidence", "Порядок: AI confidence"),
            ("channel", "Порядок: По каналу"),
            ("last_activity", "Порядок: Последняя активность"),
        ]:
            self.batch_order_selector.addItem(label, value)
        self.batch_order_selector.currentIndexChanged.connect(self.refresh)

        self.start_session_button = primary_button("Start Outreach Session")
        self.start_session_button.setObjectName("startOutreachSessionButton")
        self.start_session_button.clicked.connect(self.start_session)
        self.restore_session_button = secondary_button("Restore session")
        self.restore_session_button.setObjectName("restoreOutreachSessionButton")
        self.restore_session_button.clicked.connect(self.restore_session)
        self.focus_mode_toggle = QCheckBox("Focus Mode")
        self.focus_mode_toggle.setObjectName("sessionFocusModeToggle")
        self.focus_mode_toggle.stateChanged.connect(self._toggle_focus_mode)
        self.quick_review_toggle = QCheckBox("Quick Review 2.0")
        self.quick_review_toggle.setObjectName("quickReviewModeToggle")
        self.quick_review_toggle.stateChanged.connect(self._toggle_focus_mode)

        self.high_priority_filter = QCheckBox("High priority only")
        self.high_priority_filter.setObjectName("sessionHighPriorityOnly")
        self.no_contacted_filter = QCheckBox("No-contacted")
        self.no_contacted_filter.setObjectName("sessionNoContactedOnly")
        self.warm_filter = QCheckBox("Warm leads")
        self.warm_filter.setObjectName("sessionWarmOnly")
        self.instagram_filter = QCheckBox("Instagram")
        self.instagram_filter.setObjectName("sessionInstagramOnly")
        self.telegram_filter = QCheckBox("Telegram")
        self.telegram_filter.setObjectName("sessionTelegramOnly")
        self.tiktok_filter = QCheckBox("TikTok")
        self.tiktok_filter.setObjectName("sessionTikTokOnly")
        self.x_filter = QCheckBox("X")
        self.x_filter.setObjectName("sessionXOnly")
        self.vk_filter = QCheckBox("VK")
        self.vk_filter.setObjectName("sessionVKOnly")
        self.needs_review_filter = QCheckBox("Needs review")
        self.needs_review_filter.setObjectName("sessionNeedsReviewFilter")
        self.ready_filter = QCheckBox("Ready to send")
        self.ready_filter.setObjectName("sessionReadyToSendFilter")
        self.manual_assist_filter = QCheckBox("Manual assist")
        self.manual_assist_filter.setObjectName("sessionManualAssistFilter")
        self.followup_filter = QCheckBox("Follow-up due")
        self.followup_filter.setObjectName("sessionFollowupDueFilter")
        self.has_reply_filter = QCheckBox("Has reply")
        self.has_reply_filter.setObjectName("sessionHasReplyFilter")
        self.low_confidence_filter = QCheckBox("Low confidence")
        self.low_confidence_filter.setObjectName("sessionLowConfidenceFilter")
        self.search_input = QLineEdit()
        self.search_input.setObjectName("sessionGlobalSearchInput")
        self.search_input.setPlaceholderText("Search leads, companies, handles, domains...")
        self.search_input.returnPressed.connect(self.refresh)
        for checkbox in (
            self.high_priority_filter,
            self.no_contacted_filter,
            self.warm_filter,
            self.instagram_filter,
            self.telegram_filter,
            self.tiktok_filter,
            self.x_filter,
            self.vk_filter,
            self.needs_review_filter,
            self.ready_filter,
            self.manual_assist_filter,
            self.followup_filter,
            self.has_reply_filter,
            self.low_confidence_filter,
        ):
            checkbox.stateChanged.connect(self.refresh)

        self.progress_label = QLabel("Session not started")
        self.progress_label.setObjectName("sessionProgressLabel")
        self.priority_label = QLabel("Priority: —")
        self.priority_label.setObjectName("sessionPriorityLabel")
        self.risk_label = helper_text("Safe/manual execution. No hidden automation.")
        self.risk_label.setObjectName("sessionRiskLabel")
        self.hotkey_helper = helper_text(
            "Hotkeys: Cmd+K palette • J/K or N/P next/prev • Enter approve • E edit • C copy • O open • S sent • F follow-up • 1/2/3 variants"
        )
        self.hotkey_helper.setObjectName("sessionHotkeyHelperLabel")
        self.hotkey_helper.setWordWrap(True)

        self.lead_summary = helper_text("Start a session to review the next lead.")
        self.lead_summary.setObjectName("sessionLeadSummary")
        self.lead_summary.setWordWrap(True)
        self.draft_editor = QTextEdit()
        self.draft_editor.setObjectName("sessionDraftEditor")
        self.draft_editor.setPlaceholderText("AI draft or manual text appears here...")
        self.draft_editor.setMinimumHeight(260)
        self.draft_editor.textChanged.connect(self._save_draft_state_silent)

        self.approve_button = primary_button("A Approve")
        self.approve_button.setObjectName("sessionApproveButton")
        self.approve_button.clicked.connect(self.approve_current)
        self.regenerate_button = secondary_button("R Regenerate")
        self.regenerate_button.setObjectName("sessionRegenerateButton")
        self.regenerate_button.clicked.connect(self.regenerate_current)
        self.copy_button = secondary_button("C Copy")
        self.copy_button.setObjectName("sessionCopyButton")
        self.copy_button.clicked.connect(self.copy_current)
        self.open_profile_button = secondary_button("O Open profile")
        self.open_profile_button.setObjectName("sessionOpenProfileButton")
        self.open_profile_button.clicked.connect(self.open_current_profile)
        self.mark_sent_button = secondary_button("S Mark sent")
        self.mark_sent_button.setObjectName("sessionMarkSentButton")
        self.mark_sent_button.clicked.connect(self.mark_current_sent)
        self.previous_button = secondary_button("P Previous")
        self.previous_button.setObjectName("sessionPreviousButton")
        self.previous_button.clicked.connect(self.previous_lead)
        self.next_button = secondary_button("N Next")
        self.next_button.setObjectName("sessionNextButton")
        self.next_button.clicked.connect(self.next_lead)
        self.skip_button = secondary_button("Skip")
        self.skip_button.setObjectName("sessionSkipButton")
        self.skip_button.clicked.connect(self.skip_current)
        self.followup_button = secondary_button("F Follow-up")
        self.followup_button.setObjectName("sessionFollowupButton")
        self.followup_button.clicked.connect(self.followup_current)
        self.lead_status_button = secondary_button("L Set Warm")
        self.lead_status_button.setObjectName("sessionLeadStatusButton")
        self.lead_status_button.clicked.connect(self.set_current_warm)
        self.short_variant_button = secondary_button("1 Short")
        self.short_variant_button.setObjectName("sessionVariantShortButton")
        self.short_variant_button.clicked.connect(lambda: self.choose_variant("short"))
        self.friendly_variant_button = secondary_button("2 Friendly")
        self.friendly_variant_button.setObjectName("sessionVariantFriendlyButton")
        self.friendly_variant_button.clicked.connect(lambda: self.choose_variant("friendly"))
        self.direct_variant_button = secondary_button("3 Direct")
        self.direct_variant_button.setObjectName("sessionVariantDirectButton")
        self.direct_variant_button.clicked.connect(lambda: self.choose_variant("direct"))

        self.feedback_selector = QComboBox()
        self.feedback_selector.setObjectName("sessionAiFeedbackSelector")
        for rating, label in [
            ("useful", "Useful"),
            ("generic", "Generic"),
            ("inaccurate", "Inaccurate"),
            ("too_aggressive", "Too aggressive"),
            ("weak_personalization", "Weak personalization"),
        ]:
            self.feedback_selector.addItem(label, rating)
        self.save_feedback_button = secondary_button("Save AI feedback")
        self.save_feedback_button.setObjectName("sessionSaveAiFeedbackButton")
        self.save_feedback_button.clicked.connect(self.save_ai_feedback)

        self.metrics_label = helper_text("Reviewed: 0 • Copied: 0 • Sent manually: 0 • AI acceptance: 0")
        self.metrics_label.setObjectName("sessionMetricsLabel")
        self.feedback_label = helper_text("High Volume Mode is keyboard-first and still manual-confirmed.")
        self.feedback_label.setObjectName("sessionFeedbackLabel")
        self.feedback_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(_header("Outreach Session", "High Volume Operator Mode: быстрый review, copy/open/mark-sent и никаких скрытых отправок."))
        layout.addWidget(self._build_session_controls())
        layout.addWidget(self._build_review_panel(), 1)
        layout.addWidget(self.metrics_label)
        layout.addWidget(self.feedback_label)

        self.hotkey_shortcuts: dict[str, QShortcut] = {}
        self._register_session_hotkeys()
        self.refresh()

    def _build_session_controls(self) -> QFrame:
        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        top = QHBoxLayout()
        top.addWidget(QLabel("Operator mode"))
        top.addWidget(self.mode_selector)
        top.addWidget(self.batch_order_selector)
        top.addWidget(self.start_session_button)
        top.addWidget(self.restore_session_button)
        top.addWidget(self.focus_mode_toggle)
        top.addWidget(self.quick_review_toggle)
        top.addStretch(1)
        layout.addLayout(top)
        self.filters_widget = QWidget()
        filters = QHBoxLayout(self.filters_widget)
        filters.setContentsMargins(0, 0, 0, 0)
        filters.addWidget(self.high_priority_filter)
        filters.addWidget(self.no_contacted_filter)
        filters.addWidget(self.warm_filter)
        filters.addWidget(self.instagram_filter)
        filters.addWidget(self.telegram_filter)
        filters.addWidget(self.tiktok_filter)
        filters.addWidget(self.x_filter)
        filters.addWidget(self.vk_filter)
        filters.addWidget(self.search_input, 1)
        layout.addWidget(self.filters_widget)
        self.chips_widget = QWidget()
        chips = QHBoxLayout(self.chips_widget)
        chips.setContentsMargins(0, 0, 0, 0)
        for checkbox in (
            self.needs_review_filter,
            self.ready_filter,
            self.manual_assist_filter,
            self.followup_filter,
            self.has_reply_filter,
            self.low_confidence_filter,
        ):
            chips.addWidget(checkbox)
        chips.addStretch(1)
        layout.addWidget(self.chips_widget)
        status = QHBoxLayout()
        status.addWidget(self.progress_label)
        status.addWidget(self.priority_label)
        status.addStretch(1)
        layout.addLayout(status)
        layout.addWidget(self.risk_label)
        layout.addWidget(self.hotkey_helper)
        return frame

    def _build_review_panel(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("outreachSessionSplitter")
        left = card()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 14, 16, 16)
        left_title = QLabel("Lead")
        left_title.setObjectName("dashboardTitle")
        left_layout.addWidget(left_title)
        left_layout.addWidget(self.lead_summary, 1)

        center = card()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(16, 14, 16, 16)
        center_title = QLabel("Draft")
        center_title.setObjectName("dashboardTitle")
        center_layout.addWidget(center_title)
        center_layout.addWidget(self.draft_editor, 1)

        right = card()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 14, 16, 16)
        right_layout.setSpacing(8)
        action_title = QLabel("Actions")
        action_title.setObjectName("dashboardTitle")
        right_layout.addWidget(action_title)
        for button in (
            self.approve_button,
            self.regenerate_button,
            self.copy_button,
            self.open_profile_button,
            self.mark_sent_button,
            self.next_button,
            self.previous_button,
            self.skip_button,
            self.followup_button,
            self.lead_status_button,
            self.short_variant_button,
            self.friendly_variant_button,
            self.direct_variant_button,
        ):
            right_layout.addWidget(button)
        right_layout.addWidget(self.feedback_selector)
        right_layout.addWidget(self.save_feedback_button)
        right_layout.addStretch(1)

        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(right)
        splitter.setSizes([320, 520, 260])
        return splitter

    def _register_session_hotkeys(self) -> None:
        bindings: dict[str, Callable[[], None]] = {
            "A": self.approve_current,
            "Return": self.approve_current,
            "Enter": self.approve_current,
            "R": self.regenerate_current,
            "C": self.copy_current,
            "Ctrl+C": self.copy_current,
            "Meta+C": self.copy_current,
            "O": self.open_current_profile,
            "Ctrl+O": self.open_current_profile,
            "Meta+O": self.open_current_profile,
            "S": self.mark_current_sent,
            "Ctrl+S": self.mark_current_sent,
            "Meta+S": self.mark_current_sent,
            "N": self.next_lead,
            "J": self.next_lead,
            "Space": self.next_lead,
            "P": self.previous_lead,
            "K": self.previous_lead,
            "F": self.followup_current,
            "L": self.set_current_warm,
            "E": self._edit_draft_focus,
            "1": lambda: self.choose_variant("short"),
            "2": lambda: self.choose_variant("friendly"),
            "3": lambda: self.choose_variant("direct"),
            "Esc": self.clear_operator_focus,
        }
        for key, callback in bindings.items():
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setObjectName(f"sessionHotkey_{key.replace('+', '_')}")
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(lambda cb=callback, name=key: self._handle_hotkey(cb, name))
            self.hotkey_shortcuts[key] = shortcut

    def _filters(self):
        from ..operator import ReviewQueueFilters

        channels: set[str] = set()
        if self.instagram_filter.isChecked():
            channels.add("instagram")
        if self.telegram_filter.isChecked():
            channels.add("telegram")
        if self.tiktok_filter.isChecked():
            channels.add("tiktok")
        if self.x_filter.isChecked():
            channels.add("x")
        if self.vk_filter.isChecked():
            channels.add("vk")
        return ReviewQueueFilters(
            only_high_priority=self.high_priority_filter.isChecked(),
            only_no_contacted=self.no_contacted_filter.isChecked(),
            only_warm=self.warm_filter.isChecked(),
            channels=channels,
            search=self.search_input.text().strip(),
            order_by=str(self.batch_order_selector.currentData() or "priority"),
            needs_review=self.needs_review_filter.isChecked(),
            ready_to_send=self.ready_filter.isChecked(),
            manual_assist=self.manual_assist_filter.isChecked(),
            follow_up_due=self.followup_filter.isChecked(),
            has_reply=self.has_reply_filter.isChecked(),
            low_confidence=self.low_confidence_filter.isChecked(),
        )

    def _persist_mode(self) -> None:
        self.service.set_operator_mode(str(self.mode_selector.currentData() or "precision"))

    def _toggle_focus_mode(self) -> None:
        enabled = self.focus_mode_toggle.isChecked() or self.quick_review_toggle.isChecked()
        for widget in (self.filters_widget, self.chips_widget, self.risk_label):
            widget.setVisible(not enabled)
        self.feedback_label.setText(
            "Quick Review включен: только текущий лид, черновик, hotkeys и действия."
            if enabled
            else "Quick Review выключен. Фильтры и HUD снова видны."
        )

    def refresh(self) -> None:
        settings_index = self.mode_selector.findData(self.service.operator_mode())
        self.mode_selector.blockSignals(True)
        self.mode_selector.setCurrentIndex(settings_index if settings_index >= 0 else 0)
        self.mode_selector.blockSignals(False)
        snapshot = None
        if self.current_session_id:
            try:
                snapshot = self.service.operator_session_snapshot(self.current_session_id, self._filters())
            except ValueError:
                snapshot = None
        if snapshot is None:
            snapshot = self.service.restore_outreach_session(self.campaign_id_getter())
        if snapshot is not None:
            self._render_snapshot(snapshot)
        else:
            self._render_empty()

    def start_session(self) -> None:
        snapshot = self.service.start_outreach_session(
            self.campaign_id_getter(),
            mode=str(self.mode_selector.currentData() or "high_volume"),
            filters=self._filters(),
        )
        self._render_snapshot(snapshot)
        self.feedback_label.setText("Session started. Autosend is off; operator actions are manual-confirmed.")

    def restore_session(self) -> None:
        snapshot = self.service.restore_outreach_session(self.campaign_id_getter())
        if snapshot is None:
            self.feedback_label.setText("Нет сохраненной сессии. Нажмите Start Outreach Session.")
            return
        self._render_snapshot(snapshot)
        self.feedback_label.setText("Session restored with lead position and filters.")

    def _render_empty(self) -> None:
        self.current_session_id = None
        self.current_contact_id = None
        self.current_snapshot = None
        self.progress_label.setText("Session not started")
        self.priority_label.setText("Priority: —")
        self.lead_summary.setText("Start a session to review leads.")
        self._loading_draft = True
        self.draft_editor.setPlainText("")
        self._loading_draft = False
        self.metrics_label.setText("Reviewed: 0 • Copied: 0 • Sent manually: 0 • AI acceptance: 0")

    def _render_snapshot(self, snapshot: dict[str, object]) -> None:
        self.current_snapshot = snapshot
        session = dict(snapshot.get("session") or {})
        self.current_session_id = int(session.get("id") or 0) or None
        current = snapshot.get("current")
        metrics = dict(snapshot.get("metrics") or {})
        rate = dict(snapshot.get("rate_limit") or {})
        total = int(snapshot.get("total") or 0)
        index = int(snapshot.get("index") or 0)
        progress = round(((index + 1) / total) * 100) if total else 0
        self.progress_label.setText(f"Lead {index + 1 if total else 0}/{total} • {progress}% • {session.get('mode') or 'precision'}")
        self.metrics_label.setText(
            f"Reviewed: {metrics.get('reviewed_leads', 0)} • "
            f"Copied: {metrics.get('copied_messages', 0)} • "
            f"Sent manually: {metrics.get('manually_sent', 0)} • "
            f"Skipped: {metrics.get('skipped_leads', 0)} • "
            f"AI acceptance: {metrics.get('ai_acceptance_rate', 0)}"
        )
        warnings = rate.get("warnings") or ["Safe/manual execution. No bypass attempts."]
        self.risk_label.setText(" • ".join(str(item) for item in warnings[:3]))
        if not current:
            self.current_contact_id = None
            self.priority_label.setText("Priority: —")
            self.lead_summary.setText("Нет лидов под текущие фильтры.")
            self._loading_draft = True
            self.draft_editor.setPlainText("")
            self._loading_draft = False
            return
        item = dict(current)
        contact = dict(item.get("contact") or {})
        priority = dict(item.get("priority") or {})
        self.current_contact_id = int(contact.get("id") or 0) or None
        self.priority_label.setText(f"{priority.get('label', 'Priority')} • {priority.get('score', 0)}")
        recipient = contact.get("email") or contact.get("handle") or contact.get("external_id") or contact.get("profile_url") or ""
        reasons = ", ".join(str(reason) for reason in priority.get("reasons", [])[:4])
        self.lead_summary.setText(
            f"{recipient}\n"
            f"Канал: {contact.get('channel') or 'email'} • Статус: {contact.get('status') or 'new'} • Lead: {contact.get('lead_status') or 'New'}\n"
            f"Имя: {contact.get('name') or '—'} • Компания: {contact.get('company') or '—'}\n"
            f"Сайт: {contact.get('website') or '—'}\n"
            f"Причины приоритета: {reasons or 'данных мало'}"
        )
        self._loading_draft = True
        draft_text = str(session.get("unsaved_draft") or contact.get("generated_message") or contact.get("base_message") or "")
        self.draft_editor.setPlainText(draft_text)
        self._loading_draft = False

    def _current(self) -> tuple[int, int] | None:
        if not self.current_session_id or not self.current_contact_id:
            self.feedback_label.setText("Нет выбранного лида в session queue.")
            return None
        return self.current_session_id, self.current_contact_id

    def _edit_draft_focus(self) -> None:
        self.draft_editor.setFocus()
        self.feedback_label.setText("Draft focused. Type safely; single-key hotkeys pause while editing.")

    def _focus_is_text_input(self) -> bool:
        focus = QApplication.focusWidget()
        return isinstance(focus, (QLineEdit, QTextEdit))

    def _handle_hotkey(self, callback: Callable[[], None], key: str) -> None:
        if key != "Esc" and self._focus_is_text_input():
            return
        callback()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if self._focus_is_text_input():
            super().keyPressEvent(event)
            return
        modifiers = event.modifiers()
        key = event.key()
        command_or_control = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        if key in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self.approve_current()
            event.accept()
            return
        if key in {Qt.Key.Key_A}:
            self.approve_current()
            event.accept()
            return
        if key in {Qt.Key.Key_R}:
            self.regenerate_current()
            event.accept()
            return
        if key in {Qt.Key.Key_J, Qt.Key.Key_N}:
            self.next_lead()
            event.accept()
            return
        if key in {Qt.Key.Key_K, Qt.Key.Key_P}:
            self.previous_lead()
            event.accept()
            return
        if key == Qt.Key.Key_E:
            self._edit_draft_focus()
            event.accept()
            return
        if key == Qt.Key.Key_F:
            self.followup_current()
            event.accept()
            return
        if key == Qt.Key.Key_L:
            self.set_current_warm()
            event.accept()
            return
        if key == Qt.Key.Key_Space:
            self.next_lead()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.clear_operator_focus()
            event.accept()
            return
        if key == Qt.Key.Key_C and command_or_control:
            self.copy_current()
            event.accept()
            return
        if key == Qt.Key.Key_O and command_or_control:
            self.open_current_profile()
            event.accept()
            return
        if key == Qt.Key.Key_S and command_or_control:
            self.mark_current_sent()
            event.accept()
            return
        super().keyPressEvent(event)

    def _save_draft_state_silent(self) -> None:
        if self._loading_draft or not self.current_session_id or not self.current_contact_id:
            return
        self.service.operator_save_draft_state(
            self.current_session_id,
            self.current_contact_id,
            self.draft_editor.toPlainText(),
        )

    def _save_current_draft_to_contact(self) -> None:
        if not self.current_contact_id:
            return
        text = self.draft_editor.toPlainText().strip()
        self.service.update_contact(self.current_contact_id, {"generated_message": text})
        if self.current_session_id:
            self.service.operator_save_draft_state(self.current_session_id, self.current_contact_id, text)

    def clear_operator_focus(self) -> None:
        focus = QApplication.focusWidget()
        if focus is not None:
            focus.clearFocus()
        self.feedback_label.setText("Focus cleared. Session state preserved.")

    def approve_current(self) -> None:
        current = self._current()
        if not current:
            return
        self._save_current_draft_to_contact()
        self.service.operator_approve_draft(*current)
        self.feedback_label.setText("Draft approved for manual/human-controlled execution. No send triggered.")
        self.refresh_callback()

    def regenerate_current(self) -> None:
        current = self._current()
        if not current:
            return
        result = self.service.operator_regenerate_draft(*current)
        self.feedback_label.setText(
            f"Regenerate queued: {result.count}" if result.ok else f"Regenerate blocked: {result.error}"
        )
        self.refresh_callback()

    def copy_current(self) -> None:
        current = self._current()
        if not current:
            return
        self._save_current_draft_to_contact()
        text = self.service.operator_copy_message(*current)
        QApplication.clipboard().setText(text)
        self.feedback_label.setText("Message copied. Operator sends manually; app did not send.")
        self.refresh()

    def open_current_profile(self) -> None:
        current = self._current()
        if not current:
            return
        action = self.service.operator_open_profile(*current)
        if action.profile_url:
            open_external_url(action.profile_url)
            self.feedback_label.setText("Profile opened. Manual Assist only; no hidden automation.")
        else:
            self.feedback_label.setText("Нет profile URL. Скопируйте текст и откройте канал вручную.")
        self.refresh_callback()

    def mark_current_sent(self) -> None:
        current = self._current()
        if not current:
            return
        self._save_current_draft_to_contact()
        snapshot = self.service.operator_mark_manually_sent(*current)
        self._render_snapshot(snapshot)
        self.feedback_label.setText("Marked manually sent. Moving to next lead.")
        self.refresh_callback()

    def next_lead(self) -> None:
        if not self.current_session_id:
            self.feedback_label.setText("Start a session first.")
            return
        self._save_current_draft_to_contact()
        self._render_snapshot(self.service.operator_move_session(self.current_session_id, direction="next"))

    def previous_lead(self) -> None:
        if not self.current_session_id:
            self.feedback_label.setText("Start a session first.")
            return
        self._save_current_draft_to_contact()
        self._render_snapshot(self.service.operator_move_session(self.current_session_id, direction="previous"))

    def skip_current(self) -> None:
        current = self._current()
        if not current:
            return
        self._save_current_draft_to_contact()
        self._render_snapshot(self.service.operator_skip_lead(*current))
        self.feedback_label.setText("Lead skipped. No message was sent.")

    def followup_current(self) -> None:
        current = self._current()
        if not current:
            return
        self.service.operator_schedule_followup(*current)
        self.feedback_label.setText("Follow-up reminder scheduled. No message was sent.")
        self.refresh_callback()

    def set_current_warm(self) -> None:
        current = self._current()
        if not current:
            return
        status = self.service.operator_change_lead_status(current[0], current[1], "Warm")
        self.feedback_label.setText(f"Lead status set to {status}.")
        self.refresh_callback()

    def choose_variant(self, variant: str) -> None:
        current = self._current()
        if not current:
            return
        text = self.service.operator_select_variant(current[0], current[1], variant)
        self.draft_editor.setPlainText(text)
        self.feedback_label.setText(f"Variant selected: {variant}. Review before any manual send.")
        self.refresh_callback()

    def save_ai_feedback(self) -> None:
        current = self._current()
        if not current:
            return
        rating = str(self.feedback_selector.currentData() or "useful")
        self.service.operator_save_ai_feedback(current[0], current[1], rating)
        self.feedback_label.setText(f"AI feedback saved: {rating}.")
        self.refresh()


class UnifiedInboxView(QWidget):
    def __init__(self, service: CampaignService, campaign_id_getter: Callable[[], int], refresh_callback: Callable[[], None]):
        super().__init__()
        self.setObjectName("unifiedInboxView")
        self.service = service
        self.campaign_id_getter = campaign_id_getter
        self.refresh_callback = refresh_callback
        self.current_thread_id: int | None = None
        self.current_contact_id: int | None = None

        self.search_input = QLineEdit()
        self.search_input.setObjectName("inboxSearchInput")
        self.search_input.setPlaceholderText("Поиск по контактам, replies, заметкам...")
        self.search_input.returnPressed.connect(self.refresh)

        self.channel_filter = QComboBox()
        self.channel_filter.setObjectName("inboxChannelFilter")
        self.channel_filter.addItem("Все каналы", "all")
        for channel_id, label in self.service.channel_options():
            self.channel_filter.addItem(label, channel_id)
        self.channel_filter.currentIndexChanged.connect(self.refresh)

        self.lead_filter = QComboBox()
        self.lead_filter.setObjectName("inboxLeadFilter")
        self.lead_filter.addItem("Все стадии", "all")
        for status in ["New", "Contacted", "Warm", "Interested", "Negotiating", "Closed", "Lost"]:
            self.lead_filter.addItem(status, status)
        self.lead_filter.currentIndexChanged.connect(self.refresh)

        self.unread_filter = QComboBox()
        self.unread_filter.setObjectName("inboxUnreadFilter")
        self.unread_filter.addItem("Все", "all")
        self.unread_filter.addItem("Непрочитанные", "unread")
        self.unread_filter.addItem("Прочитанные", "read")
        self.unread_filter.currentIndexChanged.connect(self.refresh)

        self.sync_now_button = primary_button("Sync now")
        self.sync_now_button.setObjectName("inboxSyncNowButton")
        self.sync_now_button.clicked.connect(self.sync_now)
        self.refresh_inbox_button = secondary_button("Refresh inbox")
        self.refresh_inbox_button.setObjectName("inboxRefreshButton")
        self.refresh_inbox_button.clicked.connect(self.refresh)
        self.open_conversation_button = secondary_button("Open conversation")
        self.open_conversation_button.setObjectName("inboxOpenConversationButton")
        self.open_conversation_button.clicked.connect(self._load_selected_thread)
        self.sync_status_label = helper_text("Sync mode: manual. Read-only ingestion; no auto-reply.")
        self.sync_status_label.setObjectName("inboxSyncStatusLabel")

        self.conversation_list = QTableWidget(0, 5)
        self.conversation_list.setObjectName("inboxConversationList")
        self.conversation_list.setHorizontalHeaderLabels(["Канал", "Контакт", "Стадия", "Статус", "Последняя активность"])
        self.conversation_list.setMinimumHeight(320)
        self.conversation_list.setColumnWidth(0, 90)
        self.conversation_list.setColumnWidth(1, 220)
        self.conversation_list.setColumnWidth(2, 115)
        self.conversation_list.setColumnWidth(3, 95)
        self.conversation_list.setColumnWidth(4, 160)
        apply_table_style(self.conversation_list)
        self.conversation_list.itemSelectionChanged.connect(self._load_selected_thread)

        self.thread_table = QTableWidget(0, 5)
        self.thread_table.setObjectName("conversationThreadTable")
        self.thread_table.setHorizontalHeaderLabels(["Время", "Направление", "Тип", "Статус", "Сообщение"])
        self.thread_table.setMinimumHeight(300)
        self.thread_table.setColumnWidth(0, 145)
        self.thread_table.setColumnWidth(1, 110)
        self.thread_table.setColumnWidth(2, 110)
        self.thread_table.setColumnWidth(3, 100)
        self.thread_table.setColumnWidth(4, 420)
        apply_table_style(self.thread_table)

        self.thread_summary = helper_text("Выберите conversation слева. AI Assist только предлагает, но ничего не отправляет.")
        self.thread_summary.setObjectName("conversationSummaryLabel")

        self.lead_selector = QComboBox()
        self.lead_selector.setObjectName("leadStatusSelector")
        for status in ["New", "Contacted", "Warm", "Interested", "Negotiating", "Closed", "Lost"]:
            self.lead_selector.addItem(status, status)
        self.lead_selector.currentIndexChanged.connect(self._change_lead_status)

        self.reply_status_selector = QComboBox()
        self.reply_status_selector.setObjectName("inboxReplyStatusSelector")
        for status, label in [
            ("interested", "Interested"),
            ("maybe_later", "Maybe later"),
            ("not_interested", "Not interested"),
            ("no_response", "No response"),
            ("follow_up_needed", "Follow-up needed"),
            ("closed", "Closed"),
        ]:
            self.reply_status_selector.addItem(label, status)

        self.reply_composer = QTextEdit()
        self.reply_composer.setObjectName("replyComposerInput")
        self.reply_composer.setPlaceholderText("Вставьте входящий ответ или подготовьте ручную заметку...")
        self.reply_composer.setMinimumHeight(90)

        self.save_reply_button = primary_button("Сохранить reply")
        self.save_reply_button.setObjectName("inboxSaveReplyButton")
        self.save_reply_button.clicked.connect(self.save_manual_reply)

        self.summarize_button = secondary_button("AI summary")
        self.summarize_button.setObjectName("inboxSummarizeButton")
        self.summarize_button.clicked.connect(self.summarize_current)

        self.suggest_reply_button = secondary_button("Suggest reply")
        self.suggest_reply_button.setObjectName("inboxSuggestReplyButton")
        self.suggest_reply_button.clicked.connect(self.suggest_reply)

        self.suggest_followup_button = secondary_button("Suggest follow-up")
        self.suggest_followup_button.setObjectName("inboxSuggestFollowupButton")
        self.suggest_followup_button.clicked.connect(self.suggest_followup)

        self.mark_read_button = secondary_button("Отметить прочитанным")
        self.mark_read_button.setObjectName("inboxMarkReadButton")
        self.mark_read_button.clicked.connect(self.mark_read)
        self.copy_reply_button = secondary_button("Copy reply")
        self.copy_reply_button.setObjectName("inboxCopyReplyButton")
        self.copy_reply_button.clicked.connect(self.copy_reply)
        self.open_profile_button = secondary_button("Open profile")
        self.open_profile_button.setObjectName("inboxOpenProfileButton")
        self.open_profile_button.clicked.connect(self.open_profile)
        self.mark_replied_manual_button = secondary_button("Mark replied manually")
        self.mark_replied_manual_button.setObjectName("inboxMarkRepliedManualButton")
        self.mark_replied_manual_button.clicked.connect(self.mark_replied_manually)
        self.mark_followup_done_button = secondary_button("Mark follow-up done")
        self.mark_followup_done_button.setObjectName("inboxMarkFollowupDoneButton")
        self.mark_followup_done_button.clicked.connect(self.mark_followup_done)

        self.feedback_label = helper_text("No autosend: оператор вручную читает, редактирует и решает следующий шаг.")
        self.feedback_label.setObjectName("inboxFeedbackLabel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(_header("Входящие", "Unified inbox для email, Telegram и будущих каналов. Reply intelligence без auto-reply."))

        filters_card = card()
        filters = QHBoxLayout(filters_card)
        filters.setContentsMargins(16, 12, 16, 12)
        filters.addWidget(self.search_input, 1)
        filters.addWidget(self.channel_filter)
        filters.addWidget(self.lead_filter)
        filters.addWidget(self.unread_filter)
        filters.addWidget(self.sync_now_button)
        filters.addWidget(self.refresh_inbox_button)
        filters.addWidget(self.open_conversation_button)
        layout.addWidget(filters_card)
        layout.addWidget(self.sync_status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("inboxSplitter")
        left = card()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 14, 16, 16)
        left_title = QLabel("Conversations")
        left_title.setObjectName("dashboardTitle")
        left_layout.addWidget(left_title)
        left_layout.addWidget(self.conversation_list, 1)

        right = card()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 14, 16, 16)
        top = QHBoxLayout()
        title = QLabel("Thread")
        title.setObjectName("dashboardTitle")
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(QLabel("Lead"))
        top.addWidget(self.lead_selector)
        top.addWidget(self.mark_read_button)
        right_layout.addLayout(top)
        right_layout.addWidget(self.thread_summary)
        right_layout.addWidget(self.thread_table, 1)

        composer_row = QHBoxLayout()
        composer_row.addWidget(QLabel("Reply status"))
        composer_row.addWidget(self.reply_status_selector)
        composer_row.addStretch(1)
        right_layout.addLayout(composer_row)
        right_layout.addWidget(self.reply_composer)
        actions = QHBoxLayout()
        actions.addWidget(self.save_reply_button)
        actions.addWidget(self.summarize_button)
        actions.addWidget(self.suggest_reply_button)
        actions.addWidget(self.suggest_followup_button)
        actions.addWidget(self.copy_reply_button)
        actions.addWidget(self.open_profile_button)
        actions.addWidget(self.mark_replied_manual_button)
        actions.addWidget(self.mark_followup_done_button)
        actions.addStretch(1)
        right_layout.addLayout(actions)
        right_layout.addWidget(self.feedback_label)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([430, 720])
        layout.addWidget(splitter, 1)

    def refresh(self) -> None:
        rows = self.service.unified_inbox(
            self.campaign_id_getter(),
            channel=str(self.channel_filter.currentData() or "all"),
            lead_status=str(self.lead_filter.currentData() or "all"),
            unread=str(self.unread_filter.currentData() or "all"),
            search=self.search_input.text().strip(),
        )
        self.conversation_list.setRowCount(len(rows))
        selected_thread = self.current_thread_id
        for row_index, row in enumerate(rows):
            recipient = row.get("email") or row.get("handle") or row.get("external_id") or f"#{row.get('contact_id')}"
            values = [
                row.get("channel") or "email",
                recipient,
                row.get("lead_status") or "New",
                row.get("unread_state") or "read",
                row.get("last_activity_at") or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, {"thread_id": row["id"], "contact_id": row["contact_id"]})
                self.conversation_list.setItem(row_index, column, item)
            if selected_thread and int(row["id"]) == selected_thread:
                self.conversation_list.selectRow(row_index)
        if rows and self.current_thread_id is None:
            self.conversation_list.selectRow(0)
        elif not rows:
            self.current_thread_id = None
            self.current_contact_id = None
            self.thread_table.setRowCount(0)
            self.thread_summary.setText("Пока нет conversations. Добавьте получателя или сохраните reply.")
        settings = self.service.settings()
        email_state = self.service.inbox_sync_state("email", self.service.active_sender_email())
        telegram_state = self.service.inbox_sync_state("telegram", "telegram_bot")
        self.sync_status_label.setText(
            f"Sync: {settings.get('inbox_sync_mode', 'manual')} • "
            f"Email {email_state.get('status', 'never')} ({email_state.get('last_sync_at') or 'never'}) • "
            f"Telegram {telegram_state.get('status', 'never')} ({telegram_state.get('last_sync_at') or 'never'})"
        )

    def _load_selected_thread(self) -> None:
        items = self.conversation_list.selectedItems()
        if not items:
            return
        data = items[0].data(Qt.ItemDataRole.UserRole) or {}
        thread_id = int(data.get("thread_id") or 0)
        contact_id = int(data.get("contact_id") or 0)
        if not thread_id or not contact_id:
            return
        self.current_thread_id = thread_id
        self.current_contact_id = contact_id
        row = self.service.conversation_thread(contact_id)
        lead_status = row.get("lead_status") or "New"
        self.lead_selector.blockSignals(True)
        index = self.lead_selector.findData(lead_status)
        self.lead_selector.setCurrentIndex(index if index >= 0 else 0)
        self.lead_selector.blockSignals(False)
        self.thread_summary.setText(
            f"{row.get('summary') or 'Summary появится после reply или AI summary.'}\n"
            f"Intent: {row.get('intent') or 'manual review'} • Next: {row.get('recommended_next_action') or 'прочитать conversation'}"
        )
        messages = self.service.conversation_messages(thread_id)
        self.thread_table.setRowCount(len(messages))
        for row_index, message in enumerate(messages):
            values = [
                message.get("created_at") or "",
                message.get("direction") or "",
                message.get("message_type") or "",
                message.get("status") or "",
                message.get("body") or message.get("subject") or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.thread_table.setItem(row_index, column, item)

    def save_manual_reply(self) -> None:
        if not self.current_contact_id:
            self.feedback_label.setText("Выберите conversation слева.")
            return
        text = self.reply_composer.toPlainText().strip()
        if not text:
            self.feedback_label.setText("Вставьте текст reply перед сохранением.")
            return
        result = self.service.add_manual_reply_to_conversation(
            self.current_contact_id,
            text,
            reply_status=str(self.reply_status_selector.currentData() or "no_response"),
        )
        analysis = result["analysis"]
        self.reply_composer.clear()
        self.feedback_label.setText(f"Reply сохранен. Intent: {analysis.intent}. AI ничего не отправлял.")
        self.refresh_callback()

    def summarize_current(self) -> None:
        if not self.current_thread_id:
            self.feedback_label.setText("Выберите conversation для summary.")
            return
        thread = self.service.summarize_conversation(self.current_thread_id)
        self.feedback_label.setText(f"Summary обновлен: {thread.get('summary') or 'готово'}")
        self.refresh_callback()

    def suggest_reply(self) -> None:
        if not self.current_contact_id:
            self.feedback_label.setText("Выберите conversation для AI reply assist.")
            return
        text = self.reply_composer.toPlainText().strip() or "Reply отсутствует. Сформируй осторожный ручной черновик."
        suggestion = self.service.conversation_reply_suggestions(self.current_contact_id, text)
        self.feedback_label.setText(
            f"{suggestion.summary}\nShort: {suggestion.short_reply}\nFormal: {suggestion.formal_reply}\nFriendly: {suggestion.friendly_reply}"
        )

    def suggest_followup(self) -> None:
        if not self.current_contact_id:
            self.feedback_label.setText("Выберите conversation для follow-up suggestion.")
            return
        suggestion = self.service.suggest_followup_for_contact(self.current_contact_id)
        self.feedback_label.setText(
            f"Follow-up suggestion: {suggestion.get('due_at') or 'manual review'} • {suggestion.get('recommendation')}"
        )
        self.refresh_callback()

    def mark_read(self) -> None:
        if not self.current_thread_id:
            self.feedback_label.setText("Выберите conversation.")
            return
        self.service.conversations.mark_thread_read(self.current_thread_id)
        self.feedback_label.setText("Conversation отмечен как прочитанный.")
        self.refresh_callback()

    def copy_reply(self) -> None:
        text = self.reply_composer.toPlainText().strip()
        if not text:
            self.feedback_label.setText("Нет текста для копирования.")
            return
        QApplication.clipboard().setText(text)
        self.feedback_label.setText("Reply скопирован. Отправка остается ручной.")

    def open_profile(self) -> None:
        if not self.current_contact_id:
            self.feedback_label.setText("Выберите conversation.")
            return
        contact = self.service.db.get_contact(self.current_contact_id) or {}
        url = str(contact.get("profile_url") or contact.get("social_profile") or "").strip()
        if not url:
            self.feedback_label.setText("Для контакта нет profile URL.")
            return
        open_external_url(url)
        self.feedback_label.setText("Профиль открыт вручную. Приложение ничего не отправляет.")

    def mark_replied_manually(self) -> None:
        if not self.current_contact_id:
            self.feedback_label.setText("Выберите conversation.")
            return
        self.service.mark_manual_reply_done(self.current_contact_id, self.reply_composer.toPlainText().strip())
        self.feedback_label.setText("Ответ отмечен как отправленный вручную. No autosend.")
        self.refresh_callback()

    def mark_followup_done(self) -> None:
        if not self.current_contact_id:
            self.feedback_label.setText("Выберите conversation.")
            return
        self.service.mark_followup_done(self.current_contact_id)
        self.feedback_label.setText("Follow-up отмечен выполненным вручную. No autosend.")
        self.refresh_callback()

    def _change_lead_status(self) -> None:
        if not self.current_contact_id:
            return
        status = str(self.lead_selector.currentData() or "New")
        self.service.change_lead_status(self.current_contact_id, status)
        self.feedback_label.setText(f"Lead status: {status}")
        self.refresh_callback()

    def sync_now(self) -> None:
        settings = self.service.settings()
        queued: list[str] = []
        if settings.get("email_sync_enabled", "false").lower() == "true":
            result = self.service.enqueue_email_sync(self.campaign_id_getter())
            if result.ok:
                queued.append("Email")
            else:
                self.feedback_label.setText(result.error)
        if settings.get("telegram_sync_enabled", "false").lower() == "true":
            result = self.service.enqueue_telegram_sync(self.campaign_id_getter())
            if result.ok:
                queued.append("Telegram")
            else:
                self.feedback_label.setText(result.error)
        if queued:
            self.feedback_label.setText(f"Sync queued: {', '.join(queued)}. Очередь обработает read-only ingestion.")
        else:
            self.feedback_label.setText("Sync выключен. Включите Email или Telegram sync в Аккаунты и настройки.")
        self.refresh_callback()


class ReplyInboxView(QWidget):
    def __init__(self, service: CampaignService, campaign_id_getter: Callable[[], int], refresh_callback: Callable[[], None]):
        super().__init__()
        self.service = service
        self.campaign_id_getter = campaign_id_getter
        self.refresh_callback = refresh_callback
        self.contact_selector = QComboBox()
        self.contact_selector.setObjectName("replyContactSelector")
        self.status_selector = QComboBox()
        self.status_selector.setObjectName("replyStatusSelector")
        for status, label in [
            ("interested", "Interested"),
            ("maybe_later", "Maybe later"),
            ("not_interested", "Not interested"),
            ("no_response", "No response"),
            ("follow_up_needed", "Follow-up needed"),
            ("closed", "Closed"),
        ]:
            self.status_selector.addItem(label, status)
        self.reply_text = QTextEdit()
        self.reply_text.setObjectName("replyTextInput")
        self.reply_text.setPlaceholderText("Вставьте reply от получателя...")
        self.reply_text.setMinimumHeight(120)
        self.add_reply_button = primary_button("Добавить reply")
        self.add_reply_button.setObjectName("addReplyButton")
        self.add_reply_button.clicked.connect(self.add_reply)
        self.suggest_button = secondary_button("AI предложить ответ")
        self.suggest_button.setObjectName("replySuggestButton")
        self.suggest_button.clicked.connect(self.suggest_reply)
        self.suggestion_label = helper_text("AI Reply Assist не отправляет ответы. Он только предлагает варианты.")
        self.replies_table = QTableWidget(0, 6)
        self.replies_table.setObjectName("replyInboxTable")
        self.replies_table.setHorizontalHeaderLabels(["Время", "Получатель", "Статус", "Reply", "AI summary", "Next action"])
        apply_table_style(self.replies_table)
        self.replies_table.setMinimumHeight(260)
        self.replies_table.setColumnWidth(0, 150)
        self.replies_table.setColumnWidth(1, 180)
        self.replies_table.setColumnWidth(3, 260)
        self.replies_table.setColumnWidth(4, 260)
        self.replies_table.setColumnWidth(5, 260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(_header("Ответы", "Reply Inbox: ручной учет ответов и AI-помощник без автоответов."))
        form_card = card()
        form = QVBoxLayout(form_card)
        form.setContentsMargins(18, 16, 18, 18)
        top = QHBoxLayout()
        top.addWidget(QLabel("Контакт"))
        top.addWidget(self.contact_selector, 1)
        top.addWidget(QLabel("Статус"))
        top.addWidget(self.status_selector)
        form.addLayout(top)
        form.addWidget(self.reply_text)
        actions = QHBoxLayout()
        actions.addWidget(self.add_reply_button)
        actions.addWidget(self.suggest_button)
        actions.addStretch(1)
        form.addLayout(actions)
        form.addWidget(self.suggestion_label)
        layout.addWidget(form_card)
        table_card = card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.addWidget(self.replies_table, 1)
        layout.addWidget(table_card, 1)

    def refresh(self) -> None:
        current_id = self.contact_selector.currentData()
        self.contact_selector.blockSignals(True)
        self.contact_selector.clear()
        for contact in self.service.contacts(self.campaign_id_getter()):
            label = contact.get("email") or contact.get("handle") or contact.get("external_id") or f"#{contact['id']}"
            self.contact_selector.addItem(str(label), int(contact["id"]))
        if current_id is not None:
            index = self.contact_selector.findData(current_id)
            if index >= 0:
                self.contact_selector.setCurrentIndex(index)
        self.contact_selector.blockSignals(False)
        rows = self.service.list_replies(self.campaign_id_getter())
        self.replies_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            recipient = row.get("email") or row.get("handle") or row.get("external_id") or ""
            values = [
                row.get("created_at") or "",
                recipient,
                row.get("reply_status") or "",
                row.get("reply_text") or "",
                row.get("ai_summary") or "",
                row.get("suggested_next_action") or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.replies_table.setItem(row_index, column, item)

    def add_reply(self) -> None:
        contact_id = self.contact_selector.currentData()
        text = self.reply_text.toPlainText().strip()
        if not contact_id or not text:
            QMessageBox.information(self, "Ответы", "Выберите контакт и добавьте текст reply.")
            return
        self.service.add_reply(int(contact_id), text, reply_status=str(self.status_selector.currentData()))
        self.reply_text.clear()
        self.refresh_callback()
        QMessageBox.information(self, "Ответы", "Reply сохранен. AI ничего не отправлял.")

    def suggest_reply(self) -> None:
        contact_id = self.contact_selector.currentData()
        text = self.reply_text.toPlainText().strip()
        if not contact_id or not text:
            QMessageBox.information(self, "AI Reply Assist", "Выберите контакт и вставьте reply.")
            return
        result = self.service.reply_suggestions(int(contact_id), text)
        self.suggestion_label.setText(
            f"{result.summary}\nNext: {result.suggested_next_action}\n"
            f"Short: {result.short_reply}\nFormal: {result.formal_reply}\nFriendly: {result.friendly_reply}"
        )


class AIAssistIntelligenceView(QWidget):
    def __init__(self, service: CampaignService, campaign_id_getter: Callable[[], int]):
        super().__init__()
        self.service = service
        self.campaign_id_getter = campaign_id_getter
        self.contact_selector = QComboBox()
        self.contact_selector.setObjectName("aiAssistContactSelector")
        self.preset_selector = QComboBox()
        self.preset_selector.setObjectName("campaignPresetSelector")
        for preset in self.service.analytics.list_presets():
            self.preset_selector.addItem(preset["name"], preset["id"])
        self.score_button = primary_button("Оценить качество черновика")
        self.score_button.setObjectName("aiScoreDraftButton")
        self.score_button.clicked.connect(self.score_selected)
        self.reply_hint = QLineEdit()
        self.reply_hint.setObjectName("aiReplyHintInput")
        self.reply_hint.setPlaceholderText("Reply для AI Assist...")
        self.reply_button = secondary_button("Сгенерировать варианты ответа")
        self.reply_button.setObjectName("aiGenerateReplyButton")
        self.reply_button.clicked.connect(self.generate_reply_options)
        self.quality_panel = helper_text("Quality scoring появится после оценки. AI не подтверждает и не отправляет сообщения.")

        self.drafts_table = QTableWidget(0, 6)
        self.drafts_table.setObjectName("aiDraftsTable")
        self.drafts_table.setHorizontalHeaderLabels(["Получатель", "Канал", "AI", "Confidence", "Warnings", "Статус"])
        apply_table_style(self.drafts_table)
        self.drafts_table.setMinimumHeight(320)
        self.drafts_table.setColumnWidth(0, 210)
        self.drafts_table.setColumnWidth(4, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(_header("AI Assist", "Черновики, quality scoring и reply suggestions. Без auto-send."))
        controls = card()
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(18, 16, 18, 18)
        row = QHBoxLayout()
        row.addWidget(QLabel("Контакт"))
        row.addWidget(self.contact_selector, 1)
        row.addWidget(QLabel("Preset"))
        row.addWidget(self.preset_selector)
        row.addWidget(self.score_button)
        controls_layout.addLayout(row)
        reply_row = QHBoxLayout()
        reply_row.addWidget(self.reply_hint, 1)
        reply_row.addWidget(self.reply_button)
        controls_layout.addLayout(reply_row)
        controls_layout.addWidget(self.quality_panel)
        layout.addWidget(controls)
        table_card = card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.addWidget(self.drafts_table, 1)
        layout.addWidget(table_card, 1)

    def refresh(self) -> None:
        contacts = self.service.contacts(self.campaign_id_getter())
        self.contact_selector.blockSignals(True)
        current = self.contact_selector.currentData()
        self.contact_selector.clear()
        for contact in contacts:
            label = contact.get("email") or contact.get("handle") or contact.get("external_id") or f"#{contact['id']}"
            self.contact_selector.addItem(str(label), int(contact["id"]))
        if current is not None:
            index = self.contact_selector.findData(current)
            if index >= 0:
                self.contact_selector.setCurrentIndex(index)
        self.contact_selector.blockSignals(False)

        self.drafts_table.setRowCount(len(contacts))
        for row, contact in enumerate(contacts):
            recipient = contact.get("email") or contact.get("handle") or contact.get("external_id") or ""
            values = [
                recipient,
                contact.get("channel") or "email",
                "AI" if int(contact.get("ai_generated") or 0) else "",
                contact.get("ai_confidence") or "",
                contact.get("ai_warnings") or "",
                contact.get("status") or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.drafts_table.setItem(row, column, item)

    def score_selected(self) -> None:
        contact_id = self.contact_selector.currentData()
        if not contact_id:
            QMessageBox.information(self, "AI Assist", "Выберите контакт.")
            return
        score = self.service.score_contact_draft(int(contact_id))
        self.quality_panel.setText(
            f"Spam risk: {score.spam_risk}\n"
            f"Personalization: {score.personalization_quality}\n"
            f"Too generic: {score.genericness_score}\n"
            f"Tone quality: {score.tone_quality}\n"
            f"Warnings: {', '.join(score.warnings) or 'нет'}"
        )
        self.refresh()

    def generate_reply_options(self) -> None:
        contact_id = self.contact_selector.currentData()
        text = self.reply_hint.text().strip()
        if not contact_id or not text:
            QMessageBox.information(self, "AI Reply Assist", "Выберите контакт и добавьте reply.")
            return
        result = self.service.reply_suggestions(int(contact_id), text)
        self.quality_panel.setText(
            f"{result.summary}\nNext: {result.suggested_next_action}\n"
            f"1) {result.short_reply}\n2) {result.formal_reply}\n3) {result.friendly_reply}"
        )


class AnalyticsView(QWidget):
    def __init__(self, service: CampaignService, campaign_id_getter: Callable[[], int]):
        super().__init__()
        self.service = service
        self.campaign_id_getter = campaign_id_getter
        self.metric_labels: dict[str, QLabel] = {}
        self.breakdown_label = helper_text("Channel breakdown появится после refresh.")
        self.refresh_button = secondary_button("Обновить аналитику")
        self.refresh_button.setObjectName("analyticsRefreshButton")
        self.refresh_button.clicked.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(_header("Аналитика", "Минимальная сводка по отправкам, ответам и каналам."))
        grid_card = card()
        grid = QGridLayout(grid_card)
        grid.setContentsMargins(14, 14, 14, 14)
        items = [
            ("sent", "Sent"),
            ("reply_rate", "Reply rate"),
            ("approval_rate", "Approval rate"),
            ("ai_drafts", "AI drafts"),
            ("dry_run", "Dry-run"),
            ("errors", "Errors"),
        ]
        for index, (key, title) in enumerate(items):
            metric = _metric_card(title, "0")
            self.metric_labels[key] = metric.findChildren(QLabel)[1]
            grid.addWidget(metric, index // 3, index % 3)
        layout.addWidget(grid_card)
        detail_card = card()
        detail = QVBoxLayout(detail_card)
        detail.setContentsMargins(18, 16, 18, 18)
        detail.addWidget(self.refresh_button)
        detail.addWidget(self.breakdown_label)
        layout.addWidget(detail_card)
        layout.addStretch(1)

    def refresh(self) -> None:
        metrics = self.service.campaign_metrics(self.campaign_id_getter())
        for key, label in self.metric_labels.items():
            label.setText(str(metrics.get(key, 0)))
        self.breakdown_label.setText(
            f"Channels: {metrics.get('channel_breakdown', {})}\n"
            f"Response statuses: {metrics.get('response_statuses', {})}\n"
            "AI не отправляет и не подтверждает сообщения автоматически."
        )
