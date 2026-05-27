from __future__ import annotations

from urllib.parse import urlparse


GENERIC_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yandex.ru",
    "ya.ru",
    "mail.ru",
    "bk.ru",
    "inbox.ru",
    "list.ru",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "yahoo.com",
    "icloud.com",
    "me.com",
    "proton.me",
    "protonmail.com",
}


def email_domain(email: str) -> str:
    value = (email or "").strip().lower()
    if "@" not in value:
        return ""
    return value.rsplit("@", 1)[1].strip(". ")


def is_generic_email_domain(domain: str) -> bool:
    return (domain or "").strip().lower() in GENERIC_EMAIL_DOMAINS


def normalize_domain(domain: str) -> str:
    value = (domain or "").strip().lower()
    value = value.removeprefix("www.")
    return value.strip(".")


def normalize_url(value: str) -> str:
    url = (value or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    return parsed._replace(fragment="", path=path).geturl()


def domain_from_url(url: str) -> str:
    parsed = urlparse(normalize_url(url))
    return normalize_domain(parsed.netloc)


def same_domain(url: str, base_domain: str) -> bool:
    domain = domain_from_url(url)
    base = normalize_domain(base_domain)
    return bool(domain and base and (domain == base or domain.endswith(f".{base}")))


def candidate_website_url(contact: dict) -> tuple[str, list[str]]:
    warnings: list[str] = []
    website = normalize_url(str(contact.get("website") or ""))
    if website:
        return website, warnings

    domain = email_domain(str(contact.get("email") or ""))
    if not domain:
        return "", ["Нет сайта и домена email для enrichment."]
    if is_generic_email_domain(domain):
        return "", ["Generic email domain пропущен: нельзя выводить компанию из личного почтового домена."]
    return normalize_url(domain), warnings
