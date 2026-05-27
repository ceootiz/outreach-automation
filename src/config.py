from __future__ import annotations

import os
from pathlib import Path

from .platform_utils import (
    ensure_app_dirs,
    get_data_dir,
    get_exports_dir,
    get_imports_dir,
    get_logs_dir,
    get_cache_dir,
)

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - convenience fallback before dependencies are installed
    def load_dotenv(path: Path, override: bool = False) -> None:
        if not path.exists():
            return
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if override or key not in os.environ:
                os.environ[key.strip()] = value.strip().strip('"').strip("'")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = get_data_dir()
IMPORTS_DIR = get_imports_dir()
EXPORTS_DIR = get_exports_dir()
LOGS_DIR = get_logs_dir()
CACHE_DIR = get_cache_dir()
ENV_PATH = PROJECT_ROOT / ".env"


DEFAULT_SETTINGS: dict[str, str] = {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": "587",
    "sender_email": "",
    "daily_send_limit": "25",
    "delay_seconds": "5",
    "review_mode": "true",
    "follow_up_delay_days": "2",
    "safe_mode": "true",
    "send_mode": "dry_run",
    "active_channel": "email",
    "execution_mode": "dry_run",
    "execution_mode_email": "dry_run",
    "execution_mode_telegram": "dry_run",
    "execution_mode_x": "dry_run",
    "execution_mode_instagram": "dry_run",
    "execution_mode_vk": "dry_run",
    "execution_mode_tiktok": "dry_run",
    "real_send_confirm_required": "true",
    "allowed_test_recipient": "",
    "onboarding_completed": "false",
    "work_mode": "manual",
    "ai_provider": "off",
    "ai_model": "gpt-4.1-mini",
    "ai_generation_mode": "simple",
    "ai_research_provider": "off",
    "ai_research_model": "gpt-4.1-mini",
    "ai_writer_provider": "off",
    "ai_writer_model": "gpt-4.1-mini",
    "ai_max_drafts_per_batch": "25",
    "ai_campaign_topic": "",
    "ai_tone": "friendly",
    "ai_drafts_only": "true",
    "web_enrichment_enabled": "false",
    "web_enrichment_max_contacts_per_batch": "25",
    "web_enrichment_max_pages": "2",
    "web_enrichment_timeout_seconds": "8",
    "web_enrichment_cache_ttl_days": "7",
    "web_enrichment_respect_robots": "true",
    "inbox_sync_mode": "manual",
    "email_sync_enabled": "false",
    "telegram_sync_enabled": "false",
    "inbox_sync_interval_minutes": "5",
    "active_campaign_preset": "b2b_email_outreach",
    "operator_quick_start": "",
    "operator_mode": "precision",
    "operator_session_cooldown_seconds": "0",
}


def ensure_project_dirs() -> None:
    ensure_app_dirs()


def load_environment() -> None:
    load_dotenv(ENV_PATH, override=False)


def get_gmail_app_password() -> str:
    return get_gmail_password()


def get_gmail_password(sender_email: str | None = None) -> str:
    if sender_email:
        from .credential_store import get_stored_gmail_app_password

        stored_password = get_stored_gmail_app_password(sender_email)
        if stored_password:
            return stored_password
    load_environment()
    return os.getenv("GMAIL_APP_PASSWORD", "").strip()


def get_openai_api_key() -> str:
    from .credential_store import load_ai_api_key

    stored_key = load_ai_api_key("openai")
    if stored_key:
        return stored_key
    load_environment()
    return os.getenv("OPENAI_API_KEY", "").strip()


def get_openai_research_api_key() -> str:
    from .credential_store import load_ai_brain_api_key

    stored_key = load_ai_brain_api_key("research", "openai")
    if stored_key:
        return stored_key
    load_environment()
    return (
        os.getenv("OPENAI_RESEARCH_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )


def get_openai_writer_api_key() -> str:
    from .credential_store import load_ai_brain_api_key

    stored_key = load_ai_brain_api_key("writer", "openai")
    if stored_key:
        return stored_key
    load_environment()
    return (
        os.getenv("OPENAI_WRITER_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )


def get_telegram_bot_token() -> str:
    from .credential_store import load_telegram_bot_token

    stored_token = load_telegram_bot_token()
    if stored_token:
        return stored_token
    load_environment()
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def as_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y", "да"}


def as_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default
