from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..app_metadata import AppMetadata, get_app_metadata
from .theme import COLORS, helper_text, section_title, set_button_kind


class AboutDialog(QDialog):
    def __init__(self, metadata: AppMetadata | None = None, parent=None):
        super().__init__(parent)
        self.metadata = metadata or get_app_metadata()
        self.setWindowTitle(f"О приложении {self.metadata.name}")
        self.setModal(True)
        self.setMinimumWidth(420)

        icon = QLabel("✉")
        icon.setFixedSize(54, 54)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background: {COLORS['primary_soft']}; color: {COLORS['primary']}; "
            "border-radius: 18px; font-size: 24px; font-weight: 900;"
        )

        title = section_title(self.metadata.name)
        version = helper_text(f"Версия {self.metadata.version}\nСборка: {self.metadata.build_timestamp}")
        note = helper_text(self.metadata.safety_note)
        close_button = QPushButton("Закрыть")
        set_button_kind(close_button, "primary")
        close_button.clicked.connect(self.accept)

        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(icon)
        text_box = QVBoxLayout()
        text_box.addWidget(title)
        text_box.addWidget(version)
        top.addLayout(text_box, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        layout.addLayout(top)
        layout.addWidget(note)
        layout.addWidget(helper_text(self.metadata.copyright_text))
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)
