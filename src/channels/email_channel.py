from __future__ import annotations

from typing import Any

from ..excel_importer import is_valid_email
from .base import BaseChannel, ChannelCheckResult, ChannelLimit


class EmailChannel(BaseChannel):
    def __init__(self) -> None:
        super().__init__(
            channel_id="email",
            display_name="Email",
            required_fields=("email",),
            supports_dry_run=True,
            supports_live_send=True,
            supports_official_api=True,
            limitation_text=(
                "Email-отправка работает через выбранный Gmail-профиль, "
                "с ручным подтверждением, дневными лимитами, blacklist и dry-run по умолчанию."
            ),
            limits=(
                ChannelLimit("Дневной лимит", "Задается в настройках"),
                ChannelLimit("Боевой режим", "Только после явного подтверждения"),
            ),
        )

    def platform_recipient(self, contact: dict[str, Any]) -> str:
        return str(contact.get("email") or "").strip().lower()

    def validate_recipient(self, contact: dict[str, Any]) -> tuple[bool, str]:
        email = self.platform_recipient(contact)
        if email and is_valid_email(email):
            return True, ""
        return False, "Не удалось определить получателя: email в строке пустой или неверный."

    def check_connection(self, credentials: dict[str, str] | None = None) -> ChannelCheckResult:
        return ChannelCheckResult(True, "Email использует активный Gmail-профиль.")
