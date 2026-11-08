"""Registration, login, logout, CSRF bootstrap, and current-user endpoints."""

from __future__ import annotations

import secrets
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError

from backend.api.auth_schemas import (
    AuthResponse,
    CsrfResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from backend.api.dependencies.auth import (
    csrf_cookie_name,
    get_current_user,
    require_csrf,
    session_cookie_name,
)
from backend.api.services.auth_service import (
    AccountAlreadyExistsError,
    AuthService,
    InvalidCredentialsError,
)
from backend.core.config import settings
from backend.infrastructure.database.models.user import User
from backend.security.rate_limit import (
    AuthRateLimiter,
    RateLimitExceeded,
    RateLimiterUnavailable,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
auth_service = AuthService()
rate_limiter = AuthRateLimiter()


def _client_ip(request: Request) -> str:
    # Deliberately ignore X-Forwarded-For. Only trust proxy headers after an
    # explicit trusted-proxy configuration is added to the deployment.
    return request.client.host if request.client is not None else "unknown"


def _enforce_rate_limit(
    *, purpose: str, request: Request, identity: str, limit: int, window_seconds: int
) -> None:
    try:
        rate_limiter.enforce(
            purpose=purpose,
            client_ip=_client_ip(request),
            identity=identity,
            limit=limit,
            window_seconds=window_seconds,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from None
    except RateLimiterUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable.",
            headers={"Retry-After": "5"},
        ) from None


def _set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=csrf_cookie_name(),
        value=token,
        max_age=3600,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=session_cookie_name(),
        value=token,
        max_age=settings.AUTH_SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )


def _issue_csrf(response: Response) -> str:
    token = secrets.token_urlsafe(32)
    _set_csrf_cookie(response, token)
    return token


def _mark_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _raise_service_unavailable() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication service is temporarily unavailable.",
    ) from None


@router.get("/csrf", response_model=CsrfResponse, summary="Get a CSRF token")
def get_csrf(request: Request, response: Response) -> CsrfResponse:
    _mark_no_store(response)
    existing = request.cookies.get(csrf_cookie_name())
    token = existing if existing and 32 <= len(existing) <= 256 else _issue_csrf(response)
    if token == existing:
        _set_csrf_cookie(response, token)
    return CsrfResponse(csrf_token=token)


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    _: None = Depends(require_csrf),
) -> AuthResponse:
    _enforce_rate_limit(
        purpose="register",
        request=request,
        identity="",
        limit=settings.AUTH_REGISTER_RATE_LIMIT,
        window_seconds=settings.AUTH_REGISTER_RATE_WINDOW_SECONDS,
    )
    try:
        result = auth_service.register(email=payload.email, password=payload.password)
    except AccountAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        ) from None
    except SQLAlchemyError:
        _raise_service_unavailable()

    _mark_no_store(response)
    _set_session_cookie(response, result.session_token)
    csrf_token = _issue_csrf(response)
    return AuthResponse(
        user=UserResponse.model_validate(result.user),
        csrf_token=csrf_token,
    )


@router.post("/login", response_model=AuthResponse, summary="Log in")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    _: None = Depends(require_csrf),
) -> AuthResponse:
    _enforce_rate_limit(
        purpose="login",
        request=request,
        identity=payload.email,
        limit=settings.AUTH_LOGIN_RATE_LIMIT,
        window_seconds=settings.AUTH_LOGIN_RATE_WINDOW_SECONDS,
    )
    try:
        result = auth_service.login(email=payload.email, password=payload.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
        ) from None
    except SQLAlchemyError:
        _raise_service_unavailable()

    _mark_no_store(response)
    _set_session_cookie(response, result.session_token)
    csrf_token = _issue_csrf(response)
    return AuthResponse(
        user=UserResponse.model_validate(result.user),
        csrf_token=csrf_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Log out")
def logout(
    request: Request,
    response: Response,
    _: None = Depends(require_csrf),
) -> None:
    # Logout is idempotent, including for an expired session. The CSRF token
    # and exact-origin check still protect this state-changing endpoint.
    token = request.cookies.get(session_cookie_name())
    if token:
        try:
            auth_service.revoke(session_token=token)
        except SQLAlchemyError:
            _raise_service_unavailable()

    _mark_no_store(response)
    response.delete_cookie(
        key=session_cookie_name(),
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
    response.delete_cookie(
        key=csrf_cookie_name(),
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
    return None


@router.get("/me", response_model=UserResponse, summary="Get the current account")
def get_me(
    response: Response,
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    _mark_no_store(response)
    return UserResponse.model_validate(current_user)
