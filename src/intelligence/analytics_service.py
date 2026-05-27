from __future__ import annotations

from typing import Any

from ..db import Database
from .contact_timeline_service import ContactTimelineService
from .metrics_service import MetricsService


CAMPAIGN_PRESETS: dict[str, dict[str, str]] = {
    "b2b_email_outreach": {
        "name": "B2B Email Outreach",
        "tone": "Деловой",
        "length": "Короткое письмо до 1200 символов",
        "prompt_hints": "Уважительно, без fake familiarity, один clear ask.",
        "follow_up": "Через 2-3 дня, только после ручного подтверждения.",
    },
    "telegram_outreach": {
        "name": "Telegram Outreach",
        "tone": "Короткий",
        "length": "1-3 коротких абзаца",
        "prompt_hints": "Прямо, дружелюбно, без давления.",
        "follow_up": "Только manual reminder, без автоотправки.",
    },
    "influencer_collaboration": {
        "name": "Influencer Collaboration",
        "tone": "Дружелюбный",
        "length": "Коротко и конкретно",
        "prompt_hints": "Указать формат сотрудничества, не выдумывать факты.",
        "follow_up": "Напомнить один раз после ручной проверки.",
    },
    "affiliate_proposal": {
        "name": "Affiliate Proposal",
        "tone": "Премиальный",
        "length": "Кратко, с понятной выгодой",
        "prompt_hints": "Без обещаний дохода и агрессивных claims.",
        "follow_up": "Уточнить интерес и формат.",
    },
    "partnership_intro": {
        "name": "Partnership Intro",
        "tone": "Деловой",
        "length": "Короткое intro",
        "prompt_hints": "Сфокусироваться на релевантности и следующем шаге.",
        "follow_up": "Предложить короткий созвон или обмен деталями.",
    },
}


class AnalyticsService:
    def __init__(
        self,
        db: Database,
        metrics: MetricsService | None = None,
        timeline: ContactTimelineService | None = None,
    ):
        self.db = db
        self.metrics = metrics or MetricsService(db)
        self.timeline = timeline or ContactTimelineService(db)

    def campaign_dashboard(self, campaign_id: int) -> dict[str, Any]:
        campaign = self.db.fetch_one("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
        return {
            "campaign": campaign or {},
            "metrics": self.metrics.campaign_metrics(campaign_id),
            "recent_events": self.timeline.recent_events(campaign_id, limit=20),
            "presets": self.list_presets(),
        }

    def list_presets(self) -> list[dict[str, str]]:
        return [dict({"id": preset_id}, **preset) for preset_id, preset in CAMPAIGN_PRESETS.items()]

    def preset(self, preset_id: str) -> dict[str, str]:
        if preset_id not in CAMPAIGN_PRESETS:
            raise ValueError("Unknown campaign preset")
        return dict({"id": preset_id}, **CAMPAIGN_PRESETS[preset_id])
