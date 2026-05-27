from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_BACKUP_KEEP = 10


class DatabaseRecoveryError(RuntimeError):
    def __init__(self, message: str, recovery_backup: Path | None = None):
        super().__init__(message)
        self.recovery_backup = recovery_backup


@dataclass(frozen=True, slots=True)
class DatabaseCheckResult:
    ok: bool
    message: str
    recovery_backup: Path | None = None


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def backup_database(
    db_path: Path,
    backups_dir: Path,
    reason: str = "manual",
    keep: int = DEFAULT_BACKUP_KEEP,
) -> Path | None:
    db_path = Path(db_path)
    if not db_path.exists() or db_path.stat().st_size == 0:
        return None
    backups_dir.mkdir(parents=True, exist_ok=True)
    safe_reason = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in reason).strip("_")
    backup_path = backups_dir / f"{db_path.stem}_{safe_reason}_{_timestamp()}.sqlite"
    shutil.copy2(db_path, backup_path)
    rotate_backups(backups_dir, keep=keep)
    return backup_path


def rotate_backups(backups_dir: Path, keep: int = DEFAULT_BACKUP_KEEP) -> None:
    if keep <= 0 or not backups_dir.exists():
        return
    backups = sorted(
        backups_dir.glob("*.sqlite"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[keep:]:
        old_backup.unlink(missing_ok=True)


def check_database_integrity(db_path: Path) -> DatabaseCheckResult:
    db_path = Path(db_path)
    if not db_path.exists():
        return DatabaseCheckResult(True, "database missing; will initialize")
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError as exc:
        return DatabaseCheckResult(False, f"database open failed: {exc}")
    message = str(row[0]) if row else "empty integrity result"
    return DatabaseCheckResult(message.lower() == "ok", message)


def prepare_database(
    db_path: Path,
    backups_dir: Path,
    keep: int = DEFAULT_BACKUP_KEEP,
) -> DatabaseCheckResult:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    backups_dir.mkdir(parents=True, exist_ok=True)

    integrity = check_database_integrity(db_path)
    if not integrity.ok:
        recovery = None
        if db_path.exists():
            recovery = backup_database(db_path, backups_dir, reason="recovery_corrupt", keep=keep)
            recovered_path = db_path.with_name(f"{db_path.stem}.corrupt.{_timestamp()}{db_path.suffix}")
            shutil.move(str(db_path), recovered_path)
        raise DatabaseRecoveryError(
            "Локальная база повреждена. Создана recovery-копия, приложение запустит новую базу.",
            recovery,
        )

    backup_database(db_path, backups_dir, reason="startup", keep=keep)
    return integrity
