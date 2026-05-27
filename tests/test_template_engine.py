from __future__ import annotations

from src.template_engine import TemplateEngine


def test_template_variables_are_replaced() -> None:
    engine = TemplateEngine()

    email = engine.render_email(
        {
            "name": "Maria",
            "company": "Northwind",
            "topic": "creator tools",
            "base_message": "I noticed your creator workflow.",
        },
        "Idea for {{company}}",
        "Hi {{name}}, {{base_message}} Topic: {{topic}}",
    )

    assert email.subject == "Idea for Northwind"
    assert "Hi Maria" in email.body
    assert "I noticed your creator workflow." in email.body
    assert "creator tools" in email.body
