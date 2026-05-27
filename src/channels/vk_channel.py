from __future__ import annotations

from .social_base import SocialDryRunChannel


class VKChannel(SocialDryRunChannel):
    def __init__(self) -> None:
        super().__init__(
            channel_id="vk",
            display_name="VK",
            required_fields=("handle", "profile_url", "external_id"),
            supports_official_api=True,
            limitation_text=(
                "VK требует официальной авторизации/API и соблюдения лимитов. "
                "Stage 3.0 не выполняет live-отправку."
            ),
        )
