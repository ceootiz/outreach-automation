from __future__ import annotations

import stat
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _script(name: str) -> Path:
    return PROJECT_ROOT / "scripts" / name


def _launcher(name: str) -> Path:
    return PROJECT_ROOT / "launchers" / name


def _is_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & stat.S_IXUSR)


def test_create_launcher_script_exists_and_is_executable() -> None:
    script = _script("create_launcher.sh")

    assert script.exists()
    assert _is_executable(script)


def test_create_launcher_generates_command_launchers() -> None:
    subprocess.run([str(_script("create_launcher.sh"))], cwd=PROJECT_ROOT, check=True)

    main_launcher = _launcher("Gmail Рассылка.command")
    alt_launcher = _launcher("Gmail Рассылка Launcher.command")

    assert main_launcher.exists()
    assert alt_launcher.exists()
    assert _is_executable(main_launcher)
    assert _is_executable(alt_launcher)


def test_launcher_contains_production_and_dev_fallbacks() -> None:
    text = _launcher("Gmail Рассылка.command").read_text(encoding="utf-8")

    assert 'dist/${APP_NAME}.app' in text
    assert 'scripts/run_mac.sh' in text
    assert "Собранное приложение не найдено. Запускаю dev-режим." in text
    assert "Окружение не настроено. Запустите scripts/setup_mac.sh" in text
    assert "OUTREACH_AUTOMATION_LAUNCH_MODE" in text


def test_launcher_does_not_read_or_print_secrets() -> None:
    combined = "\n".join(
        [
            _script("create_launcher.sh").read_text(encoding="utf-8"),
            _launcher("Gmail Рассылка.command").read_text(encoding="utf-8"),
            _launcher("Gmail Рассылка Launcher.command").read_text(encoding="utf-8"),
        ]
    )

    assert "GMAIL_APP_PASSWORD" not in combined
    assert ".env" not in combined
    assert "dotenv" not in combined.lower()


def test_applescript_launcher_script_exists_and_is_executable() -> None:
    script = _script("create_macos_launcher_app.sh")
    text = script.read_text(encoding="utf-8")

    assert script.exists()
    assert _is_executable(script)
    assert "Contents/MacOS" in text
    assert "Info.plist" in text
    assert "resources/icons/app_icon.icns" in text
    assert 'APP_NAME="Gmail Рассылка Launcher"' in text
    assert 'APP_PATH="${LAUNCHERS_DIR}/${APP_NAME}.app"' in text


def test_readme_mentions_user_launcher_flow() -> None:
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "## Быстрый запуск без терминала" in text
    assert "./scripts/create_launcher.sh" in text
    assert "launchers/Gmail Рассылка.command" in text
    assert "./scripts/build_macos.sh" in text
