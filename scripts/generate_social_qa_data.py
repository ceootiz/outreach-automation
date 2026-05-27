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


SOCIAL_QA_CAMPAIGN_NAME = "Social Full Ready QA"
SOCIAL_CHANNELS = ("instagram", "tiktok", "x", "vk")
DEFAULT_PER_CHANNEL = 25


PROFILE_URLS = {
    "instagram": "https://www.instagram.com/{handle}/",
    "tiktok": "https://www.tiktok.com/@{handle}",
    "x": "https://x.com/{handle}",
    "vk": "https://vk.com/{handle}",
}


def _db_path(path: str | None = None) -> Path:
    return Path(path).expanduser() if path else DATA_DIR / "outreach.sqlite"


def _row(channel: str, index: int, campaign_id: int) -> dict[str, str]:
    handle = f"qa_{channel}_{index:03d}"
    style = {
        "instagram": "короткий creator-friendly DM",
        "tiktok": "очень короткое creator-style сообщение",
        "x": "лаконичный direct DM",
        "vk": "прямое social-сообщение",
    }[channel]
    return {
        "campaign_id": campaign_id,
        "channel": channel,
        "handle": handle,
        "profile_url": PROFILE_URLS[channel].format(handle=handle),
        "name": f"Social QA Lead {index:03d}",
        "company": f"{channel.title()} QA Studio {index:03d}",
        "topic": "social collaboration qa",
        "website": f"https://example.com/{channel}/qa-{index:03d}",
        "social_profile": PROFILE_URLS[channel].format(handle=handle),
        "subject": "",
        "generated_message": (
            f"Привет! Это безопасный QA-черновик для {style}. "
            "Оператор копирует текст и отправляет вручную."
        ),
        "status": "pending_review" if index % 3 else "approved",
    }


def generate_social_qa_data(
    *,
    per_channel: int = DEFAULT_PER_CHANNEL,
    reset: bool = False,
    db_path: str | None = None,
) -> dict[str, int]:
    db = Database(_db_path(db_path))
    db.initialize()
    if reset:
        db.execute("DELETE FROM campaigns WHERE name = ?", (SOCIAL_QA_CAMPAIGN_NAME,))
    existing = db.fetch_one("SELECT id FROM campaigns WHERE name = ? ORDER BY id DESC LIMIT 1", (SOCIAL_QA_CAMPAIGN_NAME,))
    campaign_id = int(existing["id"]) if existing else db.create_campaign(SOCIAL_QA_CAMPAIGN_NAME)
    service = CampaignService(db, sleep_fn=lambda _: None)
    service.save_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "active_channel": "instagram",
            "execution_mode_instagram": "manual_assist",
            "execution_mode_tiktok": "manual_assist",
            "execution_mode_x": "manual_assist",
            "execution_mode_vk": "manual_assist",
            "operator_mode": "high_volume",
        }
    )

    imported = 0
    for channel in SOCIAL_CHANNELS:
        for index in range(1, per_channel + 1):
            result = service.add_contact_rows(campaign_id, [_row(channel, index, campaign_id)], source="social_qa_demo")
            if not result.imported_count:
                continue
            contact = service.contacts(campaign_id)[0]
            contact_id = int(contact["id"])
            confidence = round(0.35 + ((index % 8) * 0.07), 2)
            service.db.update_contact(
                contact_id,
                {
                    "ai_generated": 1,
                    "ai_confidence": confidence,
                    "ai_notes": "Social QA/demo dataset. No real recipient.",
                    "ai_warnings": "low confidence" if confidence < 0.5 else "",
                    "research_brief_json": (
                        '{"recipient_type":"creator","source_basis":["qa_demo"],'
                        '"do_not_claim":["Не утверждать, что профиль изучен"]}'
                    ),
                    "research_confidence": min(confidence + 0.1, 0.95),
                    "research_status": "qa_demo",
                    "research_warnings": "synthetic social lead",
                    "enrichment_status": "success" if index % 4 else "partial",
                    "enrichment_result_json": (
                        '{"status":"success","public_summary":"Synthetic social profile for QA only",'
                        '"source_urls":["https://example.com"],"warnings":["qa demo"]}'
                    ),
                    "enrichment_confidence": 0.78 if index % 4 else 0.42,
                    "lead_status": "Warm" if index % 5 == 0 else "New",
                    "last_error": "",
                },
            )
            if index % 10 == 0:
                service.add_reply(contact_id, "QA manual reply marker for search.", reply_status="maybe_later")
            if index % 7 == 0:
                service.schedule_followup(contact_id, days_from_now=4, note="Social QA follow-up reminder")
            imported += 1

    db.log_send(
        None,
        campaign_id,
        "social_qa_data",
        "ok",
        f"synthetic=true; count={imported}; no real sends; no real profiles",
        channel="manual_assist",
    )
    return {"campaign_id": campaign_id, "count": imported}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate safe synthetic social leads for Stage 4.8 QA.")
    parser.add_argument("--per-channel", type=int, default=DEFAULT_PER_CHANNEL)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--db-path", default="")
    args = parser.parse_args()
    result = generate_social_qa_data(
        per_channel=max(args.per_channel, 1),
        reset=args.reset,
        db_path=args.db_path or None,
    )
    print(f"Social QA data ready: campaign_id={result['campaign_id']} leads={result['count']}")
    print("Dataset is synthetic/demo only. No real profiles, tokens, secrets, or sends were used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
