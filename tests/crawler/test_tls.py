import ssl

from backend.crawler import tls as tls_module
from backend.crawler.tls import TLSCollector


class FakeRawSocket:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


class FakeTLSSocket:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def version(self):
        return "TLSv1.3"

    def getpeercert(self):
        return {
            "subject": (
                (
                    ("commonName", "example.com"),
                ),
            ),
            "issuer": (
                (
                    ("commonName", "Test CA"),
                ),
            ),
            "notBefore": "Jan 01 00:00:00 2026 GMT",
            "notAfter": "Jan 01 00:00:00 2027 GMT",
        }


class FakeSSLContext:
    def wrap_socket(self, raw_socket, server_hostname):
        assert server_hostname == "example.com"
        return FakeTLSSocket()


def test_tls_verification_succeeds(monkeypatch):
    monkeypatch.setattr(
        tls_module.ssl,
        "create_default_context",
        lambda: FakeSSLContext(),
    )

    monkeypatch.setattr(
        tls_module.socket,
        "create_connection",
        lambda address, timeout: FakeRawSocket(),
    )

    observation = TLSCollector().verify(
        "https://example.com/",
    )

    assert observation.category == "tls_certificate"
    assert observation.data["verified"] is True
    assert observation.data["hostname"] == "example.com"
    assert observation.data["port"] == 443
    assert observation.data["protocol"] == "https"
    assert observation.data["tls_version"] == "TLSv1.3"
    assert observation.data["error"] is None


def test_tls_verification_fails_for_invalid_certificate(monkeypatch):
    class InvalidCertificateContext:
        def wrap_socket(self, raw_socket, server_hostname):
            raise ssl.SSLCertVerificationError(
                1,
                "certificate verify failed",
            )

    monkeypatch.setattr(
        tls_module.ssl,
        "create_default_context",
        lambda: InvalidCertificateContext(),
    )

    monkeypatch.setattr(
        tls_module.socket,
        "create_connection",
        lambda address, timeout: FakeRawSocket(),
    )

    observation = TLSCollector().verify(
        "https://example.com/",
    )

    assert observation.category == "tls_certificate"
    assert observation.data["verified"] is False
    assert observation.data["protocol"] == "https"
    assert observation.data["error"] is not None


def test_tls_verification_fails_when_connection_cannot_be_established(
    monkeypatch,
):
    def raise_connection_error(address, timeout):
        raise OSError("Connection refused")

    monkeypatch.setattr(
        tls_module.socket,
        "create_connection",
        raise_connection_error,
    )

    observation = TLSCollector().verify(
        "https://example.com/",
    )

    assert observation.category == "tls_certificate"
    assert observation.data["verified"] is False
    assert observation.data["error"] == "Connection refused"


def test_tls_verification_does_not_run_for_http_url():
    observation = TLSCollector().verify(
        "http://example.com/",
    )

    assert observation.category == "tls_certificate"
    assert observation.data["verified"] is False
    assert observation.data["protocol"] is None
    assert observation.data["error"] == "URL is not HTTPS."


def test_tls_verification_supports_explicit_port(monkeypatch):
    captured_address = {}

    monkeypatch.setattr(
        tls_module.ssl,
        "create_default_context",
        lambda: FakeSSLContext(),
    )

    def fake_connection(address, timeout):
        captured_address["value"] = address
        return FakeRawSocket()

    monkeypatch.setattr(
        tls_module.socket,
        "create_connection",
        fake_connection,
    )

    observation = TLSCollector().verify(
        "https://example.com:8443/",
    )

    assert observation.data["verified"] is True
    assert observation.data["port"] == 8443
    assert captured_address["value"] == (
        "example.com",
        8443,
    )