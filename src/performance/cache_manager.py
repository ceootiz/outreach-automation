from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(slots=True)
class CacheEntry(Generic[T]):
    value: T
    created_at: float
    ttl_seconds: float
    version: str = ""

    def expired(self, now: float | None = None) -> bool:
        return (now if now is not None else time.monotonic()) - self.created_at > self.ttl_seconds


class CacheManager:
    def __init__(self, default_ttl_seconds: float = 60.0, max_items: int = 256):
        self.default_ttl_seconds = max(float(default_ttl_seconds), 0.1)
        self.max_items = max(int(max_items), 1)
        self._entries: dict[str, CacheEntry[object]] = {}

    def get(self, key: str, *, version: str = "") -> object | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if version and entry.version != version:
            self._entries.pop(key, None)
            return None
        if entry.expired():
            self._entries.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: object, *, ttl_seconds: float | None = None, version: str = "") -> object:
        if len(self._entries) >= self.max_items and key not in self._entries:
            oldest_key = min(self._entries, key=lambda item: self._entries[item].created_at)
            self._entries.pop(oldest_key, None)
        self._entries[key] = CacheEntry(
            value=value,
            created_at=time.monotonic(),
            ttl_seconds=float(ttl_seconds or self.default_ttl_seconds),
            version=version,
        )
        return value

    def invalidate(self, prefix: str = "") -> None:
        if not prefix:
            self._entries.clear()
            return
        for key in list(self._entries):
            if key.startswith(prefix):
                self._entries.pop(key, None)

    def stats(self) -> dict[str, int]:
        return {"items": len(self._entries), "max_items": self.max_items}
