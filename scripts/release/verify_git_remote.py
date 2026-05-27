#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_APPROVED_REPOS = {"outreach-automation", "outreach_automation"}
BLOCKED_REMOTE_MARKERS = {"purchase-updater"}


@dataclass(frozen=True, slots=True)
class RemoteCheck:
    ok: bool
    remote_url: str
    repo_name: str
    message: str


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "git command failed").strip())
    return result.stdout.strip()


def get_origin_url() -> str:
    return _run_git(["remote", "get-url", "origin"])


def approved_repo_names() -> set[str]:
    names = set(DEFAULT_APPROVED_REPOS)
    extra = os.getenv("OUTREACH_AUTOMATION_APPROVED_RELEASE_REPOS", "").strip()
    if extra:
        names.update(part.strip().lower() for part in extra.split(",") if part.strip())
    return names


def repo_name_from_url(remote_url: str) -> str:
    cleaned = remote_url.strip()
    if not cleaned:
        return ""
    if cleaned.startswith("git@"):
        match = re.search(r"[:/]([^/:]+?)(?:\.git)?$", cleaned)
        return (match.group(1) if match else "").lower()
    parsed = urlparse(cleaned)
    path = parsed.path or cleaned
    name = Path(path.rstrip("/")).name
    if name.endswith(".git"):
        name = name[:-4]
    return name.lower()


def validate_remote_url(remote_url: str, approved: set[str] | None = None) -> RemoteCheck:
    normalized = remote_url.strip()
    lowered = normalized.lower()
    repo_name = repo_name_from_url(normalized)
    approved_names = approved or approved_repo_names()
    for blocked in BLOCKED_REMOTE_MARKERS:
        if blocked in lowered:
            return RemoteCheck(
                ok=False,
                remote_url=normalized,
                repo_name=repo_name,
                message=(
                    "Blocked wrong GitHub remote: origin points to Purchase-Updater. "
                    "Do not push outreach_automation releases there."
                ),
            )
    if repo_name not in approved_names:
        return RemoteCheck(
            ok=False,
            remote_url=normalized,
            repo_name=repo_name,
            message=(
                f"Blocked unapproved release repo '{repo_name or '<unknown>'}'. "
                f"Allowed repo names: {', '.join(sorted(approved_names))}."
            ),
        )
    return RemoteCheck(
        ok=True,
        remote_url=normalized,
        repo_name=repo_name,
        message=f"Release remote OK: {normalized}",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Git remote before release or push.")
    parser.add_argument("--remote-url", help="Override remote URL for tests or dry-runs.")
    parser.add_argument("--remote-name", default="origin")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        remote_url = args.remote_url or _run_git(["remote", "get-url", args.remote_name])
        check = validate_remote_url(remote_url)
    except Exception as exc:
        print(f"Git remote verification failed: {exc}", file=sys.stderr)
        return 1
    stream = sys.stdout if check.ok else sys.stderr
    print(check.message, file=stream)
    if not check.ok:
        print("Expected remote: https://github.com/ceootiz/outreach-automation.git", file=stream)
        print(
            "If the repo does not exist yet, create it first, then set origin and push.",
            file=stream,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
