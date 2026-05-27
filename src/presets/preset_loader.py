from __future__ import annotations

from .preset_registry import DEFAULT_PRESETS
from .preset_schema import CampaignPreset


def load_presets() -> list[CampaignPreset]:
    return list(DEFAULT_PRESETS.values())


def get_preset(preset_id: str) -> CampaignPreset:
    normalized = (preset_id or "").strip().lower()
    if normalized not in DEFAULT_PRESETS:
        raise ValueError(f"Unknown campaign preset: {preset_id}")
    return DEFAULT_PRESETS[normalized]
