from __future__ import annotations

from .social_base import SocialDryRunChannel


class InstagramChannel(SocialDryRunChannel):
    def __init__(self) -> None:
        super().__init__(
            channel_id="instagram",
            display_name="Instagram",
            required_fields=("handle", "profile_url", "external_id"),
            supports_official_api=True,
            limitation_text=(
                "Instagram строго ограничивает автоматические сообщения. "
                "Безопасный режим не выполняет массовую отправку."
            ),
        )
