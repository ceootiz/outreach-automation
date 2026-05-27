from __future__ import annotations

from typing import Any


def like_pattern(query: str) -> str:
    return f"%{(query or '').strip()}%"


def compact_text(*values: Any, limit: int = 220) -> str:
    text = " • ".join(str(value).strip() for value in values if str(value or "").strip())
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "…"


def title_from_contact(contact: dict[str, Any]) -> str:
    return (
        str(contact.get("company") or "").strip()
        or str(contact.get("name") or "").strip()
        or str(contact.get("handle") or "").strip()
        or str(contact.get("external_id") or "").strip()
        or str(contact.get("email") or "").strip()
        or "Contact"
    )
