from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ChannelCheckResult:
    ok: bool
    message: str


@dataclass(frozen=True, slots=True)
class ChannelSendResult:
    ok: bool
    status: str
    message: str = ""


@dataclass(frozen=True, slots=True)
class ChannelLimit:
    label: str
    value: str


class ChannelSafetyError(RuntimeError):
    """Raised when a channel action is blocked by product safety rules."""


@dataclass(slots=True)
class BaseChannel:
    channel_id: str
    display_name: str
    required_fields: tuple[str, ...]
    supports_dry_run: bool = True
    supports_live_send: bool = False
    supports_official_api: bool = False
    limitation_text: str = ""
    live_disabled_message: str = (
        "Боевая отправка для этого канала пока отключена. "
        "Можно подготовить сообщения и сделать тестовый прогон."
    )
    limits: tuple[ChannelLimit, ...] = field(default_factory=tuple)

    def platform_recipient(self, contact: dict[str, Any]) -> str:
        for key in ("handle", "profile_url", "external_id", "email"):
            value = str(contact.get(key) or "").strip()
            if value:
                return value
        return ""

    def validate_recipient(self, contact: dict[str, Any]) -> tuple[bool, str]:
        for field in self.required_fields:
            if str(contact.get(field) or "").strip():
                return True, ""
        field_list = ", ".join(self.required_fields)
        return False, f"Не указан получатель для канала {self.display_name}: {field_list}."

    def check_connection(self, credentials: dict[str, str] | None = None) -> ChannelCheckResult:
        if self.supports_live_send:
            return ChannelCheckResult(True, f"{self.display_name}: подключение доступно.")
        return ChannelCheckResult(
            False,
            f"{self.display_name}: live-интеграция пока отключена. Используйте dry-run и ручную проверку.",
        )

    def send_message(self, *args: Any, **kwargs: Any) -> ChannelSendResult:
        raise ChannelSafetyError(self.live_disabled_message)

    def get_limits(self) -> tuple[ChannelLimit, ...]:
        return self.limits

    def explain_limitations(self) -> str:
        return self.limitation_text
