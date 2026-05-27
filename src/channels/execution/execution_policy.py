from __future__ import annotations

from dataclasses import dataclass, field

from .capability_matrix import DRY_RUN, MANUAL_ASSIST, OFFICIAL_API, ChannelCapability, get_channel_capability


EXECUTION_MODE_LABELS = {
    DRY_RUN: "Dry-run",
    OFFICIAL_API: "Official API",
    MANUAL_ASSIST: "Manual Assist",
}


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    ok: bool
    channel: str
    requested_mode: str
    effective_mode: str
    status: str
    message: str = ""
    manual_required: bool = False
    warnings: list[str] = field(default_factory=list)
    capability: ChannelCapability = field(default_factory=lambda: get_channel_capability("email"))


class ExecutionPolicy:
    def capability(self, channel_id: str | None) -> ChannelCapability:
        return get_channel_capability(channel_id)

    def allowed_modes(self, channel_id: str | None) -> tuple[str, ...]:
        return self.capability(channel_id).allowed_execution_modes

    def default_mode(self, channel_id: str | None) -> str:
        capability = self.capability(channel_id)
        return DRY_RUN if DRY_RUN in capability.allowed_execution_modes else capability.allowed_execution_modes[0]

    def normalize_mode(self, channel_id: str | None, requested_mode: str | None) -> str:
        normalized = (requested_mode or "").strip().lower()
        if normalized == "live":
            normalized = OFFICIAL_API
        if normalized == "official":
            normalized = OFFICIAL_API
        if normalized == "manual":
            normalized = MANUAL_ASSIST
        return normalized if normalized in self.allowed_modes(channel_id) else self.default_mode(channel_id)

    def decide(
        self,
        channel_id: str | None,
        requested_mode: str | None,
        *,
        send_mode: str = "dry_run",
        confirm_live_send: bool = False,
    ) -> ExecutionDecision:
        capability = self.capability(channel_id)
        requested = (requested_mode or "").strip().lower() or self.default_mode(capability.channel_id)
        effective = self.normalize_mode(capability.channel_id, requested)

        if requested in {OFFICIAL_API, "live", "official"} and not capability.supports_live_send:
            return ExecutionDecision(
                ok=False,
                channel=capability.channel_id,
                requested_mode=requested,
                effective_mode=MANUAL_ASSIST if capability.requires_manual_assist else DRY_RUN,
                status="blocked",
                message=(
                    "Боевая отправка для этого канала отключена. "
                    "Используйте Manual Assist или dry-run без скрытой автоматизации."
                ),
                manual_required=capability.requires_manual_assist,
                warnings=[capability.limitation_text, capability.risk_explanation],
                capability=capability,
            )

        if effective == OFFICIAL_API and send_mode == "live" and capability.requires_human_confirmation and not confirm_live_send:
            return ExecutionDecision(
                ok=False,
                channel=capability.channel_id,
                requested_mode=requested,
                effective_mode=effective,
                status="blocked",
                message="Live send is blocked until the operator explicitly confirms.",
                manual_required=False,
                warnings=[capability.risk_explanation],
                capability=capability,
            )

        if effective == MANUAL_ASSIST:
            return ExecutionDecision(
                ok=True,
                channel=capability.channel_id,
                requested_mode=requested,
                effective_mode=MANUAL_ASSIST,
                status="manual_required",
                message="Manual Assist подготовит текст и профиль, но ничего не отправит автоматически.",
                manual_required=True,
                warnings=[capability.limitation_text, capability.risk_explanation],
                capability=capability,
            )

        if effective == DRY_RUN:
            return ExecutionDecision(
                ok=True,
                channel=capability.channel_id,
                requested_mode=requested,
                effective_mode=DRY_RUN,
                status="dry_run",
                message="Dry-run: реальные сообщения не отправляются.",
                warnings=[],
                capability=capability,
            )

        return ExecutionDecision(
            ok=True,
            channel=capability.channel_id,
            requested_mode=requested,
            effective_mode=OFFICIAL_API,
            status="official_api",
            message="Official API path. Human confirmation and safe-mode guardrails still apply.",
            warnings=[capability.risk_explanation],
            capability=capability,
        )
