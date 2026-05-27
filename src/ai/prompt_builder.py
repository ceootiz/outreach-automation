from __future__ import annotations

import json

from .result_schema import EmailDraftInput


TONE_LABELS = {
    "friendly": "дружелюбный",
    "business": "деловой",
    "short": "короткий",
    "premium": "премиальный",
}


CHANNEL_CONTEXT = {
    "email": {
        "label": "Email",
        "format": "Нужны subject и body. Subject до 90 символов, body до 1200 символов.",
        "style": "короткое аккуратное письмо",
    },
    "x": {
        "label": "X / Twitter",
        "format": "Subject должен быть пустой строкой. Body — короткое DM-сообщение без давления.",
        "style": "очень короткий DM-style текст",
    },
    "instagram": {
        "label": "Instagram",
        "format": "Subject должен быть пустой строкой. Body — короткое дружелюбное сообщение.",
        "style": "casual direct message",
    },
    "telegram": {
        "label": "Telegram",
        "format": "Subject должен быть пустой строкой. Body — прямое и лаконичное сообщение.",
        "style": "короткое сообщение в чат",
    },
    "vk": {
        "label": "VK",
        "format": "Subject должен быть пустой строкой. Body — короткое social outreach сообщение.",
        "style": "лаконичное личное сообщение",
    },
    "tiktok": {
        "label": "TikTok",
        "format": "Subject должен быть пустой строкой. Body — очень короткое outreach сообщение.",
        "style": "очень короткое сообщение",
    },
}


def tone_to_ru(tone: str) -> str:
    return TONE_LABELS.get((tone or "").strip().lower(), "дружелюбный")


def build_email_draft_messages(input_data: EmailDraftInput) -> list[dict[str, str]]:
    channel_id = (input_data.channel or "email").strip().lower()
    channel_context = CHANNEL_CONTEXT.get(channel_id, CHANNEL_CONTEXT["email"])
    recipient_payload = {
        "email": input_data.email,
        "channel": channel_id,
        "name": input_data.name,
        "company": input_data.company,
        "website": input_data.website,
        "social_profile": input_data.social_profile,
        "note": input_data.note,
        "email_domain": input_data.email.split("@", 1)[1] if "@" in input_data.email else "",
    }
    user_payload = {
        "campaign_topic": input_data.campaign_topic,
        "tone": tone_to_ru(input_data.tone),
        "channel": channel_context,
        "execution": {
            "mode": input_data.execution_mode or "dry_run",
            "notes": input_data.execution_notes,
            "rules": (
                "AI creates drafts only. Manual Assist means the operator copies and sends manually. "
                "Official API still requires human confirmation. Never imply hidden automation."
            ),
        },
        "recipient": recipient_payload,
    }
    system = (
        "Ты помогаешь оператору подготовить безопасный черновик сообщения для выбранного канала. "
        "Ты НЕ отправляешь сообщения и НЕ просишь обойти антиспам, капчи или правила платформ. "
        "Пиши на русском по умолчанию, если тема явно не на английском. "
        "Не выдумывай факты о получателе, компании, сайте или соцпрофиле. "
        "Используй только явно переданные данные. Если данных мало, пиши нейтрально и добавь warning. "
        "Не говори, что изучил сайт/профиль, если во входных данных нет конкретных фактов. "
        "Не используй агрессивный рекламный тон, fake familiarity или обещания без основания. "
        "Не создавай ощущение массового спама, давления, срочности или скрытой автоматизации. "
        "Учитывай execution mode: для Manual Assist текст должен звучать естественно для ручной отправки; "
        "для каналов X/Instagram/TikTok/VK используй короткий human-style outreach без темы письма. "
        "Для social channels body должен быть value-first, friendly but not cringe, без давления, без fake familiarity, "
        "без фраз 'я изучил ваш профиль' или 'видел ваши посты', если таких фактов нет во входных данных. "
        "Черновик должен быть спокойным, коротким, честным и легко редактируемым оператором. "
        f"Канал: {channel_context['label']}. Формат: {channel_context['format']} "
        "Верни только валидный JSON без Markdown."
    )
    user = (
        "Сгенерируй индивидуальный черновик по данным ниже.\n"
        f"Стиль канала: {channel_context['style']}.\n"
        "Формат ответа строго:\n"
        "{\n"
        '  "subject": "...",\n'
        '  "body": "...",\n'
        '  "personalization_notes": "...",\n'
        '  "confidence": 0.0,\n'
        '  "warnings": []\n'
        "}\n\n"
        f"Входные данные:\n{json.dumps(user_payload, ensure_ascii=False, indent=2)}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
