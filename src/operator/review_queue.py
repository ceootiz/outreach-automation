from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .lead_prioritizer import HIGH_PRIORITY, LeadPrioritizer


ORDER_PRIORITY = "priority"
ORDER_NEW = "new"
ORDER_AI_CONFIDENCE = "ai_confidence"
ORDER_CHANNEL = "channel"
ORDER_LAST_ACTIVITY = "last_activity"
ORDER_OPTIONS = {
    ORDER_PRIORITY,
    ORDER_NEW,
    ORDER_AI_CONFIDENCE,
    ORDER_CHANNEL,
    ORDER_LAST_ACTIVITY,
}


@dataclass(slots=True)
class ReviewQueueFilters:
    only_high_priority: bool = False
    only_no_contacted: bool = False
    only_warm: bool = False
    min_ai_confidence: float | None = None
    channels: set[str] = field(default_factory=set)
    recipient_types: set[str] = field(default_factory=set)
    search: str = ""
    order_by: str = ORDER_PRIORITY
    needs_review: bool = False
    ready_to_send: bool = False
    manual_assist: bool = False
    follow_up_due: bool = False
    has_reply: bool = False
    low_confidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "only_high_priority": self.only_high_priority,
            "only_no_contacted": self.only_no_contacted,
            "only_warm": self.only_warm,
            "min_ai_confidence": self.min_ai_confidence,
            "channels": sorted(self.channels),
            "recipient_types": sorted(self.recipient_types),
            "search": self.search,
            "order_by": self.order_by,
            "needs_review": self.needs_review,
            "ready_to_send": self.ready_to_send,
            "manual_assist": self.manual_assist,
            "follow_up_due": self.follow_up_due,
            "has_reply": self.has_reply,
            "low_confidence": self.low_confidence,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "ReviewQueueFilters":
        data = value or {}
        min_confidence = data.get("min_ai_confidence")
        return cls(
            only_high_priority=bool(data.get("only_high_priority")),
            only_no_contacted=bool(data.get("only_no_contacted")),
            only_warm=bool(data.get("only_warm")),
            min_ai_confidence=float(min_confidence) if min_confidence not in (None, "") else None,
            channels={str(item).strip().lower() for item in data.get("channels", []) if str(item).strip()},
            recipient_types={str(item).strip().lower() for item in data.get("recipient_types", []) if str(item).strip()},
            search=str(data.get("search") or "").strip(),
            order_by=normalize_order(data.get("order_by")),
            needs_review=bool(data.get("needs_review")),
            ready_to_send=bool(data.get("ready_to_send")),
            manual_assist=bool(data.get("manual_assist")),
            follow_up_due=bool(data.get("follow_up_due")),
            has_reply=bool(data.get("has_reply")),
            low_confidence=bool(data.get("low_confidence")),
        )


@dataclass(frozen=True, slots=True)
class ReviewQueueItem:
    contact: dict[str, Any]
    priority: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"contact": dict(self.contact), "priority": dict(self.priority)}


def _contains(contact: dict[str, Any], needle: str) -> bool:
    if not needle:
        return True
    text = " ".join(str(contact.get(key) or "") for key in (
        "email",
        "handle",
        "profile_url",
        "external_id",
        "name",
        "company",
        "topic",
        "website",
        "social_profile",
        "generated_message",
        "base_message",
    )).lower()
    return needle.lower() in text


class ReviewQueueBuilder:
    def __init__(self, prioritizer: LeadPrioritizer | None = None):
        self.prioritizer = prioritizer or LeadPrioritizer()

    def build(self, contacts: list[dict[str, Any]], filters: ReviewQueueFilters | None = None) -> list[ReviewQueueItem]:
        selected_filters = filters or ReviewQueueFilters()
        items: list[ReviewQueueItem] = []
        for contact in contacts:
            if not self._matches(contact, selected_filters):
                continue
            priority = self.prioritizer.score_contact(contact)
            if selected_filters.only_high_priority and priority.label != HIGH_PRIORITY:
                continue
            items.append(ReviewQueueItem(contact=contact, priority=priority.to_dict()))
        return sorted(
            items,
            key=lambda item: self._sort_key(item, selected_filters.order_by),
        )

    @staticmethod
    def _matches(contact: dict[str, Any], filters: ReviewQueueFilters) -> bool:
        channel = str(contact.get("channel") or "email").strip().lower()
        if filters.channels and channel not in filters.channels:
            return False
        if filters.only_no_contacted and str(contact.get("status") or "new") in {"sent", "dry_run_sent"}:
            return False
        if filters.only_warm and str(contact.get("lead_status") or "") not in {"Warm", "Interested", "Negotiating"}:
            return False
        status = str(contact.get("status") or "new")
        if filters.needs_review and status != "pending_review":
            return False
        if filters.ready_to_send and status != "approved":
            return False
        if filters.manual_assist and channel not in {"instagram", "x", "tiktok", "vk"}:
            return False
        if filters.follow_up_due and not str(contact.get("follow_up_due_at") or "").strip():
            return False
        if filters.has_reply and not str(contact.get("replied_at") or "").strip():
            return False
        if filters.low_confidence:
            try:
                if float(contact.get("ai_confidence") or 0.0) >= 0.45:
                    return False
            except (TypeError, ValueError):
                pass
        if filters.min_ai_confidence is not None:
            try:
                if float(contact.get("ai_confidence") or 0.0) < filters.min_ai_confidence:
                    return False
            except (TypeError, ValueError):
                return False
        if filters.recipient_types:
            brief = str(contact.get("research_brief_json") or "").lower()
            if not any(recipient_type in brief for recipient_type in filters.recipient_types):
                return False
        return _contains(contact, filters.search)

    @staticmethod
    def _sort_key(item: ReviewQueueItem, order_by: str) -> tuple[Any, ...]:
        contact = item.contact
        priority_score = int(item.priority["score"])
        contact_id = int(contact.get("id") or 0)
        status_rank = {
            "pending_review": 0,
            "approved": 1,
            "new": 2,
            "dry_run_sent": 3,
            "sent": 4,
            "failed": 5,
        }.get(str(contact.get("status") or ""), 9)
        if order_by == ORDER_NEW:
            return (status_rank, contact_id)
        if order_by == ORDER_AI_CONFIDENCE:
            return (-_float(contact.get("ai_confidence")), -priority_score, contact_id)
        if order_by == ORDER_CHANNEL:
            return (str(contact.get("channel") or "email"), -priority_score, contact_id)
        if order_by == ORDER_LAST_ACTIVITY:
            return (str(contact.get("updated_at") or contact.get("created_at") or ""), -priority_score, contact_id)
        return (-priority_score, status_rank, contact_id)


def normalize_order(value: Any) -> str:
    order = str(value or ORDER_PRIORITY).strip().lower()
    return order if order in ORDER_OPTIONS else ORDER_PRIORITY


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
