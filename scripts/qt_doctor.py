#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _reexec_with_venv_python() -> None:
    venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return
    if Path(sys.executable).resolve() == venv_python.resolve():
        return
    os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])


def _plugins_path() -> Path:
    from PySide6.QtCore import QLibraryInfo

    library_path = getattr(QLibraryInfo, "LibraryPath", QLibraryInfo)
    plugins_key = getattr(library_path, "PluginsPath", None)
    if plugins_key is None:
        plugins_key = getattr(QLibraryInfo, "PluginsPath")
    return Path(QLibraryInfo.path(plugins_key))


def main() -> int:
    _reexec_with_venv_python()
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")

    try:
        import PySide6

        plugin_path = _plugins_path()
    except Exception as exc:
        print(f"PySide6 version: unavailable")
        print(f"PySide6 import error: {exc}")
        print(f"Qt plugin path: unavailable")
        print(f"Platforms path: unavailable")
        print("Exists libqcocoa.dylib: false")
        print(f"Current QT_PLUGIN_PATH: {os.environ.get('QT_PLUGIN_PATH', '')}")
        print(
            "Current QT_QPA_PLATFORM_PLUGIN_PATH: "
            f"{os.environ.get('QT_QPA_PLATFORM_PLUGIN_PATH', '')}"
        )
        print(f"Current QT_QPA_PLATFORM: {os.environ.get('QT_QPA_PLATFORM', '')}")
        return 1

    platforms_path = plugin_path / "platforms"
    cocoa_plugin = platforms_path / "libqcocoa.dylib"

    print(f"PySide6 version: {PySide6.__version__}")
    print(f"PySide6 location: {Path(PySide6.__file__).resolve()}")
    print(f"Qt plugin path: {plugin_path}")
    print(f"Platforms path: {platforms_path}")
    print(f"Exists libqcocoa.dylib: {str(cocoa_plugin.exists()).lower()}")
    print(f"Current QT_PLUGIN_PATH: {os.environ.get('QT_PLUGIN_PATH', '')}")
    print(
        "Current QT_QPA_PLATFORM_PLUGIN_PATH: "
        f"{os.environ.get('QT_QPA_PLATFORM_PLUGIN_PATH', '')}"
    )
    print(f"Current QT_QPA_PLATFORM: {os.environ.get('QT_QPA_PLATFORM', '')}")

    return 0 if cocoa_plugin.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
