from __future__ import annotations

from datetime import datetime
from typing import Any

from .config import as_int
from .credential_store import (
    delete_profile_password,
    get_stored_gmail_app_password,
    has_profile_password,
    load_profile_password,
    save_profile_password,
)
from .db import Database
from .excel_importer import is_valid_email
from .logger_setup import get_logger, redact_secret
from .mailer import ConnectionCheckResult, GmailSMTPMailer


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def default_profile_name(email: str) -> str:
    local = normalize_email(email).split("@", 1)[0]
    return local or "Gmail"


class GmailProfileService:
    def __init__(self, db: Database, mailer: GmailSMTPMailer | None = None):
        self.db = db
        self.mailer = mailer or GmailSMTPMailer()
        self.logger = get_logger()

    def list_profiles(self) -> list[dict[str, Any]]:
        rows = self.db.fetch_all(
            """
            SELECT *
            FROM gmail_profiles
            ORDER BY is_active DESC, updated_at DESC, id DESC
            """
        )
        for row in rows:
            row["has_password"] = self.has_password(int(row["id"]), row["email"])
        return rows

    def create_profile(
        self,
        name: str,
        email: str,
        password: str,
        *,
        make_active: bool = True,
    ) -> dict[str, Any]:
        email = self._validate_email(email)
        password = (password or "").strip()
        if not password:
            raise ValueError("Введите Gmail App Password для профиля.")
        profile_name = (name or "").strip() or default_profile_name(email)
        has_profiles = bool(self.list_profiles())
        make_active = make_active or not has_profiles
        with self.db.connect() as conn:
            if make_active:
                conn.execute("UPDATE gmail_profiles SET is_active = 0, updated_at = CURRENT_TIMESTAMP")
            cursor = conn.execute(
                """
                INSERT INTO gmail_profiles (profile_name, email, is_active)
                VALUES (?, ?, ?)
                """,
                (profile_name, email, 1 if make_active else 0),
            )
            profile_id = int(cursor.lastrowid)
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("active_gmail_profile_id", str(profile_id) if make_active else ""),
            )
            if make_active:
                conn.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    ("sender_email", email),
                )
        backend_name = save_profile_password(profile_id, email, password)
        self.db.log_send(None, None, "save_gmail_profile", "ok", f"profile_id={profile_id}; backend={backend_name}")
        self.logger.info("Gmail profile saved using %s", backend_name)
        profile = self.get_profile(profile_id) or {}
        profile["credential_backend"] = backend_name
        return profile

    def update_profile(
        self,
        profile_id: int,
        *,
        name: str | None = None,
        email: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        profile = self._require_profile(profile_id)
        old_email = normalize_email(profile["email"])
        new_email = self._validate_email(email if email is not None else old_email)
        new_name = (name if name is not None else profile["profile_name"] or "").strip() or default_profile_name(new_email)
        password_to_save = (password or "").strip()
        old_password = ""
        if new_email != old_email and not password_to_save:
            old_password = load_profile_password(profile_id, old_email)

        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE gmail_profiles
                SET profile_name = ?, email = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_name, new_email, profile_id),
            )
            if int(profile.get("is_active") or 0):
                conn.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    ("sender_email", new_email),
                )

        if password_to_save:
            backend_name = save_profile_password(profile_id, new_email, password_to_save)
            if new_email != old_email:
                delete_profile_password(profile_id, old_email)
        elif old_password:
            backend_name = save_profile_password(profile_id, new_email, old_password)
            delete_profile_password(profile_id, old_email)
        else:
            backend_name = ""

        self.db.log_send(None, None, "update_gmail_profile", "ok", f"profile_id={profile_id}")
        profile = self.get_profile(profile_id) or {}
        profile["credential_backend"] = backend_name
        return profile

    def delete_profile(self, profile_id: int) -> None:
        profile = self._require_profile(profile_id)
        was_active = bool(int(profile.get("is_active") or 0))
        delete_profile_password(profile_id, profile["email"])
        with self.db.connect() as conn:
            conn.execute("DELETE FROM gmail_profiles WHERE id = ?", (profile_id,))
            replacement = None
            if was_active:
                replacement = conn.execute(
                    "SELECT id, email FROM gmail_profiles ORDER BY updated_at DESC, id DESC LIMIT 1"
                ).fetchone()
                conn.execute("UPDATE gmail_profiles SET is_active = 0")
                if replacement:
                    conn.execute(
                        "UPDATE gmail_profiles SET is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (replacement["id"],),
                    )
                conn.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    ("active_gmail_profile_id", str(replacement["id"]) if replacement else ""),
                )
                conn.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    ("sender_email", str(replacement["email"]) if replacement else ""),
                )
        self.db.log_send(None, None, "delete_gmail_profile", "ok", f"profile_id={profile_id}")

    def set_active_profile(self, profile_id: int) -> dict[str, Any]:
        profile = self._require_profile(profile_id)
        email = self._validate_email(profile["email"])
        with self.db.connect() as conn:
            conn.execute("UPDATE gmail_profiles SET is_active = 0, updated_at = CURRENT_TIMESTAMP")
            conn.execute(
                "UPDATE gmail_profiles SET is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (profile_id,),
            )
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("active_gmail_profile_id", str(profile_id)),
            )
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("sender_email", email),
            )
        self.db.log_send(None, None, "set_active_gmail_profile", "ok", f"profile_id={profile_id}")
        return self.get_profile(profile_id) or {}

    def get_active_profile(self) -> dict[str, Any] | None:
        row = self.db.fetch_one(
            """
            SELECT *
            FROM gmail_profiles
            WHERE is_active = 1
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """
        )
        if row:
            row["has_password"] = self.has_password(int(row["id"]), row["email"])
        return row

    def get_profile(self, profile_id: int) -> dict[str, Any] | None:
        row = self.db.fetch_one("SELECT * FROM gmail_profiles WHERE id = ?", (profile_id,))
        if row:
            row["has_password"] = self.has_password(int(row["id"]), row["email"])
        return row

    def load_password(self, profile_id: int, email: str) -> str:
        return load_profile_password(profile_id, email)

    def has_password(self, profile_id: int, email: str) -> bool:
        return has_profile_password(profile_id, email)

    def check_profile_connection(
        self,
        profile_id: int,
        *,
        password_override: str | None = None,
        email_override: str | None = None,
    ) -> ConnectionCheckResult:
        profile = self._require_profile(profile_id)
        email = self._validate_email(email_override if email_override is not None else profile["email"])
        password = (password_override or "").strip() or self.load_password(profile_id, email)
        if not password:
            result = ConnectionCheckResult(False, "Введите и сохраните App Password для профиля Gmail.")
            self._update_check_status(profile_id, result)
            return result
        settings = self.db.get_settings()
        result = self.mailer.check_connection(
            host=settings.get("smtp_host", "smtp.gmail.com"),
            port=as_int(settings.get("smtp_port"), 587),
            sender_email=email,
            password=password,
        )
        self._update_check_status(profile_id, result)
        return result

    def migrate_legacy_credentials_if_needed(self) -> dict[str, Any] | None:
        if self.list_profiles():
            return None
        settings = self.db.get_settings()
        sender = normalize_email(settings.get("sender_email"))
        if not sender:
            return None
        legacy_password = get_stored_gmail_app_password(sender)
        if not legacy_password:
            return None
        try:
            profile = self.create_profile("Основной", sender, legacy_password, make_active=True)
        except Exception as exc:
            self.logger.warning("Legacy Gmail credential migration skipped: %s", redact_secret(exc))
            return None
        self.db.log_send(None, None, "migrate_legacy_gmail_credentials", "ok", f"profile_id={profile.get('id')}")
        return profile

    def _update_check_status(self, profile_id: int, result: ConnectionCheckResult) -> None:
        self.db.execute(
            """
            UPDATE gmail_profiles
            SET last_check_status = ?,
                last_check_at = ?,
                last_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                "connected" if result.ok else "failed",
                datetime.now().replace(microsecond=0).isoformat(sep=" "),
                "" if result.ok else redact_secret(result.message),
                profile_id,
            ),
        )

    def _require_profile(self, profile_id: int) -> dict[str, Any]:
        profile = self.get_profile(int(profile_id))
        if not profile:
            raise ValueError("Gmail profile not found.")
        return profile

    @staticmethod
    def _validate_email(email: str | None) -> str:
        normalized = normalize_email(email)
        if not normalized or not is_valid_email(normalized):
            raise ValueError("Введите корректный Gmail address.")
        return normalized
