from __future__ import annotations

from dataclasses import dataclass


APPROVE_DRAFT = "approve_draft"
REGENERATE_DRAFT = "regenerate_draft"
COPY_MESSAGE = "copy_message"
OPEN_PROFILE = "open_profile"
MARK_MANUALLY_SENT = "mark_manually_sent"
NEXT_LEAD = "next_lead"
PREVIOUS_LEAD = "previous_lead"
FOLLOW_UP = "follow_up"
CHANGE_LEAD_STATUS = "change_lead_status"
CHOOSE_SHORT_VARIANT = "choose_variant_short"
CHOOSE_FRIENDLY_VARIANT = "choose_variant_friendly"
CHOOSE_DIRECT_VARIANT = "choose_variant_direct"


@dataclass(frozen=True, slots=True)
class HotkeyAction:
    key: str
    action_id: str
    label: str
    description: str


HOTKEY_ACTIONS: dict[str, HotkeyAction] = {
    "A": HotkeyAction("A", APPROVE_DRAFT, "Approve", "Подтвердить черновик для ручной проверки."),
    "R": HotkeyAction("R", REGENERATE_DRAFT, "Regenerate", "Поставить перегенерацию черновика в очередь."),
    "C": HotkeyAction("C", COPY_MESSAGE, "Copy", "Скопировать подготовленный текст."),
    "O": HotkeyAction("O", OPEN_PROFILE, "Open", "Открыть профиль или страницу лида."),
    "S": HotkeyAction("S", MARK_MANUALLY_SENT, "Mark sent", "Отметить ручную отправку после действия оператора."),
    "N": HotkeyAction("N", NEXT_LEAD, "Next", "Перейти к следующему лиду."),
    "P": HotkeyAction("P", PREVIOUS_LEAD, "Previous", "Вернуться к предыдущему лиду."),
    "F": HotkeyAction("F", FOLLOW_UP, "Follow-up", "Запланировать или отметить follow-up."),
    "L": HotkeyAction("L", CHANGE_LEAD_STATUS, "Lead status", "Изменить стадию лида вручную."),
    "1": HotkeyAction("1", CHOOSE_SHORT_VARIANT, "Short", "Выбрать короткую AI-версию."),
    "2": HotkeyAction("2", CHOOSE_FRIENDLY_VARIANT, "Friendly", "Выбрать дружелюбную AI-версию."),
    "3": HotkeyAction("3", CHOOSE_DIRECT_VARIANT, "Direct", "Выбрать прямую AI-версию."),
}


def normalize_hotkey(key: str) -> str:
    return (key or "").strip().upper()


def action_for_hotkey(key: str) -> HotkeyAction | None:
    return HOTKEY_ACTIONS.get(normalize_hotkey(key))
