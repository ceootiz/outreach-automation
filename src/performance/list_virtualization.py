from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Sequence, TypeVar


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class VirtualPage:
    offset: int
    limit: int
    total: int

    @property
    def page(self) -> int:
        return (self.offset // self.limit) + 1 if self.limit else 1

    @property
    def pages(self) -> int:
        return max(ceil(self.total / self.limit), 1) if self.limit else 1

    @property
    def has_next(self) -> bool:
        return self.offset + self.limit < self.total

    @property
    def has_previous(self) -> bool:
        return self.offset > 0

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "offset": self.offset,
            "limit": self.limit,
            "total": self.total,
            "page": self.page,
            "pages": self.pages,
            "has_next": self.has_next,
            "has_previous": self.has_previous,
        }


def virtual_page(total: int, *, offset: int = 0, limit: int = 250) -> VirtualPage:
    safe_total = max(int(total), 0)
    safe_limit = max(min(int(limit), 1000), 1)
    safe_offset = max(min(int(offset), max(safe_total - 1, 0)), 0) if safe_total else 0
    return VirtualPage(offset=safe_offset, limit=safe_limit, total=safe_total)


def slice_window(items: Sequence[T], *, offset: int = 0, limit: int = 250) -> tuple[list[T], VirtualPage]:
    page = virtual_page(len(items), offset=offset, limit=limit)
    return list(items[page.offset: page.offset + page.limit]), page
