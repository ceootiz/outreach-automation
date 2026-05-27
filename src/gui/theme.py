from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QFrame,
    QGraphicsDropShadowEffect,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

APP_BG = "#F6F7FB"
CARD_BG = "#FFFFFF"
PRIMARY = "#0A6DFD"
TEXT_PRIMARY = "#142033"
TEXT_SECONDARY = "#667085"
BORDER = "#E6EAF2"
SUCCESS_BG = "#EAFBF0"
SUCCESS_TEXT = "#078B3E"
WARNING_BG = "#FFF7E6"
WARNING_TEXT = "#B76E00"
ERROR_BG = "#FEECEC"
ERROR_TEXT = "#D92D20"

PAGE_PADDING = 24
CARD_PADDING = 20
SECTION_GAP = 16
PAGE_PADDING_COMPACT = 16
CARD_PADDING_COMPACT = 14
SECTION_GAP_COMPACT = 10
CARD_RADIUS = 16
BUTTON_RADIUS = 10
BUTTON_MIN_HEIGHT_COMPACT = 32
TABLE_ROW_HEIGHT_COMPACT = 36
TABLE_HEADER_HEIGHT_COMPACT = 34

COLORS = {
    "bg": APP_BG,
    "surface": CARD_BG,
    "surface_soft": "#FAFBFF",
    "sidebar": CARD_BG,
    "border": BORDER,
    "border_soft": "#EEF1F6",
    "text": TEXT_PRIMARY,
    "muted": TEXT_SECONDARY,
    "muted_soft": "#9AA3B2",
    "primary": PRIMARY,
    "primary_soft": "#EAF1FF",
    "green": SUCCESS_TEXT,
    "green_soft": SUCCESS_BG,
    "amber": WARNING_TEXT,
    "amber_soft": WARNING_BG,
    "red": ERROR_TEXT,
    "red_soft": ERROR_BG,
    "purple": "#7C3AED",
    "purple_soft": "#F2ECFF",
}

RADIUS = {
    "sm": 10,
    "md": BUTTON_RADIUS,
    "lg": CARD_RADIUS,
    "xl": 20,
}

SPACING = {
    "xs": 6,
    "sm": 10,
    "md": 16,
    "lg": 24,
    "xl": 32,
}

STATUS_COLORS = {
    "Новый": (COLORS["primary"], COLORS["primary_soft"]),
    "В очереди подготовки": (COLORS["purple"], COLORS["purple_soft"]),
    "Подготовка": (COLORS["purple"], COLORS["purple_soft"]),
    "Нужно подтвердить": (COLORS["amber"], COLORS["amber_soft"]),
    "Подтверждено": (COLORS["green"], COLORS["green_soft"]),
    "В очереди отправки": (COLORS["primary"], COLORS["primary_soft"]),
    "Отправляется": (COLORS["primary"], COLORS["primary_soft"]),
    "Проверено без отправки": (COLORS["green"], COLORS["green_soft"]),
    "Отправлено": (COLORS["green"], COLORS["green_soft"]),
    "Ошибка": (COLORS["red"], COLORS["red_soft"]),
    "Черный список": (COLORS["red"], COLORS["red_soft"]),
    "Отменено": (COLORS["muted"], COLORS["border_soft"]),
}


