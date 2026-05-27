from __future__ import annotations

import webbrowser
from urllib.parse import urlparse

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def is_safe_external_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def open_external_url(url: str) -> bool:
    cleaned = (url or "").strip()
    if not is_safe_external_url(cleaned):
        return False
    if QDesktopServices.openUrl(QUrl(cleaned)):
        return True
    return bool(webbrowser.open(cleaned, new=2, autoraise=True))
