from __future__ import annotations

import socket

import pytest

from leadpilot.application.discovery import DiscoveryError
from leadpilot.infrastructure.discovery_security import (
    normalize_url,
    validate_public_url,
)


def resolver_for(address: str):
    def resolve(*_args: object, **_kwargs: object):
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (address, 0))]

    return resolve


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("example.com", "https://example.com/"),
        ("HTTP://Example.COM/path", "http://example.com/path"),
        ("https://example.com:8443/a?q=1#fragment", "https://example.com:8443/a?q=1"),
    ],
)
def test_url_normalization(value: str, expected: str) -> None:
    assert normalize_url(value) == expected


@pytest.mark.parametrize(
    "value", ["file:///tmp/a", "ftp://example.com", "mailto:a@example.com"]
)
def test_unsupported_schemes_are_rejected(value: str) -> None:
    with pytest.raises(DiscoveryError):
        normalize_url(value)


@pytest.mark.parametrize(
    "host",
    ["localhost", "127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.169.254", "::1"],
)
def test_internal_addresses_are_rejected(host: str) -> None:
    url = f"http://[{host}]" if ":" in host else f"http://{host}"
    with pytest.raises(DiscoveryError):
        validate_public_url(url, resolver_for("93.184.216.34"))


def test_public_resolved_address_is_accepted() -> None:
    assert (
        validate_public_url("https://example.test", resolver_for("93.184.216.34"))
        == "https://example.test/"
    )


def test_private_dns_result_is_rejected() -> None:
    with pytest.raises(DiscoveryError):
        validate_public_url("https://example.test", resolver_for("10.0.0.8"))
