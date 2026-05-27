from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Protocol

from ..config import get_openai_research_api_key
from ..logger_setup import redact_secret
from .provider import AIConnectionCheckResult, AIProviderError
from .research_schema import RecipientBrief, RecipientResearchInput, parse_recipient_brief


class BaseResearchBrain(Protocol):
    def research_contact(self, input_data: RecipientResearchInput) -> RecipientBrief:
        ...

    def check_connection(self) -> AIConnectionCheckResult:
        ...


def build_research_messages(input_data: RecipientResearchInput) -> list[dict[str, str]]:
    payload = {
        "campaign_topic": input_data.campaign_topic,
        "channel": input_data.channel,
        "recipient": {
            "email": input_data.email,
            "email_domain": input_data.email_domain,
            "name": input_data.name,
            "company": input_data.company,
            "website": input_data.website,
            "social_profile": input_data.social_profile,
            "note": input_data.note,
        },
        "enrichment_result": input_data.enrichment_result or {},
    }
    enrichment_status = str((input_data.enrichment_result or {}).get("status") or "").strip().lower()
    enrichment_rule = (
        "Если enrichment_result отсутствует, считай что нет web enrichment и используй только row_data. "
        "Если enrichment_result.status success или partial, можно использовать только эти публичные данные "
        "и добавить source_basis website_public_data. Если enrichment failed/blocked/skipped, не делай выводов "
        "из сайта и добавь warning. "
    )
    system = (
        "Ты Research Brain для безопасного outreach-инструмента. "
        "Ты анализируешь ТОЛЬКО данные строки получателя, тему кампании и переданный enrichment_result. "
        "Ты сам НЕ браузишь интернет и НЕ делаешь дополнительных запросов. "
        + enrichment_rule
        + "Не утверждай, что ты лично проверил сайт, соцсеть, видео, посты, метрики или новости. "
        "Разрешены только осторожные domain heuristics, но они должны быть помечены низкой уверенностью. "
        "Если данных мало, честно укажи предупреждение 'Недостаточно данных'. "
        "Не выдумывай факты, должности, аудиторию, достижения, интересы или историю отношений. "
        "Не делай выводов о личных Gmail/Yandex/Mail.ru доменах, кроме того что данных мало. "
        "Верни только валидный JSON без Markdown."
    )
    user = (
        "Сформируй structured recipient brief.\n"
        "Формат ответа строго:\n"
        "{\n"
        '  "recipient_type": "creator|brand|company|agency|unknown",\n'
        '  "likely_context": "...",\n'
        '  "positioning_angle": "...",\n'
        '  "message_hooks": ["...", "..."],\n'
        '  "do_not_claim": ["...", "..."],\n'
        '  "personalization_strength": "low|medium|high",\n'
        '  "confidence": 0.0,\n'
        '  "warnings": [],\n'
        '  "source_basis": ["row_data"]\n'
        "}\n\n"
        "source_basis может включать только: row_data, domain_heuristic, user_note, website_url_only, website_public_data.\n"
        f"Текущий enrichment status: {enrichment_status or 'none'}.\n"
        f"Входные данные:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class OpenAIResearchBrain:
    def __init__(
        self,
        model: str = "gpt-4.1-mini",
        api_key_getter: Callable[[], str] = get_openai_research_api_key,
        base_url: str = "https://api.openai.com/v1",
    ):
        self.model = (model or "gpt-4.1-mini").strip()
        self.api_key_getter = api_key_getter
        self.base_url = base_url.rstrip("/")

    def _api_key(self) -> str:
        key = (self.api_key_getter() or "").strip()
        if not key:
            raise AIProviderError("Добавьте Research Brain API key в Аккаунты и настройки → AI Assist.")
        return key

    def research_contact(self, input_data: RecipientResearchInput) -> RecipientBrief:
        api_key = self._api_key()
        payload = {
            "model": self.model,
            "messages": build_research_messages(input_data),
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        try:
            response = self._post_json("/chat/completions", payload, api_key)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            return parse_recipient_brief(content)
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
            return AIConnectionCheckResult(False, f"Research Brain failed: {redact_secret(exc)}")
        return AIConnectionCheckResult(True, "Research Brain подключен. Модель доступна.")

    def _post_json(self, path: str, payload: dict, api_key: str) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
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
