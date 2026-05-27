from __future__ import annotations

import logging
import sys
import threading
import traceback
from pathlib import Path
from types import TracebackType

from PySide6.QtWidgets import QApplication, QMessageBox

from .logger_setup import get_logger, redact_secret
from .platform_utils import get_logs_dir


USER_CRASH_TITLE = "Приложение столкнулось с ошибкой"


def format_user_crash_message(log_path: Path | None = None) -> str:
    suffix = f"\n\nЛог сохранен:\n{log_path}" if log_path else "\n\nЛог сохранен в папке logs."
    return "Приложение столкнулось с ошибкой.\nМы сохранили технический лог для диагностики." + suffix


def handle_exception(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
    logger: logging.Logger | None = None,
    show_dialog: bool = True,
) -> str:
    logger = logger or get_logger()
    sanitized_traceback = redact_secret("".join(traceback.format_exception(exc_type, exc, tb)))
    logger.error("Unhandled exception:\n%s", sanitized_traceback)
    log_path = get_logs_dir() / "app.log"
    message = format_user_crash_message(log_path)
    if show_dialog and QApplication.instance() is not None:
        QMessageBox.critical(None, USER_CRASH_TITLE, message)
    return message


def install_crash_handler(logger: logging.Logger | None = None) -> None:
    logger = logger or get_logger()

    def excepthook(exc_type, exc, tb) -> None:
        handle_exception(exc_type, exc, tb, logger=logger, show_dialog=True)

    def threadhook(args: threading.ExceptHookArgs) -> None:
        handle_exception(args.exc_type, args.exc_value, args.exc_traceback, logger=logger, show_dialog=True)

    sys.excepthook = excepthook
    threading.excepthook = threadhook
