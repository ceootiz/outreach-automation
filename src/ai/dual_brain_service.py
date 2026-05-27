from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .brain_config import BrainConfig
from .provider import AIProviderError
from .research_brain import BaseResearchBrain, OpenAIResearchBrain
from .research_schema import RecipientBrief, RecipientResearchInput
from .writer_brain import BaseWriterBrain, OpenAIWriterBrain
from .writer_schema import DraftWritingInput, WriterDraft
from ..enrichment import parse_enrichment_result


ResearchBrainFactory = Callable[[str, str], BaseResearchBrain]
WriterBrainFactory = Callable[[str, str], BaseWriterBrain]


@dataclass(slots=True)
class DualBrainResult:
    brief: RecipientBrief
    draft: WriterDraft


class DualBrainService:
    def __init__(
        self,
        research_factory: ResearchBrainFactory | None = None,
        writer_factory: WriterBrainFactory | None = None,
    ):
        self.research_factory = research_factory or self._default_research_factory
        self.writer_factory = writer_factory or self._default_writer_factory

    def _default_research_factory(self, provider: str, model: str) -> BaseResearchBrain:
        if provider == "openai":
            return OpenAIResearchBrain(model=model)
        raise AIProviderError("Research Brain выключен. Выберите OpenAI в настройках AI Assist.")

    def _default_writer_factory(self, provider: str, model: str) -> BaseWriterBrain:
        if provider == "openai":
            return OpenAIWriterBrain(model=model)
        raise AIProviderError("Writer Brain выключен. Выберите OpenAI в настройках AI Assist.")

    def research_contact(
        self,
        contact: dict,
        campaign_topic: str,
        *,
        config: BrainConfig,
    ) -> RecipientBrief:
        input_data = self._research_input(contact, campaign_topic)
        return self.research_factory(config.provider, config.model).research_contact(input_data)

    def write_from_brief(
        self,
        contact: dict,
        campaign_topic: str,
        tone: str,
        brief: RecipientBrief,
        *,
        config: BrainConfig,
        execution_mode: str = "dry_run",
        execution_notes: str = "",
    ) -> WriterDraft:
        input_data = DraftWritingInput(
            contact_id=contact.get("id"),
            email=str(contact.get("email") or ""),
            channel=str(contact.get("channel") or "email"),
            campaign_topic=campaign_topic,
            tone=tone,
            recipient_brief=brief,
            name=str(contact.get("name") or ""),
            company=str(contact.get("company") or ""),
            website=str(contact.get("website") or ""),
            social_profile=str(contact.get("social_profile") or ""),
            note=str(contact.get("topic") or ""),
            execution_mode=execution_mode,
            execution_notes=execution_notes,
        )
        return self.writer_factory(config.provider, config.model).write_draft(input_data)

    def generate(
        self,
        contact: dict,
        campaign_topic: str,
        tone: str,
        *,
        research_config: BrainConfig,
        writer_config: BrainConfig,
        execution_mode: str = "dry_run",
        execution_notes: str = "",
    ) -> DualBrainResult:
        brief = self.research_contact(contact, campaign_topic, config=research_config)
        draft = self.write_from_brief(
            contact,
            campaign_topic,
            tone,
            brief,
            config=writer_config,
            execution_mode=execution_mode,
            execution_notes=execution_notes,
        )
        return DualBrainResult(brief=brief, draft=draft)

    @staticmethod
    def _research_input(contact: dict, campaign_topic: str) -> RecipientResearchInput:
        email = str(contact.get("email") or "")
        domain = email.split("@", 1)[1] if "@" in email else ""
        enrichment = parse_enrichment_result(contact.get("enrichment_result_json") or "")
        return RecipientResearchInput(
            contact_id=contact.get("id"),
            email=email,
            email_domain=domain,
            name=str(contact.get("name") or ""),
            company=str(contact.get("company") or ""),
            website=str(contact.get("website") or ""),
            social_profile=str(contact.get("social_profile") or ""),
            channel=str(contact.get("channel") or "email"),
            note=str(contact.get("topic") or ""),
            campaign_topic=campaign_topic,
            enrichment_result=enrichment.to_dict() if enrichment.status != "skipped" else {},
        )
