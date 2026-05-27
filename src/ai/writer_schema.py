from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .research_schema import RecipientBrief


class WriterValidationError(ValueError):
    pass


@dataclass(slots=True)
class DraftWritingInput:
    contact_id: int | None
    email: str
    channel: str
    campaign_topic: str
    tone: str
    recipient_brief: RecipientBrief
    name: str = ""
    company: str = ""
    website: str = ""
    social_profile: str = ""
    note: str = ""
    execution_mode: str = "dry_run"
    execution_notes: str = ""


@dataclass(slots=True)
class WriterDraft:
    subject: str = ""
    body: str = ""
    why_this_angle: str = ""
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0


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


def parse_writer_draft(raw: str | dict[str, Any], *, require_subject: bool) -> WriterDraft:
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WriterValidationError("Writer Brain returned invalid JSON.") from exc
    elif isinstance(raw, dict):
        data = raw
    else:
        raise WriterValidationError("Writer Brain returned unsupported data.")

    subject = str(data.get("subject") or "").strip()[:90]
    body = str(data.get("body") or "").strip()[:1200]
    if require_subject and not subject:
        raise WriterValidationError("Writer Brain draft is missing subject.")
    if not body:
        raise WriterValidationError("Writer Brain draft is missing body.")
    if not require_subject:
        subject = ""

    return WriterDraft(
        subject=subject,
        body=body,
        why_this_angle=str(data.get("why_this_angle") or "").strip()[:500],
        warnings=_string_list(data.get("warnings"))[:8],
        confidence=normalize_confidence(data.get("confidence")),
    )
