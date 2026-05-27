from __future__ import annotations

import os
import time
from collections.abc import Callable

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..campaign_service import CampaignService
from ..inbox.sync_scheduler import normalize_interval, normalize_sync_mode
from .about_dialog import AboutDialog
from .campaign_view import CampaignView
from .contacts_table import ContactsTable
from .i18n import send_mode_to_ru
from .intelligence_views import (
    AIAssistIntelligenceView,
    AnalyticsView,
    CampaignDashboardView,
    ChannelCockpitView,
    ChannelReadinessView,
    GlobalSearchView,
    OutreachSessionView,
    ReplyInboxView,
    UnifiedInboxView,
)
from .logs_view import LogsView
from .onboarding import OnboardingDialog
from .operator_platform import (
    BackgroundTaskMonitorView,
    CommandPaletteDialog,
    NotificationCenterView,
    PerformancePlatformView,
)
from .settings_view import SettingsView
from .template_view import TemplateView
from .theme import COLORS, SECTION_GAP_COMPACT, app_stylesheet, card, wrap_scroll


class TabsCompat:
    def __init__(self, stack: QStackedWidget):
        self.stack = stack
        self._tabs: list[tuple[QWidget, QScrollArea, str]] = []

    def addTab(self, widget: QWidget, label: str) -> None:
        scroll = wrap_scroll(widget)
        self._tabs.append((widget, scroll, label))
        self.stack.addWidget(scroll)

    def count(self) -> int:
        return len(self._tabs)

    def tabText(self, index: int) -> str:
        return self._tabs[index][2]

    def setCurrentWidget(self, widget: QWidget) -> None:
        for original, scroll, _label in self._tabs:
            if original is widget or scroll is widget:
                self.stack.setCurrentWidget(scroll)
                return

    def currentWidget(self) -> QWidget:
        current = self.stack.currentWidget()
        for original, scroll, _label in self._tabs:
            if current is scroll:
                return original
        return current

    def scrollWidget(self, index: int) -> QScrollArea:
        return self._tabs[index][1]


