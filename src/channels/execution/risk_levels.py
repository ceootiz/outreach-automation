from __future__ import annotations

from dataclasses import dataclass


LOW = "low"
LOW_MEDIUM = "low_medium"
MEDIUM = "medium"
MEDIUM_HIGH = "medium_high"
HIGH = "high"


@dataclass(frozen=True, slots=True)
class RiskInfo:
    level: str
    label: str
    ui_label: str
    explanation: str


RISK_LEVELS: dict[str, RiskInfo] = {
    LOW: RiskInfo(
        level=LOW,
        label="Low",
        ui_label="Низкий риск",
        explanation="Официальная интеграция с понятными лимитами и подтверждением оператора.",
    ),
    LOW_MEDIUM: RiskInfo(
        level=LOW_MEDIUM,
        label="Low-medium",
        ui_label="Низко-средний риск",
        explanation="Официальная интеграция доступна, но канал требует аккуратных лимитов и явного доступа.",
    ),
    MEDIUM: RiskInfo(
        level=MEDIUM,
        label="Medium",
        ui_label="Средний риск",
        explanation="Автоматизация ограничена. Безопасный путь: dry-run или Manual Assist.",
    ),
    MEDIUM_HIGH: RiskInfo(
        level=MEDIUM_HIGH,
        label="Medium-high",
        ui_label="Средне-высокий риск",
        explanation="Live automation по умолчанию отключена. Используйте Manual Assist и ручное подтверждение.",
    ),
    HIGH: RiskInfo(
        level=HIGH,
        label="High",
        ui_label="Высокий риск",
        explanation="Безопасная автоматическая отправка недоступна. Разрешен только Manual Assist.",
    ),
}


def risk_info(level: str) -> RiskInfo:
    return RISK_LEVELS.get((level or "").strip().lower(), RISK_LEVELS[MEDIUM])


def risk_label(level: str) -> str:
    return risk_info(level).ui_label


def risk_explanation(level: str) -> str:
    return risk_info(level).explanation
