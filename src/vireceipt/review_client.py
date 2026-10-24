"""Bounded HTTP transport for the local review editor; no redirects or retries."""

import ipaddress
import json
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class ReviewClientError(Exception):
    """Safe transport error; status allows the editor to distinguish stale revisions."""

    def __init__(self, status: int | None = None) -> None:
        self.status = status
        super().__init__(f"Review API HTTP {status}" if status else "Review API request failed")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class ReviewAPIClient:
    """Connect only to a server explicitly configured on the same computer."""

    def __init__(self, base_url: str) -> None:
        try:
            parsed = urlsplit(base_url)
            host = parsed.hostname or ""
            try:
                local = ipaddress.ip_address(host).is_loopback
            except ValueError:
                local = host == "localhost"
            if (
                any(character.isspace() for character in base_url)
                or parsed.scheme not in {"http", "https"}
                or not local
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or (parsed.port is not None and not 1 <= parsed.port <= 65535)
            ):
                raise ValueError
        except ValueError:
            raise ValueError("Use a loopback review API URL without credentials or paths") from None
        self.base_url = base_url.rstrip("/")
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def _request(
        self, path: str, *, body: dict[str, Any] | None = None, image: bool = False
    ) -> Any:
        try:
            payload = (
                None
                if body is None
                else json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            )
            request = Request(
                self.base_url + path,
                data=payload,
                method="GET" if body is None else "PUT",
                headers={"Content-Type": "application/json"},
            )
            limit = MAX_IMAGE_BYTES if image else MAX_JSON_BYTES
            with self._opener.open(request, timeout=10) as response:
                raw = response.read(limit + 1)
            if len(raw) > limit:
                raise ValueError
            if image:
                return raw
            decoded = json.loads(raw.decode("utf-8"))
            json.dumps(decoded, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if not isinstance(decoded, dict):
                raise ValueError
            return decoded
        except HTTPError as error:
            error.close()
            raise ReviewClientError(error.code) from None
        except (
            OSError,
            URLError,
            HTTPException,
            ValueError,
            TypeError,
            OverflowError,
            RecursionError,
        ):
            raise ReviewClientError from None

    def list_requests(
        self, *, limit: int = 20, offset: int = 0, status: str | None = None
    ) -> dict[str, Any]:
        """Fetch one metadata page."""
        query = dict(limit=limit, offset=offset)
        if status is not None:
            query["status"] = status
        return self._request("/v1/requests?" + urlencode(query))

    def get(self, job_id: str) -> dict[str, Any]:
        """Fetch a job snapshot without image bytes."""
        return self._request(f"/v1/requests/{UUID(job_id)}")

    def image(self, job_id: str) -> bytes:
        """Read bounded original image bytes."""
        return self._request(f"/v1/requests/{UUID(job_id)}/image", image=True)

    def correct(self, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Submit exactly one correction attempt, preserving HTTP409 for the caller."""
        return self._request(f"/v1/requests/{UUID(job_id)}/correction", body=body)
