from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..campaign_service import CampaignService
from .i18n import simple_log_message, status_to_ru, user_safe_error
from .theme import apply_table_style, card, set_button_kind


class LogsView(QWidget):
    def __init__(self, service: CampaignService):
        super().__init__()
        self.service = service
        self.refresh_button = QPushButton("Обновить журнал")
        set_button_kind(self.refresh_button, "soft")
        self.refresh_button.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 7)
        self.table.setObjectName("logsTable")
        self.table.setHorizontalHeaderLabels(
            ["Время", "Тип", "Email/источник", "Действие", "Статус", "Сообщение", "ID"]
        )
        apply_table_style(self.table)
        self.table.setMinimumHeight(460)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(2, 240)
        self.table.setColumnWidth(5, 430)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.refresh_button)
        toolbar.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(16)
        layout.addWidget(self._build_header())
        self.logs_card = card()
        card_layout = QVBoxLayout(self.logs_card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(14)
        card_layout.addLayout(toolbar)
        card_layout.addWidget(self.table, 1)
        layout.addWidget(self.logs_card, 1)

    def _build_header(self):
        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 22, 24, 22)
        title = QLabel("Журнал")
        title.setObjectName("heroTitle")
        subtitle = QLabel("История действий, ошибок импорта, очереди и безопасных проверок.")
        subtitle.setObjectName("heroSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return frame

    def refresh(self) -> None:
        send_logs = self.service.db.recent_send_logs(100)
        import_errors = self.service.db.recent_import_errors(100)
        rows: list[list[str]] = []
        for row in send_logs:
            rows.append(
                [
                    str(row.get("created_at") or ""),
                    "send_log",
                    str(row.get("email") or ""),
                    str(row.get("action") or ""),
                    status_to_ru(row.get("status") or ""),
                    simple_log_message(row),
                    str(row.get("contact_id") or ""),
                ]
            )
        for row in import_errors:
            rows.append(
                [
                    str(row.get("created_at") or ""),
                    "import_error",
                    str(row.get("source_file") or row.get("email") or ""),
                    "Импорт",
                    "Ошибка",
                    user_safe_error(row.get("error") or ""),
                    str(row.get("row_number") or ""),
                ]
            )

        rows.sort(key=lambda values: values[0], reverse=True)
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_index, column_index, item)
