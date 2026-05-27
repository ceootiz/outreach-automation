from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OperatorSessionMetrics:
    reviewed_leads: int = 0
    copied_messages: int = 0
    manually_sent: int = 0
    skipped_leads: int = 0
    replies_received: int = 0
    ai_acceptance_rate: float = 0.0
    avg_review_time_seconds: float = 0.0
    followup_conversion: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewed_leads": self.reviewed_leads,
            "copied_messages": self.copied_messages,
            "manually_sent": self.manually_sent,
            "skipped_leads": self.skipped_leads,
            "replies_received": self.replies_received,
            "ai_acceptance_rate": self.ai_acceptance_rate,
            "avg_review_time_seconds": self.avg_review_time_seconds,
            "followup_conversion": self.followup_conversion,
        }
