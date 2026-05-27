from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def qt_plugin_path() -> Path:
    library_path = getattr(QLibraryInfo, "LibraryPath", QLibraryInfo)
    plugins_key = getattr(library_path, "PluginsPath", None)
    if plugins_key is None:
        plugins_key = getattr(QLibraryInfo, "PluginsPath")
    return Path(QLibraryInfo.path(plugins_key))


def test_qt_doctor_script_can_run() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/qt_doctor.py"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Python executable:" in result.stdout
    assert "PySide6 version:" in result.stdout
    assert "Qt plugin path:" in result.stdout
    assert "Exists libqcocoa.dylib:" in result.stdout
    assert "GMAIL_APP_PASSWORD" not in result.stdout


def test_run_mac_sets_qt_plugin_paths() -> None:
    text = (PROJECT_ROOT / "scripts" / "run_mac.sh").read_text(encoding="utf-8")

    assert "QT_PLUGIN_PATH" in text
    assert "QT_QPA_PLATFORM_PLUGIN_PATH" in text
    assert "QLibraryInfo.path" in text


def test_run_mac_does_not_force_offscreen_by_default() -> None:
    text = (PROJECT_ROOT / "scripts" / "run_mac.sh").read_text(encoding="utf-8")

    assert "OUTREACH_AUTOMATION_FORCE_OFFSCREEN" in text
    assert "export QT_QPA_PLATFORM=offscreen" in text
    assert "unset QT_QPA_PLATFORM" in text


def test_platform_plugin_path_exists_when_pyside6_installed() -> None:
    plugin_path = qt_plugin_path()
    platforms_path = plugin_path / "platforms"

    assert plugin_path.is_dir()
    assert platforms_path.is_dir()
    if sys.platform == "darwin":
        assert (platforms_path / "libqcocoa.dylib").exists()
