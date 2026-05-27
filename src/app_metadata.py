from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from .platform_utils import APP_NAME


APP_VERSION = "5.1.1"
APP_BUNDLE_ID = "ru.gmail-rassylka.desktop"
BUILD_TIMESTAMP = os.getenv(
    "OUTREACH_BUILD_TIMESTAMP",
    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
)


@dataclass(frozen=True, slots=True)
class AppMetadata:
    name: str = APP_NAME
    version: str = APP_VERSION
    bundle_id: str = APP_BUNDLE_ID
    build_timestamp: str = BUILD_TIMESTAMP
    copyright_text: str = "Local-first Gmail outreach tool"
    safety_note: str = "Тестовый режим включен по умолчанию. Gmail пароль хранится в защищенном хранилище."


def get_app_metadata() -> AppMetadata:
    return AppMetadata()
