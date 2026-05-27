from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


class AIDraftValidationError(ValueError):
    pass


@dataclass(slots=True)
class EmailDraftInput:
    contact_id: int | None
    email: str
    channel: str = "email"
    name: str = ""
    company: str = ""
    website: str = ""
    social_profile: str = ""
    note: str = ""
    campaign_topic: str = ""
    tone: str = "friendly"
    execution_mode: str = "dry_run"
    execution_notes: str = ""


@dataclass(slots=True)
class EmailDraftResult:
    subject: str
    body: str
    personalization_notes: str = ""
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


def normalize_confidence(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


def parse_email_draft_result(
    raw: str | dict[str, Any],
    *,
    require_subject: bool = True,
) -> EmailDraftResult:
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIDraftValidationError("AI returned invalid JSON.") from exc
    elif isinstance(raw, dict):
        data = raw
    else:
        raise AIDraftValidationError("AI returned an unsupported result type.")

    subject = str(data.get("subject") or "").strip()
    body = str(data.get("body") or "").strip()
    if require_subject and not subject:
        raise AIDraftValidationError("AI draft is missing subject.")
    if not body:
        raise AIDraftValidationError("AI draft is missing body.")

    warnings_value = data.get("warnings") or []
    warnings: list[str]
    if isinstance(warnings_value, list):
        warnings = [str(item).strip() for item in warnings_value if str(item).strip()]
    else:
        warnings = [str(warnings_value).strip()] if str(warnings_value).strip() else []

    subject = subject[:90]
    body = body[:1200]
    return EmailDraftResult(
        subject=subject,
        body=body,
        personalization_notes=str(data.get("personalization_notes") or "").strip(),
        confidence=normalize_confidence(data.get("confidence")),
        warnings=warnings,
    )
