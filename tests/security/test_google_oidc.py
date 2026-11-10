"""Identity claim policy tests with the official Google verifier mocked at its boundary.

These tests intentionally do not substitute for real signature/key validation on
an installed google-auth dependency or a full Google browser integration test.
"""
import sys
from types import ModuleType

import pytest

from backend.security.google_oidc import OidcDenied, code_challenge, verify_google_identity
from backend.core.config import settings


@pytest.fixture()
def google_verifier(monkeypatch):
    claims = {
        "iss": "https://accounts.google.com",
        "sub": "123456789",
        "email": "person@iiitg.ac.in",
        "email_verified": True,
        "hd": "iiitg.ac.in",
        "nonce": "expected-nonce",
    }
    verifier_calls = []
    request_mod = ModuleType("google.auth.transport.requests")
    request_mod.Request = lambda: object()
    transport_mod = ModuleType("google.auth.transport")
    transport_mod.requests = request_mod
    auth_mod = ModuleType("google.auth")
    auth_mod.transport = transport_mod
    id_mod = ModuleType("google.oauth2.id_token")

    def verify(token, request, audience, *, clock_skew_in_seconds):
        verifier_calls.append((token, audience, clock_skew_in_seconds))
        return claims

    id_mod.verify_oauth2_token = verify
    oauth_mod = ModuleType("google.oauth2")
    oauth_mod.id_token = id_mod
    for name, module in {
        "google.auth": auth_mod,
        "google.auth.transport": transport_mod,
        "google.auth.transport.requests": request_mod,
        "google.oauth2": oauth_mod,
        "google.oauth2.id_token": id_mod,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-google-client-id")
    yield claims, verifier_calls


def test_pkce_is_s256_and_not_plaintext():
    assert code_challenge("verifier") == "iMnq5o6zALKXGivsnlom_0F5_WYda32GHkxlV7mq7hQ"
    assert "verifier" != code_challenge("verifier")


def test_google_claims_verified_with_configured_audience(google_verifier):
    claims, calls = google_verifier
    identity = verify_google_identity("signed-test-token", "expected-nonce")
    assert identity.email == "person@iiitg.ac.in"
    assert identity.hd == "iiitg.ac.in"
    assert calls == [("signed-test-token", "test-google-client-id", 30)]


@pytest.mark.parametrize("changed", [
    {"nonce": "different"},
    {"iss": "https://attacker.example"},
    {"email_verified": False},
    {"sub": ""},
    {"azp": "different-client"},
])
def test_untrusted_google_claims_rejected(google_verifier, changed):
    claims, _ = google_verifier
    claims.update(changed)
    with pytest.raises(OidcDenied):
        verify_google_identity("signed-test-token", "expected-nonce")


def test_no_hd_is_a_valid_verified_consumer_identity_but_not_workspace(google_verifier):
    claims, _ = google_verifier
    claims.pop("hd")
    identity = verify_google_identity("signed-test-token", "expected-nonce")
    assert identity.hd is None  # Platform domain allowlist must deny separately.


def test_mismatched_hd_is_not_trusted_for_workspace_but_can_be_exact_email(google_verifier):
    claims, _ = google_verifier
    claims["hd"] = "other-workspace.example"
    identity = verify_google_identity("signed-test-token", "expected-nonce")
    # Domain admission code separately requires identity.hd == email domain.
    assert identity.email == "person@iiitg.ac.in"
    assert identity.hd != "iiitg.ac.in"
