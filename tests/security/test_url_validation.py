import asyncio

import pytest

from backend.security.url_validation import (
    PublicNetworkGuard,
    URLValidationError,
    normalize_http_url,
    validate_public_http_url,
    validate_websocket_url,
)


def public_resolver(hostname, port):
    assert hostname == "example.com"
    assert port == 443
    return ["93.184.216.34"]


def test_normalize_valid_https_url_and_strip_fragment():
    assert normalize_http_url("https://example.com/privacy#section") == "https://example.com/privacy"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/",
        "http://127.0.0.1/",
        "http://10.1.2.3/",
        "http://169.254.169.254/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "https://user:pass@example.com/",
        "https://example.com:8443/",
        "http://localhost/",
        "http://intranet/",
        "http://127.1/",
        "https://example.com/a\\b",
        "https://example.com/\nheader-injection",
    ],
)
def test_rejects_invalid_or_non_public_urls(url):
    with pytest.raises(URLValidationError):
        normalize_http_url(url)


@pytest.mark.asyncio
async def test_accepts_domain_when_all_dns_answers_are_public():
    result = await validate_public_http_url(
        "https://example.com/", resolver=public_resolver
    )
    assert result == "https://example.com/"


@pytest.mark.asyncio
async def test_rejects_private_dns_answer():
    with pytest.raises(URLValidationError, match="non-public"):
        await validate_public_http_url(
            "https://example.com/",
            resolver=lambda hostname, port: ["93.184.216.34", "10.0.0.7"],
        )


@pytest.mark.asyncio
async def test_rejects_loopback_dns_answer():
    with pytest.raises(URLValidationError, match="non-public"):
        await validate_public_http_url(
            "https://example.com/",
            resolver=lambda hostname, port: ["127.0.0.1"],
        )


@pytest.mark.asyncio
async def test_rejects_empty_dns_answers():
    with pytest.raises(URLValidationError, match="did not resolve"):
        await validate_public_http_url(
            "https://example.com/", resolver=lambda hostname, port: []
        )


@pytest.mark.asyncio
async def test_websocket_destination_uses_same_public_ip_policy():
    with pytest.raises(URLValidationError):
        await validate_websocket_url("ws://127.0.0.1/socket")


class FakeRequest:
    def __init__(self, url):
        self.url = url


class FakeRoute:
    def __init__(self, url):
        self.request = FakeRequest(url)
        self.continued = False
        self.aborted = False
        self.abort_reason = None

    async def continue_(self):
        self.continued = True

    async def abort(self, reason):
        self.aborted = True
        self.abort_reason = reason


@pytest.mark.asyncio
async def test_browser_guard_aborts_loopback_request():
    guard = PublicNetworkGuard()
    route = FakeRoute("http://127.0.0.1/admin")

    await guard.handle_http_request(route)

    assert route.aborted is True
    assert route.continued is False
    assert guard.requests_blocked == 1


class FakeWebSocketRoute:
    def __init__(self, url):
        self.url = url
        self.connected = False
        self.closed = False
        self.close_code = None

    async def connect(self):
        self.connected = True

    async def close(self, code=None, reason=None):
        self.closed = True
        self.close_code = code


@pytest.mark.asyncio
async def test_browser_guard_closes_loopback_websocket():
    guard = PublicNetworkGuard()
    route = FakeWebSocketRoute("ws://[::1]/socket")

    await guard.handle_websocket(route)

    assert route.closed is True
    assert route.connected is False
    assert route.close_code == 1008
    assert guard.websockets_blocked == 1


@pytest.mark.asyncio
async def test_browser_guard_enforces_request_budget():
    guard = PublicNetworkGuard(max_network_requests=1)
    first = FakeRoute("http://127.0.0.1/")
    second = FakeRoute("http://127.0.0.1/another")

    await guard.handle_http_request(first)
    await guard.handle_http_request(second)

    assert first.aborted is True
    assert second.aborted is True
    assert guard.requests_seen == 2

@pytest.mark.asyncio
async def test_browser_guard_continues_public_request_after_validation(monkeypatch):
    from backend.security import url_validation as validation_module

    async def approve_public(url, **_kwargs):
        assert url == "https://example.com/"
        return url

    monkeypatch.setattr(validation_module, "validate_public_http_url", approve_public)
    guard = PublicNetworkGuard()
    route = FakeRoute("https://example.com/")

    await guard.handle_http_request(route)

    assert route.continued is True
    assert route.aborted is False


@pytest.mark.asyncio
async def test_websocket_validator_rejects_control_characters():
    with pytest.raises(URLValidationError):
        await validate_websocket_url("wss://example.com/\npath")
