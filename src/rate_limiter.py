from __future__ import annotations

from dataclasses import dataclass

from .config import as_int
from .db import Database


@dataclass(slots=True)
class RateLimitState:
    daily_limit: int
    sent_today: int

    @property
    def remaining(self) -> int:
        return max(self.daily_limit - self.sent_today, 0)

    @property
    def allowed(self) -> bool:
        return self.daily_limit <= 0 or self.sent_today < self.daily_limit


class RateLimiter:
    def __init__(self, db: Database):
        self.db = db

    def state(self, daily_send_limit: int | str) -> RateLimitState:
        limit = as_int(daily_send_limit, 0)
        row = self.db.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM send_logs
            WHERE action IN ('send_email', 'live_send')
              AND status = 'sent'
              AND date(created_at, 'localtime') = date('now', 'localtime')
            """
        )
        return RateLimitState(daily_limit=limit, sent_today=int(row["count"] if row else 0))

    def can_send(self, daily_send_limit: int | str) -> bool:
        return self.state(daily_send_limit).allowed
