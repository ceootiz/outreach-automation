from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RenderBudget:
    total_items: int
    visible_items: int
    batch_size: int
    virtualized: bool

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "total_items": self.total_items,
            "visible_items": self.visible_items,
            "batch_size": self.batch_size,
            "virtualized": self.virtualized,
        }


def recommended_batch_size(total_items: int, *, target_frame_ms: int = 16) -> RenderBudget:
    total = max(int(total_items), 0)
    if total >= 25_000:
        batch = 200
    elif total >= 10_000:
        batch = 300
    elif total >= 5_000:
        batch = 500
    else:
        batch = 1000
    if target_frame_ms <= 12:
        batch = max(batch // 2, 100)
    visible = min(total, batch)
    return RenderBudget(total_items=total, visible_items=visible, batch_size=batch, virtualized=total > batch)
