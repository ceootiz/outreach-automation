from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CampaignPreset:
    preset_id: str
    name: str
    description: str
    recommended_channel: str
    recommended_execution_mode: str
    ai_tone: str
    ai_enabled: bool
    suggested_workflow: tuple[str, ...]
    recommended_limits: dict[str, str] = field(default_factory=dict)
    follow_up_strategy: str = ""
    warnings: tuple[str, ...] = ()
    ai_prompt_hints: str = ""
    quick_start_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "name": self.name,
            "description": self.description,
            "recommended_channel": self.recommended_channel,
            "recommended_execution_mode": self.recommended_execution_mode,
            "ai_tone": self.ai_tone,
            "ai_enabled": self.ai_enabled,
            "suggested_workflow": list(self.suggested_workflow),
            "recommended_limits": dict(self.recommended_limits),
            "follow_up_strategy": self.follow_up_strategy,
            "warnings": list(self.warnings),
            "ai_prompt_hints": self.ai_prompt_hints,
            "quick_start_label": self.quick_start_label,
        }