def app_stylesheet() -> str:
    return f"""
    QWidget {{
        color: {COLORS["text"]};
        font-family: "Helvetica Neue";
        font-size: 13px;
    }}
    QMainWindow, QWidget#appRoot {{
        background: {COLORS["bg"]};
    }}
    QFrame#card, QGroupBox {{
        background: {COLORS["surface"]};
        border: 1px solid {COLORS["border_soft"]};
        border-radius: {RADIUS["lg"]}px;
    }}
    QGroupBox {{
        margin-top: 18px;
        padding: 22px 18px 18px 18px;
        font-weight: 700;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 18px;
        padding: 0 8px;
        color: {COLORS["text"]};
    }}
    QLabel#heroTitle {{
        font-size: 28px;
        font-weight: 800;
        letter-spacing: 0px;
    }}
    QLabel#heroSubtitle {{
        color: {COLORS["muted"]};
        font-size: 14px;
    }}
    QLabel#sectionTitle {{
        font-size: 18px;
        font-weight: 750;
    }}
    QLabel#muted {{
        color: {COLORS["muted"]};
    }}
    QLabel#helperText {{
        color: {COLORS["muted"]};
        line-height: 140%;
        font-size: 12px;
    }}
    QPushButton {{
        background: {COLORS["surface"]};
        border: 1px solid {COLORS["border"]};
        border-radius: {RADIUS["md"]}px;
        padding: 6px 12px;
        min-height: 20px;
        font-weight: 650;
    }}
    QPushButton:hover {{
        background: {COLORS["surface_soft"]};
        border-color: #D5DAE5;
    }}
    QPushButton:pressed {{
        background: #EEF2F8;
    }}
    QPushButton:disabled {{
        background: #F2F4F8;
        color: #B3BAC8;
        border-color: #E5E9F1;
    }}
    QPushButton#primaryButton {{
        background: {COLORS["primary"]};
        color: white;
        border-color: {COLORS["primary"]};
    }}
    QPushButton#primaryButton:hover {{
        background: #1D4ED8;
    }}
    QPushButton#primaryButton:pressed {{
        background: #1647C6;
    }}
    QPushButton#primaryButton:disabled {{
        background: #B7CDFE;
        color: white;
        border-color: #B7CDFE;
    }}
    QPushButton#softButton {{
        background: {COLORS["surface"]};
        color: {COLORS["primary"]};
        border-color: #D7E5FF;
    }}
    QPushButton#softButton:hover {{
        background: {COLORS["primary_soft"]};
        border-color: #BFD5FF;
    }}
    QPushButton#softButton:pressed {{
        background: #DDEAFF;
    }}
    QPushButton#dangerButton {{
        background: {COLORS["red_soft"]};
        color: {COLORS["red"]};
        border-color: #F6CACA;
    }}
    QPushButton#dangerButton:hover {{
        background: #FDE1E1;
        border-color: #F3B8B8;
    }}
    QPushButton#ghostButton {{
        background: transparent;
        color: {COLORS["muted"]};
        border-color: transparent;
    }}
    QPushButton#ghostButton:hover {{
        background: {COLORS["surface_soft"]};
        color: {COLORS["text"]};
    }}
    QPushButton#textButton {{
        background: transparent;
        color: {COLORS["muted"]};
        border-color: transparent;
        padding-left: 2px;
        padding-right: 2px;
        text-align: left;
    }}
    QPushButton#textButton:hover {{
        color: {COLORS["primary"]};
        background: transparent;
    }}
    QPushButton#sidebarItem {{
        text-align: left;
        background: transparent;
        border: 0;
        border-radius: {RADIUS["md"]}px;
        padding: 8px 10px;
        min-height: 48px;
        font-weight: 700;
    }}
    QPushButton#sidebarItem:hover {{
        background: #F4F7FC;
    }}
    QPushButton#sidebarItem:checked {{
        background: {COLORS["primary_soft"]};
        color: {COLORS["primary"]};
        border-left: 3px solid {COLORS["primary"]};
    }}
    QLineEdit, QTextEdit, QSpinBox, QComboBox {{
        background: {COLORS["surface"]};
        border: 1px solid {COLORS["border"]};
        border-radius: {RADIUS["md"]}px;
        min-height: 30px;
        padding: 5px 10px;
        selection-background-color: {COLORS["primary"]};
    }}
    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border-color: {COLORS["primary"]};
        background: #FFFFFF;
    }}
    QLineEdit:disabled, QTextEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
        background: #F4F6FA;
        color: #A5ADBB;
        border-color: #E7EBF2;
    }}
    QTableWidget {{
        background: {COLORS["surface"]};
        border: 1px solid {COLORS["border_soft"]};
        border-radius: {RADIUS["md"]}px;
        gridline-color: {COLORS["border_soft"]};
        alternate-background-color: {COLORS["surface_soft"]};
        selection-background-color: {COLORS["primary_soft"]};
        selection-color: {COLORS["text"]};
    }}
    QTableWidget::item:hover {{
        background: #F4F7FC;
    }}
    QTableWidget::item:selected {{
        background: {COLORS["primary_soft"]};
        color: {COLORS["text"]};
    }}
    QTableWidget::item {{
        padding: 4px 6px;
    }}
    QHeaderView::section {{
        background: {COLORS["surface_soft"]};
        color: {COLORS["muted"]};
        border: 0;
        border-bottom: 1px solid {COLORS["border"]};
        min-height: {TABLE_HEADER_HEIGHT_COMPACT}px;
        padding: 6px 8px;
        font-weight: 700;
    }}
    QScrollArea {{
        background: transparent;
        border: 0;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: #D7DCE7;
        border-radius: 5px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #BFC7D6;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: #D7DCE7;
        border-radius: 5px;
        min-width: 28px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: #BFC7D6;
    }}
    QProgressBar {{
        background: {COLORS["border_soft"]};
        border: 0;
        border-radius: 8px;
        height: 8px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {COLORS["primary"]};
        border-radius: 8px;
    }}
    QProgressBar#compactQueueProgress {{
        background: #EEF2F7;
        border: 0;
        border-radius: 3px;
        height: 6px;
        max-height: 6px;
    }}
    QProgressBar#compactQueueProgress::chunk {{
        background: #8FB8FF;
        border-radius: 3px;
    }}
    QLabel#dashboardTitle {{
        color: {COLORS["text"]};
        font-size: 15px;
        font-weight: 760;
    }}
    QLabel#subtleCounter {{
        background: {COLORS["surface_soft"]};
        color: {COLORS["text"]};
        border: 1px solid {COLORS["border_soft"]};
        border-radius: 8px;
        padding: 2px 7px;
        font-size: 12px;
        font-weight: 760;
    }}
    QLabel#queueTinyPill {{
        background: {COLORS["surface_soft"]};
        color: {COLORS["muted"]};
        border: 1px solid {COLORS["border_soft"]};
        border-radius: 8px;
        padding: 2px 7px;
        font-size: 11px;
        font-weight: 720;
    }}
    """


