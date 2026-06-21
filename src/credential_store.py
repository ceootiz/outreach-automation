from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .app_metadata import APP_BUNDLE_ID
from .platform_utils import get_app_data_dir


SERVICE_NAME = f"{APP_BUNDLE_ID}.gmail-smtp"
CREDENTIAL_BACKEND_ENV = "OUTREACH_AUTOMATION_CREDENTIAL_BACKEND"
LOGGER_NAME = "outreach"


class CredentialStoreError(RuntimeError):
    pass


class CredentialStore(Protocol):
    backend_name: str

    def get_password(self, account: str) -> str:
        ...

    def set_password(self, account: str, password: str) -> None:
        ...

    def delete_password(self, account: str) -> None:
        ...


@dataclass(frozen=True, slots=True)
class CredentialStatus:
    has_password: bool
    backend_name: str
    source: str


def _normalize_account(account: str | None) -> str:
    return (account or "").strip().lower()


def _profile_account(profile_id: int | str, email: str | None = None) -> str:
    profile = str(profile_id).strip()
    if not profile:
        raise CredentialStoreError("Gmail profile id is required")
    normalized_email = _normalize_account(email)
    suffix = f".{normalized_email}" if normalized_email else ""
    return f"outreach_automation.gmail_profile.{profile}{suffix}"


def _ai_account(provider: str) -> str:
    normalized = _normalize_account(provider)
    if not normalized:
        raise CredentialStoreError("AI provider is required")
    return f"outreach_automation.ai.{normalized}.api_key"


def _ai_brain_account(brain: str, provider: str) -> str:
    normalized_brain = _normalize_account(brain)
    normalized_provider = _normalize_account(provider)
    if normalized_brain not in {"research", "writer"}:
        raise CredentialStoreError("AI brain must be research or writer")
    if not normalized_provider:
        raise CredentialStoreError("AI provider is required")
    return f"outreach_automation.ai.{normalized_brain}.{normalized_provider}.api_key"


def _telegram_account() -> str:
    return "outreach_automation.telegram.bot_token"


def _run_command(
    args: list[str],
    *,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        input=input_text,
        env=command_env,
        timeout=15,
    )


class MacOSKeychainCredentialStore:
    backend_name = "macOS Keychain"

    def __init__(self, service_name: str = SERVICE_NAME):
        if sys.platform != "darwin" or not shutil.which("security"):
            raise CredentialStoreError("macOS Keychain is unavailable")
        self.service_name = service_name

    def get_password(self, account: str) -> str:
        account = _normalize_account(account)
        if not account:
            return ""
        result = _run_command(
            [
                "security",
                "find-generic-password",
                "-s",
                self.service_name,
                "-a",
                account,
                "-w",
            ]
        )
        if result.returncode != 0:
            return ""
        return result.stdout.rstrip("\n")

    def set_password(self, account: str, password: str) -> None:
        account = _normalize_account(account)
        if not account:
            raise CredentialStoreError("Gmail address is required")
        if not password:
            raise CredentialStoreError("Gmail app password is required")
        result = _run_command(
            [
                "security",
                "add-generic-password",
                "-U",
                "-s",
                self.service_name,
                "-a",
                account,
                "-w",
                password,
            ]
        )
        if result.returncode != 0:
            raise CredentialStoreError("Unable to save password in macOS Keychain")

    def delete_password(self, account: str) -> None:
        account = _normalize_account(account)
        if not account:
            return
        _run_command(
            [
                "security",
                "delete-generic-password",
                "-s",
                self.service_name,
                "-a",
                account,
            ]
        )


