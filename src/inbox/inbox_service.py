from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..db import Database
from ..excel_importer import is_valid_email
from ..intelligence import ConversationService
from ..logger_setup import redact_secret
from ..queue_service import QueueService
from .email_sync import EmailReplyMessage
from .telegram_sync import TelegramReplyMessage


@dataclass(slots=True)
class InboxSyncResult:
    ok: bool = True
    imported_count: int = 0
    skipped_count: int = 0
    latest_checkpoint: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def message(self) -> str:
        if self.ok:
            return f"Синхронизация завершена: импортировано {self.imported_count}, пропущено {self.skipped_count}."
        return "; ".join(self.errors) or "Синхронизация завершилась с ошибкой."


class InboxIngestionService:
    def __init__(
        self,
        db: Database,
        conversations: ConversationService,
        queue: QueueService | None = None,
    ):
        self.db = db
        self.conversations = conversations
        self.queue = queue

    def sync_state(self, channel: str, account_id: str = "") -> dict[str, Any]:
        key = self._sync_key(channel, account_id)
        row = self.db.fetch_one("SELECT * FROM inbox_sync_state WHERE sync_key = ?", (key,))
        if row:
            return row
        self.db.execute(
            """
            INSERT INTO inbox_sync_state (sync_key, channel, account_id)
            VALUES (?, ?, ?)
            """,
            (key, channel, account_id),
        )
        return self.db.fetch_one("SELECT * FROM inbox_sync_state WHERE sync_key = ?", (key,)) or {}

    def save_sync_state(
        self,
        channel: str,
        account_id: str = "",
        *,
        last_synced_uid: str | None = None,
        last_update_id: int | None = None,
        status: str = "ok",
        last_error: str = "",
    ) -> None:
        key = self._sync_key(channel, account_id)
        self.db.execute(
            """
            INSERT INTO inbox_sync_state (
                sync_key, channel, account_id, last_synced_uid, last_update_id,
                last_sync_at, status, last_error
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            ON CONFLICT(sync_key) DO UPDATE SET
                last_synced_uid = COALESCE(excluded.last_synced_uid, inbox_sync_state.last_synced_uid),
                last_update_id = CASE
                    WHEN excluded.last_update_id > 0 THEN excluded.last_update_id
                    ELSE inbox_sync_state.last_update_id
                END,
                last_sync_at = CURRENT_TIMESTAMP,
                status = excluded.status,
                last_error = excluded.last_error,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                key,
                channel,
                account_id,
                last_synced_uid,
                last_update_id or 0,
                status,
                redact_secret(last_error),
            ),
        )

    def ingest_email_messages(
        self,
        messages: list[EmailReplyMessage],
        *,
        campaign_id: int,
        account_id: str,
    ) -> InboxSyncResult:
        result = InboxSyncResult()
        latest_uid = ""
        for message in messages:
            latest_uid = self._max_numeric_checkpoint(latest_uid, message.imap_uid)
            if self._message_exists("email", remote_message_id=message.remote_message_id, imap_uid=message.imap_uid):
                result.skipped_count += 1
                continue
            try:
                contact = self._match_or_create_email_contact(campaign_id, message)
                self._store_ingested_reply(
                    contact,
                    body=message.body,
                    subject=message.subject,
                    sender=message.sender_email,
                    channel="email",
                    remote_message_id=message.remote_message_id,
                    imap_uid=message.imap_uid,
                    metadata={
                        "in_reply_to": message.in_reply_to,
                        "references": message.references,
                        "sender_name": message.sender_name,
                    },
                )
                result.imported_count += 1
            except Exception as exc:
                result.errors.append(redact_secret(exc))
        result.latest_checkpoint = latest_uid
        result.ok = not result.errors
        self.save_sync_state(
            "email",
            account_id,
            last_synced_uid=latest_uid or None,
            status="ok" if result.ok else "failed",
            last_error="; ".join(result.errors),
        )
        return result

    def ingest_telegram_updates(
        self,
        updates: list[TelegramReplyMessage],
        *,
        campaign_id: int,
        account_id: str = "telegram_bot",
    ) -> InboxSyncResult:
        result = InboxSyncResult()
        latest_update = 0
        for update in updates:
            latest_update = max(latest_update, int(update.update_id))
            if self._message_exists("telegram", telegram_update_id=update.update_id):
                result.skipped_count += 1
                continue
            try:
                contact = self._match_or_create_telegram_contact(campaign_id, update)
                self._store_ingested_reply(
                    contact,
                    body=update.text,
                    subject="",
                    sender=update.sender_name or update.chat_id,
                    channel="telegram",
                    remote_message_id=f"telegram:{update.message_id}",
                    telegram_update_id=update.update_id,
                    metadata={"message_id": update.message_id, "chat_id": update.chat_id},
                )
                result.imported_count += 1
            except Exception as exc:
                result.errors.append(redact_secret(exc))
        result.latest_checkpoint = str(latest_update) if latest_update else ""
        result.ok = not result.errors
        self.save_sync_state(
            "telegram",
            account_id,
            last_update_id=latest_update,
            status="ok" if result.ok else "failed",
            last_error="; ".join(result.errors),
        )
        return result

    def _store_ingested_reply(
        self,
        contact: dict[str, Any],
        *,
        body: str,
        subject: str,
        sender: str,
        channel: str,
        remote_message_id: str = "",
        imap_uid: str = "",
        telegram_update_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        contact_id = int(contact["id"])
        thread = self.conversations.get_or_create_thread(contact_id)
        analysis = self.conversations.ai.analyze_reply(contact, body, channel=channel)
        reply_id = self.conversations.replies.add_reply(
            contact_id,
            body,
            reply_status=self._reply_status_from_analysis(analysis.intent),
            ai_summary=analysis.summary,
            suggested_next_action=analysis.recommended_next_action,
        )
        message_id = self.db.execute(
            """
            INSERT INTO conversation_messages (
                thread_id, contact_id, campaign_id, channel, direction,
                message_type, subject, body, status, remote_message_id,
                imap_uid, telegram_update_id, sender, unread_state, metadata_json
            ) VALUES (?, ?, ?, ?, 'inbound', 'reply', ?, ?, 'unread', ?, ?, ?, ?, 'unread', ?)
            """,
            (
                int(thread["id"]),
                contact_id,
                int(contact["campaign_id"]),
                channel,
                redact_secret(subject.strip()),
                redact_secret(body.strip()),
                remote_message_id.strip(),
                imap_uid.strip(),
                telegram_update_id,
                redact_secret(sender.strip()),
                self._metadata_json(dict(metadata or {}, reply_id=reply_id)),
            ),
        )
        self._update_thread_after_ingest(int(thread["id"]), analysis, suggested_lead_status=analysis.lead_status)
        self.db.update_contact(
            contact_id,
            {"unread_state": "unread", "replied_at": datetime.now().replace(microsecond=0).isoformat(sep=" ")},
        )
        if self.queue:
            self.queue.enqueue_ai_summarize_reply(
                int(contact["campaign_id"]),
                contact_id,
                int(thread["id"]),
                channel=channel,
            )
            self.queue.enqueue_ai_stage_suggestion(
                int(contact["campaign_id"]),
                contact_id,
                int(thread["id"]),
                channel=channel,
            )
        self.conversations.timeline.record_event(
            contact_id,
            "reply_added",
            title="Reply synced",
            details=analysis.summary,
            metadata={"message_id": message_id, "reply_id": reply_id, "channel": channel},
        )
        return message_id

    def _update_thread_after_ingest(self, thread_id: int, analysis, *, suggested_lead_status: str) -> None:
        self.db.execute(
            """
            UPDATE conversation_threads
            SET summary = ?, intent = ?, sentiment = ?, urgency = ?,
                recommended_next_action = ?, suggested_lead_status = ?,
                unread_state = 'unread',
                last_activity_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                redact_secret(analysis.summary),
                analysis.intent,
                analysis.sentiment,
                analysis.urgency,
                redact_secret(analysis.recommended_next_action),
                suggested_lead_status,
                thread_id,
            ),
        )

    def _match_or_create_email_contact(self, campaign_id: int, message: EmailReplyMessage) -> dict[str, Any]:
        sender = message.sender_email.strip().lower()
        if sender and is_valid_email(sender):
            existing = self.db.get_contact_by_email(campaign_id, sender)
            if existing:
                return existing
        subject_pattern = self._normalized_subject(message.subject)
        if subject_pattern:
            row = self.db.fetch_one(
                """
                SELECT *
                FROM contacts
                WHERE campaign_id = ?
                  AND channel = 'email'
                  AND lower(subject) = lower(?)
                ORDER BY id DESC
                LIMIT 1
                """,
                (campaign_id, subject_pattern),
            )
            if row:
                return row
        storage_email = sender if sender and is_valid_email(sender) else self._synthetic_orphan_email("email", message.remote_message_id or message.imap_uid)
        contact_id = self.db.add_contact(
            {
                "campaign_id": campaign_id,
                "channel": "email",
                "email": storage_email,
                "name": message.sender_name,
                "subject": message.subject,
                "base_message": "",
                "generated_message": "",
                "status": "new",
                "last_error": "Orphan conversation from IMAP sync. Review manually.",
            }
        )
        return self.db.get_contact(contact_id) or {"id": contact_id, "campaign_id": campaign_id, "channel": "email", "email": storage_email}

    def _match_or_create_telegram_contact(self, campaign_id: int, update: TelegramReplyMessage) -> dict[str, Any]:
        row = self.db.fetch_one(
            """
            SELECT *
            FROM contacts
            WHERE campaign_id = ?
              AND channel = 'telegram'
              AND external_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (campaign_id, update.chat_id),
        )
        if row:
            return row
        contact_id = self.db.add_contact(
            {
                "campaign_id": campaign_id,
                "channel": "telegram",
                "email": self._synthetic_orphan_email("telegram", update.chat_id),
                "external_id": update.chat_id,
                "handle": update.sender_name,
                "name": update.sender_name,
                "base_message": "",
                "generated_message": "",
                "status": "new",
                "last_error": "Orphan conversation from Telegram sync. Review manually.",
            }
        )
        return self.db.get_contact(contact_id) or {
            "id": contact_id,
            "campaign_id": campaign_id,
            "channel": "telegram",
            "external_id": update.chat_id,
        }

    def _message_exists(
        self,
        channel: str,
        *,
        remote_message_id: str = "",
        imap_uid: str = "",
        telegram_update_id: int | None = None,
    ) -> bool:
        if remote_message_id:
            row = self.db.fetch_one(
                """
                SELECT id FROM conversation_messages
                WHERE channel = ? AND remote_message_id = ?
                LIMIT 1
                """,
                (channel, remote_message_id),
            )
            if row:
                return True
        if imap_uid:
            row = self.db.fetch_one(
                """
                SELECT id FROM conversation_messages
                WHERE channel = ? AND imap_uid = ?
                LIMIT 1
                """,
                (channel, imap_uid),
            )
            if row:
                return True
        if telegram_update_id is not None:
            row = self.db.fetch_one(
                """
                SELECT id FROM conversation_messages
                WHERE channel = ? AND telegram_update_id = ?
                LIMIT 1
                """,
                (channel, telegram_update_id),
            )
            return row is not None
        return False

    @staticmethod
    def _sync_key(channel: str, account_id: str = "") -> str:
        return f"{channel.strip().lower()}:{account_id.strip().lower()}"

    @staticmethod
    def _max_numeric_checkpoint(left: str, right: str) -> str:
        try:
            return str(max(int(left or "0"), int(right or "0")))
        except ValueError:
            return right or left

    @staticmethod
    def _normalized_subject(subject: str) -> str:
        value = subject.strip()
        while value.lower().startswith(("re:", "fw:", "fwd:")):
            value = value.split(":", 1)[1].strip()
        return value

    @staticmethod
    def _synthetic_orphan_email(channel: str, value: str) -> str:
        import hashlib

        digest = hashlib.sha1(f"{channel}:{value}".encode("utf-8")).hexdigest()[:14]
        return f"{channel}-orphan-{digest}@channel.local"

    @staticmethod
    def _reply_status_from_analysis(intent: str) -> str:
        if intent == "not_interested":
            return "not_interested"
        if intent in {"pricing_request", "interested"}:
            return "interested"
        if intent == "maybe_later":
            return "maybe_later"
        return "no_response"

    @staticmethod
    def _metadata_json(metadata: dict[str, Any]) -> str:
        import json

        return json.dumps(metadata, ensure_ascii=False)
