from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .execution import EXECUTION_MODE_LABELS, get_channel_capability, risk_label
from .readiness import ChannelReadiness, readiness_by_channel


CONNECTED = "Connected"
PARTIAL = "Partial"
MANUAL_ASSIST_STATE = "Manual Assist"
API_PENDING = "API Pending"
NOT_CONFIGURED = "Not Configured"
FUTURE_SUPPORT = "Future Support"


@dataclass(frozen=True, slots=True)
class ConnectorSlot:
    channel_id: str
    display_name: str
    connection_state: str
    capability_summary: str
    official_api_status: str
    execution_mode: str
    execution_mode_label: str
    limitations: str
    recommended_workflow: tuple[str, ...]
    setup_instructions: tuple[str, ...]
    credential_state: str
    risk_label: str
    risk_level: str
    readiness_percent: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "display_name": self.display_name,
            "connection_state": self.connection_state,
            "capability_summary": self.capability_summary,
            "official_api_status": self.official_api_status,
            "execution_mode": self.execution_mode,
            "execution_mode_label": self.execution_mode_label,
            "limitations": self.limitations,
            "recommended_workflow": list(self.recommended_workflow),
            "setup_instructions": list(self.setup_instructions),
            "credential_state": self.credential_state,
            "risk_label": self.risk_label,
            "risk_level": self.risk_level,
            "readiness_percent": self.readiness_percent,
        }


WORKFLOWS: dict[str, tuple[str, ...]] = {
    "email": (
        "Выберите Gmail профиль",
        "Сделайте dry-run",
        "Подтвердите получателей",
        "Отправляйте live только с safe-mode",
    ),
    "telegram": (
        "Проверьте Bot API",
        "Используйте chat_id, где бот имеет доступ",
        "Сделайте dry-run",
        "Подтвердите live отправку вручную",
    ),
    "instagram": (
        "Откройте Помощник отправки",
        "Загрузите handles/profile URLs",
        "Сгенерируйте короткий DM",
        "Откройте профиль",
        "Скопируйте текст и отправьте вручную",
        "Отметьте отправленным",
    ),
    "tiktok": (
        "Откройте Помощник отправки",
        "Загрузите creator handles",
        "Сгенерируйте очень короткий текст",
        "Откройте профиль",
        "Скопируйте и отправьте вручную",
        "Перейдите к следующему лиду",
    ),
    "x": (
        "Откройте Помощник отправки",
        "Загрузите X handles",
        "Подготовьте concise DM",
        "Откройте профиль",
        "Отправьте вручную",
        "Отметьте результат",
    ),
    "vk": (
        "Откройте Помощник отправки",
        "Загрузите VK profile URLs/user_id",
        "Подготовьте direct social message",
        "Откройте профиль/диалог",
        "Отправьте вручную",
        "Отметьте отправленным",
    ),
    "whatsapp": (
        "Дождитесь official Business Platform интеграции",
        "Не используйте неофициальную автоматизацию",
    ),
    "viber": (
        "Дождитесь official bot/business API интеграции",
        "Не используйте userbot или scraping",
    ),
}

SETUP_INSTRUCTIONS: dict[str, tuple[str, ...]] = {
    "email": ("Создайте Gmail profile и сохраните App Password в Keychain/local secure store.",),
    "telegram": ("Сохраните Bot Token", "Укажите owned test chat_id", "Проверьте getMe"),
    "instagram": ("Official API live-send не включен", "Используйте Помощник отправки"),
    "tiktok": ("Official live-send не включен", "Используйте Помощник отправки"),
    "x": ("Official API access pending", "Используйте Помощник отправки"),
    "vk": ("Official VK API authorization pending", "Используйте Помощник отправки"),
    "whatsapp": ("Future: WhatsApp Business Platform credentials.",),
    "viber": ("Future: official Viber bot/business credentials.",),
}


def build_connector_slots(
    *,
    has_email_profile: bool,
    has_telegram_token: bool,
    has_telegram_chat_id: bool,
    execution_modes: dict[str, str] | None = None,
) -> list[ConnectorSlot]:
    execution_modes = execution_modes or {}
    readiness = readiness_by_channel(
        has_email_profile=has_email_profile,
        has_telegram_token=has_telegram_token,
        has_telegram_chat_id=has_telegram_chat_id,
    )
    return [
        _slot_for(row, execution_modes.get(row.channel_id, "dry_run"))
        for row in readiness.values()
    ]


