from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TypeVar


T = TypeVar("T")


def chunked(items: Iterable[T], chunk_size: int = 500) -> Iterator[list[T]]:
    chunk: list[T] = []
    safe_size = max(int(chunk_size), 1)
    for item in items:
        chunk.append(item)
        if len(chunk) >= safe_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def preload_window(total: int, current_offset: int, *, page_size: int = 250, radius: int = 1) -> list[tuple[int, int]]:
    safe_page = max(int(page_size), 1)
    current_page = max(int(current_offset), 0) // safe_page
    start_page = max(current_page - max(int(radius), 0), 0)
    end_page = min(current_page + max(int(radius), 0), max((max(int(total), 0) - 1) // safe_page, 0))
    return [(page * safe_page, safe_page) for page in range(start_page, end_page + 1)]
