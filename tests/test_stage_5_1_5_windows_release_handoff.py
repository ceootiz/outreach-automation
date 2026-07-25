from __future__ import annotations

from pathlib import Path

from src import db_safety


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_database_integrity_check_closes_connection(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "outreach.sqlite"
    db_path.write_bytes(b"placeholder")
    state = {"closed": False}

    class Cursor:
        def fetchone(self):
            return ("ok",)

    class Connection:
        def execute(self, _query: str):
            return Cursor()

        def close(self) -> None:
            state["closed"] = True

    monkeypatch.setattr(db_safety.sqlite3, "connect", lambda _path: Connection())

    result = db_safety.check_database_integrity(db_path)

    assert result.ok is True
    assert state["closed"] is True


def test_windows_package_includes_tester_and_codex_handoff() -> None:
    script = (PROJECT_ROOT / "scripts/windows/package_windows.ps1").read_text(encoding="utf-8")

    assert "README_TESTER_RU.txt" in script
    assert "WINDOWS_CODEX_HANDOFF_RU.md" in script
    assert "CODEX_WINDOWS_HANDOFF_RU.md" in script


def test_windows_package_checks_full_runtime_forbidden_set() -> None:
    script = (PROJECT_ROOT / "scripts/windows/package_windows.ps1").read_text(encoding="utf-8")

    for forbidden in (
        ".env",
        ".venv",
        "data",
        "logs",
        "exports",
        "imports",
        "cache",
        "credentials",
        "backups",
        ".sqlite",
        ".sqlite3",
        ".db",
        ".log",
    ):
        assert forbidden in script


def test_windows_handoff_has_safety_and_verification_checklist() -> None:
    handoff = (PROJECT_ROOT / "docs/WINDOWS_CODEX_HANDOFF_RU.md").read_text(encoding="utf-8")
    tester_readme = (PROJECT_ROOT / "README_TESTER_RU.txt").read_text(encoding="utf-8")

    assert "Не выполнять live send" in handoff
    assert "test_windows.ps1" in handoff
    assert "smoke_windows.ps1" in handoff
    assert "PROFILE AFTER RESTART" in handoff
    assert "CODEX_WINDOWS_HANDOFF_RU.md" in tester_readme
