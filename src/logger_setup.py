from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import LOGS_DIR, ensure_project_dirs, load_environment


LOGGER_NAME = "outreach"


def _known_secret_values() -> list[str]:
    load_environment()
    values: list[str] = []
    for key in (
        "GMAIL_APP_PASSWORD",
        "OPENAI_API_KEY",
        "OPENAI_RESEARCH_API_KEY",
        "OPENAI_WRITER_API_KEY",
        "TELEGRAM_BOT_TOKEN",
    ):
        value = os.getenv(key, "")
        if value:
            values.append(value)
    return values


def redact_secret(value: object, extra_secrets: list[str] | tuple[str, ...] | None = None) -> str:
    text = "" if value is None else str(value)
    for secret in [*_known_secret_values(), *(extra_secrets or [])]:
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(
        r"(?i)(app[_ -]?password|password|pass)\s*([=:])\s*([^\s,;]+)",
        r"\1\2[REDACTED]",
        text,
    )
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secret(record.getMessage())
        record.args = ()
        return True


def setup_logging(log_file: Path | None = None) -> logging.Logger:
    ensure_project_dirs()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    log_path = log_file or (LOGS_DIR / "app.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactingFilter())
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(RedactingFilter())
    logger.addHandler(stream_handler)
    return logger


def get_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        return setup_logging()
    return logger
