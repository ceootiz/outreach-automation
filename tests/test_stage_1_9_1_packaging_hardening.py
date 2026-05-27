from __future__ import annotations

import stat
from pathlib import Path

from src.app_metadata import APP_VERSION, get_app_metadata


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _script(path: str) -> Path:
    return PROJECT_ROOT / "scripts" / path


def test_packaged_smoke_scripts_exist_and_are_executable() -> None:
    for script_name in ("smoke_packaged_app.sh", "smoke_dmg.sh"):
        script = _script(script_name)
        assert script.exists()
        assert script.stat().st_mode & stat.S_IXUSR
        text = script.read_text(encoding="utf-8")
        assert "OUTREACH_AUTOMATION_APP_DIR" in text
        assert "OUTREACH_AUTOMATION_SMOKE_EXIT_MS" in text
        assert "GMAIL_APP_PASSWORD" not in text


def test_build_scripts_report_sizes_and_verify_runtime_bits() -> None:
    macos_script = _script("build_macos.sh").read_text(encoding="utf-8")
    dmg_script = _script("build_dmg.sh").read_text(encoding="utf-8")

    assert "App size:" in macos_script
    assert "App size:" in dmg_script
    assert "DMG size:" in dmg_script
    assert "libqcocoa.dylib" in macos_script
    assert "app_icon.icns" in macos_script
    assert "Contents/MacOS" in macos_script


def test_pyinstaller_build_is_narrow_and_excludes_are_documented() -> None:
    text = _script("build_macos.sh").read_text(encoding="utf-8")

    assert "--collect-all PySide6" not in text
    assert "Avoid broad PySide6 collection" in text
    assert "--hidden-import PySide6.QtCore" in text
    assert "--hidden-import PySide6.QtGui" in text
    assert "--hidden-import PySide6.QtWidgets" in text
    assert "--exclude-module" in text
    assert "PySide6.QtWebEngineCore" in text
    assert "PySide6.QtQml" in text


def test_signing_notarization_docs_exist() -> None:
    docs = PROJECT_ROOT / "docs" / "MACOS_SIGNING_NOTARIZATION.md"
    text = docs.read_text(encoding="utf-8")

    assert docs.exists()
    assert "Developer ID Application" in text
    assert "notarytool" in text
    assert "stapler" in text
    assert "spctl" in text
    assert ".env" in text


def test_app_metadata_version_available_for_release_artifacts() -> None:
    metadata = get_app_metadata()

    assert APP_VERSION == "5.1.1"
    assert metadata.version == APP_VERSION
    assert metadata.bundle_id


def test_dmg_script_supports_versioned_artifact_name() -> None:
    text = _script("build_dmg.sh").read_text(encoding="utf-8")

    assert "--versioned" in text
    assert "${APP_NAME}-${APP_VERSION}.dmg" in text


def test_readme_mentions_release_smoke_and_signing_docs() -> None:
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "./scripts/smoke_packaged_app.sh" in text
    assert "./scripts/smoke_dmg.sh" in text
    assert "docs/MACOS_SIGNING_NOTARIZATION.md" in text
