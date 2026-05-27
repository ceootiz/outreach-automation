from __future__ import annotations

from .social_base import SocialDryRunChannel


class TikTokChannel(SocialDryRunChannel):
    def __init__(self) -> None:
        super().__init__(
            channel_id="tiktok",
            display_name="TikTok",
            required_fields=("handle", "profile_url", "external_id"),
            supports_official_api=False,
            limitation_text=(
                "TikTok не предназначен для массовой автоматической отправки сообщений "
                "через обычные аккаунты. Используйте только разрешенные официальные сценарии."
            ),
        )
