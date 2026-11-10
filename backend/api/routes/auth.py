"""Google-only login, legacy linking, revocable sessions and CSRF bootstrap."""
from __future__ import annotations

import secrets
from typing import NoReturn
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.api.auth_schemas import CsrfResponse, LinkLegacyAccountRequest, UserResponse
from backend.api.dependencies.auth import csrf_cookie_name, get_current_user, require_csrf, session_cookie_name
from backend.api.services.google_auth_service import (
    AdmissionDenied, GoogleAuthService, LegacyLinkDenied, LegacyLinkRequired,
)
from backend.core.config import settings
from backend.infrastructure.database.models.user import User
from backend.security.google_oidc import (
    OidcDenied, OidcStateStore, OidcUnavailable,
    exchange_code, require_google_configuration, verify_google_identity,
)
from backend.security.rate_limit import AuthRateLimiter, RateLimitExceeded, RateLimiterUnavailable

router = APIRouter(prefix="/auth", tags=["Authentication"])
auth_service = GoogleAuthService()
rate_limiter = AuthRateLimiter()
state_store = OidcStateStore()


def _client_ip(request: Request) -> str:
    # Do not trust unsolicited forwarding headers.
    return request.client.host if request.client else "unknown"


def _limit(request: Request, purpose: str, identity: str = "") -> None:
    try:
        rate_limiter.enforce(
            purpose=purpose, client_ip=_client_ip(request), identity=identity,
            limit=settings.AUTH_LOGIN_RATE_LIMIT, window_seconds=settings.AUTH_LOGIN_RATE_WINDOW_SECONDS,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail="Too many authentication attempts.", headers={"Retry-After": str(exc.retry_after)}) from None
    except RateLimiterUnavailable:
        raise HTTPException(status_code=503, detail="Authentication is temporarily unavailable.") from None


def _cookie_name(suffix: str) -> str:
    return f"__Host-privacheck_{suffix}" if settings.auth_cookie_secure else f"privacheck_{suffix}"


def _set_cookie(response: Response, name: str, value: str, ttl: int | None, *, oauth: bool = False) -> None:
    response.set_cookie(
        key=name, value=value, max_age=ttl, httponly=True,
        secure=settings.auth_cookie_secure, samesite="lax" if oauth else settings.AUTH_COOKIE_SAMESITE, path="/",
    )


def _delete_cookie(response: Response, name: str) -> None:
    response.delete_cookie(key=name, secure=settings.auth_cookie_secure, httponly=True, samesite="lax", path="/")


def _set_csrf_cookie(response: Response, token: str) -> None:
    # CSRF stays in a browser-session cookie; its value is separately checked against X-CSRF-Token.
    _set_cookie(response, csrf_cookie_name(), token, None)


def _issue_csrf(response: Response) -> str:
    token = secrets.token_urlsafe(32)
    _set_csrf_cookie(response, token)
    return token


def _mark_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _unavailable() -> NoReturn:
    raise HTTPException(status_code=503, detail="Authentication service is temporarily unavailable.") from None


def _redirect(path: str, error: str | None = None) -> RedirectResponse:
    # The frontend origin is server-configured, never accepted from a request.
    query = ("?" + urlencode({"error": error})) if error else ""
    response = RedirectResponse(f"{settings.FRONTEND_ORIGIN.rstrip('/')}{path}{query}", status_code=303)
    _mark_no_store(response)
    return response


@router.get("/csrf", response_model=CsrfResponse)
def get_csrf(request: Request, response: Response) -> CsrfResponse:
    _mark_no_store(response)
    existing = request.cookies.get(csrf_cookie_name())
    token = existing if existing and 32 <= len(existing) <= 256 else secrets.token_urlsafe(32)
    _set_csrf_cookie(response, token)
    return CsrfResponse(csrf_token=token)


@router.get("/google/start", summary="Begin Google Sign-In")
def start_google(request: Request) -> RedirectResponse:
    try:
        require_google_configuration()
    except OidcUnavailable:
        _unavailable()
    _limit(request, "google-start")
    binding = secrets.token_urlsafe(32)
    try:
        url = state_store.start(binding)
    except OidcUnavailable:
        _unavailable()
    response = RedirectResponse(url, status_code=302)
    _set_cookie(response, _cookie_name("oauth"), binding, settings.AUTH_OAUTH_TRANSACTION_TTL_SECONDS, oauth=True)
    _mark_no_store(response)
    return response


@router.get("/google/callback", summary="Complete Google Sign-In")
def google_callback(
    request: Request, state: str = "", code: str = "", error: str = ""
) -> RedirectResponse:
    response = _redirect("/login", "google_denied")
    _delete_cookie(response, _cookie_name("oauth"))
    if error or not code or not state:
        return response
    try:
        transaction = state_store.consume_callback(
            state=state, browser_binding=request.cookies.get(_cookie_name("oauth"), "")
        )
        identity = verify_google_identity(exchange_code(code, transaction["verifier"]), transaction["nonce"])
        try:
            result = auth_service.sign_in(identity)
        except LegacyLinkRequired:
            ticket = state_store.create_link(identity=identity)
            response = _redirect("/link-account")
            _delete_cookie(response, _cookie_name("oauth"))
            _set_cookie(response, _cookie_name("link"), ticket, 600, oauth=True)
            return response
        response = _redirect("/")
        _delete_cookie(response, _cookie_name("oauth"))
        _set_cookie(response, session_cookie_name(), result.session_token, None)
        _issue_csrf(response)
        return response
    except AdmissionDenied:
        return _redirect("/login", "not_allowed")
    except (OidcDenied, LegacyLinkDenied):
        return _redirect("/login", "google_denied")
    except (OidcUnavailable, SQLAlchemyError):
        return _redirect("/login", "temporarily_unavailable")


@router.post("/google/link", response_model=UserResponse, summary="Link an existing password account")
def link_legacy(
    payload: LinkLegacyAccountRequest, request: Request, response: Response,
    _: None = Depends(require_csrf),
) -> UserResponse:
    _limit(request, "legacy-link")
    ticket = request.cookies.get(_cookie_name("link"), "")
    try:
        identity = state_store.consume_link(ticket)
        result = auth_service.link_legacy(identity=identity, old_password=payload.password)
    except (OidcDenied, LegacyLinkDenied):
        raise HTTPException(status_code=401, detail="Account linking failed. Sign in with Google again to retry.") from None
    except AdmissionDenied:
        raise HTTPException(status_code=403, detail="This Google account is not allowed.") from None
    except (OidcUnavailable, SQLAlchemyError):
        _unavailable()
    _mark_no_store(response)
    _delete_cookie(response, _cookie_name("link"))
    _set_cookie(response, session_cookie_name(), result.session_token, None)
    _issue_csrf(response)
    return UserResponse.model_validate(result.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Log out")
def logout(request: Request, response: Response, _: None = Depends(require_csrf)) -> None:
    token = request.cookies.get(session_cookie_name())
    if token:
        try:
            auth_service.revoke(session_token=token)
        except SQLAlchemyError:
            _unavailable()
    _mark_no_store(response)
    for cookie in (session_cookie_name(), csrf_cookie_name(), _cookie_name("link")):
        _delete_cookie(response, cookie)
    return None


@router.get("/me", response_model=UserResponse)
def get_me(response: Response, current_user: User = Depends(get_current_user)) -> UserResponse:
    _mark_no_store(response)
    return UserResponse.model_validate(current_user)
