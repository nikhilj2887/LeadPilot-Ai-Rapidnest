from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from leadpilot.application.discovery import DiscoveryError
from leadpilot.infrastructure.discovery_security import validate_public_url


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status_code: int
    headers: dict[str, str]
    text: str
    response_time_ms: int


class WebsiteClient:
    def __init__(
        self,
        *,
        connect_timeout: float,
        read_timeout: float,
        max_response_bytes: int,
        user_agent: str,
        retry_count: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._timeout = httpx.Timeout(read_timeout, connect=connect_timeout)
        self._maximum = max_response_bytes
        self._retries = retry_count
        self._headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
        }
        self._transport = transport

    def fetch(self, url: str, *, require_html: bool = True) -> FetchResult:
        current = validate_public_url(url)
        started = time.monotonic()
        with httpx.Client(
            timeout=self._timeout,
            headers=self._headers,
            follow_redirects=False,
            verify=True,
            transport=self._transport,
        ) as client:
            for _redirect in range(6):
                response = self._request(client, current)
                try:
                    if response.is_redirect:
                        target = response.headers.get("location")
                        if not target:
                            raise DiscoveryError(
                                "The website returned an invalid redirect."
                            )
                        current = validate_public_url(urljoin(current, target))
                        continue
                    content_type = response.headers.get("content-type", "").casefold()
                    if require_html and "html" not in content_type:
                        raise DiscoveryError("The website did not return an HTML page.")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > self._maximum:
                            raise DiscoveryError(
                                "The website response was too large to scan safely."
                            )
                    encoding = response.encoding or "utf-8"
                    return FetchResult(
                        url=str(response.url),
                        status_code=response.status_code,
                        headers={
                            key.casefold(): value
                            for key, value in response.headers.items()
                        },
                        text=bytes(body).decode(encoding, errors="replace"),
                        response_time_ms=round((time.monotonic() - started) * 1000),
                    )
                finally:
                    response.close()
        raise DiscoveryError("The website redirected too many times.")

    def _request(self, client: httpx.Client, url: str) -> httpx.Response:
        for attempt in range(self._retries + 1):
            try:
                response = client.send(client.build_request("GET", url), stream=True)
                if response.status_code in {502, 503, 504} and attempt < self._retries:
                    response.close()
                    continue
                if response.status_code >= 400:
                    response.close()
                    raise DiscoveryError(
                        f"The website returned HTTP {response.status_code}."
                    )
                return response
            except DiscoveryError:
                raise
            except httpx.TimeoutException as exc:
                if attempt >= self._retries:
                    raise DiscoveryError("The website request timed out.") from exc
            except httpx.TooManyRedirects as exc:
                raise DiscoveryError("The website redirected too many times.") from exc
            except httpx.ConnectError as exc:
                message = "A secure connection to the website could not be established."
                raise DiscoveryError(message) from exc
            except httpx.HTTPError as exc:
                raise DiscoveryError("The website could not be reached.") from exc
        raise DiscoveryError("The website could not be reached.")
