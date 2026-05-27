from __future__ import annotations

from typing import Callable

from ..config import get_openai_api_key
from .openai_provider import OpenAIEmailDraftProvider
from .provider import AIConnectionCheckResult, AIProviderError, BaseAIProvider
from .result_schema import EmailDraftInput, EmailDraftResult


class AIService:
    def __init__(
        self,
        provider_factory: Callable[[str, str], BaseAIProvider] | None = None,
        api_key_getter: Callable[[], str] = get_openai_api_key,
    ):
        self.provider_factory = provider_factory or self._default_provider_factory
        self.api_key_getter = api_key_getter

    def _default_provider_factory(self, provider_name: str, model: str) -> BaseAIProvider:
        if provider_name == "openai":
            return OpenAIEmailDraftProvider(model=model, api_key_getter=self.api_key_getter)
        raise AIProviderError("AI Assist выключен. Выберите OpenAI в Аккаунты и настройки → AI Assist.")

    def provider(self, provider_name: str, model: str) -> BaseAIProvider:
        normalized = (provider_name or "off").strip().lower()
        if normalized in {"", "off"}:
            raise AIProviderError("AI Assist выключен. Выберите OpenAI в Аккаунты и настройки → AI Assist.")
        return self.provider_factory(normalized, model or "gpt-4.1-mini")

    def generate_draft_for_contact(
        self,
        contact: dict,
        campaign_topic: str,
        tone: str,
        *,
        provider_name: str,
        model: str,
        execution_mode: str = "dry_run",
        execution_notes: str = "",
    ) -> EmailDraftResult:
        input_data = EmailDraftInput(
            contact_id=contact.get("id"),
            email=str(contact.get("email") or ""),
            channel=str(contact.get("channel") or "email"),
            name=str(contact.get("name") or ""),
            company=str(contact.get("company") or ""),
            website=str(contact.get("website") or ""),
            social_profile=str(contact.get("social_profile") or ""),
            note=str(contact.get("topic") or ""),
            campaign_topic=campaign_topic,
            tone=tone,
            execution_mode=execution_mode,
            execution_notes=execution_notes,
        )
        return self.provider(provider_name, model).generate_email_draft(input_data)

    def check_connection(self, provider_name: str, model: str) -> AIConnectionCheckResult:
        try:
            return self.provider(provider_name, model).check_connection()
        except AIProviderError as exc:
            return AIConnectionCheckResult(False, str(exc))
