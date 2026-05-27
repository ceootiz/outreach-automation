from __future__ import annotations

from typing import Any

from ..http_client import HttpClientError, JsonHttpClient
from ..logger_setup import redact_secret
from .base import ChannelCheckResult, ChannelLimit, ChannelSendResult, ChannelSafetyError
from .social_base import SocialDryRunChannel


class TelegramChannel(SocialDryRunChannel):
    api_base_url = "https://api.telegram.org"

    def __init__(self, http_client: JsonHttpClient | None = None) -> None:
        super().__init__(
            channel_id="telegram",
            display_name="Telegram",
            required_fields=("handle", "external_id", "profile_url"),
            supports_official_api=True,
            limitation_text=(
                "Telegram Bot может писать только доступным чатам: тем, кто начал диалог "
                "с ботом, или чатам, где бот имеет доступ."
            ),
        )
        self.supports_live_send = True
        self.limits = (
            ChannelLimit("Official API", "Telegram Bot API"),
            ChannelLimit("Live recipient", "Только chat_id, где бот имеет доступ"),
            ChannelLimit("Dry-run", "По умолчанию, без HTTP вызова"),
        )
        self.http_client = http_client or JsonHttpClient()

    def platform_recipient(self, contact: dict[str, Any]) -> str:
        for key in ("external_id", "handle", "profile_url", "email"):
            value = str(contact.get(key) or "").strip()
            if value:
                return value
        return ""

    def validate_live_recipient(self, contact: dict[str, Any]) -> tuple[bool, str]:
        chat_id = str(contact.get("external_id") or "").strip()
        if not chat_id:
            return False, "Telegram live send требует chat_id в поле ID / chat."
        return True, chat_id

    def check_connection(self, credentials: dict[str, str] | None = None) -> ChannelCheckResult:
        token = str((credentials or {}).get("bot_token") or "").strip()
        if not token:
            return ChannelCheckResult(False, "Missing Telegram Bot Token.")
        try:
            data = self.http_client.get_json(
                self._method_url(token, "getMe"),
                secrets=[token],
            )
        except HttpClientError as exc:
            return ChannelCheckResult(False, redact_secret(str(exc), extra_secrets=[token]))
        if not data.get("ok"):
            description = str(data.get("description") or "Telegram getMe failed.")
            return ChannelCheckResult(False, redact_secret(description, extra_secrets=[token]))
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        username = str(result.get("username") or "").strip()
        first_name = str(result.get("first_name") or "").strip()
        label = f"@{username}" if username else first_name or "Telegram bot"
        return ChannelCheckResult(True, f"Telegram подключен: {label}")

    def send_message(
        self,
        *,
        bot_token: str,
        chat_id: str,
        text: str,
    ) -> ChannelSendResult:
        token = bot_token.strip()
        recipient = chat_id.strip()
        body = text.strip()
        if not token:
            raise ChannelSafetyError("Telegram live send blocked: Bot Token is missing.")
        if not recipient:
            raise ChannelSafetyError("Telegram live send blocked: chat_id is missing.")
        if not body:
            raise ChannelSafetyError("Telegram live send blocked: message is empty.")
        try:
            data = self.http_client.post_form(
                self._method_url(token, "sendMessage"),
                {"chat_id": recipient, "text": body},
                secrets=[token],
            )
        except HttpClientError as exc:
            raise ChannelSafetyError(redact_secret(str(exc), extra_secrets=[token])) from exc
        if not data.get("ok"):
            description = str(data.get("description") or "Telegram sendMessage failed.")
            raise ChannelSafetyError(redact_secret(description, extra_secrets=[token]))
        return ChannelSendResult(True, "sent", "Telegram message sent.")

    def _method_url(self, token: str, method: str) -> str:
        return f"{self.api_base_url}/bot{token}/{method}"
