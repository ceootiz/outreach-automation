#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.campaign_service import CampaignService
from src.config import DATA_DIR
from src.db import Database


QA_CAMPAIGN_NAME = "Operator QA Demo"
CHANNELS = ("email", "telegram", "instagram", "x", "tiktok", "vk")
STATUSES = ("pending_review", "approved", "new", "dry_run_sent")
LEAD_STAGES = ("New", "Contacted", "Warm", "Interested", "Negotiating")
ENRICHMENT_STATUSES = ("success", "partial", "failed", "not_checked")


def _db_path(path: str | None = None) -> Path:
    return Path(path).expanduser() if path else DATA_DIR / "outreach.sqlite"


def _fake_row(index: int, campaign_id: int) -> dict[str, str]:
    channel = CHANNELS[index % len(CHANNELS)]
    stage = LEAD_STAGES[index % len(LEAD_STAGES)]
    status = STATUSES[index % len(STATUSES)]
    company = f"QA Studio {index:03d}"
    name = f"QA Lead {index:03d}"
    message = (
        f"Здравствуйте, {name}! Это безопасный QA-черновик для проверки operator workflow. "
        "Сообщение не предназначено для реальной отправки."
    )
    row = {
        "campaign_id": campaign_id,
        "channel": channel,
        "email": "",
        "handle": "",
        "profile_url": "",
        "external_id": "",
        "name": name,
        "company": company,
        "topic": "qa demo outreach",
        "website": f"https://example.com/qa/{index:03d}",
        "social_profile": f"https://example.com/social/{index:03d}",
        "subject": "QA outreach draft" if channel == "email" else "",
        "generated_message": message,
        "status": status,
    }
    if channel == "email":
        row["email"] = f"qa-lead-{index:03d}@example.invalid"
    elif channel == "telegram":
        row["external_id"] = f"qa-chat-{100000 + index}"
        row["handle"] = f"qa_telegram_{index:03d}"
    else:
        row["handle"] = f"qa_{channel}_{index:03d}"
        row["profile_url"] = f"https://example.com/{channel}/qa_{index:03d}"
    return row


def generate_operator_qa_data(*, count: int = 100, reset: bool = False, db_path: str | None = None) -> dict[str, int]:
    db = Database(_db_path(db_path))
    db.initialize()
    if reset:
        db.execute("DELETE FROM campaigns WHERE name = ?", (QA_CAMPAIGN_NAME,))
    existing = db.fetch_one("SELECT id FROM campaigns WHERE name = ? ORDER BY id DESC LIMIT 1", (QA_CAMPAIGN_NAME,))
    campaign_id = int(existing["id"]) if existing else db.create_campaign(QA_CAMPAIGN_NAME)
    service = CampaignService(db, sleep_fn=lambda _: None)
    service.save_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "active_channel": "instagram",
            "execution_mode_instagram": "manual_assist",
            "operator_mode": "high_volume",
        }
    )

    imported = 0
    for index in range(1, count + 1):
        row = _fake_row(index, campaign_id)
        result = service.add_contact_rows(campaign_id, [row], source="operator_qa_demo")
        if not result.imported_count:
            continue
        contact = service.contacts(campaign_id)[0]
        confidence = round(0.18 + ((index % 10) * 0.08), 2)
        enrichment_status = ENRICHMENT_STATUSES[index % len(ENRICHMENT_STATUSES)]
        service.db.update_contact(
            int(contact["id"]),
            {
                "status": row["status"],
                "ai_generated": 1,
                "ai_confidence": confidence,
                "ai_notes": "QA/demo dataset. No real recipient.",
                "ai_warnings": "low data" if confidence < 0.45 else "",
                "research_confidence": min(confidence + 0.08, 0.95),
                "research_status": "qa_demo",
                "research_warnings": "synthetic lead",
                "enrichment_status": enrichment_status,
                "enrichment_confidence": 0.75 if enrichment_status == "success" else 0.35,
                "lead_status": LEAD_STAGES[index % len(LEAD_STAGES)],
                "last_error": "QA/demo synthetic lead; do not send." if index % 13 == 0 else "",
            },
        )
        if index % 11 == 0:
            service.db.update_contact(int(contact["id"]), {"replied_at": "2026-01-01 10:00:00"})
        if index % 9 == 0:
            service.schedule_followup(int(contact["id"]), days_from_now=3, note="QA follow-up reminder")
        imported += 1

    db.log_send(
        None,
        campaign_id,
        "operator_qa_data",
        "ok",
        f"synthetic=true; count={imported}; no real sends; no real recipients",
    )
    return {"campaign_id": campaign_id, "count": imported}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate safe synthetic leads for Outreach Session QA.")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--db-path", default="")
    args = parser.parse_args()
    result = generate_operator_qa_data(count=max(args.count, 1), reset=args.reset, db_path=args.db_path or None)
    print(f"Operator QA data ready: campaign_id={result['campaign_id']} leads={result['count']}")
    print("Dataset is synthetic/demo only. No real emails, tokens, secrets, or sends were used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
