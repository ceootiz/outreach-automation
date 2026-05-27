from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Mapping

from .models import GeneratedEmail
from .template_engine import TemplateEngine


class BaseAIProvider(ABC):
    @abstractmethod
    def generate_email(
        self,
        contact: Mapping[str, object],
        subject_template: str,
        body_template: str,
    ) -> GeneratedEmail:
        """Return generated subject/body for a contact."""


class PlaceholderAIProvider(BaseAIProvider):
    """Stage 1 provider: no external AI calls, only deterministic templates."""

    def __init__(self, template_engine: TemplateEngine | None = None):
        self.template_engine = template_engine or TemplateEngine()

    def generate_email(
        self,
        contact: Mapping[str, object],
        subject_template: str,
        body_template: str,
    ) -> GeneratedEmail:
        return self.template_engine.render_email(contact, subject_template, body_template)
