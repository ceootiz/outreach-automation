from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..campaign_service import CampaignService
from .theme import apply_table_style, card, helper_text, primary_button, secondary_button


def _header(title: str, subtitle: str) -> QWidget:
    frame = QWidget()
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    title_label = QLabel(title)
    title_label.setObjectName("sectionTitle")
    subtitle_label = helper_text(subtitle)
    subtitle_label.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)
    return frame


class CommandPaletteDialog(QDialog):
    def __init__(self, service: CampaignService, campaign_id: int | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("commandPaletteDialog")
        self.setWindowTitle("Command Palette")
        self.resize(720, 520)
        self.service = service
        self.campaign_id = campaign_id
        self.items: list[dict[str, object]] = []
        self.result: dict[str, object] | None = None

        self.input = QLineEdit()
        self.input.setObjectName("commandPaletteInput")
        self.input.setPlaceholderText("Search or run a safe operator command...")
        self.input.textChanged.connect(self.refresh)
        self.input.returnPressed.connect(self.run_selected)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("commandPaletteResults")
        self.table.setHorizontalHeaderLabels(["Command", "Context", "Type"])
        self.table.setMinimumHeight(340)
        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 330)
        self.table.setColumnWidth(2, 100)
        self.table.itemDoubleClicked.connect(lambda *_: self.run_selected())
        apply_table_style(self.table)

        self.run_button = primary_button("Run")
        self.run_button.setObjectName("commandPaletteRunButton")
        self.run_button.clicked.connect(self.run_selected)
        self.close_button = secondary_button("Close")
        self.close_button.setObjectName("commandPaletteCloseButton")
        self.close_button.clicked.connect(self.reject)
        self.feedback = helper_text("Cmd+K opens this palette. Commands never send messages automatically.")
        self.feedback.setObjectName("commandPaletteFeedback")
        self.feedback.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(_header("Command Palette", "Raycast-style navigation and safe operator actions. No autosend."))
        layout.addWidget(self.input)
        layout.addWidget(self.table, 1)
        bottom = QHBoxLayout()
        bottom.addWidget(self.feedback, 1)
        bottom.addWidget(self.close_button)
        bottom.addWidget(self.run_button)
        layout.addLayout(bottom)
        self.refresh()

    def refresh(self) -> None:
        self.items = self.service.command_palette_items(
            self.input.text().strip(),
            campaign_id=self.campaign_id,
            limit=40,
        )
        self.table.setRowCount(len(self.items))
        for row_index, item in enumerate(self.items):
            values = [item.get("title", ""), item.get("subtitle", ""), item.get("kind", "")]
            for col, value in enumerate(values):
                self.table.setItem(row_index, col, QTableWidgetItem(str(value)))
        if self.items:
            self.table.selectRow(0)

    def run_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.items):
            self.feedback.setText("Select a command first.")
            return
        command_id = str(self.items[row].get("id") or "")
        self.result = self.service.execute_command_palette_item(command_id, campaign_id=self.campaign_id)
        self.feedback.setText(str(self.result.get("message") or "Command selected. No send was triggered."))
        self.accept()


class NotificationCenterView(QWidget):
    def __init__(self, service: CampaignService, campaign_id_getter: Callable[[], int]):
        super().__init__()
        self.setObjectName("notificationCenterView")
        self.service = service
        self.campaign_id_getter = campaign_id_getter

        self.refresh_button = secondary_button("Refresh")
        self.refresh_button.setObjectName("notificationCenterRefreshButton")
        self.refresh_button.clicked.connect(self.refresh)
        self.summary_label = helper_text("Replies, follow-ups, AI warnings and failed jobs appear here without noisy popups.")
        self.summary_label.setObjectName("notificationCenterSummary")
        self.summary_label.setWordWrap(True)
        self.table = QTableWidget(0, 5)
        self.table.setObjectName("notificationCenterTable")
        self.table.setHorizontalHeaderLabels(["Type", "Status", "Message", "Campaign", "Time"])
        self.table.setMinimumHeight(420)
        self.table.setColumnWidth(0, 130)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 480)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 170)
        apply_table_style(self.table)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(_header("Уведомления", "Operator notification center: важное без спама и без скрытых действий."))
        top = QHBoxLayout()
        top.addWidget(self.summary_label, 1)
        top.addWidget(self.refresh_button)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        rows = self.service.notification_center(self.campaign_id_getter(), limit=60)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row.get("type", ""),
                row.get("status", ""),
                row.get("message", ""),
                row.get("campaign_id", ""),
                row.get("created_at", ""),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row_index, col, QTableWidgetItem(str(value)))
        self.summary_label.setText(f"{len(rows)} alerts. No message is sent from this screen.")


