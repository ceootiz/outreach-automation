from __future__ import annotations

from .base import BaseChannel, ChannelLimit


class SocialDryRunChannel(BaseChannel):
    def __init__(
        self,
        *,
        channel_id: str,
        display_name: str,
        required_fields: tuple[str, ...],
        supports_official_api: bool,
        limitation_text: str,
    ) -> None:
        super().__init__(
            channel_id=channel_id,
            display_name=display_name,
            required_fields=required_fields,
            supports_dry_run=True,
            supports_live_send=False,
            supports_official_api=supports_official_api,
            limitation_text=limitation_text,
            limits=(
                ChannelLimit("Stage 3.0", "Только подготовка, review и dry-run"),
                ChannelLimit("Live send", "Отключен до безопасной official API-интеграции"),
            ),
        )
