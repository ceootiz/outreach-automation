from __future__ import annotations

import json
from typing import Any

from ..db import Database
from ..logger_setup import redact_secret


class ContactTimelineService:
    def __init__(self, db: Database):
        self.db = db

    def record_event(
        self,
        contact_id: int,
        event_type: str,
        *,
        title: str = "",
        details: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        contact = self.db.get_contact(contact_id)
        campaign_id = int(contact["campaign_id"]) if contact else None
        return self.db.execute(
            """
            INSERT INTO contact_events (
                contact_id, campaign_id, event_type, title, details, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                contact_id,
                campaign_id,
                event_type.strip(),
                title.strip() or self.default_title(event_type),
                redact_secret(details),
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

    def events_for_contact(self, contact_id: int, limit: int = 100) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT *
            FROM contact_events
            WHERE contact_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (contact_id, limit),
        )

    def recent_events(self, campaign_id: int, limit: int = 100) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT contact_events.*, contacts.email, contacts.handle, contacts.external_id
            FROM contact_events
            LEFT JOIN contacts ON contacts.id = contact_events.contact_id
            WHERE contact_events.campaign_id = ?
            ORDER BY contact_events.created_at DESC, contact_events.id DESC
            LIMIT ?
            """,
            (campaign_id, limit),
        )

    def record_status_change(self, contact_id: int, from_status: str, to_status: str) -> int:
        return self.record_event(
            contact_id,
            "status_changed",
            title="Статус изменен",
            details=f"{from_status} -> {to_status}",
            metadata={"from": from_status, "to": to_status},
        )

    @staticmethod
    def default_title(event_type: str) -> str:
        titles = {
            "contact_created": "Контакт создан",
            "ai_generated": "AI draft generated",
            "approved": "Письмо подтверждено",
            "dry_run": "Dry-run выполнен",
            "sent": "Отправлено",
            "failed": "Ошибка",
            "reply_added": "Добавлен reply",
            "blacklisted": "Добавлен в blacklist",
            "note_added": "Заметка добавлена",
            "status_changed": "Статус изменен",
        }
        return titles.get(event_type, event_type.replace("_", " ").strip().title())
