from __future__ import annotations

from typing import Any

from ..db import Database


class MetricsService:
    def __init__(self, db: Database):
        self.db = db

    def campaign_metrics(self, campaign_id: int) -> dict[str, Any]:
        stats = self.db.get_stats(campaign_id)
        replies = self.db.fetch_one(
            "SELECT COUNT(*) AS count FROM replies WHERE campaign_id = ?",
            (campaign_id,),
        )
        ai = self.db.fetch_one(
            """
            SELECT
                COUNT(*) AS ai_drafts,
                AVG(ai_confidence) AS avg_confidence
            FROM contacts
            WHERE campaign_id = ? AND ai_generated = 1
            """,
            (campaign_id,),
        )
        blacklist = self.db.fetch_one("SELECT COUNT(*) AS count FROM blacklist")
        channel_rows = self.db.fetch_all(
            """
            SELECT channel, COUNT(*) AS count
            FROM contacts
            WHERE campaign_id = ?
            GROUP BY channel
            ORDER BY count DESC
            """,
            (campaign_id,),
        )
        response_status_rows = self.db.fetch_all(
            """
            SELECT reply_status, COUNT(*) AS count
            FROM replies
            WHERE campaign_id = ?
            GROUP BY reply_status
            ORDER BY count DESC
            """,
            (campaign_id,),
        )
        lead_status_rows = self.db.fetch_all(
            """
            SELECT lead_status, COUNT(*) AS count
            FROM conversation_threads
            WHERE campaign_id = ?
            GROUP BY lead_status
            ORDER BY count DESC
            """,
            (campaign_id,),
        )
        followup_suggestions = self.db.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM followup_suggestions
            WHERE campaign_id = ? AND status = 'suggested'
            """,
            (campaign_id,),
        )
        sent = int(stats.get("sent", 0))
        total = int(stats.get("total", 0))
        reply_count = int((replies or {}).get("count") or 0)
        approved = int(stats.get("approved", 0))
        lead_statuses = {row["lead_status"]: int(row["count"]) for row in lead_status_rows}
        warm_leads = sum(lead_statuses.get(status, 0) for status in ("Warm", "Interested", "Negotiating", "Closed"))
        interested = sum(lead_statuses.get(status, 0) for status in ("Interested", "Negotiating", "Closed"))
        return {
            "recipients": total,
            "ai_drafts": int((ai or {}).get("ai_drafts") or 0),
            "approved": approved,
            "sent": sent,
            "dry_run": int(stats.get("dry_run_sent", 0)),
            "errors": int(stats.get("failed", 0)),
            "replies": reply_count,
            "blacklist": int((blacklist or {}).get("count") or 0),
            "ai_confidence_average": round(float((ai or {}).get("avg_confidence") or 0), 2),
            "reply_rate": round(reply_count / sent, 2) if sent else 0,
            "approval_rate": round(approved / total, 2) if total else 0,
            "warm_lead_rate": round(warm_leads / total, 2) if total else 0,
            "interested_rate": round(interested / total, 2) if total else 0,
            "followup_suggestions": int((followup_suggestions or {}).get("count") or 0),
            "channel_breakdown": {row["channel"]: int(row["count"]) for row in channel_rows},
            "response_statuses": {
                row["reply_status"]: int(row["count"]) for row in response_status_rows
            },
            "lead_statuses": lead_statuses,
        }

    def persist_campaign_metrics(self, campaign_id: int) -> dict[str, Any]:
        metrics = self.campaign_metrics(campaign_id)
        for key, value in metrics.items():
            if isinstance(value, dict):
                metric_value = str(value)
            else:
                metric_value = str(value)
            self.db.execute(
                """
                INSERT INTO campaign_metrics (campaign_id, metric_key, metric_value)
                VALUES (?, ?, ?)
                ON CONFLICT(campaign_id, metric_key) DO UPDATE SET
                    metric_value = excluded.metric_value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (campaign_id, key, metric_value),
            )
        return metrics
