from __future__ import annotations

from typing import Any

from .capability_matrix import DRY_RUN, MANUAL_ASSIST, OFFICIAL_API
from .execution_policy import ExecutionDecision, ExecutionPolicy
from .execution_result import ChannelExecutionResult
from .manual_assist import ManualAssistAction, build_manual_assist_action


class ChannelExecutionEngine:
    def __init__(self, policy: ExecutionPolicy | None = None):
        self.policy = policy or ExecutionPolicy()

    def decide(
        self,
        channel_id: str | None,
        requested_mode: str | None,
        *,
        send_mode: str = "dry_run",
        confirm_live_send: bool = False,
    ) -> ExecutionDecision:
        return self.policy.decide(
            channel_id,
            requested_mode,
            send_mode=send_mode,
            confirm_live_send=confirm_live_send,
        )

    def result_for_contact(
        self,
        contact: dict[str, Any],
        requested_mode: str | None,
        *,
        send_mode: str = "dry_run",
        confirm_live_send: bool = False,
        recipient: str = "",
    ) -> ChannelExecutionResult:
        channel_id = str(contact.get("channel") or "email")
        decision = self.decide(
            channel_id,
            requested_mode,
            send_mode=send_mode,
            confirm_live_send=confirm_live_send,
        )
        recipient_value = recipient or self._recipient(contact)
        action = {
            DRY_RUN: "dry_run_only",
            OFFICIAL_API: "official_api_send",
            MANUAL_ASSIST: "manual_assist_prepare",
        }.get(decision.effective_mode, "blocked")
        return ChannelExecutionResult(
            status=decision.status,
            channel=decision.channel,
            mode=decision.effective_mode,
            recipient=recipient_value,
            action_taken=action,
            manual_required=decision.manual_required,
            warnings=list(decision.warnings),
            risk_level=decision.capability.risk_level,
        )

    def manual_assist_action(self, contact: dict[str, Any]) -> ManualAssistAction:
        return build_manual_assist_action(contact)

    @staticmethod
    def _recipient(contact: dict[str, Any]) -> str:
        for key in ("external_id", "profile_url", "handle", "email"):
            value = str(contact.get(key) or "").strip()
            if value:
                return value
        return ""
