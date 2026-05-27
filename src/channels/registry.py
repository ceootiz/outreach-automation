from __future__ import annotations

from .base import BaseChannel
from .email_channel import EmailChannel
from .instagram_channel import InstagramChannel
from .telegram_channel import TelegramChannel
from .tiktok_channel import TikTokChannel
from .vk_channel import VKChannel
from .x_channel import XChannel


CHANNELS: dict[str, BaseChannel] = {
    "email": EmailChannel(),
    "x": XChannel(),
    "instagram": InstagramChannel(),
    "telegram": TelegramChannel(),
    "vk": VKChannel(),
    "tiktok": TikTokChannel(),
}


def get_channel(channel_id: str | None) -> BaseChannel:
    normalized = (channel_id or "email").strip().lower()
    return CHANNELS.get(normalized, CHANNELS["email"])


def list_channels() -> list[BaseChannel]:
    return list(CHANNELS.values())


def channel_options() -> list[tuple[str, str]]:
    return [(channel.channel_id, channel.display_name) for channel in list_channels()]