def make_card(widget: QFrame | None = None, object_name: str = "card") -> QFrame:
    frame = widget or QFrame()
    frame.setObjectName(object_name)
    frame.setFrameShape(QFrame.Shape.NoFrame)
    frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    add_shadow(frame)
    return frame


def card(object_name: str = "card") -> QFrame:
    return make_card(object_name=object_name)


def wrap_scroll(content_widget: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName("pageScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setWidget(content_widget)
    return scroll


def add_shadow(widget: QWidget, blur: int = 26, y_offset: int = 8, alpha: int = 26) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    shadow.setColor(QColor(20, 30, 55, alpha))
    widget.setGraphicsEffect(shadow)


def set_button_kind(button: QPushButton, kind: str) -> QPushButton:
    button.setMinimumHeight(BUTTON_MIN_HEIGHT_COMPACT)
    button.setMaximumHeight(34)
    if kind == "primary":
        button.setObjectName("primaryButton")
    elif kind == "soft":
        button.setObjectName("softButton")
    elif kind == "danger":
        button.setObjectName("dangerButton")
    elif kind == "ghost":
        button.setObjectName("ghostButton")
    elif kind == "text":
        button.setObjectName("textButton")
    return button


def primary_button(text: str) -> QPushButton:
    return set_button_kind(QPushButton(text), "primary")


def secondary_button(text: str) -> QPushButton:
    return set_button_kind(QPushButton(text), "soft")


def danger_button(text: str) -> QPushButton:
    return set_button_kind(QPushButton(text), "danger")


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    label.setWordWrap(True)
    return label


def helper_text(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("helperText")
    label.setWordWrap(True)
    return label


def badge_style(label: str) -> str:
    text_color, bg_color = STATUS_COLORS.get(label, (COLORS["muted"], COLORS["border_soft"]))
    return (
        f"background: {bg_color}; color: {text_color}; border: 0; "
        f"border-radius: 10px; padding: 4px 10px; font-weight: 700;"
    )


def status_badge(text: str, status: str | None = None) -> QLabel:
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(badge_style(text if status is None else status))
    label.setMinimumHeight(26)
    return label


def apply_table_style(table: QTableWidget) -> None:
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setMouseTracking(True)
    table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT_COMPACT)
    table.horizontalHeader().setMinimumHeight(TABLE_HEADER_HEIGHT_COMPACT)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.horizontalHeader().setStretchLastSection(False)


def page_layout(widget: QWidget) -> QVBoxLayout:
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(6, 2, 6, 6)
    layout.setSpacing(SECTION_GAP_COMPACT)
    return layout


def apply_compact_mode(widget: QWidget) -> QWidget:
    widget.setProperty("compactMode", True)
    return widget


def compact_card_style() -> str:
    return (
        f"background: {CARD_BG}; border: 1px solid {BORDER}; "
        f"border-radius: {CARD_RADIUS}px;"
    )


def compact_button_style(kind: str = "secondary") -> str:
    if kind == "primary":
        return (
            f"background: {PRIMARY}; color: white; border: 1px solid {PRIMARY}; "
            f"border-radius: {BUTTON_RADIUS}px; min-height: {BUTTON_MIN_HEIGHT_COMPACT}px;"
        )
    return (
        f"background: {COLORS['primary_soft']}; color: {PRIMARY}; border: 1px solid #D7E5FF; "
        f"border-radius: {BUTTON_RADIUS}px; min-height: {BUTTON_MIN_HEIGHT_COMPACT}px;"
    )


def compact_table_style(table: QTableWidget) -> None:
    apply_table_style(table)
    table.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT_COMPACT)
    table.horizontalHeader().setMinimumHeight(TABLE_HEADER_HEIGHT_COMPACT)


def align_center_flags() -> Qt.AlignmentFlag:
    return Qt.AlignmentFlag.AlignCenter
