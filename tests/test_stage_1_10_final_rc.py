from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.gui.onboarding import OnboardingDialog


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_stage_completion_doc_exists_and_mentions_core_areas() -> None:
    path = PROJECT_ROOT / "docs" / "STAGE_1_COMPLETE.md"
    assert path.exists()

    text = path.read_text(encoding="utf-8")
    for phrase in (
        "Queue System",
        "Contact State Machine",
        "Dry-Run And Live",
        "Guardrails",
        "Packaging",
        "Future Roadmap",
    ):
        assert phrase in text


def test_readme_has_stage_1_release_candidate_section() -> None:
    text = _read("README.md")

    assert "## Stage 1 Release Candidate" in text
    assert "dist/Gmail Рассылка-5.1.1.dmg" in text
    assert "Тестовый режим" in text
    assert "Разрешенный тестовый получатель" in text
    assert "docs/STAGE_1_COMPLETE.md" in text


def test_release_candidate_docs_exist() -> None:
    assert (PROJECT_ROOT / "docs" / "RELEASE_CHECKLIST.md").exists()
    assert (PROJECT_ROOT / "docs" / "RELEASE_NOTES_STAGE_1.md").exists()

    checklist = _read("docs/RELEASE_CHECKLIST.md")
    notes = _read("docs/RELEASE_NOTES_STAGE_1.md")
    complete = _read("docs/STAGE_1_COMPLETE.md")

    assert "Gmail dry-check pending" in checklist
    assert "Safety Guardrails" in notes
    assert "Stage 1.10 release-candidate validation" in complete


def test_onboarding_dialog_finishes_and_marks_completed() -> None:
    app = _qapp()
    completed = {"value": False}

    dialog = OnboardingDialog(lambda: completed.__setitem__("value", True))
    assert dialog.stack.count() == 5
    assert dialog.windowTitle() == "Добро пожаловать"

    while dialog.stack.currentIndex() < dialog.stack.count() - 1:
        dialog.next()
    dialog.finish()

    assert completed["value"] is True
    assert dialog.result() == dialog.DialogCode.Accepted
    dialog.close()
    app.processEvents()


def test_completion_doc_keeps_stage_one_scope_limited() -> None:
    text = _read("docs/STAGE_1_COMPLETE.md")

    assert "No AI personalization API in Stage 1" in text
    assert "No open/click tracking" in text
    assert "No auto-replies" in text
    assert "No anti-spam bypasses" in text
