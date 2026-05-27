from __future__ import annotations

from dataclasses import dataclass

from .risk_levels import HIGH, LOW, LOW_MEDIUM, MEDIUM, MEDIUM_HIGH, risk_explanation


DRY_RUN = "dry_run"
OFFICIAL_API = "official_api"
MANUAL_ASSIST = "manual_assist"


@dataclass(frozen=True, slots=True)
class ChannelCapability:
    channel_id: str
    display_name: str
    official_api: str
    supports_live_send: bool
    supports_official_api: bool
    supports_dry_run: bool
    supports_reply_ingestion: bool
    requires_manual_assist: bool
    requires_human_confirmation: bool
    risk_level: str
    limitation_text: str
    allowed_execution_modes: tuple[str, ...]

    @property
    def risk_explanation(self) -> str:
        return risk_explanation(self.risk_level)


CAPABILITY_MATRIX: dict[str, ChannelCapability] = {
    "email": ChannelCapability(
        channel_id="email",
        display_name="Email",
        official_api="yes",
        supports_live_send=True,
        supports_official_api=True,
        supports_dry_run=True,
        supports_reply_ingestion=True,
        requires_manual_assist=False,
        requires_human_confirmation=True,
        risk_level=LOW,
        limitation_text="Gmail SMTP/IMAP через сохраненный профиль. Live send требует явного подтверждения.",
        allowed_execution_modes=(DRY_RUN, OFFICIAL_API),
    ),
    "telegram": ChannelCapability(
        channel_id="telegram",
        display_name="Telegram",
        official_api="yes",
        supports_live_send=True,
        supports_official_api=True,
        supports_dry_run=True,
        supports_reply_ingestion=True,
        requires_manual_assist=False,
        requires_human_confirmation=True,
        risk_level=LOW_MEDIUM,
        limitation_text="Official Bot API. Бот может писать только в доступные chat_id.",
        allowed_execution_modes=(DRY_RUN, OFFICIAL_API, MANUAL_ASSIST),
    ),
    "x": ChannelCapability(
        channel_id="x",
        display_name="X / Twitter",
        official_api="limited",
        supports_live_send=False,
        supports_official_api=False,
        supports_dry_run=True,
        supports_reply_ingestion=False,
        requires_manual_assist=True,
        requires_human_confirmation=True,
        risk_level=MEDIUM_HIGH,
        limitation_text="Автоматизация DM ограничена правилами платформы. Используйте Manual Assist.",
        allowed_execution_modes=(DRY_RUN, MANUAL_ASSIST),
    ),
    "instagram": ChannelCapability(
        channel_id="instagram",
        display_name="Instagram",
        official_api="restricted",
        supports_live_send=False,
        supports_official_api=False,
        supports_dry_run=True,
        supports_reply_ingestion=False,
        requires_manual_assist=True,
        requires_human_confirmation=True,
        risk_level=HIGH,
        limitation_text="Автоматическая отправка ограничена правилами платформы. Используйте Manual Assist.",
        allowed_execution_modes=(DRY_RUN, MANUAL_ASSIST),
    ),
    "vk": ChannelCapability(
        channel_id="vk",
        display_name="VK",
        official_api="partial",
        supports_live_send=False,
        supports_official_api=False,
        supports_dry_run=True,
        supports_reply_ingestion=False,
        requires_manual_assist=True,
        requires_human_confirmation=True,
        risk_level=MEDIUM,
        limitation_text="VK требует официальной авторизации/API и соблюдения лимитов. Сейчас безопасен Manual Assist.",
        allowed_execution_modes=(DRY_RUN, MANUAL_ASSIST),
    ),
    "tiktok": ChannelCapability(
        channel_id="tiktok",
        display_name="TikTok",
        official_api="limited",
        supports_live_send=False,
        supports_official_api=False,
        supports_dry_run=True,
        supports_reply_ingestion=False,
        requires_manual_assist=True,
        requires_human_confirmation=True,
        risk_level=HIGH,
        limitation_text="Безопасная автоматическая отправка недоступна. Используйте Manual Assist.",
        allowed_execution_modes=(DRY_RUN, MANUAL_ASSIST),
    ),
}


def get_channel_capability(channel_id: str | None) -> ChannelCapability:
    normalized = (channel_id or "email").strip().lower()
    return CAPABILITY_MATRIX.get(normalized, CAPABILITY_MATRIX["email"])


def list_channel_capabilities() -> list[ChannelCapability]:
    return [CAPABILITY_MATRIX[key] for key in ("email", "telegram", "x", "instagram", "vk", "tiktok")]
