from __future__ import annotations

from ..channels.execution import DRY_RUN, MANUAL_ASSIST, OFFICIAL_API
from .preset_schema import CampaignPreset


DEFAULT_PRESETS: dict[str, CampaignPreset] = {
    "b2b_email_outreach": CampaignPreset(
        preset_id="b2b_email_outreach",
        name="B2B Email Outreach",
        description="Деловая email-кампания с AI drafts, мягким тоном и обязательным dry-run перед live send.",
        recommended_channel="email",
        recommended_execution_mode=DRY_RUN,
        ai_tone="business",
        ai_enabled=True,
        suggested_workflow=(
            "Импортируйте рабочие email получателей.",
            "Сгенерируйте AI drafts и проверьте качество.",
            "Сделайте dry-run перед боевой отправкой.",
            "Отправляйте небольшими партиями с safe mode.",
        ),
        recommended_limits={"daily_send_limit": "25", "batch_size": "25", "follow_up_days": "4"},
        follow_up_strategy="Напомнить через 4-5 дней, если нет ответа.",
        warnings=("Избегайте массовых одинаковых писем без персонализации.",),
        ai_prompt_hints="Low spam tone, clear value proposition, no pressure.",
        quick_start_label="Quick Email Outreach",
    ),
    "influencer_collaboration": CampaignPreset(
        preset_id="influencer_collaboration",
        name="Influencer Collaboration",
        description="Короткий human-style outreach для creators через Instagram/X/TikTok Manual Assist.",
        recommended_channel="instagram",
        recommended_execution_mode=MANUAL_ASSIST,
        ai_tone="friendly",
        ai_enabled=True,
        suggested_workflow=(
            "Добавьте профиль creator и заметку о контексте.",
            "Сгенерируйте короткий персональный текст.",
            "Откройте профиль и отправьте вручную через Manual Assist.",
            "Отметьте контакт как manually sent.",
        ),
        recommended_limits={"daily_send_limit": "10", "batch_size": "10", "follow_up_days": "5"},
        follow_up_strategy="Один мягкий follow-up через 5 дней; не давить.",
        warnings=("Instagram/X/TikTok не отправляются автоматически. Используйте Manual Assist.",),
        ai_prompt_hints="Short casual message, high personalization, no hard sell.",
        quick_start_label="Quick Creator Outreach",
    ),
    "telegram_outreach": CampaignPreset(
        preset_id="telegram_outreach",
        name="Telegram Outreach",
        description="Аккуратная Telegram-кампания через Bot API или dry-run, только для доступных chat_id.",
        recommended_channel="telegram",
        recommended_execution_mode=DRY_RUN,
        ai_tone="short",
        ai_enabled=True,
        suggested_workflow=(
            "Проверьте Bot Token и доступный chat_id.",
            "Сделайте dry-run для всех сообщений.",
            "В live режиме отправляйте только owned/safe test chat.",
            "Отслеживайте replies через inbox sync.",
        ),
        recommended_limits={"daily_send_limit": "10", "batch_size": "10", "follow_up_days": "3"},
        follow_up_strategy="Короткий follow-up через 3 дня, только при контексте.",
        warnings=("Telegram Bot может писать только в чаты, где у него есть доступ.",),
        ai_prompt_hints="Concise direct message, no email-style subject.",
        quick_start_label="Quick Telegram Campaign",
    ),
    "partnership_intro": CampaignPreset(
        preset_id="partnership_intro",
        name="Partnership Intro",
        description="Формальное знакомство для партнерств и B2B контактов.",
        recommended_channel="email",
        recommended_execution_mode=DRY_RUN,
        ai_tone="business",
        ai_enabled=True,
        suggested_workflow=(
            "Добавьте компанию, сайт и заметку о гипотезе партнерства.",
            "Сгенерируйте drafts через Research + Writer.",
            "Проверьте, что AI не выдумал факты.",
            "Подтвердите только релевантные письма.",
        ),
        recommended_limits={"daily_send_limit": "20", "batch_size": "20", "follow_up_days": "5"},
        follow_up_strategy="Напомнить через 5 дней с коротким value-first сообщением.",
        warnings=("Проверьте формулировки: партнерские письма особенно чувствительны к fake claims.",),
        ai_prompt_hints="Company-focused, formal, measured personalization.",
        quick_start_label="Quick Partnership Intro",
    ),
    "affiliate_proposal": CampaignPreset(
        preset_id="affiliate_proposal",
        name="Affiliate Proposal",
        description="Дружелюбное value-first предложение без агрессивного продажного тона.",
        recommended_channel="email",
        recommended_execution_mode=DRY_RUN,
        ai_tone="friendly",
        ai_enabled=True,
        suggested_workflow=(
            "Добавьте контекст аудитории или площадки.",
            "Сгенерируйте персональные drafts.",
            "Проверьте spam risk и genericness.",
            "Запланируйте follow-up вместо автоповтора.",
        ),
        recommended_limits={"daily_send_limit": "20", "batch_size": "20", "follow_up_days": "4"},
        follow_up_strategy="Один friendly follow-up через 4 дня.",
        warnings=("Не обещайте доходность, если это не подтверждено в данных.",),
        ai_prompt_hints="Friendly, value-first, transparent affiliate angle.",
        quick_start_label="Quick Affiliate Proposal",
    ),
}


def preset_ids() -> tuple[str, ...]:
    return tuple(DEFAULT_PRESETS.keys())
