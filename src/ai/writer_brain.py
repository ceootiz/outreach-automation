from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Protocol

from ..config import get_openai_writer_api_key
from ..logger_setup import redact_secret
from .prompt_builder import CHANNEL_CONTEXT, tone_to_ru
from .provider import AIConnectionCheckResult, AIProviderError
from .writer_schema import DraftWritingInput, WriterDraft, parse_writer_draft


class BaseWriterBrain(Protocol):
    def write_draft(self, input_data: DraftWritingInput) -> WriterDraft:
        ...

    def check_connection(self) -> AIConnectionCheckResult:
        ...


def build_writer_messages(input_data: DraftWritingInput) -> list[dict[str, str]]:
    channel_id = (input_data.channel or "email").strip().lower()
    channel_context = CHANNEL_CONTEXT.get(channel_id, CHANNEL_CONTEXT["email"])
    payload = {
        "campaign_topic": input_data.campaign_topic,
        "tone": tone_to_ru(input_data.tone),
        "channel": channel_context,
        "contact": {
            "email": input_data.email,
            "name": input_data.name,
            "company": input_data.company,
            "website": input_data.website,
            "social_profile": input_data.social_profile,
            "note": input_data.note,
        },
        "recipient_brief": input_data.recipient_brief.to_dict(),
        "execution": {
            "mode": input_data.execution_mode or "dry_run",
            "notes": input_data.execution_notes,
            "rules": (
                "AI writes drafts only. Manual Assist means the operator copies/opens/sends manually. "
                "Official API sends only after explicit human confirmation."
            ),
        },
    }
    system = (
        "Ты Writer Brain для безопасного outreach-инструмента. "
        "Ты пишешь только черновик, который оператор обязан проверить вручную. "
        "Ты НЕ отправляешь, НЕ подтверждаешь и НЕ запускаешь live send. "
        "Используй только recipient_brief и данные контакта. Не добавляй факты, которых нет в brief. "
        "Не утверждай, что изучил сайт, профиль, видео, посты или метрики. "
        "Если brief основан на website_public_data, можно использовать смысловые инсайты, но нельзя писать "
        "получателю фразы вроде 'я изучил ваш сайт' или 'мы посмотрели ваш профиль'. "
        "Соблюдай do_not_claim из brief. Если brief говорит о недостатке данных, пиши нейтрально и добавь warning. "
        "Без fake familiarity, давления, скрытой автоматизации, агрессивного рекламного тона и обещаний без основания. "
        "Учитывай execution mode и ограничения канала. Для Manual Assist текст должен быть коротким, естественным "
        "и пригодным для ручной отправки оператором. "
        "Для X/Instagram/TikTok/VK делай текст короче email, без subject, без давления, без fake familiarity, "
        "friendly but not cringe, value-first и без утверждений о просмотре профиля, если это не подтверждено brief. "
        "Пиши на русском по умолчанию, если тема явно не на английском. "
        f"Канал: {channel_context['label']}. Формат: {channel_context['format']} "
        "Верни только валидный JSON без Markdown."
    )
    if channel_id == "email":
        schema = (
            "{\n"
            '  "subject": "...",\n'
            '  "body": "...",\n'
            '  "why_this_angle": "...",\n'
            '  "warnings": [],\n'
            '  "confidence": 0.0\n'
            "}"
        )
    else:
        schema = (
            "{\n"
            '  "body": "...",\n'
            '  "why_this_angle": "...",\n'
            '  "warnings": [],\n'
            '  "confidence": 0.0\n'
            "}"
        )
    user = (
        "Сгенерируй channel-aware черновик на основе brief.\n"
        f"Стиль канала: {channel_context['style']}.\n"
        f"Формат ответа строго:\n{schema}\n\n"
        f"Входные данные:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class OpenAIWriterBrain:
    def __init__(
        self,
        model: str = "gpt-4.1-mini",
        api_key_getter: Callable[[], str] = get_openai_writer_api_key,
        base_url: str = "https://api.openai.com/v1",
    ):
        self.model = (model or "gpt-4.1-mini").strip()
        self.api_key_getter = api_key_getter
        self.base_url = base_url.rstrip("/")

    def _api_key(self) -> str:
        key = (self.api_key_getter() or "").strip()
        if not key:
            raise AIProviderError("Добавьте Writer Brain API key в Аккаунты и настройки → AI Assist.")
        return key

    def write_draft(self, input_data: DraftWritingInput) -> WriterDraft:
        api_key = self._api_key()
        payload = {
            "model": self.model,
            "messages": build_writer_messages(input_data),
            "temperature": 0.35,
            "response_format": {"type": "json_object"},
        }
        try:
            response = self._post_json("/chat/completions", payload, api_key)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            return parse_writer_draft(content, require_subject=(input_data.channel or "email") == "email")
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
            return AIConnectionCheckResult(False, f"Writer Brain failed: {redact_secret(exc)}")
        return AIConnectionCheckResult(True, "Writer Brain подключен. Модель доступна.")

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
