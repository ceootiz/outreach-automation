from __future__ import annotations

import re
from typing import Mapping

from .models import GeneratedEmail


VARIABLE_RE = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


class TemplateEngine:
    allowed_variables = {"name", "company", "topic", "base_message"}

    def render(self, template: str, context: Mapping[str, object]) -> str:
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in self.allowed_variables:
                return match.group(0)
            return str(context.get(key) or "")

        return VARIABLE_RE.sub(replace, template or "").strip()

    def render_email(
        self,
        contact: Mapping[str, object],
        subject_template: str,
        body_template: str,
    ) -> GeneratedEmail:
        context = {
            "name": contact.get("name") or "",
            "company": contact.get("company") or "",
            "topic": contact.get("topic") or "",
            "base_message": contact.get("base_message") or "",
        }
        subject_source = str(contact.get("subject") or subject_template or "")
        body_source = str(contact.get("generated_message") or body_template or contact.get("base_message") or "")
        return GeneratedEmail(
            subject=self.render(subject_source, context),
            body=self.render(body_source, context),
        )
