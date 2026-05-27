from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QLineEdit

from src.campaign_service import CampaignService
from src.config import get_gmail_password
from src.credential_store import EncryptedFileCredentialStore
from src.db import Database
from src.gui.settings_view import SettingsView
from src.logger_setup import setup_logging
from src.mailer import GmailSMTPMailer


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def cleanup_qt_widgets(qapp: QApplication):
    yield
    for widget in QApplication.topLevelWidgets():
        settings_view = getattr(widget, "settings_view", None)
        if settings_view is not None:
            settings_view.shutdown()
        if isinstance(widget, SettingsView):
            widget.shutdown()
        widget.close()
        widget.deleteLater()
    qapp.processEvents()


@pytest.fixture()
def secure_file_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    app_dir = tmp_path / "app-data"
    monkeypatch.setenv("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(app_dir))
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    return app_dir


def make_service(tmp_path: Path) -> CampaignService:
    db = Database(tmp_path / "outreach.sqlite")
    db.initialize()
    db.set_settings(
        {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": "587",
            "sender_email": "",
            "send_mode": "dry_run",
        }
    )
    return CampaignService(db, sleep_fn=lambda _: None, export_dir=tmp_path / "exports")


def test_encrypted_file_store_persists_without_plaintext(tmp_path: Path) -> None:
    secret = "stage-test-app-password"
    store = EncryptedFileCredentialStore(tmp_path)

    store.set_password("user@gmail.com", secret)

    assert store.get_password("user@gmail.com") == secret
    assert secret not in store.data_path.read_text(encoding="utf-8")
    assert secret not in store.key_path.read_text(encoding="utf-8")


def test_saved_ui_credentials_override_env_fallback(
    secure_file_backend: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "env-password")
    store = EncryptedFileCredentialStore(secure_file_backend)
    store.set_password("user@gmail.com", "ui-password")

    assert get_gmail_password("user@gmail.com") == "ui-password"
    assert get_gmail_password("other@gmail.com") == "env-password"


def test_campaign_service_saves_credentials_outside_sqlite(
    secure_file_backend: Path,
    tmp_path: Path,
) -> None:
    secret = "secure-service-password"
    service = make_service(tmp_path)

    backend_name = service.save_gmail_credentials("User@Gmail.com", secret)

    settings = service.settings()
    assert backend_name == "encrypted local storage"
    assert settings["sender_email"] == "user@gmail.com"
    assert all(secret not in value for value in settings.values())
    assert service.gmail_credential_status("user@gmail.com").has_password
    assert get_gmail_password("user@gmail.com") == secret


def test_mailer_check_connection_uses_typed_password_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    class FakeSMTP:
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
            seen["sender"] = sender_email
            seen["password"] = password

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    result = GmailSMTPMailer(password_getter=lambda: "").check_connection(
        host="smtp.gmail.com",
        port=587,
        sender_email="typed@gmail.com",
        password="typed-password",
    )

    assert result.ok
    assert seen == {"sender": "typed@gmail.com", "password": "typed-password"}


def test_secure_password_is_redacted_from_connection_errors(
    secure_file_backend: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret = "stored-secret-password"
    log_file = tmp_path / "app.log"
    logger = setup_logging(log_file)
    EncryptedFileCredentialStore(secure_file_backend).set_password("user@gmail.com", secret)

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
            raise RuntimeError(f"rejected password={password}")

    monkeypatch.setattr("smtplib.SMTP", BadSMTP)

    result = GmailSMTPMailer().check_connection(
        host="smtp.gmail.com",
        port=587,
        sender_email="user@gmail.com",
    )
    for handler in logger.handlers:
        handler.flush()
    log_text = log_file.read_text(encoding="utf-8")

    assert result.ok is False
    assert secret not in result.message
    assert secret not in log_text


def test_settings_view_masks_and_saves_gmail_credentials(
    qapp: QApplication,
    secure_file_backend: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[tuple[str, str]] = []

    def record(_parent, title: str, text: str, *args, **kwargs):
        messages.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", record)
    monkeypatch.setattr(QMessageBox, "warning", record)
    monkeypatch.setattr(QMessageBox, "critical", record)
    service = make_service(tmp_path)
    view = SettingsView(service, refresh_callback=lambda: None)
    view.refresh()

    assert view.app_password.echoMode() == QLineEdit.EchoMode.Password
    view.sender_email.setText("ui@gmail.com")
    view.app_password.setText("ui-secret-password")
    view.save_gmail_credentials()

    assert messages[-1][0] == "Gmail"
    assert "ui-secret-password" not in messages[-1][1]
    assert view.app_password.text() == ""
    assert service.settings()["sender_email"] == "ui@gmail.com"
    assert get_gmail_password("ui@gmail.com") == "ui-secret-password"
