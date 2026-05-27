from __future__ import annotations

from .db import Database


class BlacklistService:
    def __init__(self, db: Database):
        self.db = db

    def add(self, email: str, reason: str = "") -> None:
        self.db.add_blacklist(email.strip().lower(), reason)

    def is_blocked(self, email: str) -> bool:
        return self.db.is_blacklisted(email.strip().lower())

    def blacklist_contact(self, contact_id: int, reason: str = "Manual blacklist") -> None:
        contact = self.db.get_contact(contact_id)
        if not contact:
            return
        self.add(contact["email"], reason)
        self.db.update_contact(contact_id, {"status": "blacklisted", "last_error": reason})
