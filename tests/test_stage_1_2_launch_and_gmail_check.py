from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from scripts.reset_demo_data import reset_demo_data
from src.config import DEFAULT_SETTINGS
from src.db import Database
from src.logger_setup import setup_logging
from src.mailer import GmailSMTPMailer


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_launcher_files_exist_and_are_executable() -> None:
    for script_name in ("setup_mac.sh", "run_mac.sh", "test_mac.sh"):
        path = PROJECT_ROOT / "scripts" / script_name
        assert path.exists(), f"{script_name} is missing"
        assert path.stat().st_mode & stat.S_IXUSR, f"{script_name} is not executable"


def test_check_connection_returns_clear_error_without_password() -> None:
    mailer = GmailSMTPMailer(password_getter=lambda: "")

    result = mailer.check_connection(
        host="smtp.gmail.com",
        port=587,
        sender_email="sender@example.com",
    )

    assert result.ok is False
    assert "Gmail app password is missing" in result.message


def test_check_connection_does_not_leak_password(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret = "stage-1-2-secret-password"
    log_file = tmp_path / "app.log"
    setup_logging(log_file)
    monkeypatch.setenv("GMAIL_APP_PASSWORD", secret)

    class BadSMTP:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def ehlo(self) -> None:
            return None

        def starttls(self) -> None:
            return None

        def login(self, sender_email: str, password: str) -> None:
            raise RuntimeError(f"login rejected for password={password}")

    monkeypatch.setattr("smtplib.SMTP", BadSMTP)
    mailer = GmailSMTPMailer()

    result = mailer.check_connection(
        host="smtp.gmail.com",
        port=587,
        sender_email="sender@example.com",
    )

    for handler in mailer.logger.handlers:
        handler.flush()

    log_text = log_file.read_text(encoding="utf-8")
    assert result.ok is False
    assert secret not in result.message
    assert secret not in log_text
    assert "[REDACTED]" in result.message
    assert "[REDACTED]" in log_text


def test_reset_demo_data_restores_safe_defaults(tmp_path: Path) -> None:
    db = Database(tmp_path / "outreach.sqlite")
    db.initialize()
    demo_campaign_id = db.create_campaign("Stage 1.2 Smoke Test")
    db.set_settings(
        {
            "sender_email": "stage12.sender@example.com",
            "daily_send_limit": "1",
            "delay_seconds": "0",
            "review_mode": "false",
            "safe_mode": "false",
        }
    )
    db.save_template("Default", "Changed", "Changed")
    db.add_blacklist("stage12.lead@example.com", "demo")
    assert demo_campaign_id

    reset_demo_data(db)

    settings = db.get_settings()
    for key, value in DEFAULT_SETTINGS.items():
        assert settings[key] == value
    assert db.get_template("Default")["subject_template"] == "Quick idea for {{company}}"
    assert db.fetch_one("SELECT id FROM campaigns WHERE name = ?", ("Stage 1.2 Smoke Test",)) is None
    assert not db.is_blacklisted("stage12.lead@example.com")
    assert not (tmp_path / ".env").exists()
