from __future__ import annotations

from dataclasses import dataclass


DEFAULT_BRAIN_PROVIDER = "off"
DEFAULT_BRAIN_MODEL = "gpt-4.1-mini"
DUAL_BRAIN_MODE = "dual_brain"
SIMPLE_AI_MODE = "simple"


@dataclass(frozen=True, slots=True)
class BrainConfig:
    provider: str = DEFAULT_BRAIN_PROVIDER
    model: str = DEFAULT_BRAIN_MODEL

    @property
    def enabled(self) -> bool:
        return self.provider.strip().lower() not in {"", "off"}


def normalize_generation_mode(value: str | None) -> str:
    mode = (value or SIMPLE_AI_MODE).strip().lower()
    return DUAL_BRAIN_MODE if mode in {DUAL_BRAIN_MODE, "research_writer"} else SIMPLE_AI_MODE


def normalize_brain_provider(value: str | None) -> str:
    provider = (value or DEFAULT_BRAIN_PROVIDER).strip().lower()
    return provider if provider in {"off", "openai"} else DEFAULT_BRAIN_PROVIDER
