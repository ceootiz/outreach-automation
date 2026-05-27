from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..db import Database
from ..logger_setup import redact_secret
from .contact_timeline_service import ContactTimelineService


@dataclass(frozen=True, slots=True)
class DraftQualityScore:
    spam_risk: str
    personalization_quality: str
    confidence: float
    genericness_score: float
    tone_quality: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReplySuggestionResult:
    summary: str
    suggested_next_action: str
    short_reply: str
    formal_reply: str
    friendly_reply: str


class AIQualityService:
    def __init__(self, db: Database, timeline: ContactTimelineService | None = None):
        self.db = db
        self.timeline = timeline or ContactTimelineService(db)

    def score_contact_draft(self, contact_id: int) -> DraftQualityScore:
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError("Contact not found")
        body = str(contact.get("generated_message") or contact.get("base_message") or "")
        subject = str(contact.get("subject") or "")
        personal_signals = [
            contact.get("name"),
            contact.get("company"),
            contact.get("topic"),
            contact.get("website"),
            contact.get("social_profile"),
            contact.get("handle"),
        ]
        personalization_hits = sum(1 for value in personal_signals if str(value or "").strip())
        warnings: list[str] = []

        lower = f"{subject} {body}".lower()
        spam_words = ["срочно", "гарантируем", "бесплатно", "только сегодня", "100%"]
        spam_hits = sum(1 for word in spam_words if word in lower)
        if spam_hits:
            warnings.append("В тексте есть слова, похожие на spam-trigger.")

        if len(body) > 1200:
            warnings.append("Сообщение слишком длинное.")
        if personalization_hits <= 1:
            warnings.append("Мало данных для персонализации.")

        spam_risk = "high" if spam_hits >= 2 else "medium" if spam_hits == 1 else "low"
        personalization_quality = (
            "high" if personalization_hits >= 4 else "medium" if personalization_hits >= 2 else "low"
        )
        genericness_score = max(0.0, min(1.0, 1.0 - (personalization_hits / 5)))
        confidence = float(contact.get("ai_confidence") or 0)
        if not confidence:
            confidence = 0.75 if personalization_quality == "high" else 0.55 if personalization_quality == "medium" else 0.35
        tone_quality = "warning" if spam_risk != "low" or len(body) > 1200 else "ok"
        score = DraftQualityScore(
            spam_risk=spam_risk,
            personalization_quality=personalization_quality,
            confidence=max(0.0, min(1.0, confidence)),
            genericness_score=round(genericness_score, 2),
            tone_quality=tone_quality,
            warnings=warnings,
        )
        self.save_score(contact_id, score)
        return score

    def save_score(self, contact_id: int, score: DraftQualityScore) -> None:
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError("Contact not found")
        self.db.execute(
            """
            INSERT INTO ai_metrics (
                contact_id, campaign_id, spam_risk, personalization_quality,
                confidence, genericness_score, tone_quality, warnings
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contact_id,
                int(contact["campaign_id"]),
                score.spam_risk,
                score.personalization_quality,
                score.confidence,
                score.genericness_score,
                score.tone_quality,
                redact_secret("; ".join(score.warnings)),
            ),
        )
        self.timeline.record_event(
            contact_id,
            "ai_generated",
            title="AI quality scored",
            details=f"spam={score.spam_risk}; personalization={score.personalization_quality}",
            metadata={"confidence": score.confidence, "genericness": score.genericness_score},
        )

    def latest_score(self, contact_id: int) -> dict[str, Any] | None:
        return self.db.fetch_one(
            """
            SELECT *
            FROM ai_metrics
            WHERE contact_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (contact_id,),
        )

    def suggest_replies(self, contact_id: int, reply_text: str) -> ReplySuggestionResult:
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError("Contact not found")
        safe_reply = redact_secret(reply_text.strip())
        interested = any(word in safe_reply.lower() for word in ("интерес", "цен", "подробнее", "да", "ok", "хочу"))
        summary = (
            "Получатель проявляет интерес и просит следующий шаг."
            if interested
            else "Ответ требует ручной оценки перед следующим действием."
        )
        next_action = "Ответить с деталями и предложить короткий созвон." if interested else "Проверить контекст и решить, нужен ли follow-up."
        name = str(contact.get("name") or "").strip()
        greeting = f"{name}, " if name else ""
        return ReplySuggestionResult(
            summary=summary,
            suggested_next_action=next_action,
            short_reply=f"{greeting}спасибо за ответ. Могу прислать короткие детали и следующий шаг.",
            formal_reply=(
                f"{greeting}благодарю за ответ. Подготовлю краткую информацию и предложу удобный формат продолжения."
            ),
            friendly_reply=f"{greeting}спасибо, рад(а) вашему ответу. Давайте аккуратно обсудим детали.",
        )
