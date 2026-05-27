from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class ChannelExecutionResult:
    status: str
    channel: str
    mode: str
    recipient: str = ""
    action_taken: str = ""
    manual_required: bool = False
    warnings: list[str] = field(default_factory=list)
    risk_level: str = "medium"
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "channel": self.channel,
            "mode": self.mode,
            "recipient": self.recipient,
            "action_taken": self.action_taken,
            "manual_required": self.manual_required,
            "warnings": list(self.warnings),
            "risk_level": self.risk_level,
            "timestamp": self.timestamp,
        }
