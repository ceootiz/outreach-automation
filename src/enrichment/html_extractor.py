from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin

from .domain_analyzer import same_domain


@dataclass(slots=True)
class ExtractedPage:
    url: str
    title: str = ""
    description: str = ""
    text: str = ""
    links: list[str] = field(default_factory=list)


class _VisibleTextParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self.description = ""
        self._skip_stack: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript", "svg", "canvas"}:
            self._skip_stack.append(tag)
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            if name in {"description", "og:description", "twitter:description"} and not self.description:
                self.description = attrs_dict.get("content", "").strip()
        if tag == "a":
            href = attrs_dict.get("href", "").strip()
            if href and not href.startswith(("mailto:", "tel:", "javascript:")):
                self.links.append(urljoin(self.base_url, href))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()

    def handle_data(self, data: str) -> None:
        text = normalize_text(data)
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        elif not self._skip_stack:
            self.text_parts.append(text)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_page(html: str, url: str, *, max_text_length: int = 2500) -> ExtractedPage:
    parser = _VisibleTextParser(url)
    parser.feed(html or "")
    title = normalize_text(" ".join(parser.title_parts))[:300]
    description = normalize_text(parser.description)[:700]
    text = normalize_text(" ".join(parser.text_parts))[:max_text_length]
    deduped_links: list[str] = []
    for link in parser.links:
        clean = link.split("#", 1)[0]
        if clean not in deduped_links:
            deduped_links.append(clean)
    return ExtractedPage(
        url=url,
        title=title,
        description=description,
        text=text,
        links=deduped_links[:50],
    )


def discover_public_pages(page: ExtractedPage, base_domain: str, *, limit: int = 2) -> list[str]:
    candidates: list[str] = []
    keywords = (
        "about",
        "company",
        "team",
        "contact",
        "o-nas",
        "onas",
        "about-us",
        "kontakty",
        "contacts",
    )
    for link in page.links:
        lower = link.lower()
        if not same_domain(link, base_domain):
            continue
        if any(keyword in lower for keyword in keywords) and link not in candidates:
            candidates.append(link)
        if len(candidates) >= limit:
            break
    return candidates
