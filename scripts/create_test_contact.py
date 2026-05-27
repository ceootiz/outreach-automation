#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DATA_DIR, ensure_project_dirs
from src.db import Database


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CAMPAIGN_NAME = "Stage 1.3 Test Send"


def create_test_contact(email: str, db_path: Path | None = None) -> int:
    clean_email = email.strip().lower()
    if not EMAIL_RE.match(clean_email):
        raise ValueError("Provide a valid owned test inbox email address.")

    ensure_project_dirs()
    db = Database(db_path or Path(os.getenv("OUTREACH_DB_PATH", DATA_DIR / "outreach.sqlite")))
    db.initialize()
    campaign = db.fetch_one("SELECT id FROM campaigns WHERE name = ?", (CAMPAIGN_NAME,))
    campaign_id = int(campaign["id"]) if campaign else db.create_campaign(CAMPAIGN_NAME)

    existing = db.get_contact_by_email(campaign_id, clean_email)
    fields = {
        "campaign_id": campaign_id,
        "email": clean_email,
        "name": "Test",
        "company": "Outreach Automation",
        "topic": "Stage 1.3",
        "subject": "Stage 1.3 test email",
        "base_message": "This is a controlled one-recipient test email.",
        "status": "new",
    }
    if existing:
        db.update_contact(
            existing["id"],
            {
                "name": fields["name"],
                "company": fields["company"],
                "topic": fields["topic"],
                "subject": fields["subject"],
                "base_message": fields["base_message"],
                "generated_message": "",
                "status": "new",
                "last_error": "",
                "sent_at": None,
                "follow_up_due_at": None,
            },
        )
        contact_id = int(existing["id"])
    else:
        contact_id = db.add_contact(fields)

    db.log_send(
        contact_id,
        campaign_id,
        "create_test_contact",
        "ok",
        "Created one controlled test contact. No email was sent.",
    )
    return contact_id


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("Usage: ./scripts/create_test_contact.py your_test_email@gmail.com")
        return 2
    try:
        contact_id = create_test_contact(args[0])
    except Exception as exc:
        print(f"Failed to create test contact: {exc}")
        return 1
    print(f"Created/updated Stage 1.3 test contact #{contact_id}. No email was sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
