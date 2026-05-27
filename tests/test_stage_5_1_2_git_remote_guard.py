from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = PROJECT_ROOT / "scripts" / "release" / "verify_git_remote.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("git_remote_guard", GUARD_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_purchase_updater_remote_is_blocked() -> None:
    guard = _load_guard()

    check = guard.validate_remote_url("https://github.com/ceootiz/Purchase-Updater.git")

    assert check.ok is False
    assert "Purchase-Updater" in check.message
    assert check.repo_name == "purchase-updater"


def test_outreach_automation_remotes_are_allowed() -> None:
    guard = _load_guard()

    https_check = guard.validate_remote_url("https://github.com/ceootiz/outreach-automation.git")
    ssh_check = guard.validate_remote_url("git@github.com:ceootiz/outreach_automation.git")

    assert https_check.ok is True
    assert https_check.repo_name == "outreach-automation"
    assert ssh_check.ok is True
    assert ssh_check.repo_name == "outreach_automation"


def test_unknown_repo_name_is_blocked() -> None:
    guard = _load_guard()

    check = guard.validate_remote_url("https://github.com/ceootiz/some-other-tool.git")

    assert check.ok is False
    assert "unapproved" in check.message


def test_release_scripts_call_remote_guard() -> None:
    scripts = [
        PROJECT_ROOT / "scripts" / "release" / "prepare_release.sh",
        PROJECT_ROOT / "scripts" / "release" / "github_release.sh",
        PROJECT_ROOT / "scripts" / "release" / "prepare_release.ps1",
        PROJECT_ROOT / "scripts" / "release" / "github_release.ps1",
    ]

    for path in scripts:
        text = path.read_text(encoding="utf-8")
        assert "verify_git_remote.py" in text