class MainWindow(QMainWindow):
    def __init__(self, service: CampaignService):
        super().__init__()
        self.service = service
        self._active_campaign_id = service.default_campaign_id()
        self._last_inbox_background_sync_at = 0.0
        self.setWindowTitle("Рассылка через Gmail - безопасный режим")
        self.resize(1280, 800)
        self.setMinimumSize(1180, 720)

        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        self.setStyleSheet(app_stylesheet())

        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(SECTION_GAP_COMPACT)

        self.content_stack = QStackedWidget()
        self.content_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tabs = TabsCompat(self.content_stack)

        self.contacts_view = ContactsTable(
            service,
            self.active_campaign_id,
            self.refresh_all,
        )
        self.campaign_view = CampaignView(
            service,
            self.active_campaign_id,
            self.set_active_campaign_id,
            self.contacts_view.selected_contact_ids,
            self.refresh_all,
            self.add_contact_row_from_campaign,
            self.paste_contacts_from_campaign,
            self.open_settings,
            self.delete_contacts_from_campaign,
            self.save_contacts_from_campaign,
        )
        self.template_view = TemplateView(
            service,
            self.contacts_view.selected_contact_ids,
            self.refresh_all,
        )
        self.settings_view = SettingsView(service, self.refresh_all)
        self.logs_view = LogsView(service)
        self.campaign_dashboard_view = CampaignDashboardView(
            service,
            self.active_campaign_id,
            self.set_active_campaign_id,
            self.refresh_all,
        )
        self.outreach_session_view = OutreachSessionView(service, self.active_campaign_id, self.refresh_all)
        self.ai_assist_view = AIAssistIntelligenceView(service, self.active_campaign_id)
        self.channel_cockpit_view = ChannelCockpitView(service, self.active_campaign_id, self.refresh_all)
        self.channel_readiness_view = ChannelReadinessView(service)
        self.global_search_view = GlobalSearchView(service, self.active_campaign_id, self.set_active_campaign_id, self.refresh_all)
        self.notification_center_view = NotificationCenterView(service, self.active_campaign_id)
        self.background_task_monitor_view = BackgroundTaskMonitorView(service, self.active_campaign_id)
        self.unified_inbox_view = UnifiedInboxView(service, self.active_campaign_id, self.refresh_all)
        self.reply_inbox_view = ReplyInboxView(service, self.active_campaign_id, self.refresh_all)
        self.analytics_view = AnalyticsView(service, self.active_campaign_id)
        self.performance_platform_view = PerformancePlatformView(service, self.active_campaign_id)

        self.tabs.addTab(self.campaign_view, "Рассылка")
        self.tabs.addTab(self.contacts_view, "Получатели")
        self.tabs.addTab(self.template_view, "Шаблоны")
        self.tabs.addTab(self.settings_view, "Аккаунты и настройки")
        self.tabs.addTab(self.logs_view, "Журнал")

        self.extra_page_indices: dict[str, int] = {}
        for key, widget in (
            ("campaigns", self.campaign_dashboard_view),
            ("outreach_session", self.outreach_session_view),
            ("ai_assist", self.ai_assist_view),
            ("channel_cockpit", self.channel_cockpit_view),
            ("channel_readiness", self.channel_readiness_view),
            ("global_search", self.global_search_view),
            ("notifications", self.notification_center_view),
            ("task_monitor", self.background_task_monitor_view),
            ("inbox", self.unified_inbox_view),
            ("replies", self.reply_inbox_view),
            ("analytics", self.analytics_view),
            ("performance", self.performance_platform_view),
        ):
            self.extra_page_indices[key] = self.content_stack.count()
            self.content_stack.addWidget(wrap_scroll(widget))

        self.sidebar_buttons: list[QPushButton] = []
        self.intelligence_sidebar_buttons: list[QPushButton] = []
        self.sidebar = self._build_sidebar()
        self.sidebar_scroll = wrap_scroll(self.sidebar)
        self.sidebar_scroll.setObjectName("sidebarScroll")
        self.sidebar_scroll.setFixedWidth(240)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root_layout.addWidget(self.sidebar_scroll)
        root_layout.addWidget(self.content_stack, 1)

        self._register_shortcuts()
        self._select_page(0)
        self._setup_inbox_sync_timer()
        self.refresh_all()
        self._schedule_onboarding_if_needed()

    def active_campaign_id(self) -> int:
        return self._active_campaign_id

    def set_active_campaign_id(self, campaign_id: int) -> None:
        self._active_campaign_id = campaign_id
        self.refresh_all()

    def refresh_all(self) -> None:
        self.campaign_view.refresh()
        self.contacts_view.refresh()
        self.template_view.refresh()
        self.settings_view.refresh()
        self.logs_view.refresh()
        self.campaign_dashboard_view.refresh()
        self.outreach_session_view.refresh()
        self.ai_assist_view.refresh()
        self.channel_cockpit_view.refresh()
        self.channel_readiness_view.refresh()
        self.global_search_view.refresh()
        self.notification_center_view.refresh()
        self.background_task_monitor_view.refresh()
        self.unified_inbox_view.refresh()
        self.reply_inbox_view.refresh()
        self.analytics_view.refresh()
        self.performance_platform_view.refresh()
        self._refresh_sidebar_mode()

    def add_contact_row_from_campaign(self) -> None:
        self.campaign_view.add_empty_preview_row()

    def paste_contacts_from_campaign(self) -> None:
        self.campaign_view.paste_rows_from_clipboard()

    def delete_contacts_from_campaign(self) -> None:
        self.campaign_view.delete_selected_preview_rows()

    def save_contacts_from_campaign(self) -> None:
        self.campaign_view.save_preview_rows()

    def open_settings(self) -> None:
        self._select_page(3)

    def show_about(self) -> None:
        AboutDialog(parent=self).exec()

    def _register_shortcuts(self) -> None:
        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self.save_shortcut.setObjectName("saveChangesShortcut")
        self.save_shortcut.activated.connect(self.contacts_view.save_changes)

        self.paste_shortcut = QShortcut(QKeySequence.StandardKey.Paste, self)
        self.paste_shortcut.setObjectName("pasteRowsShortcut")
        self.paste_shortcut.activated.connect(self._paste_rows_if_table_active)

        self.delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        self.delete_shortcut.setObjectName("deleteRowsShortcut")
        self.delete_shortcut.activated.connect(self._delete_rows_if_table_active)

        self.enter_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        self.enter_shortcut.setObjectName("editRowShortcut")
        self.enter_shortcut.activated.connect(self._edit_row_if_table_active)

        self.command_palette_shortcut = QShortcut(QKeySequence("Meta+K"), self)
        self.command_palette_shortcut.setObjectName("commandPaletteShortcut")
        self.command_palette_shortcut.activated.connect(self.open_command_palette)

        self.command_palette_shortcut_ctrl = QShortcut(QKeySequence("Ctrl+K"), self)
        self.command_palette_shortcut_ctrl.setObjectName("commandPaletteShortcutCtrl")
        self.command_palette_shortcut_ctrl.activated.connect(self.open_command_palette)

    def open_command_palette(self) -> None:
        dialog = CommandPaletteDialog(self.service, self.active_campaign_id(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result:
            campaign_id = dialog.result.get("campaign_id")
            if campaign_id:
                self.set_active_campaign_id(int(campaign_id))
            self.refresh_all()

    def _schedule_onboarding_if_needed(self) -> None:
        if os.getenv("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "").strip() == "1":
            return
        if os.getenv("QT_QPA_PLATFORM", "").strip().lower() == "offscreen":
            return
        if self.service.settings().get("onboarding_completed", "false").lower() == "true":
            return
        QTimer.singleShot(250, self.show_onboarding)

    def show_onboarding(self) -> None:
        dialog = OnboardingDialog(self._mark_onboarding_completed, parent=self)
        dialog.open()

    def _mark_onboarding_completed(self) -> None:
        self.service.save_settings({"onboarding_completed": "true"})

    def _setup_inbox_sync_timer(self) -> None:
        self.inbox_sync_timer = QTimer(self)
        self.inbox_sync_timer.setObjectName("inboxBackgroundSyncTimer")
        self.inbox_sync_timer.setInterval(60_000)
        self.inbox_sync_timer.timeout.connect(self._maybe_enqueue_background_inbox_sync)
        self.inbox_sync_timer.start()

    def _maybe_enqueue_background_inbox_sync(self) -> None:
        settings = self.service.settings()
        if normalize_sync_mode(settings.get("inbox_sync_mode")) != "background":
            return
        interval_seconds = normalize_interval(settings.get("inbox_sync_interval_minutes")) * 60
        now = time.monotonic()
        if now - self._last_inbox_background_sync_at < interval_seconds:
            return

        queued_any = False
        if settings.get("email_sync_enabled", "false").lower() == "true":
            queued_any = self.service.enqueue_email_sync(self.active_campaign_id()).ok or queued_any
        if settings.get("telegram_sync_enabled", "false").lower() == "true":
            queued_any = self.service.enqueue_telegram_sync(self.active_campaign_id()).ok or queued_any
        if queued_any:
            self._last_inbox_background_sync_at = now
            self.campaign_view.start_queue_worker()

    def _contacts_table_is_context(self) -> bool:
        focus_widget = QApplication.focusWidget()
        return (
            self.tabs.currentWidget() is self.contacts_view
            and focus_widget is not None
            and (
                focus_widget is self.contacts_view.table
                or self.contacts_view.table.isAncestorOf(focus_widget)
            )
        )

    def _paste_rows_if_table_active(self) -> None:
        if self._contacts_table_is_context():
            self.contacts_view.paste_from_clipboard()

    def _delete_rows_if_table_active(self) -> None:
        if self._contacts_table_is_context():
            self.contacts_view.delete_selected_rows()

    def _edit_row_if_table_active(self) -> None:
        if self._contacts_table_is_context():
            self.contacts_view.edit_selected_row()

    def closeEvent(self, event) -> None:
        self.service.save_operator_ui_state(
            active_campaign_id=self.active_campaign_id(),
            current_page_index=self.content_stack.currentIndex(),
        )
        self.campaign_view.shutdown()
        self.settings_view.shutdown()
        super().closeEvent(event)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(228)
        sidebar.setMinimumHeight(640)
        sidebar.setStyleSheet(
            f"""
            QFrame#sidebar {{
                background: {COLORS["sidebar"]};
                border: 1px solid {COLORS["border_soft"]};
                border-radius: 18px;
            }}
            """
        )
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(8)

        logo_row = QHBoxLayout()
        logo = QLabel("✈")
        logo.setFixedSize(34, 34)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(
            f"background: {COLORS['primary_soft']}; color: {COLORS['primary']}; "
            "border-radius: 12px; font-size: 18px; font-weight: 800;"
        )
        title_box = QVBoxLayout()
        app_title = QLabel("Gmail Рассылка")
        app_title.setStyleSheet("font-size: 15px; font-weight: 800;")
        app_subtitle = QLabel("Безопасная отправка писем")
        app_subtitle.setObjectName("muted")
        app_subtitle.setWordWrap(True)
        title_box.addWidget(app_title)
        title_box.addWidget(app_subtitle)
        logo_row.addWidget(logo)
        logo_row.addLayout(title_box, 1)
        layout.addLayout(logo_row)
        layout.addSpacing(4)

        self.sidebar_group = QButtonGroup(self)
        self.sidebar_group.setExclusive(True)
        items = [
            ("Рассылка", "Главная"),
            ("Получатели", "Таблица контактов"),
            ("Шаблоны", "Готовые шаблоны"),
            ("Аккаунты и настройки", "Email, лимиты, каналы"),
            ("Журнал", "История действий"),
        ]
        for index, (title, subtitle) in enumerate(items):
            button = QPushButton(f"{title}\n{subtitle}")
            button.setObjectName("sidebarItem")
            button.setCheckable(True)
            button.setMinimumHeight(50)
            button.clicked.connect(self._make_page_selector(index))
            self.sidebar_group.addButton(button, index)
            self.sidebar_buttons.append(button)
            layout.addWidget(button)

        intelligence_label = QLabel("Intelligence")
        intelligence_label.setObjectName("muted")
        intelligence_label.setStyleSheet(f"color: {COLORS['muted']}; padding: 8px 10px 2px; font-weight: 700;")
        layout.addWidget(intelligence_label)
        intelligence_items = [
            ("Кампании", "Сводка и timeline", "campaigns"),
            ("Outreach Session", "High Volume review", "outreach_session"),
            ("AI Assist", "Качество и ответы", "ai_assist"),
            ("Каналы", "Operator cockpits", "channel_cockpit"),
            ("Готовность каналов", "Что умеет канал", "channel_readiness"),
            ("Поиск", "История и контакты", "global_search"),
            ("Уведомления", "Replies and alerts", "notifications"),
            ("Задачи", "Queue health", "task_monitor"),
            ("Входящие", "Unified inbox", "inbox"),
            ("Ответы", "Reply Inbox", "replies"),
            ("Аналитика", "Метрики кампании", "analytics"),
            ("Performance", "Latency and cache", "performance"),
        ]
        for title, subtitle, key in intelligence_items:
            button = QPushButton(f"{title}\n{subtitle}")
            button.setObjectName("sidebarItem")
            button.setMinimumHeight(50)
            button.clicked.connect(self._make_page_selector(self.extra_page_indices[key]))
            self.intelligence_sidebar_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)
        self.mode_card = card("modeCard")
        self.mode_card.setGraphicsEffect(None)
        self.mode_card.setMinimumHeight(72)
        self.mode_card.setMaximumHeight(82)
        self.mode_card.setStyleSheet(
            f"QFrame#modeCard {{ background: {COLORS['green_soft']}; "
            "border: 1px solid #CDEFD8; border-radius: 14px; }"
        )
        mode_layout = QVBoxLayout(self.mode_card)
        mode_layout.setContentsMargins(12, 10, 12, 10)
        self.mode_title = QLabel("Тестовый режим")
        self.mode_title.setStyleSheet(f"color: {COLORS['green']}; font-size: 14px; font-weight: 800;")
        self.mode_subtitle = QLabel("Письма не отправляются")
        self.mode_subtitle.setStyleSheet(f"color: {COLORS['green']};")
        self.mode_subtitle.setWordWrap(True)
        mode_layout.addWidget(self.mode_title)
        mode_layout.addWidget(self.mode_subtitle)
        layout.addWidget(self.mode_card)

        self.about_button = QPushButton("О приложении")
        self.about_button.setObjectName("sidebarItem")
        self.about_button.setMinimumHeight(38)
        self.about_button.clicked.connect(self.show_about)
        layout.addWidget(self.about_button)

        ready = QLabel("● Готов к работе")
        ready.setStyleSheet(f"color: {COLORS['muted']}; padding: 4px 2px;")
        layout.addWidget(ready)
        return sidebar

    def _make_page_selector(self, index: int) -> Callable[[], None]:
        return lambda: self._select_page(index)

    def _select_page(self, index: int) -> None:
        self.content_stack.setCurrentIndex(index)
        self.service.save_operator_ui_state(
            active_campaign_id=self.active_campaign_id(),
            current_page_index=index,
        )
        if 0 <= index < len(self.sidebar_buttons):
            self.sidebar_buttons[index].setChecked(True)
        else:
            for button in self.sidebar_buttons:
                button.setChecked(False)

    def _refresh_sidebar_mode(self) -> None:
        mode = self.service.settings().get("send_mode", "dry_run")
        mode_label = send_mode_to_ru(mode)
        self.mode_title.setText(mode_label)
        if mode == "live":
            self.mode_subtitle.setText("Письма отправляются через Gmail")
            self.mode_card.setStyleSheet(
                f"QFrame#modeCard {{ background: {COLORS['amber_soft']}; "
                "border: 1px solid #F5D49B; border-radius: 14px; }"
            )
            self.mode_title.setStyleSheet(f"color: {COLORS['amber']}; font-size: 14px; font-weight: 800;")
            self.mode_subtitle.setStyleSheet(f"color: {COLORS['amber']};")
        else:
            self.mode_subtitle.setText("Письма не отправляются")
            self.mode_card.setStyleSheet(
                f"QFrame#modeCard {{ background: {COLORS['green_soft']}; "
                "border: 1px solid #CDEFD8; border-radius: 14px; }"
            )
            self.mode_title.setStyleSheet(f"color: {COLORS['green']}; font-size: 14px; font-weight: 800;")
            self.mode_subtitle.setStyleSheet(f"color: {COLORS['green']};")