def _slot_for(row: ChannelReadiness, execution_mode: str) -> ConnectorSlot:
    capability = get_channel_capability(row.channel_id)
    connection_state = _connection_state(row)
    credential_state = _credential_state(row)
    future = row.channel_id in {"whatsapp", "viber"}
    capability_summary = _capability_summary(
        row,
        False if future else capability.supports_live_send,
        False if future else capability.supports_reply_ingestion,
    )
    mode_label = EXECUTION_MODE_LABELS.get(execution_mode, execution_mode)
    return ConnectorSlot(
        channel_id=row.channel_id,
        display_name=row.display_name,
        connection_state=connection_state,
        capability_summary=capability_summary,
        official_api_status=row.official_api_live_send,
        execution_mode=execution_mode,
        execution_mode_label=mode_label,
        limitations=row.notes,
        recommended_workflow=WORKFLOWS.get(row.channel_id, ("Проверьте ограничения канала",)),
        setup_instructions=SETUP_INSTRUCTIONS.get(row.channel_id, ()),
        credential_state=credential_state,
        risk_label=risk_label(row.risk_level),
        risk_level=row.risk_level,
        readiness_percent=row.production_readiness_percent,
    )


def _connection_state(row: ChannelReadiness) -> str:
    status = row.current_status.lower()
    if row.channel_id in {"whatsapp", "viber"}:
        return FUTURE_SUPPORT
    if row.channel_id in {"instagram", "tiktok"}:
        return MANUAL_ASSIST_STATE
    if row.channel_id in {"x", "vk"}:
        return API_PENDING
    if "credentials pending" in status:
        return PARTIAL
    if row.current_status in {"Full", "Full-ready"}:
        return CONNECTED
    return NOT_CONFIGURED


def _credential_state(row: ChannelReadiness) -> str:
    if row.channel_id in {"instagram", "tiktok", "x", "vk"}:
        return "No credentials required for Manual Assist"
    if row.missing_credentials:
        return "Missing: " + ", ".join(row.missing_credentials)
    if row.channel_id in {"whatsapp", "viber"}:
        return "Future credentials"
    return "Ready"


def _capability_summary(row: ChannelReadiness, live_send: bool, reply_sync: bool) -> str:
    live = "live API" if live_send else "manual/dry-run"
    replies = "reply sync" if reply_sync else "manual replies"
    return f"{row.current_status} • {live} • {replies}"


def recommend_channel_for_lead(contact: dict[str, Any]) -> dict[str, Any]:
    channel = str(contact.get("channel") or "").strip().lower()
    handle = str(contact.get("handle") or "").strip()
    profile_url = str(contact.get("profile_url") or contact.get("social_profile") or "").lower()
    company = str(contact.get("company") or "").strip()
    email = str(contact.get("email") or "").strip().lower()
    brief = str(contact.get("research_brief_json") or "").lower()
    note = str(contact.get("note") or contact.get("ai_notes") or "").lower()
    text = " ".join([channel, handle.lower(), profile_url, company.lower(), email, brief, note])

    if "telegram" in text or str(contact.get("external_id") or "").strip().isdigit():
        return _recommend("telegram", "Есть Telegram/chat_id сигнал; быстрый controlled channel.", 0.78)
    if any(marker in text for marker in ("instagram", "creator", "influencer", "blogger")):
        return _recommend("instagram", "Creator/social lead: лучше начать с Instagram Manual Assist.", 0.74)
    if "tiktok" in text:
        return _recommend("tiktok", "TikTok creator signal: нужен короткий creator-style outreach.", 0.72)
    if "x.com" in text or "twitter" in text:
        return _recommend("x", "X profile signal: concise/direct Manual Assist.", 0.68)
    if "vk.com" in text or channel == "vk":
        return _recommend("vk", "VK profile signal: direct social Manual Assist.", 0.66)
    if company or ("@" in email and not email.endswith(("@gmail.com", "@yandex.ru", "@mail.ru", "@icloud.com"))):
        return _recommend("email", "Business/company signal: Email is the clearest primary channel.", 0.7)
    return _recommend("email", "Недостаточно social-сигналов; Email остается безопасным default.", 0.45)


def _recommend(channel_id: str, reason: str, confidence: float) -> dict[str, Any]:
    capability = get_channel_capability(channel_id)
    return {
        "channel_id": channel_id,
        "display_name": capability.display_name,
        "reason": reason,
        "confidence": confidence,
        "execution_mode": "manual_assist" if capability.requires_manual_assist else "dry_run",
        "autosend": False,
    }
