from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from src import credential_store
from src.campaign_service import CampaignService
from src.credential_store import CredentialStoreError, EncryptedFileCredentialStore
from src.db import Database
from src.gui.settings_view import SettingsView


class WorkingStore:
    backend_name = "Windows Credential Manager"

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get_password(self, account: str) -> str:
        return self.values.get(account, "")

    def set_password(self, account: str, password: str) -> None:
        self.values[account] = password

    def delete_password(self, account: str) -> None:
        self.values.pop(account, None)


class FailingStore:
    backend_name = "Windows Credential Manager"

    def get_password(self, account: str) -> str:
        raise CredentialStoreError("simulated keyring read failure")

    def set_password(self, account: str, password: str) -> None:
        raise CredentialStoreError("simulated keyring write failure")

    def delete_password(self, account: str) -> None:
        raise CredentialStoreError("simulated keyring delete failure")


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def isolated_app_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    app_dir = tmp_path / "app-data"
    monkeypatch.setenv("OUTREACH_AUTOMATION_APP_DIR", str(app_dir))
    monkeypatch.delenv("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", raising=False)
    return app_dir


def make_service(tmp_path: Path) -> CampaignService:
    db = Database(tmp_path / "outreach.sqlite")
    db.initialize()
    db.set_settings({"smtp_host": "smtp.gmail.com", "smtp_port": "587", "send_mode": "dry_run"})
    return CampaignService(db, sleep_fn=lambda _: None, export_dir=tmp_path / "exports")


def test_windows_keyring_successful_save_and_read(monkeypatch: pytest.MonkeyPatch, isolated_app_dir: Path) -> None:
    store = WorkingStore()
    monkeypatch.setattr(credential_store, "get_credential_store", lambda: store)

    backend = credential_store.save_profile_password(7, "User@Example.com", "keyring-secret")

    assert backend == "Windows Credential Manager"
    assert credential_store.load_profile_password(7, "user@example.com") == "keyring-secret"
    assert not (isolated_app_dir / "credentials" / "gmail_credentials.enc").exists()


def test_windows_keyring_failure_activates_encrypted_fallback(
    monkeypatch: pytest.MonkeyPatch,
    isolated_app_dir: Path,
) -> None:
    monkeypatch.setattr(credential_store, "get_credential_store", lambda: FailingStore())

    backend = credential_store.save_profile_password(8, "user@example.com", "fallback-secret")

    assert "fallback" in backend
    assert "encrypted local storage" in backend
    assert credential_store.load_profile_password(8, "user@example.com") == "fallback-secret"
    encrypted_file = isolated_app_dir / "credentials" / "gmail_credentials.enc"
    assert encrypted_file.exists()
    assert "fallback-secret" not in encrypted_file.read_text(encoding="utf-8")


def test_corrupted_fallback_storage_does_not_crash_on_read(
    monkeypatch: pytest.MonkeyPatch,
    isolated_app_dir: Path,
) -> None:
    monkeypatch.setattr(credential_store, "get_credential_store", lambda: FailingStore())
    credentials_dir = isolated_app_dir / "credentials"
    credentials_dir.mkdir(parents=True)
    (credentials_dir / ".credential_key").write_text("not-valid-base64", encoding="utf-8")
    (credentials_dir / "gmail_credentials.enc").write_text("not-json", encoding="utf-8")

    assert credential_store.load_profile_password(9, "user@example.com") == ""


def test_corrupted_fallback_storage_is_recovered_on_save(
    monkeypatch: pytest.MonkeyPatch,
    isolated_app_dir: Path,
) -> None:
    monkeypatch.setattr(credential_store, "get_credential_store", lambda: FailingStore())
    credentials_dir = isolated_app_dir / "credentials"
    credentials_dir.mkdir(parents=True)
    (credentials_dir / ".credential_key").write_text("not-valid-base64", encoding="utf-8")
    (credentials_dir / "gmail_credentials.enc").write_text("not-json", encoding="utf-8")

    credential_store.save_profile_password(10, "user@example.com", "recovered-secret")

    assert credential_store.load_profile_password(10, "user@example.com") == "recovered-secret"
    assert "recovered-secret" not in (credentials_dir / "gmail_credentials.enc").read_text(encoding="utf-8")


def test_settings_ui_save_is_not_blocked_by_keyring_failure(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    isolated_app_dir: Path,
    tmp_path: Path,
) -> None:
    messages: list[tuple[str, str]] = []

    def record(_parent, title: str, text: str, *args, **kwargs):
        messages.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(credential_store, "get_credential_store", lambda: FailingStore())
    monkeypatch.setattr(QMessageBox, "information", record)
    monkeypatch.setattr(QMessageBox, "warning", record)
    monkeypatch.setattr(QMessageBox, "critical", record)
    service = make_service(tmp_path)
    view = SettingsView(service, refresh_callback=lambda: None)
    view.refresh()

    view.profile_name.setText("Windows Gmail")
    view.sender_email.setText("user@gmail.com")
    view.app_password.setText("ui-fallback-secret")
    view.save_gmail_credentials()

    assert messages
    assert messages[-1][0] == "Gmail"
    assert "critical" not in messages[-1][1].lower()
    assert "ui-fallback-secret" not in messages[-1][1]
    assert service.list_gmail_profiles()[0]["email"] == "user@gmail.com"
    assert credential_store.load_profile_password(1, "user@gmail.com") == "ui-fallback-secret"
    view.shutdown()


def test_settings_ui_contains_google_app_password_hint(qapp: QApplication, tmp_path: Path) -> None:
    view = SettingsView(make_service(tmp_path), refresh_callback=lambda: None)
    hint = view.gmail_instruction_label.text()

    assert "Для Gmail используйте пароль приложения Google, а не обычный пароль аккаунта." in hint
    assert "Google Account → Security → 2-Step Verification → App passwords" in hint
    view.shutdown()
