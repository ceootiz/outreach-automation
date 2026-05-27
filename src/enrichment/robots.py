from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass(slots=True)
class RobotsDecision:
    allowed: bool
    robots_url: str = ""
    warnings: list[str] = field(default_factory=list)


def robots_url_for(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def is_allowed_by_robots(
    url: str,
    *,
    robots_text: str,
    user_agent: str,
) -> bool:
    parsed = urlparse(url)
    path = parsed.path or "/"
    active = False
    matched_rules: list[str] = []
    for raw_line in (robots_text or "").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        key = key.lower()
        if key == "user-agent":
            agent = value.lower()
            active = agent == "*" or agent in user_agent.lower()
            continue
        if not active:
            continue
        if key == "disallow":
            rule = value.strip()
            if rule:
                matched_rules.append(rule)
        elif key == "allow":
            rule = value.strip()
            if rule and path.startswith(rule):
                return True
    return not any(path.startswith(rule) for rule in matched_rules)


class RobotsChecker:
    def __init__(self, http_client, *, user_agent: str):
        self.http_client = http_client
        self.user_agent = user_agent
        self._cache: dict[str, RobotsDecision | str] = {}

    def can_fetch(self, url: str) -> RobotsDecision:
        robots_url = robots_url_for(url)
        if not robots_url:
            return RobotsDecision(True, warnings=["Не удалось определить robots.txt URL."])
        cached = self._cache.get(robots_url)
        if isinstance(cached, RobotsDecision):
            return cached
        if isinstance(cached, str):
            allowed = is_allowed_by_robots(url, robots_text=cached, user_agent=self.user_agent)
            if not allowed:
                return RobotsDecision(False, robots_url=robots_url, warnings=["robots.txt запрещает fetch этой страницы."])
            return RobotsDecision(True, robots_url=robots_url)
        try:
            response = self.http_client.get(robots_url, timeout=5, user_agent=self.user_agent)
        except Exception as exc:
            decision = RobotsDecision(True, robots_url=robots_url, warnings=[f"robots.txt недоступен: {exc}"])
            self._cache[robots_url] = decision
            return decision
        if response.status_code == 404:
            decision = RobotsDecision(True, robots_url=robots_url)
            self._cache[robots_url] = decision
            return decision
        if response.status_code >= 400:
            decision = RobotsDecision(True, robots_url=robots_url, warnings=[f"robots.txt вернул HTTP {response.status_code}."])
            self._cache[robots_url] = decision
            return decision
        self._cache[robots_url] = response.text
        allowed = is_allowed_by_robots(url, robots_text=response.text, user_agent=self.user_agent)
        if not allowed:
            return RobotsDecision(False, robots_url=robots_url, warnings=["robots.txt запрещает fetch этой страницы."])
        return RobotsDecision(True, robots_url=robots_url)
