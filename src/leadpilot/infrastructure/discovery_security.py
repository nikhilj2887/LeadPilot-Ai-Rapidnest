from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from leadpilot.application.discovery import DiscoveryError

Resolver = Callable[..., list[tuple[object, object, object, object, tuple[Any, ...]]]]


def normalize_url(value: str) -> str:
    candidate = value.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise DiscoveryError("Only HTTP and HTTPS website URLs are supported.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise DiscoveryError("Enter a valid public website URL.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise DiscoveryError("The website URL contains an invalid port.") from exc
    host = parsed.hostname.lower().rstrip(".")
    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc += f":{port}"
    return urlunsplit(
        (parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, "")
    )


def _is_blocked(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not ip.is_global or ip in ipaddress.ip_network("169.254.169.254/32")


def validate_public_url(value: str, resolver: Resolver = socket.getaddrinfo) -> str:
    normalized = normalize_url(value)
    host = urlsplit(normalized).hostname or ""
    if host.casefold() == "localhost" or host.endswith(".localhost"):
        raise DiscoveryError("Local and internal network addresses cannot be scanned.")
    try:
        literal = ipaddress.ip_address(host)
        addresses = {str(literal)}
    except ValueError:
        try:
            addresses = {
                item[4][0] for item in resolver(host, None, type=socket.SOCK_STREAM)
            }
        except OSError as exc:
            raise DiscoveryError("The website hostname could not be resolved.") from exc
    if not addresses or any(_is_blocked(address) for address in addresses):
        raise DiscoveryError("Local and internal network addresses cannot be scanned.")
    return normalized
