"""URL validation and outbound-request policy for the PrivaCheck browser.

This module is a defense-in-depth SSRF control, not a substitute for network
isolation. The browser worker must still run behind an egress policy that
prevents connections to private, loopback, link-local, reserved and metadata
networks. Application-level DNS checks cannot, by themselves, eliminate the
DNS time-of-check/time-of-use race between validation and Chromium connecting.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from typing import Callable, Iterable
from urllib.parse import SplitResult, urlsplit, urlunsplit

MAX_URL_LENGTH = 2_048
DEFAULT_DNS_TIMEOUT_SECONDS = 2.0
DEFAULT_MAX_NETWORK_REQUESTS = 1_500
DEFAULT_MAX_UNIQUE_HOSTS = 100

_FORBIDDEN_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home",
    ".home.arpa",
    ".test",
    ".invalid",
    ".example",
)
_FORBIDDEN_EXACT_HOSTS = {"localhost", "localhost."}
_DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
_NUMERIC_HOST_RE = re.compile(r"^[0-9.]+$")
_NUMERIC_ALIAS_RE = re.compile(
    r"^(?:(?:0x[0-9a-f]+)|(?:[0-9]+))(?:\.(?:(?:0x[0-9a-f]+)|(?:[0-9]+)))*$",
    re.IGNORECASE,
)


class URLValidationError(ValueError):
    """Raised when a requested URL is malformed or unsafe to scan."""


@dataclass(frozen=True)
class _ParsedTarget:
    normalized_url: str
    scheme: str
    hostname: str
    port: int
    ip_literal: ipaddress.IPv4Address | ipaddress.IPv6Address | None


def _is_public_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True only for globally routable unicast IP addresses."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped

    return bool(
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def _parse_and_normalize_http_url(value: str) -> _ParsedTarget:
    if not isinstance(value, str):
        raise URLValidationError("URL must be a string.")
    if not value or len(value) > MAX_URL_LENGTH:
        raise URLValidationError("URL is empty or exceeds the permitted length.")
    if value != value.strip():
        raise URLValidationError("URL must not contain leading or trailing whitespace.")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise URLValidationError("URL contains control characters.")
    if any(char.isspace() for char in value) or "\\" in value:
        raise URLValidationError("URL contains unsupported whitespace or backslashes.")

    try:
        parsed: SplitResult = urlsplit(value)
        scheme = parsed.scheme.lower()
        # Accessing .port can itself raise ValueError for malformed ports.
        supplied_port = parsed.port
    except ValueError as exc:
        raise URLValidationError("URL is malformed.") from exc

    if scheme not in {"http", "https"}:
        raise URLValidationError("Only HTTP and HTTPS URLs are allowed.")
    if not parsed.netloc or not parsed.hostname:
        raise URLValidationError("URL must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise URLValidationError("URLs containing credentials are not allowed.")
    if "%" in parsed.hostname:
        # Reject IPv6 zone identifiers and percent-encoded hostname tricks.
        raise URLValidationError("Encoded hostnames and IP zone identifiers are not allowed.")

    default_port = 80 if scheme == "http" else 443
    port = supplied_port if supplied_port is not None else default_port
    if port != default_port:
        raise URLValidationError("Only the standard HTTP (80) and HTTPS (443) ports are allowed.")

    raw_host = parsed.hostname.rstrip(".")
    if not raw_host:
        raise URLValidationError("URL must include a valid hostname.")

    ip_literal: ipaddress.IPv4Address | ipaddress.IPv6Address | None
    try:
        ip_literal = ipaddress.ip_address(raw_host)
    except ValueError:
        ip_literal = None

    if ip_literal is not None:
        if not _is_public_ip(ip_literal):
            raise URLValidationError("URL destination is not a public IP address.")
        hostname = ip_literal.compressed.lower()
        authority_host = f"[{hostname}]" if isinstance(ip_literal, ipaddress.IPv6Address) else hostname
    else:
        # Reject legacy/non-canonical numeric host forms such as 127.1,
        # 0177.0.0.1, 0x7f000001 and similar browser/resolver ambiguities.
        if _NUMERIC_HOST_RE.fullmatch(raw_host) or _NUMERIC_ALIAS_RE.fullmatch(raw_host):
            raise URLValidationError("Non-canonical numeric hostnames are not allowed.")

        try:
            hostname = raw_host.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise URLValidationError("Hostname is invalid.") from exc

        if len(hostname) > 253 or "." not in hostname:
            raise URLValidationError("A fully qualified public hostname is required.")
        if hostname in _FORBIDDEN_EXACT_HOSTS or any(
            hostname.endswith(suffix) for suffix in _FORBIDDEN_HOST_SUFFIXES
        ):
            raise URLValidationError("Local or reserved hostnames are not allowed.")

        labels = hostname.split(".")
        if any(not _DNS_LABEL_RE.fullmatch(label) for label in labels):
            raise URLValidationError("Hostname contains an invalid DNS label.")
        authority_host = hostname

    # Remove fragments because they are client-side only. Keep path/query for
    # normal website scanning, and omit a default port to canonicalize the URL.
    normalized_url = urlunsplit(
        (scheme, authority_host, parsed.path, parsed.query, "")
    )
    return _ParsedTarget(
        normalized_url=normalized_url,
        scheme=scheme,
        hostname=hostname,
        port=port,
        ip_literal=ip_literal,
    )


def normalize_http_url(value: str) -> str:
    """Validate URL syntax and policy; do not perform DNS resolution.

    Use this for fast request-model validation. Before a scan starts, and for
    outbound browser requests, also call :func:`validate_public_http_url`.
    """
    return _parse_and_normalize_http_url(value).normalized_url


def _resolve_host(hostname: str, port: int) -> list[str]:
    """Resolve every IPv4/IPv6 answer returned by the system resolver."""
    try:
        results = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except (OSError, socket.gaierror) as exc:
        raise URLValidationError("Destination hostname could not be resolved safely.") from exc

    addresses: list[str] = []
    for result in results:
        sockaddr = result[4]
        if not sockaddr:
            continue
        addresses.append(str(sockaddr[0]))

    if not addresses:
        raise URLValidationError("Destination hostname did not resolve to an IP address.")
    return addresses


async def validate_public_http_url(
    value: str,
    *,
    dns_timeout_seconds: float = DEFAULT_DNS_TIMEOUT_SECONDS,
    resolver: Callable[[str, int], Iterable[str]] | None = None,
) -> str:
    """Validate a scan URL and reject DNS answers outside the public Internet.

    All A/AAAA answers must be globally routable. A mixed public/private DNS
    answer is rejected rather than selecting only the public answer. ``resolver``
    is provided to make tests deterministic; production callers should omit it.
    """
    target = _parse_and_normalize_http_url(value)
    if target.ip_literal is not None:
        # Literal IPs were already classified by the syntax/policy parser.
        return target.normalized_url

    if dns_timeout_seconds <= 0:
        raise URLValidationError("DNS timeout must be positive.")

    resolve = resolver or _resolve_host
    try:
        addresses = await asyncio.wait_for(
            asyncio.to_thread(resolve, target.hostname, target.port),
            timeout=dns_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise URLValidationError("Destination DNS lookup timed out.") from exc
    except URLValidationError:
        raise
    except Exception as exc:
        raise URLValidationError("Destination hostname could not be resolved safely.") from exc

    parsed_addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for raw_address in addresses:
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            raise URLValidationError("DNS returned an invalid destination address.") from exc
        if not _is_public_ip(address):
            raise URLValidationError("Destination DNS includes a non-public IP address.")
        parsed_addresses.append(address)

    if not parsed_addresses:
        raise URLValidationError("Destination hostname did not resolve to an IP address.")

    return target.normalized_url


async def validate_websocket_url(
    value: str,
    *,
    dns_timeout_seconds: float = DEFAULT_DNS_TIMEOUT_SECONDS,
) -> str:
    """Validate a ws/wss destination using the HTTP(S) destination policy."""
    if not isinstance(value, str) or not value or len(value) > MAX_URL_LENGTH:
        raise URLValidationError("WebSocket URL is empty or exceeds the permitted length.")
    if value != value.strip() or any(
        ord(char) < 0x20 or ord(char) == 0x7F or char.isspace() for char in value
    ) or "\\" in value:
        raise URLValidationError("WebSocket URL contains unsupported whitespace or backslashes.")

    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise URLValidationError("WebSocket URL is malformed.") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"ws", "wss"}:
        raise URLValidationError("Only ws:// and wss:// WebSocket destinations are allowed.")

    mapped_scheme = "http" if scheme == "ws" else "https"
    mapped_url = urlunsplit(
        (mapped_scheme, parsed.netloc, parsed.path, parsed.query, "")
    )
    validated = await validate_public_http_url(
        mapped_url,
        dns_timeout_seconds=dns_timeout_seconds,
    )
    validated_parts = urlsplit(validated)
    restored_scheme = "ws" if scheme == "ws" else "wss"
    return urlunsplit(
        (restored_scheme, validated_parts.netloc, validated_parts.path, validated_parts.query, "")
    )


@dataclass
class PublicNetworkGuard:
    """Apply the destination policy to browser HTTP(S) and WebSocket traffic."""

    max_network_requests: int = DEFAULT_MAX_NETWORK_REQUESTS
    max_unique_hosts: int = DEFAULT_MAX_UNIQUE_HOSTS
    dns_timeout_seconds: float = DEFAULT_DNS_TIMEOUT_SECONDS
    requests_seen: int = 0
    requests_blocked: int = 0
    websockets_seen: int = 0
    websockets_blocked: int = 0
    _seen_hosts: set[str] = field(default_factory=set, init=False, repr=False)
    _state_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _dns_semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(32), init=False, repr=False)

    async def install(self, context: object) -> None:
        """Install routing before navigation; fail closed if hooks are unavailable."""
        route = getattr(context, "route", None)
        route_web_socket = getattr(context, "route_web_socket", None)
        if not callable(route) or not callable(route_web_socket):
            raise RuntimeError(
                "Browser context lacks required HTTP/WebSocket routing support; scan refused."
            )

        await route("**/*", self.handle_http_request)
        await route_web_socket("**/*", self.handle_websocket)

    async def _reserve_budget(self, hostname: str | None) -> None:
        async with self._state_lock:
            self.requests_seen += 1
            if self.requests_seen > self.max_network_requests:
                raise URLValidationError("Scan outbound-request budget exceeded.")
            if hostname and hostname not in self._seen_hosts:
                if len(self._seen_hosts) >= self.max_unique_hosts:
                    raise URLValidationError("Scan outbound-host budget exceeded.")
                self._seen_hosts.add(hostname)

    async def handle_http_request(self, route: object) -> None:
        """Fail closed on unsafe URLs and continue only validated requests."""
        request = getattr(route, "request", None)
        request_url = getattr(request, "url", "")
        try:
            parts = urlsplit(request_url)
            scheme = parts.scheme.lower()
            # These schemes do not make network connections. Permit ordinary
            # page-local resources, while blocking file:/ftp:/custom protocols.
            if scheme in {"about", "data", "blob", "javascript"}:
                await route.continue_()
                return
            try:
                raw_hostname = urlsplit(request_url).hostname
            except ValueError:
                raw_hostname = None
            await self._reserve_budget(raw_hostname)
            target = _parse_and_normalize_http_url(request_url)
            async with self._dns_semaphore:
                await validate_public_http_url(
                    target.normalized_url,
                    dns_timeout_seconds=self.dns_timeout_seconds,
                )
            await route.continue_()
        except Exception:
            self.requests_blocked += 1
            try:
                await route.abort("blockedbyclient")
            except Exception:
                # Playwright may report that another browser event already
                # completed the route; the security decision remains fail-closed.
                pass

    async def handle_websocket(self, websocket_route: object) -> None:
        """Only connect WebSockets after validating their resolved destination."""
        websocket_url = getattr(websocket_route, "url", "")
        self.websockets_seen += 1
        try:
            try:
                raw_hostname = urlsplit(websocket_url).hostname
            except ValueError:
                raw_hostname = None
            await self._reserve_budget(raw_hostname)
            async with self._dns_semaphore:
                await validate_websocket_url(
                    websocket_url,
                    dns_timeout_seconds=self.dns_timeout_seconds,
                )
            await websocket_route.connect()
        except Exception:
            self.websockets_blocked += 1
            try:
                await websocket_route.close(
                    code=1008,
                    reason="Blocked by PrivaCheck network policy",
                )
            except Exception:
                pass
