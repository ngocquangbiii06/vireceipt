"""Small non-streaming Chat Completions client for configured compatible endpoints."""

import ipaddress
import json
import math
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ChatAPIError(RuntimeError):
    """Sanitized API failure without credentials, image data or provider diagnostics."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class ChatClient:
    """Call an explicitly configured model; never select a provider or retry a request."""

    base_url: str
    model: str
    api_key: str | None = field(default=None, repr=False)
    timeout: float = 60
    max_tokens: int = 4096

    def __post_init__(self) -> None:
        url = urlsplit(self.base_url)
        host = url.hostname
        try:
            loopback = host == "localhost" or ipaddress.ip_address(host or "").is_loopback
        except ValueError:
            loopback = False
        if (
            not host
            or url.scheme not in {"https", "http"}
            or (url.scheme == "http" and not loopback)
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or not self.model.strip()
            or isinstance(self.timeout, bool)
            or not math.isfinite(self.timeout)
            or self.timeout <= 0
            or isinstance(self.max_tokens, bool)
            or not isinstance(self.max_tokens, int)
            or self.max_tokens <= 0
        ):
            raise ValueError("Invalid chat configuration")

    def complete(self, messages: list[dict[str, Any]]) -> str:
        """Return a complete assistant answer or raise a sanitized failure."""
        try:
            body = json.dumps(
                {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "max_tokens": self.max_tokens,
                    "stream": False,
                },
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, RecursionError):
            raise ChatAPIError("invalid_request") from None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            request = Request(self.base_url.rstrip("/") + "/chat/completions", body, headers)
            with build_opener(_NoRedirect()).open(request, timeout=self.timeout) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
        except HTTPError as error:
            status = error.code
            error.close()
            raise ChatAPIError(f"http_status_{status}") from None
        except (OSError, URLError, ValueError):
            raise ChatAPIError("network_error") from None
        try:
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError
            choice = json.loads(raw)["choices"][0]
            message = choice["message"]
            content = message["content"]
            if (
                choice["finish_reason"] != "stop"
                or not isinstance(content, str)
                or message.get("refusal")
                or message.get("tool_calls")
            ):
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError, RecursionError):
            raise ChatAPIError("invalid_response") from None
        return content
