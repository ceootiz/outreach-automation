from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable

from ..config import get_openai_api_key
from ..logger_setup import redact_secret
from .prompt_builder import build_email_draft_messages
from .provider import AIConnectionCheckResult, AIProviderError
from .result_schema import EmailDraftInput, EmailDraftResult, parse_email_draft_result


class OpenAIEmailDraftProvider:
    def __init__(
        self,
        model: str = "gpt-4.1-mini",
        api_key_getter: Callable[[], str] = get_openai_api_key,
        base_url: str = "https://api.openai.com/v1",
    ):
        self.model = (model or "gpt-4.1-mini").strip()
        self.api_key_getter = api_key_getter
        self.base_url = base_url.rstrip("/")

    def _api_key(self) -> str:
        key = (self.api_key_getter() or "").strip()
        if not key:
            raise AIProviderError("Добавьте API key в Аккаунты и настройки → AI Assist.")
        return key

    def generate_email_draft(self, input_data: EmailDraftInput) -> EmailDraftResult:
        api_key = self._api_key()
        payload = {
            "model": self.model,
            "messages": build_email_draft_messages(input_data),
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
        }
        try:
            response = self._post_json("/chat/completions", payload, api_key)
            content = (
                response.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return parse_email_draft_result(
                content,
                require_subject=(input_data.channel or "email") == "email",
            )
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError(redact_secret(exc, extra_secrets=[api_key])) from exc

    def check_connection(self) -> AIConnectionCheckResult:
        try:
            api_key = self._api_key()
            self._get_json(f"/models/{self.model}", api_key)
        except AIProviderError as exc:
            return AIConnectionCheckResult(False, str(exc))
        except Exception as exc:
            return AIConnectionCheckResult(
                False,
                f"AI connection failed: {redact_secret(exc)}",
            )
        return AIConnectionCheckResult(True, "AI подключен. Модель доступна.")

    def _post_json(self, path: str, payload: dict, api_key: str) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        return self._request_json(request, api_key)

    def _get_json(self, path: str, api_key: str) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        return self._request_json(request, api_key)

    @staticmethod
    def _request_json(request: urllib.request.Request, api_key: str) -> dict:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AIProviderError(redact_secret(f"OpenAI HTTP {exc.code}: {body}", [api_key])) from exc
        except urllib.error.URLError as exc:
            raise AIProviderError(redact_secret(f"OpenAI network error: {exc}", [api_key])) from exc
