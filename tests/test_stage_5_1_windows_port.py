from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import credential_store
from src.app_metadata import APP_VERSION
from src.credential_store import WindowsCredentialStore
from src.platform_actions import is_safe_external_url
from src.platform_utils import ensure_app_dirs, get_app_data_dir, get_cache_dir


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_windows_app_data_path_resolution_and_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    appdata = tmp_path / "Roaming"
    path = get_app_data_dir(platform_name="win32", os_name="nt", env={"APPDATA": str(appdata)}, home=tmp_path)

    assert path == appdata / "Gmail Рассылка"

    override = tmp_path / "override"
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(override))
    dirs = ensure_app_dirs()
    assert dirs["cache"] == get_cache_dir()
    assert (override / "cache").is_dir()


def test_windows_credential_manager_backend_uses_windows_vault_without_secret_in_args(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(args, *, input_text=None, env=None):
        calls.append({"args": args, "input_text": input_text, "env": env or {}})
        return SimpleNamespace(returncode=0, stdout="stored-secret\r\n", stderr="")

    monkeypatch.setattr(credential_store.os, "name", "nt", raising=False)
    monkeypatch.setattr(credential_store.shutil, "which", lambda name: "powershell.exe")
    monkeypatch.setattr(credential_store, "_run_command", fake_run)

    store = WindowsCredentialStore(service_name="stage51.service")
    store.set_password("User@Example.com", "super-secret-value")
    assert store.get_password("User@Example.com") == "stored-secret"
    store.delete_password("User@Example.com")

    set_call = calls[0]
    assert "super-secret-value" not in " ".join(str(part) for part in set_call["args"])
    assert "super-secret-value" not in str(set_call["input_text"])
    assert set_call["env"]["OUTREACH_CREDENTIAL_VALUE"] == "super-secret-value"
    assert store.backend_name == "Windows Credential Manager"


def test_windows_scripts_launchers_spec_and_icon_exist() -> None:
    expected = [
        "scripts/windows/setup_windows.ps1",
        "scripts/windows/run_windows.ps1",
        "scripts/windows/test_windows.ps1",
        "scripts/windows/build_windows.ps1",
        "scripts/windows/package_windows.ps1",
        "scripts/windows/smoke_windows.ps1",
        "launchers/windows/Gmail Рассылка.bat",
        "launchers/windows/Gmail Рассылка.ps1",
        "packaging/windows/Gmail Рассылка Windows.spec",
        "resources/icons/app_icon.ico",
        "docs/WINDOWS_INSTALL.md",
        "docs/STAGE_5_1_WINDOWS_PORT.md",
    ]

    for relative in expected:
        assert (PROJECT_ROOT / relative).exists(), relative

    assert (PROJECT_ROOT / "resources/icons/app_icon.ico").stat().st_size > 1024


def test_windows_build_and_package_scripts_are_safe_and_versioned() -> None:
    build = (PROJECT_ROOT / "scripts/windows/build_windows.ps1").read_text(encoding="utf-8")
    package = (PROJECT_ROOT / "scripts/windows/package_windows.ps1").read_text(encoding="utf-8")
    smoke = (PROJECT_ROOT / "scripts/windows/smoke_windows.ps1").read_text(encoding="utf-8")
    spec = (PROJECT_ROOT / "packaging/windows/Gmail Рассылка Windows.spec").read_text(encoding="utf-8")

    assert "qwindows.dll" in build
    assert "app_icon.ico" in build
    assert "dist\\windows" in build and "$AppName" in build
    assert "$AppName-$Version-windows.zip" in package
    assert ".env" in package and "outreach.sqlite" in package
    assert "OUTREACH_AUTOMATION_SMOKE_EXIT_MS" in smoke
    assert "OUTREACH_AUTOMATION_CREDENTIAL_BACKEND" in smoke
    assert "PySide6.QtWidgets" in spec
    assert "resources/icons/app_icon.png" in spec


def test_cross_platform_open_profile_abstraction_is_used_in_gui() -> None:
    assert is_safe_external_url("https://example.com/profile")
    assert not is_safe_external_url("file:///etc/passwd")
    assert not is_safe_external_url("javascript:alert(1)")

    gui_sources = [
        PROJECT_ROOT / "src/gui/campaign_view.py",
        PROJECT_ROOT / "src/gui/intelligence_views.py",
    ]
    for path in gui_sources:
        text = path.read_text(encoding="utf-8")
        assert "open_external_url" in text
        assert "QDesktopServices" not in text
        assert "os.startfile" not in text


def test_windows_package_docs_for_non_technical_user() -> None:
    guide = (PROJECT_ROOT / "docs/WINDOWS_INSTALL.md").read_text(encoding="utf-8")
    assert "double-click" in guide.lower()
    assert "%APPDATA%\\Gmail Рассылка" in guide
    assert "SmartScreen" in guide
    assert "Never share Gmail App Passwords" in guide


def test_version_bumped_to_5_1_0() -> None:
    assert APP_VERSION == "5.1.1"
