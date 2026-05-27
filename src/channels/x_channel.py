from __future__ import annotations

from .social_base import SocialDryRunChannel


class XChannel(SocialDryRunChannel):
    def __init__(self) -> None:
        super().__init__(
            channel_id="x",
            display_name="X / Twitter",
            required_fields=("handle", "profile_url", "external_id"),
            supports_official_api=True,
            limitation_text=(
                "Автоматизация личных сообщений ограничена правилами платформы. "
                "Используйте только разрешенные API и ручное подтверждение."
            ),
        )
