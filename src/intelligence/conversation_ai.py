from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..logger_setup import redact_secret


@dataclass(frozen=True, slots=True)
class ConversationAnalysisResult:
    summary: str
    intent: str
    sentiment: str
    urgency: str
    recommended_next_action: str
    followup_timing: str
    followup_tone: str
    lead_status: str


@dataclass(frozen=True, slots=True)
class ConversationReplySuggestions:
    summary: str
    intent: str
    sentiment: str
    urgency: str
    recommended_next_action: str
    short_reply: str
    friendly_reply: str
    formal_reply: str


class ConversationAI:
    """Deterministic conversation intelligence layer.

    This class intentionally does not call an external model. It provides a
    safe local baseline for inbox workflows and keeps all suggestions as drafts.
    """

    def analyze_reply(
        self,
        contact: dict[str, Any],
        reply_text: str,
        *,
        channel: str = "email",
    ) -> ConversationAnalysisResult:
        text = redact_secret(reply_text.strip())
        lower = text.lower()
        channel_id = (channel or contact.get("channel") or "email").strip().lower()

        negative = any(
            marker in lower
            for marker in (
                "не интересно",
                "not interested",
                "unsubscribe",
                "отпишите",
                "не пишите",
                "stop",
                "нет, спасибо",
            )
        )
        pricing = any(marker in lower for marker in ("цен", "price", "стоим", "медиакит", "media kit", "прайс"))
        positive = any(
            marker in lower
            for marker in ("интерес", "подробнее", "да", "ок", "ok", "готов", "let's", "супер", "хочу")
        )
        timing = any(marker in lower for marker in ("позже", "next week", "через", "later", "напишите"))
        urgent = any(marker in lower for marker in ("срочно", "today", "сегодня", "asap", "завтра"))

        if negative:
            sentiment = "negative"
            intent = "not_interested"
            lead_status = "Lost"
            summary = "Контакт отказался или попросил больше не писать."
            next_action = "Не отправлять follow-up. При необходимости добавить в blacklist/stop-list вручную."
            followup_timing = "не нужен"
            followup_tone = "none"
        elif pricing:
            sentiment = "positive"
            intent = "pricing_request"
            lead_status = "Interested"
            summary = "Контакт заинтересован и просит детали, цену или медиакит."
            next_action = "Ответить с краткими деталями и предложить следующий шаг."
            followup_timing = "через 2 дня, если нет ответа"
            followup_tone = "деловой"
        elif positive:
            sentiment = "positive"
            intent = "interested"
            lead_status = "Warm"
            summary = "Контакт проявляет интерес и открыт к продолжению."
            next_action = "Ответить коротко, уточнить контекст и предложить удобный формат продолжения."
            followup_timing = "через 3 дня, если нет ответа"
            followup_tone = "дружелюбный"
        elif timing:
            sentiment = "neutral"
            intent = "maybe_later"
            lead_status = "Warm"
            summary = "Контакт просит вернуться позже или не готов отвечать сейчас."
            next_action = "Запланировать ручной follow-up на подходящую дату."
            followup_timing = "через 5-7 дней"
            followup_tone = "спокойный"
        else:
            sentiment = "neutral"
            intent = "needs_review"
            lead_status = "Contacted"
            summary = "Ответ требует ручной оценки. Данных недостаточно для уверенного вывода."
            next_action = "Оператору нужно прочитать reply и выбрать дальнейшее действие."
            followup_timing = "после ручной оценки"
            followup_tone = "нейтральный"

        if channel_id in {"telegram", "x", "instagram", "vk", "tiktok"} and not negative:
            next_action = f"{next_action} Для {channel_id} держать ответ коротким и без давления."

        return ConversationAnalysisResult(
            summary=summary,
            intent=intent,
            sentiment=sentiment,
            urgency="high" if urgent else "normal",
            recommended_next_action=next_action,
            followup_timing=followup_timing,
            followup_tone=followup_tone,
            lead_status=lead_status,
        )

    def suggest_replies(
        self,
        contact: dict[str, Any],
        reply_text: str,
        *,
        channel: str = "email",
    ) -> ConversationReplySuggestions:
        analysis = self.analyze_reply(contact, reply_text, channel=channel)
        name = str(contact.get("name") or "").strip()
        greeting = f"{name}, " if name else ""
        channel_id = (channel or contact.get("channel") or "email").strip().lower()

        if analysis.intent == "not_interested":
            short = f"{greeting}понял(а), спасибо за ответ. Больше не буду беспокоить."
            friendly = f"{greeting}спасибо, что ответили. Уважаю ваше решение и больше не буду писать по этому поводу."
            formal = f"{greeting}благодарю за ответ. Зафиксирую, что продолжение сейчас неактуально."
        elif channel_id == "email":
            short = f"{greeting}спасибо за ответ. Могу прислать краткие детали и предложить следующий шаг."
            friendly = f"{greeting}спасибо, рад(а) вашему ответу. Давайте аккуратно обсудим детали и удобный формат."
            formal = (
                f"{greeting}благодарю за ответ. Подготовлю краткую информацию и предложу удобный вариант продолжения."
            )
        else:
            short = f"{greeting}спасибо за ответ. Могу коротко прислать детали?"
            friendly = f"{greeting}класс, спасибо. Напишу коротко по сути и без лишнего давления."
            formal = f"{greeting}благодарю. Могу отправить краткие детали следующим сообщением."

        return ConversationReplySuggestions(
            summary=analysis.summary,
            intent=analysis.intent,
            sentiment=analysis.sentiment,
            urgency=analysis.urgency,
            recommended_next_action=analysis.recommended_next_action,
            short_reply=short,
            friendly_reply=friendly,
            formal_reply=formal,
        )

    def suggested_due_at(self, analysis: ConversationAnalysisResult) -> str:
        if analysis.intent == "not_interested":
            return ""
        if analysis.urgency == "high":
            due = datetime.now().replace(microsecond=0) + timedelta(days=1)
        elif analysis.intent in {"pricing_request", "interested"}:
            due = datetime.now().replace(microsecond=0) + timedelta(days=2)
        else:
            due = datetime.now().replace(microsecond=0) + timedelta(days=4)
        return due.isoformat(sep=" ")
