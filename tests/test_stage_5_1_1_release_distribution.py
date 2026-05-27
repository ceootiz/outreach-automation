from __future__ import annotations

import importlib.util
import json
import stat
import sys
import zipfile
from pathlib import Path

from src.app_metadata import APP_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = PROJECT_ROOT / "scripts" / "release" / "validate_release.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("release_validator", VALIDATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _safe_windows_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Gmail Рассылка/Gmail Рассылка.exe", b"fake exe")
        archive.writestr("WINDOWS_INSTALL.md", "double-click Gmail Рассылка.exe")
        archive.writestr("Gmail Рассылка.ps1", "Write-Host 'launch'")


def test_release_scripts_docs_and_version_exist() -> None:
    expected = [
        "scripts/release/prepare_release.sh",
        "scripts/release/prepare_release.ps1",
        "scripts/release/github_release.sh",
        "scripts/release/github_release.ps1",
        "scripts/release/validate_release.py",
        "docs/RELEASE_PROCESS.md",
        "docs/RELEASE_NOTES_5_1_1.md",
    ]

    for relative in expected:
        assert (PROJECT_ROOT / relative).exists(), relative

    for relative in ("scripts/release/prepare_release.sh", "scripts/release/github_release.sh"):
        mode = (PROJECT_ROOT / relative).stat().st_mode
        assert mode & stat.S_IXUSR

    assert APP_VERSION == "5.1.1"


def test_release_validator_generates_manifest_checksums_and_assets(tmp_path: Path) -> None:
    validator = _load_validator()
    macos_dmg = tmp_path / "Gmail Рассылка-5.1.1.dmg"
    windows_zip = tmp_path / "Gmail Рассылка-5.1.1-windows.zip"
    output = tmp_path / "release_manifest.json"
    asset_dir = tmp_path / "assets"

    macos_dmg.write_bytes(b"fake dmg")
    app_bundle = tmp_path / "Gmail Рассылка.app" / "Contents" / "MacOS"
    app_bundle.mkdir(parents=True)
    (app_bundle / "Gmail Рассылка").write_bytes(b"fake app")
    _safe_windows_zip(windows_zip)

    result = validator.main(
        [
            "--version",
            "5.1.1",
            "--macos-dmg",
            str(macos_dmg),
            "--windows-zip",
            str(windows_zip),
            "--output",
            str(output),
            "--asset-dir",
            str(asset_dir),
            "--smoke-status",
            "passed",
            "--tests-passed",
            "302",
        ]
    )

    assert result == 0
    assert macos_dmg.with_suffix(".dmg.sha256").exists()
    assert windows_zip.with_suffix(".zip.sha256").exists()
    assert (asset_dir / macos_dmg.name).exists()
    assert (asset_dir / windows_zip.name).exists()
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["version"] == "5.1.1"
    assert manifest["smoke_status"] == "passed"
    assert manifest["tests_passed_count"] == 302
    assert manifest["github_release"]["tag"] == "v5.1.1"
    assert manifest["safety"]["autosend_enabled"] is False


def test_release_validator_rejects_runtime_data_in_windows_zip(tmp_path: Path) -> None:
    validator = _load_validator()
    bad_zip = tmp_path / "Gmail Рассылка-5.1.1-windows.zip"
    with zipfile.ZipFile(bad_zip, "w") as archive:
        archive.writestr("Gmail Рассылка/.env", "GMAIL_APP_PASSWORD=secret")

    result = validator.main(
        [
            "--version",
            "5.1.1",
            "--windows-zip",
            str(bad_zip),
            "--allow-missing-macos",
            "--output",
            str(tmp_path / "manifest.json"),
        ]
    )

    assert result == 1


def test_release_docs_are_draft_first_and_secret_safe() -> None:
    process = (PROJECT_ROOT / "docs" / "RELEASE_PROCESS.md").read_text(encoding="utf-8")
    notes = (PROJECT_ROOT / "docs" / "RELEASE_NOTES_5_1_1.md").read_text(encoding="utf-8")
    github_sh = (PROJECT_ROOT / "scripts" / "release" / "github_release.sh").read_text(encoding="utf-8")
    github_ps1 = (PROJECT_ROOT / "scripts" / "release" / "github_release.ps1").read_text(encoding="utf-8")

    assert "Do not upload if the remote points to the wrong repository" in process
    assert "No autosend" in notes
    assert "--create-draft" in github_sh
    assert "-CreateDraft" in github_ps1
    assert "gh release create" in github_sh
    assert "gh release create" in github_ps1
