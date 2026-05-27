from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .result_schema import EmailDraftInput, EmailDraftResult


class AIProviderError(RuntimeError):
    pass


@dataclass(slots=True)
class AIConnectionCheckResult:
    ok: bool
    message: str


class BaseAIProvider(Protocol):
    def generate_email_draft(self, input_data: EmailDraftInput) -> EmailDraftResult:
        ...

    def check_connection(self) -> AIConnectionCheckResult:
        ...
