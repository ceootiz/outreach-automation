from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


HIGH_PRIORITY = "High Priority"
MEDIUM_PRIORITY = "Medium Priority"
LOW_PRIORITY = "Low Priority"


@dataclass(frozen=True, slots=True)
class LeadPriority:
    score: int
    label: str
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "label": self.label, "reasons": list(self.reasons)}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


class LeadPrioritizer:
    def score_contact(self, contact: dict[str, Any]) -> LeadPriority:
        score = 35
        reasons: list[str] = []

        confidence = _float(contact.get("ai_confidence"), 0.0)
        research_confidence = _float(contact.get("research_confidence"), 0.0)
        enrichment_confidence = _float(contact.get("enrichment_confidence"), 0.0)

        if confidence >= 0.75:
            score += 18
            reasons.append("AI confidence high")
        elif confidence >= 0.45:
            score += 10
            reasons.append("AI confidence usable")
        elif int(contact.get("ai_generated") or 0):
            score -= 8
            reasons.append("AI confidence weak")

        if research_confidence >= 0.65:
            score += 12
            reasons.append("research brief strong")
        elif _text(contact.get("research_status")):
            score += 4
            reasons.append("research brief available")

        if enrichment_confidence >= 0.65 or _text(contact.get("enrichment_status")) == "success":
            score += 12
            reasons.append("public enrichment available")
        elif _text(contact.get("website")) or _text(contact.get("social_profile")):
            score += 6
            reasons.append("profile/site data present")

        if _text(contact.get("company")):
            score += 7
            reasons.append("company known")
        if _text(contact.get("name")):
            score += 5
            reasons.append("name known")
        if _text(contact.get("note")) or _text(contact.get("topic")):
            score += 6
            reasons.append("operator note/topic present")

        lead_status = _text(contact.get("lead_status")) or "New"
        if lead_status in {"Warm", "Interested", "Negotiating"}:
            score += 16
            reasons.append(f"lead stage {lead_status}")
        elif lead_status in {"Lost", "Closed"}:
            score -= 30
            reasons.append(f"lead stage {lead_status}")

        channel = _text(contact.get("channel")) or "email"
        if channel in {"telegram", "email"}:
            score += 4
            reasons.append(f"{channel} execution is clearer")
        elif channel in {"instagram", "tiktok", "x"}:
            score -= 3
            reasons.append(f"{channel} requires manual assist")

        warnings = " ".join(
            _text(contact.get(key))
            for key in ("ai_warnings", "research_warnings", "enrichment_warnings", "last_error")
        ).lower()
        if warnings:
            score -= 12
            reasons.append("warnings require review")
        if "spam" in warnings or "aggressive" in warnings:
            score -= 10
            reasons.append("spam/aggressive warning")

        if _text(contact.get("generated_message")):
            score += 6
            reasons.append("draft ready")

        score = max(0, min(100, score))
        if score >= 75:
            label = HIGH_PRIORITY
        elif score >= 45:
            label = MEDIUM_PRIORITY
        else:
            label = LOW_PRIORITY
        return LeadPriority(score=score, label=label, reasons=reasons[:6])