class WindowsCredentialStore:
    backend_name = "Windows Credential Manager"

    def __init__(self, service_name: str = SERVICE_NAME):
        self.powershell = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
        if os.name != "nt" or not self.powershell:
            raise CredentialStoreError("Windows Credential Manager is unavailable")
        self.service_name = service_name

    @staticmethod
    def _ps_quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _powershell(self, script: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return _run_command(
            [
                self.powershell or "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "-",
            ],
            input_text=script,
            env=env,
        )

    def get_password(self, account: str) -> str:
        account = _normalize_account(account)
        if not account:
            return ""
        service = self._ps_quote(self.service_name)
        account_value = self._ps_quote(account)
        script = (
            "$ErrorActionPreference='Stop';"
            "$vault=New-Object Windows.Security.Credentials.PasswordVault;"
            f"$cred=$vault.Retrieve({service},{account_value});"
            "$cred.RetrievePassword();"
            "Write-Output $cred.Password"
        )
        result = self._powershell(script)
        if result.returncode != 0:
            return ""
        return result.stdout.rstrip("\r\n")

    def set_password(self, account: str, password: str) -> None:
        account = _normalize_account(account)
        if not account:
            raise CredentialStoreError("Gmail address is required")
        if not password:
            raise CredentialStoreError("Gmail app password is required")
        service = self._ps_quote(self.service_name)
        account_value = self._ps_quote(account)
        script = (
            "$ErrorActionPreference='Stop';"
            "$password=$env:OUTREACH_CREDENTIAL_VALUE;"
            "$vault=New-Object Windows.Security.Credentials.PasswordVault;"
            "$cred=New-Object Windows.Security.Credentials.PasswordCredential"
            f"({service},{account_value},$password);"
            "Remove-Item Env:OUTREACH_CREDENTIAL_VALUE -ErrorAction SilentlyContinue;"
            "$vault.Add($cred)"
        )
        result = self._powershell(script, env={"OUTREACH_CREDENTIAL_VALUE": password})
        if result.returncode != 0:
            raise CredentialStoreError("Unable to save password in Windows Credential Manager")

    def delete_password(self, account: str) -> None:
        account = _normalize_account(account)
        if not account:
            return
        service = self._ps_quote(self.service_name)
        account_value = self._ps_quote(account)
        script = (
            "$ErrorActionPreference='SilentlyContinue';"
            "$vault=New-Object Windows.Security.Credentials.PasswordVault;"
            f"$cred=$vault.Retrieve({service},{account_value});"
            "if ($cred) { $vault.Remove($cred) }"
        )
        self._powershell(script)


class WindowsDPAPICredentialStore:
    backend_name = "Windows DPAPI encrypted local storage"

    def __init__(self, base_dir: Path | None = None, service_name: str = SERVICE_NAME):
        if os.name != "nt":
            raise CredentialStoreError("Windows DPAPI is unavailable")
        root = base_dir or get_app_data_dir()
        self.service_name = service_name
        self.dir = root / "credentials"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.data_path = self.dir / "windows_credentials.dpapi"

    def get_password(self, account: str) -> str:
        account = _normalize_account(account)
        if not account or not self.data_path.exists():
            return ""
        data = self._load_payload()
        return str(data.get(self.service_name, {}).get(account, ""))

    def set_password(self, account: str, password: str) -> None:
        account = _normalize_account(account)
        if not account:
            raise CredentialStoreError("Gmail address is required")
        if not password:
            raise CredentialStoreError("Gmail app password is required")
        try:
            data = self._load_payload()
        except CredentialStoreError:
            self._quarantine_corrupt_payload()
            data = {}
        service = data.setdefault(self.service_name, {})
        service[account] = password
        self._save_payload(data)

    def delete_password(self, account: str) -> None:
        account = _normalize_account(account)
        if not account or not self.data_path.exists():
            return
        try:
            data = self._load_payload()
        except CredentialStoreError:
            self._quarantine_corrupt_payload()
            return
        service = data.setdefault(self.service_name, {})
        service.pop(account, None)
        self._save_payload(data)

    def _load_payload(self) -> dict[str, dict[str, str]]:
        if not self.data_path.exists():
            return {}
        try:
            protected = self.data_path.read_bytes()
            plaintext = self._unprotect(protected)
            decoded = json.loads(plaintext.decode("utf-8"))
            if not isinstance(decoded, dict):
                return {}
            return decoded
        except Exception as exc:
            raise CredentialStoreError("Unable to read Windows DPAPI credential storage") from exc

    def _save_payload(self, data: dict[str, dict[str, str]]) -> None:
        plaintext = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        protected = self._protect(plaintext)
        self.data_path.write_bytes(protected)
        EncryptedFileCredentialStore._chmod_private(self.data_path)

    def _quarantine_corrupt_payload(self) -> None:
        if not self.data_path.exists():
            return
        suffix = f".corrupt.{int(time.time())}"
        try:
            self.data_path.replace(self.data_path.with_name(self.data_path.name + suffix))
        except OSError:
            try:
                self.data_path.unlink()
            except OSError:
                pass

    @staticmethod
    def _protect(data: bytes) -> bytes:
        import ctypes
        from ctypes import wintypes

        if not hasattr(ctypes, "windll"):
            raise CredentialStoreError("Windows DPAPI is unavailable")

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        input_buffer = ctypes.create_string_buffer(data)
        input_blob = DATA_BLOB(len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        output_blob = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(output_blob),
        ):
            raise CredentialStoreError("Windows DPAPI encryption failed")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(output_blob.pbData)

    @staticmethod
    def _unprotect(data: bytes) -> bytes:
        import ctypes
        from ctypes import wintypes

        if not hasattr(ctypes, "windll"):
            raise CredentialStoreError("Windows DPAPI is unavailable")

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        input_buffer = ctypes.create_string_buffer(data)
        input_blob = DATA_BLOB(len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        output_blob = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(output_blob),
        ):
            raise CredentialStoreError("Windows DPAPI decryption failed")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(output_blob.pbData)


class EncryptedFileCredentialStore:
    backend_name = "encrypted local storage"

    def __init__(self, base_dir: Path | None = None, service_name: str = SERVICE_NAME):
        root = base_dir or get_app_data_dir()
        self.service_name = service_name
        self.dir = root / "credentials"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.key_path = self.dir / ".credential_key"
        self.data_path = self.dir / "gmail_credentials.enc"

    def get_password(self, account: str) -> str:
        account = _normalize_account(account)
        if not account or not self.data_path.exists():
            return ""
        data = self._load_payload()
        return str(data.get(self.service_name, {}).get(account, ""))

    def set_password(self, account: str, password: str) -> None:
        account = _normalize_account(account)
        if not account:
            raise CredentialStoreError("Gmail address is required")
        if not password:
            raise CredentialStoreError("Gmail app password is required")
        try:
            data = self._load_payload()
        except CredentialStoreError:
            self._quarantine_corrupt_payload()
            data = {}
        service = data.setdefault(self.service_name, {})
        service[account] = password
        self._save_payload(data)

    def delete_password(self, account: str) -> None:
        account = _normalize_account(account)
        if not account:
            return
        try:
            data = self._load_payload()
        except CredentialStoreError:
            self._quarantine_corrupt_payload()
            return
        service = data.setdefault(self.service_name, {})
        service.pop(account, None)
        self._save_payload(data)

    def _key(self) -> bytes:
        if self.key_path.exists():
            try:
                encoded = self.key_path.read_text(encoding="utf-8").strip()
                return base64.urlsafe_b64decode(encoded.encode("ascii"))
            except Exception:
                self._quarantine_path(self.key_path)
        key = secrets.token_bytes(32)
        self.key_path.write_text(
            base64.urlsafe_b64encode(key).decode("ascii"),
            encoding="utf-8",
        )
        self._chmod_private(self.key_path)
        return key

    def _load_payload(self) -> dict[str, dict[str, str]]:
        if not self.data_path.exists():
            return {}
        key = self._key()
        try:
            blob = json.loads(self.data_path.read_text(encoding="utf-8"))
            nonce = base64.urlsafe_b64decode(blob["nonce"].encode("ascii"))
            ciphertext = base64.urlsafe_b64decode(blob["ciphertext"].encode("ascii"))
            tag = base64.urlsafe_b64decode(blob["tag"].encode("ascii"))
            expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
            if not hmac.compare_digest(tag, expected):
                raise CredentialStoreError("Encrypted credential file failed integrity check")
            plaintext = self._xor_stream(ciphertext, key, nonce)
            decoded = json.loads(plaintext.decode("utf-8"))
            if not isinstance(decoded, dict):
                return {}
            return decoded
        except CredentialStoreError:
            raise
        except Exception as exc:
            raise CredentialStoreError("Unable to read encrypted credential storage") from exc

    def _save_payload(self, data: dict[str, dict[str, str]]) -> None:
        key = self._key()
        nonce = secrets.token_bytes(16)
        plaintext = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ciphertext = self._xor_stream(plaintext, key, nonce)
        tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        payload = {
            "version": 1,
            "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
            "tag": base64.urlsafe_b64encode(tag).decode("ascii"),
        }
        self.data_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        self._chmod_private(self.data_path)

    def _quarantine_corrupt_payload(self) -> None:
        self._quarantine_path(self.data_path)

    @staticmethod
    def _quarantine_path(path: Path) -> None:
        if not path.exists():
            return
        suffix = f".corrupt.{int(time.time())}"
        try:
            path.replace(path.with_name(path.name + suffix))
        except OSError:
            try:
                path.unlink()
            except OSError:
                pass

    @staticmethod
    def _xor_stream(data: bytes, key: bytes, nonce: bytes) -> bytes:
        output = bytearray()
        counter = 0
        while len(output) < len(data):
            counter_bytes = counter.to_bytes(8, "big")
            block = hmac.new(key, nonce + counter_bytes, hashlib.sha256).digest()
            output.extend(block)
            counter += 1
        return bytes(value ^ mask for value, mask in zip(data, output))

    @staticmethod
    def _chmod_private(path: Path) -> None:
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def get_credential_store() -> CredentialStore:
    requested = os.getenv(CREDENTIAL_BACKEND_ENV, "auto").strip().lower()
    if requested in {"file", "local", "encrypted_file"}:
        return EncryptedFileCredentialStore()
    if requested in {"keychain", "macos"}:
        return MacOSKeychainCredentialStore()
    if requested in {"windows", "credential_manager"}:
        return WindowsCredentialStore()

    try:
        if sys.platform == "darwin":
            return MacOSKeychainCredentialStore()
        if os.name == "nt":
            return WindowsCredentialStore()
    except CredentialStoreError:
        pass
    return EncryptedFileCredentialStore()


def _credential_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def _log_store_failure(action: str, backend_name: str, exc: Exception) -> None:
    logger = _credential_logger()
    if logger.handlers:
        logger.warning(
            "Credential backend failure: action=%s backend=%s error_type=%s",
            action,
            backend_name,
            type(exc).__name__,
        )


def _fallback_credential_stores(primary_backend: str | None = None) -> list[CredentialStore]:
    stores: list[CredentialStore] = []
    seen = {primary_backend} if primary_backend else set()
    for factory in (WindowsDPAPICredentialStore, EncryptedFileCredentialStore):
        try:
            store = factory()
        except CredentialStoreError:
            continue
        if store.backend_name in seen:
            continue
        stores.append(store)
        seen.add(store.backend_name)
    return stores


def _set_password_resilient(account: str, password: str) -> str:
    store = get_credential_store()
    try:
        store.set_password(account, password)
        return store.backend_name
    except CredentialStoreError as exc:
        _log_store_failure("set_password", store.backend_name, exc)
        last_error: CredentialStoreError | None = exc
        for fallback in _fallback_credential_stores(store.backend_name):
            try:
                fallback.set_password(account, password)
                return f"{fallback.backend_name} (fallback from {store.backend_name})"
            except CredentialStoreError as fallback_exc:
                _log_store_failure("set_password_fallback", fallback.backend_name, fallback_exc)
                last_error = fallback_exc
        raise CredentialStoreError("Unable to save password in secure credential storage") from last_error


def _get_password_resilient(account: str) -> str:
    store = get_credential_store()
    try:
        password = store.get_password(account)
        if password:
            return password
    except CredentialStoreError as exc:
        _log_store_failure("get_password", store.backend_name, exc)
    for fallback in _fallback_credential_stores(store.backend_name):
        try:
            password = fallback.get_password(account)
            if password:
                return password
        except CredentialStoreError as fallback_exc:
            _log_store_failure("get_password_fallback", fallback.backend_name, fallback_exc)
            continue
    return ""


def _delete_password_resilient(account: str) -> None:
    stores: list[CredentialStore] = []
    primary: CredentialStore | None = None
    try:
        primary = get_credential_store()
        stores.append(primary)
    except CredentialStoreError:
        primary = None
    stores.extend(_fallback_credential_stores(primary.backend_name if primary else None))
    for store in stores:
        try:
            store.delete_password(account)
        except CredentialStoreError as exc:
            _log_store_failure("delete_password", store.backend_name, exc)


def save_gmail_app_password(account: str, password: str) -> str:
    return _set_password_resilient(_normalize_account(account), password)


def save_profile_password(profile_id: int | str, email: str, password: str) -> str:
    return _set_password_resilient(_profile_account(profile_id, email), password)


def load_profile_password(profile_id: int | str, email: str) -> str:
    try:
        return _get_password_resilient(_profile_account(profile_id, email))
    except CredentialStoreError:
        return ""


def delete_profile_password(profile_id: int | str, email: str) -> None:
    try:
        _delete_password_resilient(_profile_account(profile_id, email))
    except CredentialStoreError:
        return


def has_profile_password(profile_id: int | str, email: str) -> bool:
    return bool(load_profile_password(profile_id, email))


def save_ai_api_key(provider: str, api_key: str) -> str:
    return _set_password_resilient(_ai_account(provider), api_key)


def save_ai_brain_api_key(brain: str, provider: str, api_key: str) -> str:
    return _set_password_resilient(_ai_brain_account(brain, provider), api_key)


def load_ai_api_key(provider: str) -> str:
    try:
        return _get_password_resilient(_ai_account(provider))
    except CredentialStoreError:
        return ""


def load_ai_brain_api_key(brain: str, provider: str) -> str:
    try:
        return _get_password_resilient(_ai_brain_account(brain, provider))
    except CredentialStoreError:
        return ""


def delete_ai_api_key(provider: str) -> None:
    try:
        _delete_password_resilient(_ai_account(provider))
    except CredentialStoreError:
        return


def delete_ai_brain_api_key(brain: str, provider: str) -> None:
    try:
        _delete_password_resilient(_ai_brain_account(brain, provider))
    except CredentialStoreError:
        return


def has_ai_api_key(provider: str) -> bool:
    return bool(load_ai_api_key(provider))


def has_ai_brain_api_key(brain: str, provider: str) -> bool:
    return bool(load_ai_brain_api_key(brain, provider))


def save_telegram_bot_token(token: str) -> str:
    return _set_password_resilient(_telegram_account(), token)


def load_telegram_bot_token() -> str:
    try:
        return _get_password_resilient(_telegram_account())
    except CredentialStoreError:
        return ""


def delete_telegram_bot_token() -> None:
    try:
        _delete_password_resilient(_telegram_account())
    except CredentialStoreError:
        return


def has_telegram_bot_token() -> bool:
    return bool(load_telegram_bot_token())


def get_telegram_credential_status() -> CredentialStatus:
    store = get_credential_store()
    token = _get_password_resilient(_telegram_account())
    return CredentialStatus(
        has_password=bool(token),
        backend_name=store.backend_name,
        source="secure_storage" if token else "",
    )


def get_stored_gmail_app_password(account: str | None) -> str:
    account = _normalize_account(account)
    if not account:
        return ""
    try:
        return _get_password_resilient(account)
    except CredentialStoreError:
        return ""


def delete_gmail_app_password(account: str | None) -> None:
    account = _normalize_account(account)
    if not account:
        return
    try:
        _delete_password_resilient(account)
    except CredentialStoreError:
        return


def get_gmail_credential_status(account: str | None) -> CredentialStatus:
    store = get_credential_store()
    password = _get_password_resilient(_normalize_account(account))
    return CredentialStatus(
        has_password=bool(password),
        backend_name=store.backend_name,
        source="secure_storage" if password else "",
    )
