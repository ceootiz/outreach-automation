from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .execution import get_channel_capability, risk_label


FULL = "Full"
FULL_READY = "Full-ready"
MANUAL_FULL = "Manual Assist Full"
API_PENDING = "API Pending"
FUTURE = "Future slot"


@dataclass(frozen=True, slots=True)
class ChannelReadiness:
    channel_id: str
    display_name: str
    current_status: str
    official_api_live_send: str
    reply_ingestion: str
    manual_assist_readiness: str
    risk_level: str
    missing_settings: tuple[str, ...]
    missing_credentials: tuple[str, ...]
    missing_tests: tuple[str, ...]
    missing_ui_pieces: tuple[str, ...]
    production_readiness_percent: int
    notes: str

    @property
    def risk_ui_label(self) -> str:
        return risk_label(self.risk_level)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "display_name": self.display_name,
            "current_status": self.current_status,
            "official_api_live_send": self.official_api_live_send,
            "reply_ingestion": self.reply_ingestion,
            "manual_assist_readiness": self.manual_assist_readiness,
            "risk_level": self.risk_level,
            "risk_ui_label": self.risk_ui_label,
            "missing_settings": list(self.missing_settings),
            "missing_credentials": list(self.missing_credentials),
            "missing_tests": list(self.missing_tests),
            "missing_ui_pieces": list(self.missing_ui_pieces),
            "production_readiness_percent": self.production_readiness_percent,
            "notes": self.notes,
        }


BASE_READINESS: dict[str, ChannelReadiness] = {
    "email": ChannelReadiness(
        channel_id="email",
        display_name="Email",
        current_status=FULL,
        official_api_live_send="yes: Gmail SMTP",
        reply_ingestion="yes: Gmail IMAP read-only",
        manual_assist_readiness="optional",
        risk_level=get_channel_capability("email").risk_level,
        missing_settings=(),
        missing_credentials=(),
        missing_tests=(),
        missing_ui_pieces=(),
        production_readiness_percent=96,
        notes="Full email path with Gmail profiles, dry-run, live guardrails, IMAP ingestion and reports.",
    ),
    "telegram": ChannelReadiness(
        channel_id="telegram",
        display_name="Telegram",
        current_status=FULL_READY,
        official_api_live_send="yes: official Bot API",
        reply_ingestion="yes: getUpdates polling",
        manual_assist_readiness="ready fallback",
        risk_level=get_channel_capability("telegram").risk_level,
        missing_settings=(),
        missing_credentials=(),
        missing_tests=(),
        missing_ui_pieces=(),
        production_readiness_percent=92,
        notes="Official Bot API only. Bot can message only chat_id values where it has access.",
    ),
    "instagram": ChannelReadiness(
        channel_id="instagram",
        display_name="Instagram",
        current_status=MANUAL_FULL,
        official_api_live_send="restricted: not enabled",
        reply_ingestion="manual only",
        manual_assist_readiness="full",
        risk_level=get_channel_capability("instagram").risk_level,
        missing_settings=(),
        missing_credentials=("official Instagram messaging API approval",),
        missing_tests=(),
        missing_ui_pieces=(),
        production_readiness_percent=88,
        notes="Import, handle/profile URL, enrichment, AI drafts, priority, copy/open/mark sent, replies, timeline and follow-ups are Manual Assist ready.",
    ),
    "tiktok": ChannelReadiness(
        channel_id="tiktok",
        display_name="TikTok",
        current_status=MANUAL_FULL,
        official_api_live_send="limited: not enabled",
        reply_ingestion="manual only",
        manual_assist_readiness="full",
        risk_level=get_channel_capability("tiktok").risk_level,
        missing_settings=(),
        missing_credentials=("safe official TikTok messaging API path",),
        missing_tests=(),
        missing_ui_pieces=(),
        production_readiness_percent=86,
        notes="Safe automatic DM is unavailable. Operator copy/open/mark-sent flow is the production path.",
    ),
    "x": ChannelReadiness(
        channel_id="x",
        display_name="X",
        current_status="Manual Assist/API Pending",
        official_api_live_send="limited: not enabled",
        reply_ingestion="manual only",
        manual_assist_readiness="full",
        risk_level=get_channel_capability("x").risk_level,
        missing_settings=(),
        missing_credentials=("approved official X messaging API access",),
        missing_tests=(),
        missing_ui_pieces=(),
        production_readiness_percent=82,
        notes="Concise Manual Assist flow is ready. Official API live-send remains pending.",
    ),
    "vk": ChannelReadiness(
        channel_id="vk",
        display_name="VK",
        current_status="Manual Assist/API Pending",
        official_api_live_send="partial: not enabled",
        reply_ingestion="manual only",
        manual_assist_readiness="full",
        risk_level=get_channel_capability("vk").risk_level,
        missing_settings=(),
        missing_credentials=("safe official VK API authorization",),
        missing_tests=(),
        missing_ui_pieces=(),
        production_readiness_percent=82,
        notes="Manual profile/dialog handoff is ready. Official API live-send is intentionally disabled.",
    ),
    "whatsapp": ChannelReadiness(
        channel_id="whatsapp",
        display_name="WhatsApp",
        current_status=FUTURE,
        official_api_live_send="future: official Business Platform required",
        reply_ingestion="future",
        manual_assist_readiness="not implemented",
        risk_level="high",
        missing_settings=("channel UI", "official provider setup"),
        missing_credentials=("WhatsApp Business Platform credentials",),
        missing_tests=("channel integration tests",),
        missing_ui_pieces=("contact columns", "Manual Assist panel", "settings card"),
        production_readiness_percent=15,
        notes="Future channel only. No unsafe automation or unofficial account control planned.",
    ),
    "viber": ChannelReadiness(
        channel_id="viber",
        display_name="Viber",
        current_status=FUTURE,
        official_api_live_send="future: official bot/business API required",
        reply_ingestion="future",
        manual_assist_readiness="not implemented",
        risk_level="high",
        missing_settings=("channel UI", "official provider setup"),
        missing_credentials=("official Viber bot/business credentials",),
        missing_tests=("channel integration tests",),
        missing_ui_pieces=("contact columns", "Manual Assist panel", "settings card"),
        production_readiness_percent=15,
        notes="Future channel only. No scraping, userbot or hidden automation planned.",
    ),
}