class BackgroundTaskMonitorView(QWidget):
    def __init__(self, service: CampaignService, campaign_id_getter: Callable[[], int]):
        super().__init__()
        self.setObjectName("backgroundTaskMonitorView")
        self.service = service
        self.campaign_id_getter = campaign_id_getter

        self.refresh_button = secondary_button("Refresh")
        self.refresh_button.setObjectName("taskMonitorRefreshButton")
        self.refresh_button.clicked.connect(self.refresh)
        self.health_label = QLabel("Queue health: -")
        self.health_label.setObjectName("taskMonitorHealthLabel")
        self.health_label.setStyleSheet("font-size: 18px; font-weight: 800;")
        self.summary_label = helper_text("AI, sync, enrichment and export jobs stay observable and recoverable.")
        self.summary_label.setObjectName("taskMonitorSummary")
        self.summary_label.setWordWrap(True)
        self.table = QTableWidget(0, 3)
        self.table.setObjectName("taskMonitorTable")
        self.table.setHorizontalHeaderLabels(["Status", "Job type", "Count"])
        self.table.setMinimumHeight(260)
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 300)
        self.table.setColumnWidth(2, 100)
        apply_table_style(self.table)
        self.failed_table = QTableWidget(0, 4)
        self.failed_table.setObjectName("taskMonitorFailedTable")
        self.failed_table.setHorizontalHeaderLabels(["Job", "Contact", "Error", "Updated"])
        self.failed_table.setMinimumHeight(180)
        self.failed_table.setColumnWidth(0, 160)
        self.failed_table.setColumnWidth(1, 90)
        self.failed_table.setColumnWidth(2, 460)
        self.failed_table.setColumnWidth(3, 160)
        apply_table_style(self.failed_table)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(_header("Задачи", "Background task monitor: queue health, retries and failed work in one calm panel."))
        top = QHBoxLayout()
        top.addWidget(self.health_label)
        top.addStretch(1)
        top.addWidget(self.refresh_button)
        layout.addLayout(top)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Failed tasks"))
        layout.addWidget(self.failed_table)
        self.refresh()

    def refresh(self) -> None:
        snapshot = self.service.background_task_monitor(self.campaign_id_getter())
        self.health_label.setText(f"Queue health: {snapshot.get('queue_health', '-')}")
        rows: list[tuple[str, str, int]] = []
        by_status = dict(snapshot.get("by_status") or {})
        by_type = dict(snapshot.get("by_type") or {})
        for status, count in by_status.items():
            rows.append((status, "all", int(count)))
        for job_type, count in by_type.items():
            rows.append(("all", job_type, int(count)))
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for col, value in enumerate(row):
                self.table.setItem(row_index, col, QTableWidgetItem(str(value)))
        failed = list(snapshot.get("failed_tasks") or [])
        self.failed_table.setRowCount(len(failed))
        for row_index, row in enumerate(failed):
            values = [row.get("job_type", ""), row.get("contact_id", ""), row.get("last_error", ""), row.get("updated_at", "")]
            for col, value in enumerate(values):
                self.failed_table.setItem(row_index, col, QTableWidgetItem(str(value)))
        self.summary_label.setText(
            f"Queued: {by_status.get('queued', 0)} • Failed: {by_status.get('failed', 0)} • Retries pending: {snapshot.get('retries_pending', 0)}"
        )


class PerformancePlatformView(QWidget):
    def __init__(self, service: CampaignService, campaign_id_getter: Callable[[], int]):
        super().__init__()
        self.setObjectName("performancePlatformView")
        self.service = service
        self.campaign_id_getter = campaign_id_getter

        self.refresh_button = secondary_button("Refresh")
        self.refresh_button.setObjectName("performanceRefreshButton")
        self.refresh_button.clicked.connect(self.refresh)
        self.summary_label = helper_text("Latency, cache and render budgets for large operator workloads.")
        self.summary_label.setObjectName("performanceSummaryLabel")
        self.summary_label.setWordWrap(True)
        self.table = QTableWidget(0, 2)
        self.table.setObjectName("performanceSnapshotTable")
        self.table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.table.setMinimumHeight(420)
        self.table.setColumnWidth(0, 240)
        self.table.setColumnWidth(1, 560)
        apply_table_style(self.table)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(_header("Performance", "Caching, virtualization and recovery state for production operator sessions."))
        top = QHBoxLayout()
        top.addWidget(self.summary_label, 1)
        top.addWidget(self.refresh_button)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        snapshot = self.service.performance_snapshot(self.campaign_id_getter())
        rows = [
            ("Render budget", snapshot.get("render_budget", {})),
            ("Cache", snapshot.get("cache", {})),
            ("Latency", snapshot.get("latency", {})),
            ("Session state", snapshot.get("session_state", {})),
        ]
        self.table.setRowCount(len(rows))
        for row_index, (key, value) in enumerate(rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(key))
            self.table.setItem(row_index, 1, QTableWidgetItem(str(value)))
        self.summary_label.setText("Performance snapshot is local-only. No network calls, no sends.")
