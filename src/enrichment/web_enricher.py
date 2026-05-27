from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .domain_analyzer import candidate_website_url, domain_from_url
from .html_extractor import ExtractedPage, discover_public_pages, extract_page
from .result_schema import EnrichmentResult, utc_now_iso
from .robots import RobotsChecker


USER_AGENT = "Gmail-Rassylka/3.7 (+public-web-enrichment; no-login; contact-row-research)"


@dataclass(slots=True)
class FetchResponse:
    url: str
    status_code: int
    text: str
    content_type: str = "text/html"


class UrllibHttpClient:
    def get(self, url: str, *, timeout: int = 8, user_agent: str = USER_AGENT) -> FetchResponse:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.5",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read(300_000).decode(charset, errors="replace")
                return FetchResponse(
                    url=response.geturl(),
                    status_code=int(response.status),
                    text=body,
                    content_type=content_type,
                )
        except urllib.error.HTTPError as exc:
            body = exc.read(20_000).decode("utf-8", errors="replace")
            return FetchResponse(url=url, status_code=int(exc.code), text=body, content_type="")


class WebEnricher:
    def __init__(
        self,
        *,
        http_client: Any | None = None,
        user_agent: str = USER_AGENT,
        max_pages: int = 2,
        timeout_seconds: int = 8,
        max_text_length: int = 2500,
        respect_robots: bool = True,
    ):
        self.http_client = http_client or UrllibHttpClient()
        self.user_agent = user_agent
        self.max_pages = max(1, min(int(max_pages or 2), 3))
        self.timeout_seconds = max(2, min(int(timeout_seconds or 8), 20))
        self.max_text_length = max(500, min(int(max_text_length or 2500), 6000))
        self.respect_robots = bool(respect_robots)

    def enrich(self, contact: dict) -> EnrichmentResult:
        start_url, warnings = candidate_website_url(contact)
        if not start_url:
            return EnrichmentResult(status="skipped", warnings=warnings, confidence=0.0)

        domain = domain_from_url(start_url)
        source_urls: list[str] = []
        pages: list[ExtractedPage] = []
        fetch_warnings = list(warnings)
        robots_checker = RobotsChecker(self.http_client, user_agent=self.user_agent) if self.respect_robots else None

        for url in self._page_plan(start_url, pages, domain):
            if len(pages) >= self.max_pages:
                break
            if robots_checker is not None:
                decision = robots_checker.can_fetch(url)
                fetch_warnings.extend(decision.warnings)
                if not decision.allowed:
                    return EnrichmentResult(
                        status="blocked",
                        source_urls=source_urls,
                        domain=domain,
                        source_basis=["website_url_only"],
                        warnings=fetch_warnings,
                        fetched_at=utc_now_iso(),
                    )
            try:
                response = self.http_client.get(url, timeout=self.timeout_seconds, user_agent=self.user_agent)
            except Exception as exc:
                fetch_warnings.append(f"Fetch failed: {exc}")
                continue
            if response.status_code >= 400:
                fetch_warnings.append(f"{url} вернул HTTP {response.status_code}.")
                continue
            if "html" not in response.content_type.lower() and response.content_type:
                fetch_warnings.append(f"{url} не похож на HTML страницу.")
                continue
            page = extract_page(response.text, response.url or url, max_text_length=self.max_text_length)
            if page.text or page.title or page.description:
                pages.append(page)
                source_urls.append(page.url)

        if not pages:
            return EnrichmentResult(
                status="failed",
                source_urls=source_urls,
                domain=domain,
                source_basis=["website_url_only"],
                warnings=fetch_warnings or ["Публичные страницы не удалось получить."],
                fetched_at=utc_now_iso(),
            )

        title = pages[0].title
        description = pages[0].description
        combined_text = " ".join(page.text for page in pages if page.text).strip()
        signals = self._signals_from_text(combined_text, contact)
        status = "success" if pages and not fetch_warnings else "partial"
        confidence = 0.78 if status == "success" else 0.52
        return EnrichmentResult(
            status=status,
            source_urls=source_urls,
            domain=domain,
            title=title,
            description=description,
            public_summary=combined_text[:2500],
            likely_category=self._category_from_signals(signals),
            signals=signals,
            source_basis=["website_public_data"],
            warnings=fetch_warnings,
            fetched_at=utc_now_iso(),
            confidence=confidence,
        )

    def _page_plan(self, start_url: str, pages: list[ExtractedPage], domain: str):
        yielded: set[str] = set()
        yielded.add(start_url)
        yield start_url
        if pages:
            for url in discover_public_pages(pages[0], domain, limit=max(0, self.max_pages - 1)):
                if url not in yielded:
                    yielded.add(url)
                    yield url

    @staticmethod
    def _signals_from_text(text: str, contact: dict) -> list[str]:
        lower = (text or "").lower()
        signals: list[str] = []
        buckets = {
            "media/content": ("media", "youtube", "podcast", "контент", "блог", "reels", "shorts"),
            "agency": ("agency", "агентство", "маркетинг", "performance", "seo", "smm"),
            "ecommerce": ("shop", "store", "ecommerce", "магазин", "каталог", "доставка"),
            "saas": ("saas", "software", "platform", "crm", "api", "dashboard"),
            "education": ("course", "academy", "школ", "обуч", "университет"),
        }
        for label, words in buckets.items():
            if any(word in lower for word in words):
                signals.append(label)
        company = str(contact.get("company") or "").strip()
        if company:
            signals.append("company_from_row")
        if str(contact.get("note") or contact.get("topic") or "").strip():
            signals.append("user_note")
        return signals[:8]

    @staticmethod
    def _category_from_signals(signals: list[str]) -> str:
        for signal in signals:
            if signal not in {"company_from_row", "user_note"}:
                return signal
        return signals[0] if signals else ""
