from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


PROFILE_NOT_FOUND = "Профиль не найден"

PROFILE_URL_TEMPLATES = {
    "instagram": "https://www.instagram.com/{handle}/",
    "tiktok": "https://www.tiktok.com/@{handle}",
    "x": "https://x.com/{handle}",
    "vk": "https://vk.com/{handle}",
}

SAFE_PROFILE_HOSTS = {
    "instagram": ("instagram.com", "www.instagram.com"),
    "tiktok": ("tiktok.com", "www.tiktok.com"),
    "x": ("x.com", "www.x.com", "twitter.com", "www.twitter.com"),
    "vk": ("vk.com", "www.vk.com"),
}


@dataclass(frozen=True, slots=True)
class ProfileUrlResult:
    channel: str
    url: str
    display_text: str
    source: str
    ok: bool
    warning: str = ""

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "channel": self.channel,
            "url": self.url,
            "display_text": self.display_text,
            "source": self.source,
            "ok": self.ok,
            "warning": self.warning,
        }


def normalize_handle(handle: str) -> str:
    value = (handle or "").strip()
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            value = parts[0]
    return value.lstrip("@").strip().strip("/")


def profile_url_for(
    channel: str | None,
    *,
    handle: str = "",
    profile_url: str = "",
    external_id: str = "",
) -> ProfileUrlResult:
    channel_id = (channel or "").strip().lower()
    explicit = (profile_url or "").strip()
    if explicit:
        warning = _validate_explicit_url(channel_id, explicit)
        return ProfileUrlResult(
            channel=channel_id,
            url=explicit,
            display_text=explicit,
            source="profile_url",
            ok=not bool(warning),
            warning=warning,
        )

    clean_handle = normalize_handle(handle)
    if channel_id == "vk" and not clean_handle and str(external_id or "").strip().isdigit():
        clean_handle = f"id{str(external_id).strip()}"

    template = PROFILE_URL_TEMPLATES.get(channel_id)
    if template and clean_handle:
        url = template.format(handle=clean_handle)
        return ProfileUrlResult(
            channel=channel_id,
            url=url,
            display_text=url,
            source="handle" if handle else "external_id",
            ok=True,
        )

    return ProfileUrlResult(
        channel=channel_id,
        url="",
        display_text=PROFILE_NOT_FOUND,
        source="missing",
        ok=False,
        warning="Добавьте handle, profile URL или platform id.",
    )


def _validate_explicit_url(channel_id: str, value: str) -> str:
    if not value.startswith(("http://", "https://")):
        return "Profile URL должен начинаться с http:// или https://."
    hosts = SAFE_PROFILE_HOSTS.get(channel_id)
    if not hosts:
        return ""
    hostname = (urlparse(value).hostname or "").lower()
    if hostname not in hosts:
        return "Profile URL не похож на официальный домен выбранного канала."
    return ""
