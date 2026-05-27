#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.app_metadata import APP_VERSION, APP_NAME  # noqa: E402


FORBIDDEN_NAMES = {
    ".env",
    ".venv",
    "data",
    "logs",
    "exports",
    "imports",
    "cache",
    "credentials",
    "backups",
    "outreach.sqlite",
    "gmail_credentials.enc",
    ".credential_key",
}
FORBIDDEN_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".log"}
TEXT_SUFFIXES = {
    ".bat",
    ".cfg",
    ".csv",
    ".env",
    ".ini",
    ".json",
    ".md",
    ".ps1",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SECRET_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "sk-proj-",
    "sk-live-",
    "xoxb-",
    "GMAIL_APP_PASSWORD=",
    "TELEGRAM_BOT_TOKEN=",
)


@dataclass(slots=True)
class ArtifactRecord:
    platform: str
    path: str
    exists: bool
    required: bool
    size_bytes: int | None = None
    sha256: str | None = None
    checksum_path: str | None = None
    validation_status: str = "missing"
    warnings: list[str] | None = None


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_checksum(path: Path, digest: str) -> Path:
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return checksum_path


def _is_forbidden_path(parts: tuple[str, ...]) -> bool:
    lowered = [part.strip().lower() for part in parts if part.strip()]
    if any(part in FORBIDDEN_NAMES for part in lowered):
        return True
    return any(Path(part).suffix.lower() in FORBIDDEN_SUFFIXES for part in lowered)


def _scan_text_for_secret(name: str, data: bytes) -> str | None:
    suffix = Path(name).suffix.lower()
    if suffix not in TEXT_SUFFIXES or len(data) > 1024 * 1024:
        return None
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return None
    for marker in SECRET_MARKERS:
        if marker in text:
            return marker
    return None


def _validate_zip(path: Path) -> list[str]:
    warnings: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            parts = tuple(part for part in Path(info.filename).parts if part not in {"", "."})
            if _is_forbidden_path(parts):
                raise RuntimeError(f"Release ZIP contains forbidden runtime/secrets path: {info.filename}")
            if not info.is_dir() and info.file_size <= 1024 * 1024:
                marker = _scan_text_for_secret(info.filename, archive.read(info))
                if marker:
                    raise RuntimeError(f"Release ZIP contains secret-like marker in {info.filename}: {marker}")
    return warnings


def _validate_app_bundle_near_dmg(dmg_path: Path) -> list[str]:
    warnings: list[str] = []
    app_bundle = dmg_path.parent / f"{APP_NAME}.app"
    if not app_bundle.exists():
        return ["macOS app bundle not found next to DMG; DMG content was smoke-tested separately"]
    for child in app_bundle.rglob("*"):
        rel_parts = child.relative_to(app_bundle).parts
        if _is_forbidden_path(rel_parts):
            raise RuntimeError(f"macOS app bundle contains forbidden runtime/secrets path: {_rel(child)}")
    return warnings


def _artifact_record(platform: str, path: Path, *, required: bool) -> ArtifactRecord:
    record = ArtifactRecord(platform=platform, path=_rel(path), exists=path.exists(), required=required, warnings=[])
    if not path.exists():
        return record
    digest = _sha256(path)
    checksum_path = _write_checksum(path, digest)
    record.size_bytes = path.stat().st_size
    record.sha256 = digest
    record.checksum_path = _rel(checksum_path)
    record.validation_status = "validated"
    return record


def _copy_asset(path: Path, asset_dir: Path) -> None:
    if not path.exists():
        return
    destination = asset_dir / path.name
    if path.resolve() == destination.resolve():
        return
    shutil.copy2(path, destination)


def build_manifest(args: argparse.Namespace) -> tuple[dict[str, object], int]:
    version = args.version
    macos_dmg = Path(args.macos_dmg or PROJECT_ROOT / "dist" / f"{APP_NAME}-{version}.dmg")
    windows_zip = Path(args.windows_zip or PROJECT_ROOT / "dist" / "windows" / f"{APP_NAME}-{version}-windows.zip")
    notes_path = PROJECT_ROOT / "docs" / f"RELEASE_NOTES_{version.replace('.', '_')}.md"

    mac_required = not args.allow_missing_macos
    win_required = not args.allow_missing_windows
    records = [
        _artifact_record("macos", macos_dmg, required=mac_required),
        _artifact_record("windows", windows_zip, required=win_required),
    ]
    exit_code = 0

    for record in records:
        path = PROJECT_ROOT / record.path
        if record.required and not record.exists:
            record.validation_status = "missing-required"
            exit_code = 1
        if record.exists:
            if record.platform == "windows":
                record.warnings = _validate_zip(path)
            if record.platform == "macos":
                record.warnings = _validate_app_bundle_near_dmg(path)

    supported_platforms = [
        {"platform": record.platform, "artifact": record.path, "status": record.validation_status}
        for record in records
    ]
    manifest: dict[str, object] = {
        "version": version,
        "build_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app_name": APP_NAME,
        "supported_platforms": supported_platforms,
        "artifacts": [asdict(record) for record in records],
        "checksums": {
            record.platform: {"sha256": record.sha256, "file": record.checksum_path}
            for record in records
            if record.sha256
        },
        "smoke_status": args.smoke_status,
        "tests_passed_count": args.tests_passed,
        "safety": {
            "no_secrets_policy": True,
            "runtime_data_excluded": True,
            "autosend_enabled": False,
            "unsafe_social_automation": False,
        },
        "github_release": {
            "tag": f"v{version}",
            "title": f"v{version}",
            "notes_file": _rel(notes_path),
            "draft_recommended": True,
            "upload_ready": all(record.exists for record in records if record.required),
        },
    }

    output_path = Path(args.output or PROJECT_ROOT / "dist" / "release_manifest.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.asset_dir:
        asset_dir = Path(args.asset_dir)
        asset_dir.mkdir(parents=True, exist_ok=True)
        for record in records:
            artifact_path = PROJECT_ROOT / record.path
            _copy_asset(artifact_path, asset_dir)
            if record.checksum_path:
                _copy_asset(PROJECT_ROOT / record.checksum_path, asset_dir)
        _copy_asset(output_path, asset_dir)
        _copy_asset(notes_path, asset_dir)

    print(f"Release manifest written: {_rel(output_path)}")
    for record in records:
        state = "OK" if record.exists else ("MISSING" if record.required else "SKIPPED")
        print(f"- {record.platform}: {state} {record.path}")
        if record.checksum_path:
            print(f"  checksum: {record.checksum_path}")
    return manifest, exit_code


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate release artifacts and generate release manifest.")
    parser.add_argument("--version", default=APP_VERSION)
    parser.add_argument("--macos-dmg")
    parser.add_argument("--windows-zip")
    parser.add_argument("--output")
    parser.add_argument("--asset-dir")
    parser.add_argument("--allow-missing-macos", action="store_true")
    parser.add_argument("--allow-missing-windows", action="store_true")
    parser.add_argument("--smoke-status", default="unknown")
    parser.add_argument("--tests-passed", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        _, exit_code = build_manifest(args)
    except Exception as exc:
        print(f"Release validation failed: {exc}", file=sys.stderr)
        return 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
