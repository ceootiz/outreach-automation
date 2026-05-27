from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .logger_setup import redact_secret


class HttpClientError(RuntimeError):
    pass


class JsonHttpClient:
    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def get_json(self, url: str, *, secrets: list[str] | None = None) -> dict[str, Any]:
        request = urllib.request.Request(url, method="GET")
        return self._request_json(request, secrets or [])

    def post_form(
        self,
        url: str,
        data: dict[str, Any],
        *,
        secrets: list[str] | None = None,
    ) -> dict[str, Any]:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        return self._request_json(request, secrets or [])

    def _request_json(self, request: urllib.request.Request, secrets: list[str]) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise HttpClientError(
                redact_secret(f"HTTP {exc.code}: {body}", extra_secrets=secrets)
            ) from exc
        except urllib.error.URLError as exc:
            raise HttpClientError(
                redact_secret(f"Network error: {exc}", extra_secrets=secrets)
            ) from exc
        except json.JSONDecodeError as exc:
            raise HttpClientError("HTTP response is not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise HttpClientError("HTTP response JSON is not an object.")
        return payload
