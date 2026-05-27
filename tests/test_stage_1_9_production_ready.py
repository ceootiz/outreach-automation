from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest

from src.app_metadata import get_app_metadata
from src.campaign_service import CampaignService
from src.crash_handler import handle_exception
from src.db import Database
from src.db_safety import DatabaseRecoveryError, backup_database, prepare_database
from src.platform_utils import (
    ensure_app_dirs,
    get_app_data_dir,
    get_backups_dir,
    get_exports_dir,
    get_logs_dir,
)


def test_platform_dirs_resolve_and_auto_create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(tmp_path / "Gmail Рассылка"))

    paths = ensure_app_dirs()

    assert get_app_data_dir() == tmp_path / "Gmail Рассылка"
    assert paths["data"].is_dir()
    assert paths["exports"].is_dir()
    assert paths["imports"].is_dir()
    assert paths["logs"].is_dir()
    assert paths["backups"].is_dir()


def test_backup_rotation_keeps_latest_files(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "outreach.sqlite"
    backups_dir = tmp_path / "backups"
    db_path.parent.mkdir()
    db_path.write_text("one", encoding="utf-8")

    for index in range(4):
        db_path.write_text(f"content-{index}", encoding="utf-8")
        backup_database(db_path, backups_dir, reason=f"test_{index}", keep=2)

    backups = sorted(backups_dir.glob("*.sqlite"))
    assert len(backups) == 2
    assert all("test_" in backup.name for backup in backups)


def test_corrupt_database_gets_recovery_backup(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "outreach.sqlite"
    backups_dir = tmp_path / "backups"
    db_path.parent.mkdir()
    db_path.write_bytes(b"not a sqlite database")

    with pytest.raises(DatabaseRecoveryError) as exc:
        prepare_database(db_path, backups_dir)

    assert exc.value.recovery_backup is not None
    assert exc.value.recovery_backup.exists()
    assert list(db_path.parent.glob("outreach.corrupt.*.sqlite"))


def test_onboarding_state_persists(tmp_path: Path) -> None:
    db = Database(tmp_path / "outreach.sqlite")
    db.initialize()
    service = CampaignService(db)

    assert service.settings()["onboarding_completed"] == "false"
    service.save_settings({"onboarding_completed": "true"})
    assert service.settings()["onboarding_completed"] == "true"


def test_app_metadata_and_resources_exist() -> None:
    metadata = get_app_metadata()

    assert metadata.name == "Gmail Рассылка"
    assert metadata.version
    assert metadata.bundle_id
    assert Path("resources/icons/app_icon.png").exists()
    assert Path("resources/icons/app_icon.icns").exists()


def test_build_scripts_exist_and_are_executable() -> None:
    for script in (Path("scripts/build_macos.sh"), Path("scripts/build_dmg.sh")):
        assert script.exists()
        mode = script.stat().st_mode
        assert mode & stat.S_IXUSR
        text = script.read_text(encoding="utf-8")
        assert "Gmail Рассылка" in text


def test_no_developer_only_default_data_paths_remain() -> None:
    from src import config

    project_root = Path(__file__).resolve().parents[1]
    assert project_root not in config.DATA_DIR.parents
    assert project_root not in config.EXPORTS_DIR.parents
    assert project_root not in config.LOGS_DIR.parents


def test_exports_and_logs_dirs_are_configurable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(tmp_path / "runtime"))

    assert get_exports_dir() == tmp_path / "runtime" / "exports"
    assert get_logs_dir() == tmp_path / "runtime" / "logs"
    assert get_backups_dir() == tmp_path / "runtime" / "backups"


def test_crash_handler_callable_without_leaking_traceback(tmp_path: Path) -> None:
    logger = logging.getLogger("stage_1_9_crash_test")
    logger.handlers.clear()
    log_path = tmp_path / "crash.log"
    logger.addHandler(logging.FileHandler(log_path, encoding="utf-8"))
    logger.setLevel(logging.ERROR)

    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        message = handle_exception(type(exc), exc, exc.__traceback__, logger=logger, show_dialog=False)

    assert "Приложение столкнулось с ошибкой" in message
    assert "RuntimeError: boom" in log_path.read_text(encoding="utf-8")
