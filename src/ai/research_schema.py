from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


RECIPIENT_TYPES = {"creator", "brand", "company", "agency", "unknown"}
PERSONALIZATION_STRENGTHS = {"low", "medium", "high"}
SOURCE_BASIS = {"row_data", "domain_heuristic", "user_note", "website_url_only", "website_public_data"}


class ResearchValidationError(ValueError):
    pass


@dataclass(slots=True)
class RecipientResearchInput:
    contact_id: int | None
    email: str
    email_domain: str = ""
    name: str = ""
    company: str = ""
    website: str = ""
    social_profile: str = ""
    channel: str = "email"
    note: str = ""
    campaign_topic: str = ""
    enrichment_result: dict[str, Any] | None = None


@dataclass(slots=True)
class RecipientBrief:
    recipient_type: str = "unknown"
    likely_context: str = ""
    positioning_angle: str = ""
    message_hooks: list[str] = field(default_factory=list)
    do_not_claim: list[str] = field(default_factory=list)
    personalization_strength: str = "low"
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    source_basis: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipient_type": self.recipient_type,
            "likely_context": self.likely_context,
            "positioning_angle": self.positioning_angle,
            "message_hooks": self.message_hooks,
            "do_not_claim": self.do_not_claim,
            "personalization_strength": self.personalization_strength,
            "confidence": self.confidence,
            "warnings": self.warnings,
            "source_basis": self.source_basis,
        }


def normalize_confidence(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def parse_recipient_brief(raw: str | dict[str, Any]) -> RecipientBrief:
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ResearchValidationError("Research Brain returned invalid JSON.") from exc
    elif isinstance(raw, dict):
        data = raw
    else:
        raise ResearchValidationError("Research Brain returned unsupported data.")

    recipient_type = str(data.get("recipient_type") or "unknown").strip().lower()
    if recipient_type not in RECIPIENT_TYPES:
        recipient_type = "unknown"
    strength = str(data.get("personalization_strength") or "low").strip().lower()
    if strength not in PERSONALIZATION_STRENGTHS:
        strength = "low"
    source_basis = [
        item for item in _string_list(data.get("source_basis")) if item in SOURCE_BASIS
    ] or ["row_data"]

    warnings = _string_list(data.get("warnings"))
    if strength == "low" and not warnings:
        warnings.append("Недостаточно данных для уверенной персонализации.")

    return RecipientBrief(
        recipient_type=recipient_type,
        likely_context=str(data.get("likely_context") or "").strip()[:800],
        positioning_angle=str(data.get("positioning_angle") or "").strip()[:500],
        message_hooks=_string_list(data.get("message_hooks"))[:5],
        do_not_claim=_string_list(data.get("do_not_claim"))[:8],
        personalization_strength=strength,
        confidence=normalize_confidence(data.get("confidence")),
        warnings=warnings[:8],
        source_basis=source_basis[:6],
    )
