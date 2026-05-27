from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .config import DEFAULT_SETTINGS
from .logger_setup import redact_secret


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL DEFAULT 'active'
                );

                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER NOT NULL,
                    channel TEXT NOT NULL DEFAULT 'email',
                    email TEXT NOT NULL,
                    handle TEXT DEFAULT '',
                    profile_url TEXT DEFAULT '',
                    external_id TEXT DEFAULT '',
                    name TEXT DEFAULT '',
                    company TEXT DEFAULT '',
                    topic TEXT DEFAULT '',
                    website TEXT DEFAULT '',
                    social_profile TEXT DEFAULT '',
                    subject TEXT DEFAULT '',
                    base_message TEXT DEFAULT '',
                    generated_message TEXT DEFAULT '',
                    ai_generated INTEGER NOT NULL DEFAULT 0,
                    ai_confidence REAL,
                    ai_notes TEXT DEFAULT '',
                    ai_warnings TEXT DEFAULT '',
                    research_brief_json TEXT DEFAULT '',
                    research_confidence REAL,
                    research_warnings TEXT DEFAULT '',
                    research_status TEXT DEFAULT '',
                    enrichment_result_json TEXT DEFAULT '',
                    enrichment_status TEXT DEFAULT 'not_checked',
                    enrichment_source_urls TEXT DEFAULT '',
                    enrichment_warnings TEXT DEFAULT '',
                    enrichment_confidence REAL,
                    status TEXT NOT NULL DEFAULT 'new',
                    last_error TEXT DEFAULT '',
                    sent_at TEXT,
                    replied_at TEXT,
                    follow_up_due_at TEXT,
                    lead_status TEXT NOT NULL DEFAULT 'New',
                    unread_state TEXT NOT NULL DEFAULT 'read',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
                    UNIQUE (campaign_id, email)
                );

                CREATE TABLE IF NOT EXISTS templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    subject_template TEXT NOT NULL DEFAULT '',
                    body_template TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS gmail_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    is_active INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_check_status TEXT DEFAULT '',
                    last_check_at TEXT,
                    last_error TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS blacklist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    reason TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS send_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER,
                    campaign_id INTEGER,
                    channel TEXT NOT NULL DEFAULT 'email',
                    platform_recipient TEXT DEFAULT '',
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS job_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER,
                    contact_id INTEGER,
                    job_group_id TEXT,
                    channel TEXT NOT NULL DEFAULT 'email',
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    priority INTEGER NOT NULL DEFAULT 100,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    progress_percent INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS contact_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL,
                    campaign_id INTEGER,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    details TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL,
                    campaign_id INTEGER,
                    reply_text TEXT NOT NULL,
                    reply_status TEXT NOT NULL DEFAULT 'no_response',
                    ai_summary TEXT DEFAULT '',
                    suggested_next_action TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS ai_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL,
                    campaign_id INTEGER,
                    spam_risk TEXT NOT NULL DEFAULT 'low',
                    personalization_quality TEXT NOT NULL DEFAULT 'low',
                    confidence REAL NOT NULL DEFAULT 0,
                    genericness_score REAL NOT NULL DEFAULT 0,
                    tone_quality TEXT NOT NULL DEFAULT 'ok',
                    warnings TEXT DEFAULT '',
                    research_model TEXT DEFAULT '',
                    writer_model TEXT DEFAULT '',
                    research_confidence REAL,
                    writer_confidence REAL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS campaign_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER NOT NULL,
                    metric_key TEXT NOT NULL,
                    metric_value TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
                    UNIQUE (campaign_id, metric_key)
                );

                CREATE TABLE IF NOT EXISTS followups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL,
                    campaign_id INTEGER,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    note TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS conversation_threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER,
                    contact_id INTEGER NOT NULL UNIQUE,
                    channel TEXT NOT NULL DEFAULT 'email',
                    lead_status TEXT NOT NULL DEFAULT 'New',
                    unread_state TEXT NOT NULL DEFAULT 'read',
                    summary TEXT DEFAULT '',
                    intent TEXT DEFAULT '',
                    sentiment TEXT DEFAULT '',
                    urgency TEXT DEFAULT '',
                    recommended_next_action TEXT DEFAULT '',
                    suggested_lead_status TEXT DEFAULT '',
                    last_activity_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL,
                    contact_id INTEGER NOT NULL,
                    campaign_id INTEGER,
                    channel TEXT NOT NULL DEFAULT 'email',
                    direction TEXT NOT NULL DEFAULT 'inbound',
                    message_type TEXT NOT NULL DEFAULT 'reply',
                    subject TEXT DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'new',
                    remote_message_id TEXT DEFAULT '',
                    imap_uid TEXT DEFAULT '',
                    telegram_update_id INTEGER,
                    sender TEXT DEFAULT '',
                    unread_state TEXT NOT NULL DEFAULT 'unread',
                    metadata_json TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (thread_id) REFERENCES conversation_threads(id) ON DELETE CASCADE,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS ai_reply_suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL,
                    contact_id INTEGER NOT NULL,
                    campaign_id INTEGER,
                    reply_id INTEGER,
                    channel TEXT NOT NULL DEFAULT 'email',
                    summary TEXT DEFAULT '',
                    intent TEXT DEFAULT '',
                    sentiment TEXT DEFAULT '',
                    urgency TEXT DEFAULT '',
                    recommended_next_action TEXT DEFAULT '',
                    short_reply TEXT DEFAULT '',
                    friendly_reply TEXT DEFAULT '',
                    formal_reply TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (thread_id) REFERENCES conversation_threads(id) ON DELETE CASCADE,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL,
                    FOREIGN KEY (reply_id) REFERENCES replies(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS followup_suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL,
                    contact_id INTEGER NOT NULL,
                    campaign_id INTEGER,
                    suggested_due_at TEXT DEFAULT '',
                    tone TEXT DEFAULT '',
                    reason TEXT DEFAULT '',
                    recommendation TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'suggested',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (thread_id) REFERENCES conversation_threads(id) ON DELETE CASCADE,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS inbox_sync_state (
                    sync_key TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    account_id TEXT NOT NULL DEFAULT '',
                    last_synced_uid TEXT DEFAULT '',
                    last_update_id INTEGER NOT NULL DEFAULT 0,
                    last_sync_at TEXT,
                    status TEXT NOT NULL DEFAULT 'never',
                    last_error TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS enrichment_cache (
                    cache_key TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    domain TEXT DEFAULT '',
                    fetched_at TEXT NOT NULL,
                    expires_at TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'failed',
                    title TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    public_summary TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS operator_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'precision',
                    current_contact_id INTEGER,
                    review_index INTEGER NOT NULL DEFAULT 0,
                    filters_json TEXT NOT NULL DEFAULT '{}',
                    draft_variant TEXT DEFAULT '',
                    unsaved_draft TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
                    FOREIGN KEY (current_contact_id) REFERENCES contacts(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS operator_session_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    contact_id INTEGER,
                    action TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES operator_sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS ai_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL,
                    campaign_id INTEGER,
                    session_id INTEGER,
                    rating TEXT NOT NULL,
                    note TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL,
                    FOREIGN KEY (session_id) REFERENCES operator_sessions(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS import_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER,
                    source_file TEXT NOT NULL,
                    row_number INTEGER,
                    email TEXT DEFAULT '',
                    error TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_contacts_campaign_status
                    ON contacts(campaign_id, status);
                CREATE INDEX IF NOT EXISTS idx_send_logs_created_at
                    ON send_logs(created_at);
                CREATE INDEX IF NOT EXISTS idx_job_queue_status_priority
                    ON job_queue(status, priority, created_at);
                CREATE INDEX IF NOT EXISTS idx_gmail_profiles_active
                    ON gmail_profiles(is_active, updated_at);
                CREATE INDEX IF NOT EXISTS idx_contact_events_contact_created
                    ON contact_events(contact_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_replies_campaign_status
                    ON replies(campaign_id, reply_status);
                CREATE INDEX IF NOT EXISTS idx_ai_metrics_contact
                    ON ai_metrics(contact_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_followups_due
                    ON followups(status, due_at);
                CREATE INDEX IF NOT EXISTS idx_conversation_threads_campaign_activity
                    ON conversation_threads(campaign_id, last_activity_at);
                CREATE INDEX IF NOT EXISTS idx_conversation_threads_lead_unread
                    ON conversation_threads(lead_status, unread_state);
                CREATE INDEX IF NOT EXISTS idx_conversation_messages_thread_created
                    ON conversation_messages(thread_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_conversation_messages_remote
                    ON conversation_messages(channel, remote_message_id);
                CREATE INDEX IF NOT EXISTS idx_conversation_messages_imap_uid
                    ON conversation_messages(channel, imap_uid);
                CREATE INDEX IF NOT EXISTS idx_conversation_messages_telegram_update
                    ON conversation_messages(channel, telegram_update_id);
                CREATE INDEX IF NOT EXISTS idx_ai_reply_suggestions_contact_created
                    ON ai_reply_suggestions(contact_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_followup_suggestions_status_due
                    ON followup_suggestions(status, suggested_due_at);
                CREATE INDEX IF NOT EXISTS idx_inbox_sync_state_channel_account
                    ON inbox_sync_state(channel, account_id);
                CREATE INDEX IF NOT EXISTS idx_enrichment_cache_domain
                    ON enrichment_cache(domain, fetched_at);
                CREATE INDEX IF NOT EXISTS idx_operator_sessions_campaign
                    ON operator_sessions(campaign_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_operator_session_events_session_action
                    ON operator_session_events(session_id, action, created_at);
                CREATE INDEX IF NOT EXISTS idx_ai_feedback_contact
                    ON ai_feedback(contact_id, created_at);
                """
            )

            self._ensure_contact_columns(conn)
            self._ensure_auxiliary_columns(conn)

            if not conn.execute("SELECT id FROM campaigns LIMIT 1").fetchone():
                conn.execute("INSERT INTO campaigns (name) VALUES (?)", ("Default Campaign",))

            for key, value in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, value),
                )

            conn.execute(
                """
                INSERT OR IGNORE INTO templates (name, subject_template, body_template)
                VALUES (?, ?, ?)
                """,
                (
                    "Default",
                    "Quick idea for {{company}}",
                    "Hi {{name}},\n\n{{base_message}}\n\nBest regards,",
                ),
            )

    @staticmethod
    def _ensure_contact_columns(conn: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(contacts)").fetchall()
        }
        columns = {
            "channel": "TEXT NOT NULL DEFAULT 'email'",
            "handle": "TEXT DEFAULT ''",
            "profile_url": "TEXT DEFAULT ''",
            "external_id": "TEXT DEFAULT ''",
            "website": "TEXT DEFAULT ''",
            "social_profile": "TEXT DEFAULT ''",
            "ai_generated": "INTEGER NOT NULL DEFAULT 0",
            "ai_confidence": "REAL",
            "ai_notes": "TEXT DEFAULT ''",
            "ai_warnings": "TEXT DEFAULT ''",
            "research_brief_json": "TEXT DEFAULT ''",
            "research_confidence": "REAL",
            "research_warnings": "TEXT DEFAULT ''",
            "research_status": "TEXT DEFAULT ''",
            "enrichment_result_json": "TEXT DEFAULT ''",
            "enrichment_status": "TEXT DEFAULT 'not_checked'",
            "enrichment_source_urls": "TEXT DEFAULT ''",
            "enrichment_warnings": "TEXT DEFAULT ''",
            "enrichment_confidence": "REAL",
            "lead_status": "TEXT NOT NULL DEFAULT 'New'",
            "unread_state": "TEXT NOT NULL DEFAULT 'read'",
        }
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE contacts ADD COLUMN {column} {definition}")

    @staticmethod
    def _ensure_auxiliary_columns(conn: sqlite3.Connection) -> None:
        def add_missing(table: str, columns: dict[str, str]) -> None:
            existing = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for column, definition in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

        add_missing(
            "send_logs",
            {
                "channel": "TEXT NOT NULL DEFAULT 'email'",
                "platform_recipient": "TEXT DEFAULT ''",
            },
        )
        add_missing("job_queue", {"channel": "TEXT NOT NULL DEFAULT 'email'"})

        add_missing(
            "contact_events",
            {
                "metadata_json": "TEXT DEFAULT ''",
            },
        )
        add_missing(
            "replies",
            {
                "ai_summary": "TEXT DEFAULT ''",
                "suggested_next_action": "TEXT DEFAULT ''",
            },
        )
        add_missing(
            "conversation_threads",
            {
                "suggested_lead_status": "TEXT DEFAULT ''",
            },
        )
        add_missing(
            "conversation_messages",
            {
                "remote_message_id": "TEXT DEFAULT ''",
                "imap_uid": "TEXT DEFAULT ''",
                "telegram_update_id": "INTEGER",
                "sender": "TEXT DEFAULT ''",
                "unread_state": "TEXT NOT NULL DEFAULT 'unread'",
            },
        )
        add_missing(
            "ai_metrics",
            {
                "research_model": "TEXT DEFAULT ''",
                "writer_model": "TEXT DEFAULT ''",
                "research_confidence": "REAL",
                "writer_confidence": "REAL",
            },
        )
        add_missing(
            "operator_sessions",
            {
                "draft_variant": "TEXT DEFAULT ''",
                "unsaved_draft": "TEXT DEFAULT ''",
            },
        )

    def fetch_one(self, query: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        return dict(row) if row else None

    def fetch_all(self, query: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def execute(self, query: str, params: Iterable[Any] = ()) -> int:
        with self.connect() as conn:
            cursor = conn.execute(query, tuple(params))
            return int(cursor.lastrowid or cursor.rowcount or 0)

    def execute_many(self, query: str, rows: Iterable[Iterable[Any]]) -> None:
        with self.connect() as conn:
            conn.executemany(query, rows)

    def get_campaigns(self) -> list[dict[str, Any]]:
        return self.fetch_all("SELECT * FROM campaigns ORDER BY created_at DESC, id DESC")

    def create_campaign(self, name: str) -> int:
        return self.execute("INSERT INTO campaigns (name) VALUES (?)", (name,))

    def get_default_campaign_id(self) -> int:
        row = self.fetch_one("SELECT id FROM campaigns ORDER BY id LIMIT 1")
        if row:
            return int(row["id"])
        return self.create_campaign("Default Campaign")

    def get_settings(self) -> dict[str, str]:
        rows = self.fetch_all("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in rows}

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    def set_settings(self, values: dict[str, str]) -> None:
        with self.connect() as conn:
            for key, value in values.items():
                conn.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, value),
                )

    def get_template(self, name: str = "Default") -> dict[str, Any]:
        row = self.fetch_one("SELECT * FROM templates WHERE name = ?", (name,))
        if not row:
            self.initialize()
            row = self.fetch_one("SELECT * FROM templates WHERE name = ?", (name,))
        if not row:
            raise RuntimeError("Default template is missing")
        return row

    def save_template(self, name: str, subject_template: str, body_template: str) -> None:
        self.execute(
            """
            INSERT INTO templates (name, subject_template, body_template)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                subject_template = excluded.subject_template,
                body_template = excluded.body_template,
                updated_at = CURRENT_TIMESTAMP
            """,
            (name, subject_template, body_template),
        )

    def add_contact(self, contact: dict[str, Any]) -> int:
        return self.execute(
            """
            INSERT INTO contacts (
                campaign_id, channel, email, handle, profile_url, external_id,
                name, company, topic, website, social_profile, subject,
                base_message, generated_message, ai_generated, ai_confidence,
                ai_notes, ai_warnings, research_brief_json, research_confidence,
                research_warnings, research_status, enrichment_result_json,
                enrichment_status, enrichment_source_urls, enrichment_warnings,
                enrichment_confidence, status, last_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contact["campaign_id"],
                contact.get("channel", "email") or "email",
                contact["email"],
                contact.get("handle", ""),
                contact.get("profile_url", ""),
                contact.get("external_id", ""),
                contact.get("name", ""),
                contact.get("company", ""),
                contact.get("topic", ""),
                contact.get("website", ""),
                contact.get("social_profile", ""),
                contact.get("subject", ""),
                contact.get("base_message", ""),
                contact.get("generated_message", ""),
                contact.get("ai_generated", 0),
                contact.get("ai_confidence"),
                contact.get("ai_notes", ""),
                contact.get("ai_warnings", ""),
                contact.get("research_brief_json", ""),
                contact.get("research_confidence"),
                contact.get("research_warnings", ""),
                contact.get("research_status", ""),
                contact.get("enrichment_result_json", ""),
                contact.get("enrichment_status", "not_checked"),
                contact.get("enrichment_source_urls", ""),
                contact.get("enrichment_warnings", ""),
                contact.get("enrichment_confidence"),
                contact.get("status", "new"),
                contact.get("last_error", ""),
            ),
        )

    def get_contact(self, contact_id: int) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM contacts WHERE id = ?", (contact_id,))

    def get_contact_by_email(self, campaign_id: int, email: str) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT * FROM contacts WHERE campaign_id = ? AND lower(email) = lower(?)",
            (campaign_id, email),
        )

    def update_contact(self, contact_id: int, fields: dict[str, Any]) -> None:
        allowed = {
            "email",
            "channel",
            "handle",
            "profile_url",
            "external_id",
            "name",
            "company",
            "topic",
            "website",
            "social_profile",
            "subject",
            "base_message",
            "generated_message",
            "ai_generated",
            "ai_confidence",
            "ai_notes",
            "ai_warnings",
            "research_brief_json",
            "research_confidence",
            "research_warnings",
            "research_status",
            "enrichment_result_json",
            "enrichment_status",
            "enrichment_source_urls",
            "enrichment_warnings",
            "enrichment_confidence",
            "lead_status",
            "unread_state",
            "status",
            "last_error",
            "sent_at",
            "replied_at",
            "follow_up_due_at",
        }
        clean_fields = {key: value for key, value in fields.items() if key in allowed}
        if not clean_fields:
            return
        clean_fields["updated_at"] = "CURRENT_TIMESTAMP"
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in clean_fields.items():
            if key == "updated_at":
                assignments.append("updated_at = CURRENT_TIMESTAMP")
            else:
                assignments.append(f"{key} = ?")
                params.append(value)
        params.append(contact_id)
        self.execute(f"UPDATE contacts SET {', '.join(assignments)} WHERE id = ?", params)

    def delete_contacts(self, contact_ids: Iterable[int]) -> int:
        ids = [int(contact_id) for contact_id in contact_ids]
        if not ids:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        return self.execute(f"DELETE FROM contacts WHERE id IN ({placeholders})", ids)

    def list_contacts(
        self,
        campaign_id: int,
        status: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM contacts WHERE campaign_id = ?"
        params: list[Any] = [campaign_id]
        if status and status != "all":
            query += " AND status = ?"
            params.append(status)
        if search:
            pattern = f"%{search.strip()}%"
            query += (
                " AND (email LIKE ? OR name LIKE ? OR company LIKE ? OR topic LIKE ? "
                "OR website LIKE ? OR social_profile LIKE ? OR channel LIKE ? "
                "OR handle LIKE ? OR profile_url LIKE ? OR external_id LIKE ?)"
            )
            params.extend([pattern] * 10)
        query += " ORDER BY id DESC"
        return self.fetch_all(query, params)

    def get_stats(self, campaign_id: int) -> dict[str, int]:
        stats = {
            "total": 0,
            "pending_review": 0,
            "approved": 0,
            "generation_queued": 0,
            "generating": 0,
            "queued": 0,
            "sending": 0,
            "dry_run_sent": 0,
            "sent": 0,
            "failed": 0,
            "blacklisted": 0,
            "cancelled": 0,
        }
        rows = self.fetch_all(
            "SELECT status, COUNT(*) AS count FROM contacts WHERE campaign_id = ? GROUP BY status",
            (campaign_id,),
        )
        for row in rows:
            count = int(row["count"])
            stats["total"] += count
            if row["status"] in stats:
                stats[row["status"]] = count
        return stats

    def add_blacklist(self, email: str, reason: str = "") -> None:
        self.execute(
            """
            INSERT INTO blacklist (email, reason) VALUES (lower(?), ?)
            ON CONFLICT(email) DO UPDATE SET reason = excluded.reason
            """,
            (email, reason),
        )

    def is_blacklisted(self, email: str) -> bool:
        row = self.fetch_one("SELECT id FROM blacklist WHERE email = lower(?)", (email,))
        return row is not None

    def log_send(
        self,
        contact_id: int | None,
        campaign_id: int | None,
        action: str,
        status: str,
        error: str = "",
        channel: str = "email",
        platform_recipient: str = "",
    ) -> None:
        self.execute(
            """
            INSERT INTO send_logs (
                contact_id, campaign_id, channel, platform_recipient, action, status, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contact_id,
                campaign_id,
                channel or "email",
                platform_recipient or "",
                action,
                status,
                redact_secret(error),
            ),
        )

    def log_import_error(
        self,
        campaign_id: int,
        source_file: str,
        row_number: int | None,
        email: str,
        error: str,
    ) -> None:
        self.execute(
            """
            INSERT INTO import_errors (campaign_id, source_file, row_number, email, error)
            VALUES (?, ?, ?, ?, ?)
            """,
            (campaign_id, source_file, row_number, email, redact_secret(error)),
        )

    def recent_send_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT send_logs.*, contacts.email
            FROM send_logs
            LEFT JOIN contacts ON contacts.id = send_logs.contact_id
            ORDER BY send_logs.created_at DESC, send_logs.id DESC
            LIMIT ?
            """,
            (limit,),
        )

    def recent_import_errors(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM import_errors ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        )
