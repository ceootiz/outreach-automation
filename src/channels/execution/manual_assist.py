from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..profile_urls import PROFILE_URL_TEMPLATES, normalize_handle, profile_url_for
from .capability_matrix import get_channel_capability


@dataclass(frozen=True, slots=True)
class ManualAssistAction:
    contact_id: int
    channel: str
    recipient: str
    profile_url: str
    message: str
    subject: str = ""
    copy_text: str = ""
    instructions: str = ""
    risk_level: str = "medium"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contact_id": self.contact_id,
            "channel": self.channel,
            "recipient": self.recipient,
            "profile_url": self.profile_url,
            "message": self.message,
            "subject": self.subject,
            "copy_text": self.copy_text or self.message,
            "instructions": self.instructions,
            "risk_level": self.risk_level,
            "warnings": list(self.warnings),
        }


def infer_profile_url(channel_id: str, handle: str, profile_url: str = "") -> str:
    result = profile_url_for(channel_id, handle=handle, profile_url=profile_url)
    return result.url


def build_manual_assist_action(contact: dict[str, Any]) -> ManualAssistAction:
    channel_id = str(contact.get("channel") or "email").strip().lower()
    capability = get_channel_capability(channel_id)
    handle = normalize_handle(str(contact.get("handle") or ""))
    profile_result = profile_url_for(
        channel_id,
        handle=handle,
        profile_url=str(contact.get("profile_url") or ""),
        external_id=str(contact.get("external_id") or ""),
    )
    profile_url = profile_result.url
    recipient = (
        str(contact.get("external_id") or "").strip()
        or profile_url
        or (f"@{handle}" if handle else "")
        or str(contact.get("email") or "").strip()
    )
    message = str(contact.get("generated_message") or contact.get("base_message") or "").strip()
    subject = str(contact.get("subject") or "").strip()
    warnings = [capability.limitation_text, capability.risk_explanation]
    if not recipient:
        warnings.append("Получатель не указан. Добавьте handle, profile URL, chat_id или email.")
    if profile_result.warning:
        warnings.append(profile_result.warning)
    if not message:
        warnings.append("Сообщение пустое. Сначала подготовьте текст или AI-черновик.")
    instructions = (
        "Скопируйте подготовленный текст, откройте профиль вручную и отправьте сообщение только если это уместно. "
        "Приложение не логинится в платформы, не обходит ограничения и не отправляет скрыто."
    )
    return ManualAssistAction(
        contact_id=int(contact.get("id") or 0),
        channel=channel_id,
        recipient=recipient,
        profile_url=profile_url,
        message=message,
        subject=subject,
        copy_text=message,
        instructions=instructions,
        risk_level=capability.risk_level,
        warnings=warnings,
    )
