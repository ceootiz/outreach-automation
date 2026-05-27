#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DATA_DIR, DEFAULT_SETTINGS, ensure_project_dirs  # noqa: E402

DEFAULT_SUBJECT_TEMPLATE = "Quick idea for {{company}}"
DEFAULT_BODY_TEMPLATE = "Hi {{name}},\n\n{{base_message}}\n\nBest regards,"
DEMO_CAMPAIGN_PREFIXES = (
    "Stage 1.1 Smoke",
    "Stage 1.1 Limit Smoke",
    "Stage 1.2 Smoke",
    "Stage 1.3 Test Send",
    "Stage 1.3 Smoke",
    "Demo Campaign",
)
DEMO_EMAIL_PREFIXES = ("stage11.", "stage12.", "demo.")

def initialize_minimal_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'active'
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

        CREATE TABLE IF NOT EXISTS blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            reason TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS job_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            contact_id INTEGER,
            job_group_id TEXT,
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
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def reset_sqlite(db_path: Path, wipe_demo_campaigns: bool = True) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        initialize_minimal_schema(conn)

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

        conn.execute(
            """
            INSERT INTO templates (name, subject_template, body_template)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                subject_template = excluded.subject_template,
                body_template = excluded.body_template,
                updated_at = CURRENT_TIMESTAMP
            """,
            ("Default", DEFAULT_SUBJECT_TEMPLATE, DEFAULT_BODY_TEMPLATE),
        )

        if wipe_demo_campaigns:
            for prefix in DEMO_CAMPAIGN_PREFIXES:
                conn.execute(
                    """
                    DELETE FROM job_queue
                    WHERE campaign_id IN (
                        SELECT id FROM campaigns WHERE name LIKE ?
                    )
                    """,
                    (f"{prefix}%",),
                )
                conn.execute("DELETE FROM campaigns WHERE name LIKE ?", (f"{prefix}%",))

        for prefix in DEMO_EMAIL_PREFIXES:
            conn.execute("DELETE FROM blacklist WHERE email LIKE ?", (f"{prefix}%",))

        if not conn.execute("SELECT id FROM campaigns LIMIT 1").fetchone():
            conn.execute("INSERT INTO campaigns (name) VALUES (?)", ("Default Campaign",))


def reset_demo_data(db, wipe_demo_campaigns: bool = True) -> None:
    reset_sqlite(Path(db.path), wipe_demo_campaigns=wipe_demo_campaigns)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reset safe demo settings/templates and remove only known demo/smoke data. "
            "Does not delete .env, exports, or log files."
        )
    )
    parser.add_argument(
        "--keep-demo-campaigns",
        action="store_true",
        help="Only reset settings/templates; keep demo campaign rows.",
    )
    args = parser.parse_args()

    ensure_project_dirs()
    reset_sqlite(DATA_DIR / "outreach.sqlite", wipe_demo_campaigns=not args.keep_demo_campaigns)
    print("Demo data reset complete. .env, exports, and log files were not deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
