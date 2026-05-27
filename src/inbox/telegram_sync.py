from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..http_client import HttpClientError, JsonHttpClient
from ..logger_setup import redact_secret


@dataclass(frozen=True, slots=True)
class TelegramReplyMessage:
    update_id: int
    message_id: int
    chat_id: str
    sender_name: str
    text: str
    received_at: str = ""


class TelegramSyncClientProtocol(Protocol):
    def fetch_updates(self, *, bot_token: str, offset: int = 0, limit: int = 50) -> list[TelegramReplyMessage]:
        ...


class TelegramSyncClient:
    """Safe Telegram Bot API polling client.

    Uses getUpdates only. It does not send messages, set webhooks, or perform
    any account automation outside official Bot API access.
    """

    api_base_url = "https://api.telegram.org"

    def __init__(self, http_client: JsonHttpClient | None = None):
        self.http_client = http_client or JsonHttpClient(timeout=20)

    def fetch_updates(self, *, bot_token: str, offset: int = 0, limit: int = 50) -> list[TelegramReplyMessage]:
        token = bot_token.strip()
        if not token:
            raise RuntimeError("Telegram sync requires saved Bot Token.")
        try:
            payload = self.http_client.post_form(
                f"{self.api_base_url}/bot{token}/getUpdates",
                {
                    "offset": max(offset, 0),
                    "limit": max(1, min(limit, 100)),
                    "timeout": 0,
                    "allowed_updates": '["message"]',
                },
                secrets=[token],
            )
        except HttpClientError as exc:
            raise RuntimeError(redact_secret(str(exc), extra_secrets=[token])) from exc
        if not payload.get("ok"):
            raise RuntimeError(redact_secret(str(payload.get("description") or "Telegram getUpdates failed."), extra_secrets=[token]))
        result = payload.get("result")
        if not isinstance(result, list):
            return []
        messages: list[TelegramReplyMessage] = []
        for update in result:
            parsed = self._parse_update(update)
            if parsed:
                messages.append(parsed)
        return messages

    def _parse_update(self, update: Any) -> TelegramReplyMessage | None:
        if not isinstance(update, dict):
            return None
        message = update.get("message")
        if not isinstance(message, dict):
            return None
        text = str(message.get("text") or "").strip()
        if not text:
            return None
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        sender = message.get("from") if isinstance(message.get("from"), dict) else {}
        chat_id = str(chat.get("id") or "").strip()
        if not chat_id:
            return None
        first_name = str(sender.get("first_name") or chat.get("first_name") or "").strip()
        username = str(sender.get("username") or chat.get("username") or "").strip()
        label = f"@{username}" if username else first_name
        return TelegramReplyMessage(
            update_id=int(update.get("update_id") or 0),
            message_id=int(message.get("message_id") or 0),
            chat_id=chat_id,
            sender_name=label,
            text=text,
            received_at=str(message.get("date") or ""),
        )
