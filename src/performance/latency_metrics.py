from __future__ import annotations

import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator


@dataclass(frozen=True, slots=True)
class LatencyMetric:
    name: str
    average_ms: float
    p95_ms: float
    slowest_ms: float
    count: int

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "name": self.name,
            "average_ms": self.average_ms,
            "p95_ms": self.p95_ms,
            "slowest_ms": self.slowest_ms,
            "count": self.count,
        }


@dataclass(slots=True)
class LatencyMetrics:
    samples: dict[str, list[float]] = field(default_factory=dict)

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.add(name, (time.perf_counter() - start) * 1000)

    def add(self, name: str, value_ms: float) -> None:
        self.samples.setdefault(name, []).append(float(value_ms))

    def summary(self, name: str) -> LatencyMetric:
        values = self.samples.get(name, [])
        if not values:
            return LatencyMetric(name=name, average_ms=0.0, p95_ms=0.0, slowest_ms=0.0, count=0)
        ordered = sorted(values)
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        return LatencyMetric(
            name=name,
            average_ms=round(statistics.mean(values), 2),
            p95_ms=round(p95, 2),
            slowest_ms=round(max(values), 2),
            count=len(values),
        )

    def all_summaries(self) -> list[dict[str, float | int | str]]:
        return [self.summary(name).to_dict() for name in sorted(self.samples)]
