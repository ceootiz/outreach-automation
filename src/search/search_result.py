from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SearchResult:
    result_type: str
    title: str
    snippet: str
    channel: str = ""
    campaign_id: int | None = None
    contact_id: int | None = None
    object_id: int | None = None
    action: str = "open"

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_type": self.result_type,
            "title": self.title,
            "snippet": self.snippet,
            "channel": self.channel,
            "campaign_id": self.campaign_id,
            "contact_id": self.contact_id,
            "object_id": self.object_id,
            "action": self.action,
        }
