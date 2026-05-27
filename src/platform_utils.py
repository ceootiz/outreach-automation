from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "Gmail Рассылка"
APP_SUPPORT_ENV = "OUTREACH_AUTOMATION_APP_DIR"


def _home() -> Path:
    return Path.home().expanduser()


def get_app_data_dir(
    *,
    platform_name: str | None = None,
    os_name: str | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    selected_env = env if env is not None else os.environ
    selected_home = home or _home()
    override = selected_env.get(APP_SUPPORT_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    current_platform = platform_name or sys.platform
    current_os = os_name or os.name
    if current_platform == "darwin":
        return selected_home / "Library" / "Application Support" / APP_NAME
    if current_os == "nt" or current_platform.startswith("win"):
        base = Path(selected_env.get("APPDATA", str(selected_home / "AppData" / "Roaming")))
        return base / APP_NAME
    return Path(selected_env.get("XDG_DATA_HOME", str(selected_home / ".local" / "share"))) / APP_NAME


def get_data_dir() -> Path:
    return get_app_data_dir() / "data"


def get_logs_dir() -> Path:
    return get_app_data_dir() / "logs"


def get_exports_dir() -> Path:
    return get_app_data_dir() / "exports"


def get_backups_dir() -> Path:
    return get_app_data_dir() / "backups"


def get_imports_dir() -> Path:
    return get_app_data_dir() / "imports"


def get_cache_dir() -> Path:
    return get_app_data_dir() / "cache"


def ensure_app_dirs() -> dict[str, Path]:
    paths = {
        "app": get_app_data_dir(),
        "data": get_data_dir(),
        "exports": get_exports_dir(),
        "imports": get_imports_dir(),
        "logs": get_logs_dir(),
        "backups": get_backups_dir(),
        "cache": get_cache_dir(),
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / relative_path
