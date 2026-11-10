"""Google OIDC server flow; authorize identities independently of Google login.

Redis holds short-lived one-time OAuth state and account-link challenges. No
Google bearer/refresh token is persisted or exposed to JavaScript.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.api.services.auth_service import normalize_email
from backend.core.config import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class OidcUnavailable(Exception):
    """Missing configuration or unavailable authentication infrastructure."""


class OidcDenied(Exception):
    """OAuth transaction or Google identity failed verification."""


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    hd: str | None
    name: str | None


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def code_challenge(verifier: str) -> str:
    import base64

    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def require_google_configuration() -> None:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise OidcUnavailable("Google Sign-In is not configured.")


def verify_google_identity(token: str, expected_nonce: str) -> GoogleIdentity:
    """Validate Google's signature, key, issuer, audience, times and nonce."""
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token

        claims = google_id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=30,
        )
        if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise ValueError("Unexpected issuer")
        if not secrets.compare_digest(str(claims.get("nonce", "")), expected_nonce):
            raise ValueError("Nonce mismatch")
        if claims.get("azp") not in (None, settings.GOOGLE_CLIENT_ID):
            raise ValueError("Unexpected authorized party")
        if claims.get("email_verified") is not True:
            raise ValueError("Unverified email")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not (1 <= len(subject) <= 255):
            raise ValueError("Invalid subject")
        email = normalize_email(claims["email"])
        hd_raw = claims.get("hd")
        hd = hd_raw.strip().lower() if isinstance(hd_raw, str) else None
        if hd and len(hd) > 253:
            raise ValueError("Invalid hosted domain")
        # A mismatched hd is NEVER sufficient for domain admission. An exact
        # email allowlist may still accept a verified external/alias account.
        name = claims.get("name")
        if not isinstance(name, str):
            name = None
        return GoogleIdentity(sub=subject, email=email, hd=hd, name=name[:255] if name else None)
    except Exception as exc:
        raise OidcDenied("Google identity verification failed") from exc


class OidcStateStore:
    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or settings.AUTH_OAUTH_REDIS_URL
        self._redis: Any = None

    def _client(self):
        if self._redis is None:
            from redis import Redis

            self._redis = Redis.from_url(
                self.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
            )
        return self._redis

    def _put(self, name: str, token: str, payload: dict[str, Any], ttl: int) -> None:
        try:
            ok = self._client().set(f"privacheck:oidc:{name}:{digest(token)}", json.dumps(payload), nx=True, ex=ttl)
            if not ok:
                raise OidcUnavailable("Unable to establish one-time authentication challenge.")
        except Exception as exc:
            raise OidcUnavailable("Temporary authentication storage is unavailable.") from exc

    def _consume(self, name: str, token: str) -> dict[str, Any]:
        if not token or len(token) > 256:
            raise OidcDenied("Missing or invalid authentication challenge")
        try:
            raw = self._client().getdel(f"privacheck:oidc:{name}:{digest(token)}")
        except Exception as exc:
            raise OidcUnavailable("Temporary authentication storage is unavailable.") from exc
        if not raw:
            raise OidcDenied("Authentication challenge was used or expired")
        try:
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("Bad state")
            return result
        except ValueError as exc:
            raise OidcDenied("Invalid authentication challenge") from exc

    def start(self, browser_binding: str) -> str:
        require_google_configuration()
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        nonce = secrets.token_urlsafe(32)
        self._put(
            "state", state,
            {"browser_hash": digest(browser_binding), "verifier": verifier, "nonce": nonce},
            settings.AUTH_OAUTH_TRANSACTION_TTL_SECONDS,
        )
        return AUTH_URL + "?" + urlencode({
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        })

    def consume_callback(self, *, state: str, browser_binding: str) -> dict[str, str]:
        transaction = self._consume("state", state)
        if not browser_binding or not secrets.compare_digest(
            str(transaction.get("browser_hash", "")), digest(browser_binding)
        ):
            raise OidcDenied("Authentication callback did not match initiating browser")
        if not all(isinstance(transaction.get(key), str) for key in ("nonce", "verifier")):
            raise OidcDenied("Invalid authentication transaction")
        return transaction

    def create_link(self, *, identity: GoogleIdentity) -> str:
        ticket = secrets.token_urlsafe(32)
        self._put("link", ticket, {"sub": identity.sub, "email": identity.email, "hd": identity.hd, "name": identity.name}, 600)
        return ticket

    def consume_link(self, ticket: str) -> GoogleIdentity:
        record = self._consume("link", ticket)
        try:
            return GoogleIdentity(sub=record["sub"], email=record["email"], hd=record["hd"], name=record["name"])
        except (KeyError, TypeError, ValueError) as exc:
            raise OidcDenied("Invalid account-link challenge") from exc


def exchange_code(code: str, verifier: str) -> str:
    """Exchange once, over HTTPS; discard Google's access token immediately."""
    require_google_configuration()
    if not code or len(code) > 4096:
        raise OidcDenied("Invalid authorization code")
    try:
        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            response = client.post(TOKEN_URL, data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
            })
            response.raise_for_status()
            token = response.json().get("id_token")
        if not isinstance(token, str) or not token:
            raise ValueError("No Google ID token")
        return token
    except Exception as exc:
        raise OidcDenied("Google code exchange failed") from exc
