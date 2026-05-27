from __future__ import annotations

import stat
from pathlib import Path

from src.app_metadata import APP_VERSION, get_app_metadata


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _script(name: str) -> Path:
    return PROJECT_ROOT / "scripts" / name


def _is_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & stat.S_IXUSR)


def test_release_docs_exist() -> None:
    checklist = PROJECT_ROOT / "docs" / "RELEASE_CHECKLIST.md"
    notes = PROJECT_ROOT / "docs" / "RELEASE_NOTES_STAGE_1.md"

    assert checklist.exists()
    assert notes.exists()
    assert "Gmail dry-check pending" in checklist.read_text(encoding="utf-8")
    assert "Safety Guardrails" in notes.read_text(encoding="utf-8")


def test_signing_notarization_scripts_exist_and_skip_without_env() -> None:
    sign = _script("sign_macos.sh")
    notarize = _script("notarize_macos.sh")

    assert sign.exists()
    assert notarize.exists()
    assert _is_executable(sign)
    assert _is_executable(notarize)

    sign_text = sign.read_text(encoding="utf-8")
    notarize_text = notarize.read_text(encoding="utf-8")
    assert "DEVELOPER_ID_APP is not set" in sign_text
    assert "NOTARY_APPLE_ID" in notarize_text
    assert "NOTARY_TEAM_ID" in notarize_text
    assert "NOTARY_KEYCHAIN_PROFILE" in notarize_text
    assert "notarytool submit" in notarize_text
    assert "stapler staple" in notarize_text


def test_release_and_secret_audit_scripts_exist() -> None:
    release_smoke = _script("release_smoke.sh")
    no_secrets = _script("check_no_secrets.sh")

    assert release_smoke.exists()
    assert no_secrets.exists()
    assert _is_executable(release_smoke)
    assert _is_executable(no_secrets)
    assert "./scripts/smoke_packaged_app.sh" in release_smoke.read_text(encoding="utf-8")
    assert "./scripts/smoke_dmg.sh" in release_smoke.read_text(encoding="utf-8")
    assert ".env is tracked" in no_secrets.read_text(encoding="utf-8")


def test_build_scripts_call_optional_signing_and_notarization() -> None:
    build_macos = _script("build_macos.sh").read_text(encoding="utf-8")
    build_dmg = _script("build_dmg.sh").read_text(encoding="utf-8")

    assert "./scripts/sign_macos.sh" in build_macos
    assert "./scripts/notarize_macos.sh" in build_dmg


def test_app_metadata_version_exists_for_rc() -> None:
    metadata = get_app_metadata()

    assert APP_VERSION == "5.1.1"
    assert metadata.version == APP_VERSION
    assert metadata.name == "Gmail Рассылка"


def test_readme_mentions_release_candidate_flow() -> None:
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "./scripts/check_no_secrets.sh" in text
    assert "./scripts/release_smoke.sh" in text
    assert "docs/RELEASE_CHECKLIST.md" in text
    assert "docs/RELEASE_NOTES_STAGE_1.md" in text