READINESS_ORDER = ("email", "telegram", "instagram", "tiktok", "x", "vk", "whatsapp", "viber")


def list_channel_readiness(
    *,
    has_email_profile: bool = True,
    has_telegram_token: bool = True,
    has_telegram_chat_id: bool = True,
) -> list[ChannelReadiness]:
    rows = [BASE_READINESS[channel_id] for channel_id in READINESS_ORDER]
    adjusted: list[ChannelReadiness] = []
    for row in rows:
        if row.channel_id == "email" and not has_email_profile:
            adjusted.append(
                replace(
                    row,
                    current_status="Full-ready, credentials pending",
                    missing_credentials=("active Gmail profile with App Password",),
                    production_readiness_percent=88,
                    notes=row.notes + " Active sender credentials are still required for live SMTP/IMAP.",
                )
            )
            continue
        if row.channel_id == "telegram" and (not has_telegram_token or not has_telegram_chat_id):
            missing = []
            if not has_telegram_token:
                missing.append("Telegram Bot Token")
            if not has_telegram_chat_id:
                missing.append("default owned test chat_id")
            adjusted.append(
                replace(
                    row,
                    current_status="Full-ready, live credentials pending",
                    missing_credentials=tuple(missing),
                    production_readiness_percent=84,
                    notes=row.notes + " Configure token/chat_id for controlled live verification.",
                )
            )
            continue
        adjusted.append(row)
    return adjusted


def readiness_by_channel(**kwargs: Any) -> dict[str, ChannelReadiness]:
    return {row.channel_id: row for row in list_channel_readiness(**kwargs)}
