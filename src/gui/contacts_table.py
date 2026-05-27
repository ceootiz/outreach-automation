from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..campaign_service import CampaignService
from ..config import IMPORTS_DIR
from ..excel_importer import is_valid_email, map_headers
from ..models import CONTACT_STATUSES
from .i18n import STATUS_LABELS_RU, status_from_ru, status_to_ru
from .theme import (
    COLORS,
    STATUS_COLORS,
    apply_table_style,
    card,
    helper_text,
    section_title,
    set_button_kind,
)


CONTACT_COLUMNS = [
    ("id", "✓"),
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

EDITABLE_COLUMNS = {
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


class ContactsTable(QWidget):
    def __init__(
        self,
        service: CampaignService,
        active_campaign_id: Callable[[], int],
        refresh_callback: Callable[[], None],
    ):
        super().__init__()
        self.service = service
        self.active_campaign_id = active_campaign_id
        self.refresh_callback = refresh_callback
        self._loading = False
        self.action_map: dict[str, dict[str, str]] = {}

        self.status_filter = QComboBox()
        self.status_filter.setObjectName("contactsStatusFilter")
        for status, label in STATUS_LABELS_RU.items():
            self.status_filter.addItem(label, status)
        self.status_filter.currentIndexChanged.connect(self.refresh)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("contactsSearchInput")
        self.search_input.setPlaceholderText("Поиск по email, имени, компании или заметке")
        self.search_input.textChanged.connect(self.refresh)

        self.add_button = QPushButton("+ Добавить строку")
        self.paste_button = QPushButton("Вставить из буфера")
        self.import_button = QPushButton("Загрузить Excel/CSV")
        self.example_button = QPushButton("Скачать пример Excel")
        self.delete_button = QPushButton("Удалить выбранные")
        self.save_button = QPushButton("Сохранить изменения")
        self.refresh_button = QPushButton("Обновить")
        self.approve_button = QPushButton("Подтвердить выбранные")
        self.blacklist_button = QPushButton("В черный список")
        set_button_kind(self.add_button, "primary")
        set_button_kind(self.paste_button, "soft")
        set_button_kind(self.import_button, "soft")
        set_button_kind(self.example_button, "soft")
        set_button_kind(self.delete_button, "danger")
        set_button_kind(self.save_button, "soft")
        set_button_kind(self.refresh_button, "ghost")
        set_button_kind(self.approve_button, "soft")
        set_button_kind(self.blacklist_button, "danger")
        self.add_button.setToolTip("Добавить пустую строку")
        self.paste_button.setToolTip("Вставить строки из Excel или Google Sheets")
        self.import_button.setToolTip("Загрузить XLSX или CSV")
        self.save_button.setToolTip("Cmd/Ctrl + S")
        self.delete_button.setToolTip("Delete")

        self.add_button.clicked.connect(self.add_empty_row)
        self.paste_button.clicked.connect(self.paste_from_clipboard)
        self.import_button.clicked.connect(self.import_file)
        self.example_button.clicked.connect(self.download_example_excel)
        self.delete_button.clicked.connect(self.delete_selected_rows)
        self.save_button.clicked.connect(self.save_changes)
        self.refresh_button.clicked.connect(self.refresh)
        self.approve_button.clicked.connect(self.approve_selected)
        self.blacklist_button.clicked.connect(self.blacklist_selected)
        self._register_action_map()

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(self.status_filter)
        toolbar.addWidget(self.search_input, 1)
        for button in (
            self.add_button,
            self.paste_button,
            self.import_button,
            self.example_button,
            self.delete_button,
            self.save_button,
            self.refresh_button,
            self.approve_button,
            self.blacklist_button,
        ):
            toolbar.addWidget(button)

        self.table = QTableWidget(0, len(CONTACT_COLUMNS))
        self.table.setObjectName("recipientTable")
        self.table.setHorizontalHeaderLabels([label for _, label in CONTACT_COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.itemChanged.connect(self._on_item_changed)
        apply_table_style(self.table)
        self.table.setMinimumHeight(420)
        self.table.setColumnWidth(0, 48)
        self.table.setColumnWidth(1, 190)
        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(3, 300)
        self.table.setColumnWidth(4, 130)
        self.table.setColumnWidth(5, 160)
        self.table.setColumnWidth(6, 160)
        self.table.setColumnWidth(7, 150)
        self.table.setColumnWidth(8, 220)
        self.table.setColumnWidth(9, 180)
        self.table.setColumnWidth(10, 190)
        self.table.setColumnWidth(11, 70)
        self.table.setColumnWidth(12, 110)
        self.table.setColumnWidth(13, 95)
        self.table.setColumnWidth(14, 180)
        self.table.setColumnWidth(15, 210)
        self.table.setColumnWidth(16, 130)
        self.table.verticalHeader().setDefaultSectionSize(40)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(16)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_help_card())
        self.empty_state = self._build_empty_state()
        layout.addWidget(self.empty_state)
        self.table_card = card()
        table_layout = QVBoxLayout(self.table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(14)
        table_layout.addLayout(toolbar)
        table_layout.addWidget(self.table, 1)
        layout.addWidget(self.table_card, 1)

    def _register_action_map(self) -> None:
        """Developer-visible clickability map for recipient table actions."""
        actions: list[tuple[str, QWidget, str, str]] = [
            ("contacts.add_row", self.add_button, "add_empty_row", "Добавить пустую строку"),
            ("contacts.paste_rows", self.paste_button, "paste_from_clipboard", "Вставить строки из буфера"),
            ("contacts.import_file", self.import_button, "import_file", "Открыть импорт Excel/CSV"),
            ("contacts.example_excel", self.example_button, "download_example_excel", "Создать пример Excel"),
            ("contacts.delete_selected", self.delete_button, "delete_selected_rows", "Удалить выбранные строки"),
            ("contacts.save_changes", self.save_button, "save_changes", "Сохранить новые строки"),
            ("contacts.refresh", self.refresh_button, "refresh", "Обновить таблицу"),
            ("contacts.approve_selected", self.approve_button, "approve_selected", "Подтвердить выбранные строки"),
            ("contacts.blacklist_selected", self.blacklist_button, "blacklist_selected", "Добавить выбранные строки в черный список"),
            ("contacts.search", self.search_input, "QLineEdit.setText", "Искать по получателям"),
            ("contacts.status_filter", self.status_filter, "QComboBox.setCurrentIndex", "Фильтровать по статусу"),
        ]
        self.action_map = {}
        for action_id, widget, slot_name, expected in actions:
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
        frame.setMinimumHeight(112)
        frame.setMaximumHeight(138)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)
        title = QLabel("Получатели")
        title.setObjectName("heroTitle")
        title.setMaximumHeight(44)
        subtitle = QLabel(
            "Добавьте email, тему и сообщение. Каждая строка — отдельное письмо."
        )
        subtitle.setObjectName("heroSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setMaximumHeight(48)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return frame

    def _build_help_card(self) -> QFrame:
        frame = card()
        frame.setMinimumHeight(126)
        frame.setMaximumHeight(156)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(section_title("Как заполнить?"))
        layout.addWidget(
            helper_text(
                "Вручную: нажмите “Добавить строку”.\n"
                "Из Excel/Google Sheets: скопируйте столбцы Email / Тема / Сообщение и нажмите “Вставить из буфера”.\n"
                "Из файла: нажмите “Загрузить Excel/CSV”."
            )
        )
        return frame

    def _build_empty_state(self) -> QFrame:
        frame = card()
        frame.setProperty("emptyState", True)
        frame.setMinimumHeight(160)
        frame.setMaximumHeight(195)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        self.empty_icon_label = QLabel("✉")
        self.empty_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_icon_label.setFixedSize(36, 36)
        self.empty_icon_label.setStyleSheet(
            f"background: {COLORS['primary_soft']}; color: {COLORS['primary']}; "
            "border-radius: 14px; font-size: 18px; font-weight: 800;"
        )
        title = section_title("Пока нет получателей")
        text = helper_text("Добавьте строку, вставьте из Excel или загрузите файл.")
        actions = QHBoxLayout()
        self.empty_add_button = QPushButton("+ Добавить строку")
        self.empty_import_button = QPushButton("Загрузить Excel")
        set_button_kind(self.empty_add_button, "primary")
        set_button_kind(self.empty_import_button, "soft")
        self.empty_add_button.clicked.connect(self.add_empty_row)
        self.empty_import_button.clicked.connect(self.import_file)
        actions.addWidget(self.empty_add_button)
        actions.addWidget(self.empty_import_button)
        actions.addStretch(1)
        layout.addWidget(self.empty_icon_label, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title)
        layout.addWidget(text)
        layout.addLayout(actions)
        return frame

    def refresh(self) -> None:
        self._loading = True
        selected_ids = set(self.selected_contact_ids())
        status = self.status_filter.currentData()
        search = self.search_input.text().strip()
        rows = self.service.contacts(self.active_campaign_id(), status=status, search=search)

        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))
        for row_index, contact in enumerate(rows):
            self._populate_row(row_index, contact)
            if int(contact["id"]) in selected_ids:
                self.table.selectRow(row_index)
        is_all_status = not status or status == "all"
        self.empty_state.setVisible(len(rows) == 0 and not search and is_all_status)
        self.table_card.setVisible(len(rows) > 0 or bool(search) or not is_all_status)
        self._loading = False

    def selected_contact_ids(self) -> list[int]:
        ids: list[int] = []
        for model_index in self.table.selectionModel().selectedRows():
            id_item = self.table.item(model_index.row(), 0)
            if not id_item:
                continue
            try:
                contact_id = int(id_item.text())
            except ValueError:
                continue
            ids.append(contact_id)
        return sorted(set(ids))

    def add_empty_row(self) -> None:
        self._loading = True
        row_index = self.table.rowCount()
        self.table.insertRow(row_index)
        self._populate_row(
            row_index,
            {
                "id": "",
                "channel": "email",
                "email": "",
                "handle": "",
                "profile_url": "",
                "external_id": "",
                "subject": "",
                "generated_message": "",
                "name": "",
                "company": "",
                "topic": "",
                "website": "",
                "social_profile": "",
                "status": "new",
                "last_error": "",
            },
        )
        self._loading = False
        self.table.selectRow(row_index)

    def paste_from_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        rows = self.parse_clipboard_rows(text)
        if not rows:
            QMessageBox.information(
                self,
                "Вставить из буфера",
                "В буфере нет строк с email и сообщением.",
            )
            return
        result = self.service.add_contact_rows(
            self.active_campaign_id(),
            rows,
            source="clipboard",
        )
        message = f"Добавлено строк: {result.imported_count}\nПропущено: {result.skipped_count}"
        if result.errors:
            message += "\n\n" + "\n".join(result.errors[:10])
        QMessageBox.information(self, "Вставка завершена", message)
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
        try:
            result = self.service.import_file(Path(file_path), self.active_campaign_id())
        except Exception as exc:
            QMessageBox.critical(self, "Загрузить Excel/CSV", str(exc))
            return
        message = f"Добавлено получателей: {result.imported_count}\nПропущено строк: {result.skipped_count}"
        if result.errors:
            message += "\n\n" + "\n".join(result.errors[:10])
        QMessageBox.information(self, "Загрузка завершена", message)
        self.refresh_callback()

    def download_example_excel(self) -> None:
        try:
            path = self.service.export_example_contacts_template()
        except Exception as exc:
            QMessageBox.critical(self, "Пример Excel", str(exc))
            return
        QMessageBox.information(self, "Пример Excel", f"Файл создан:\n{path}")

    def save_changes(self) -> None:
        rows_to_create: list[dict[str, Any]] = []
        for row_index in range(self.table.rowCount()):
            id_item = self.table.item(row_index, 0)
            if id_item and id_item.text().strip():
                continue
            row = self._row_to_contact(row_index)
            if row.get("email") or row.get("handle") or row.get("profile_url") or row.get("external_id"):
                rows_to_create.append(row)
        if not rows_to_create:
            QMessageBox.information(self, "Сохранить изменения", "Новых строк для сохранения нет.")
            return
        result = self.service.add_contact_rows(
            self.active_campaign_id(),
            rows_to_create,
            source="manual_table",
        )
        message = f"Сохранено строк: {result.imported_count}\nПропущено: {result.skipped_count}"
        if result.errors:
            message += "\n\n" + "\n".join(result.errors[:10])
        QMessageBox.information(self, "Сохранить изменения", message)
        self.refresh_callback()

    def delete_selected_rows(self) -> None:
        selected_rows = sorted(
            {index.row() for index in self.table.selectionModel().selectedRows()},
            reverse=True,
        )
        if not selected_rows:
            QMessageBox.information(self, "Удалить выбранные", "Выберите одну или несколько строк.")
            return
        contact_ids: list[int] = []
        for row_index in selected_rows:
            id_item = self.table.item(row_index, 0)
            if id_item and id_item.text().strip():
                try:
                    contact_ids.append(int(id_item.text()))
                except ValueError:
                    pass
            else:
                self.table.removeRow(row_index)
        deleted = self.service.delete_contacts(contact_ids) if contact_ids else 0
        QMessageBox.information(self, "Удалить выбранные", f"Удалено строк: {deleted + len(selected_rows) - len(contact_ids)}")
        self.refresh_callback()

    def approve_selected(self) -> None:
        ids = self.selected_contact_ids()
        if not ids:
            QMessageBox.information(self, "Подтвердить выбранные", "Выберите одну или несколько строк.")
            return
        count = self.service.approve_contacts(ids)
        QMessageBox.information(self, "Подтвердить выбранные", f"Подтверждено строк: {count}")
        self.refresh_callback()

    def blacklist_selected(self) -> None:
        ids = self.selected_contact_ids()
        if not ids:
            QMessageBox.information(self, "В черный список", "Выберите одну или несколько строк.")
            return
        count = self.service.blacklist_contacts(ids, reason="Добавлено вручную")
        QMessageBox.information(self, "В черный список", f"Добавлено в черный список: {count}")
        self.refresh_callback()

    def edit_selected_row(self) -> None:
        current = self.table.currentItem()
        if current and CONTACT_COLUMNS[current.column()][0] in EDITABLE_COLUMNS:
            self.table.editItem(current)
            return
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        target = self.table.item(row, 1) or self.table.item(row, 3)
        if target:
            self.table.setCurrentItem(target)
            self.table.editItem(target)

    def _populate_row(self, row_index: int, contact: dict[str, Any]) -> None:
        channel_id = str(contact.get("channel") or "email")
        for column_index, (key, _) in enumerate(CONTACT_COLUMNS):
            value = contact.get(key)
            if key == "email" and channel_id != "email" and str(value or "").endswith("@channel.local"):
                value = ""
            if key == "generated_message":
                value = contact.get("generated_message") or contact.get("base_message") or ""
            if key == "status":
                value = status_to_ru(value or "new")
            if key == "last_error" and not value and not (
                contact.get("generated_message") or contact.get("base_message")
            ):
                value = "Нет сообщения"
            if key == "ai_badge":
                value = "AI" if int(contact.get("ai_generated") or 0) else ""
            if key == "enrichment_status":
                value = self._enrichment_status_label(str(contact.get("enrichment_status") or "not_checked"))
            if key == "channel":
                value = channel_id
            item = QTableWidgetItem("" if value is None else str(value))
            if key not in EDITABLE_COLUMNS:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if key == "id":
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if key == "email" and item.text() and not is_valid_email(item.text()):
                item.setBackground(QColor(COLORS["red_soft"]))
                item.setForeground(QColor(COLORS["red"]))
            if key == "generated_message" and not item.text().strip():
                item.setText("Нет сообщения")
                item.setBackground(QColor(COLORS["amber_soft"]))
                item.setForeground(QColor(COLORS["amber"]))
            if key == "status":
                item.setData(Qt.ItemDataRole.UserRole, "status_badge")
                text_color, bg_color = STATUS_COLORS.get(
                    item.text(),
                    (COLORS["muted"], COLORS["border_soft"]),
                )
                item.setForeground(QColor(text_color))
                item.setBackground(QColor(bg_color))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if key == "ai_badge" and item.text():
                item.setToolTip(
                    "AI Assist: черновик создан AI и требует ручной проверки.\n"
                    + str(contact.get("ai_notes") or "")
                    + ("\nWarnings: " + str(contact.get("ai_warnings") or "") if contact.get("ai_warnings") else "")
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
            self.table.setItem(row_index, column_index, item)

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

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        key = CONTACT_COLUMNS[item.column()][0]
        if key not in EDITABLE_COLUMNS:
            return
        id_item = self.table.item(item.row(), 0)
        if not id_item or not id_item.text().strip():
            return
        try:
            contact_id = int(id_item.text())
        except ValueError:
            return
        value = item.text().strip()
        fields: dict[str, Any]
        if key == "status":
            status = status_from_ru(value)
            if status not in CONTACT_STATUSES:
                QMessageBox.warning(
                    self,
                    "Неверный статус",
                    "Используйте один из статусов: "
                    + ", ".join(STATUS_LABELS_RU[status] for status in sorted(CONTACT_STATUSES)),
                )
                self.refresh()
                return
            fields = {"status": status}
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
            self.service.update_contact(contact_id, fields)
        except Exception as exc:
            QMessageBox.critical(self, "Не удалось сохранить", str(exc))
            self.refresh()

    def _row_to_contact(self, row_index: int) -> dict[str, str]:
        values = {}
        for column_index, (key, _) in enumerate(CONTACT_COLUMNS):
            item = self.table.item(row_index, column_index)
            values[key] = "" if item is None else item.text().strip()
        status = status_from_ru(values.get("status", "")) or "new"
        message = values.get("generated_message", "")
        if message == "Нет сообщения":
            message = ""
        return {
            "email": values.get("email", ""),
            "channel": values.get("channel", "") or "email",
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

    @staticmethod
    def parse_clipboard_rows(text: str) -> list[dict[str, str]]:
        raw_rows = [
            [cell.strip() for cell in line.split("\t")]
            for line in text.splitlines()
            if line.strip()
        ]
        if not raw_rows:
            return []
        mapping = map_headers(raw_rows[0])
        data_rows = raw_rows
        if "email" in mapping:
            data_rows = raw_rows[1:]

        rows: list[dict[str, str]] = []
        for values in data_rows:
            if not values:
                continue
            if mapping and "email" in mapping:
                row = {
                    "email": ContactsTable._value(values, mapping.get("email")),
                    "subject": ContactsTable._value(values, mapping.get("subject")),
                    "generated_message": ContactsTable._value(values, mapping.get("base_message")),
                    "name": ContactsTable._value(values, mapping.get("name")),
                    "company": ContactsTable._value(values, mapping.get("company")),
                    "topic": ContactsTable._value(values, mapping.get("topic")),
                    "website": ContactsTable._value(values, mapping.get("website")),
                    "social_profile": ContactsTable._value(values, mapping.get("social_profile")),
                    "channel": ContactsTable._value(values, mapping.get("channel")) or "email",
                    "handle": ContactsTable._value(values, mapping.get("handle")),
                    "profile_url": ContactsTable._value(values, mapping.get("profile_url")),
                    "external_id": ContactsTable._value(values, mapping.get("external_id")),
                }
            elif len(values) == 2:
                row = {"email": values[0], "generated_message": values[1]}
            else:
                row = {
                    "email": values[0] if len(values) > 0 else "",
                    "subject": values[1] if len(values) > 1 else "",
                    "generated_message": values[2] if len(values) > 2 else "",
                    "name": values[3] if len(values) > 3 else "",
                    "company": values[4] if len(values) > 4 else "",
                    "topic": values[5] if len(values) > 5 else "",
                    "website": values[6] if len(values) > 6 else "",
                    "social_profile": values[7] if len(values) > 7 else "",
                    "channel": values[8] if len(values) > 8 else "email",
                    "handle": values[9] if len(values) > 9 else "",
                    "profile_url": values[10] if len(values) > 10 else "",
                    "external_id": values[11] if len(values) > 11 else "",
                }
            if row.get("email") or row.get("generated_message"):
                row["base_message"] = row.get("generated_message", "")
                rows.append(row)
        return rows

    @staticmethod
    def _value(values: list[str], index: int | None) -> str:
        if index is None or index >= len(values):
            return ""
        return values[index].strip()
