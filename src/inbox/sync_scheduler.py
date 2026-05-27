from __future__ import annotations

from dataclasses import dataclass


SYNC_MODES = {"off", "manual", "background"}


@dataclass(frozen=True, slots=True)
class SyncSchedulerConfig:
    mode: str = "manual"
    interval_minutes: int = 5


def normalize_sync_mode(value: str | None) -> str:
    mode = (value or "manual").strip().lower()
    return mode if mode in SYNC_MODES else "manual"


def normalize_interval(value: int | str | None) -> int:
    try:
        interval = int(value or 5)
    except (TypeError, ValueError):
        interval = 5
    return max(interval, 5)
