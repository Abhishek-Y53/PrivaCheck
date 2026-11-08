"""Valkey/Redis-backed fixed-window rate limiting for authentication endpoints."""

from __future__ import annotations

import hashlib
from typing import Any

from backend.core.config import settings


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__("Rate limit exceeded")


class RateLimiterUnavailable(Exception):
    """Authentication fails closed when the configured rate-limit store is down."""


_INCREMENT_WITH_TTL = """
local pair_count = redis.call('INCR', KEYS[1])
if pair_count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ip_count = redis.call('INCR', KEYS[2])
if ip_count == 1 then
    redis.call('EXPIRE', KEYS[2], ARGV[1])
end
return {pair_count, ip_count}
"""


class AuthRateLimiter:
    """Use the existing Valkey/Redis service; do not trust forwarded IP headers."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or settings.AUTH_RATE_LIMIT_REDIS_URL or settings.BROKER_URL
        self._client: Any | None = None

    def enforce(
        self,
        *,
        purpose: str,
        client_ip: str,
        identity: str = "",
        limit: int,
        window_seconds: int,
    ) -> None:
        material = f"{purpose}\0{client_ip}\0{identity}".encode("utf-8")
        digest = hashlib.sha256(material).hexdigest()
        ip_digest = hashlib.sha256(
            f"{purpose}\0{client_ip}".encode("utf-8")
        ).hexdigest()
        pair_key = f"privacheck:auth:rate:{purpose}:pair:{digest}"
        ip_key = f"privacheck:auth:rate:{purpose}:ip:{ip_digest}"
        try:
            pair_count, ip_count = self._get_client().eval(
                _INCREMENT_WITH_TTL, 2, pair_key, ip_key, window_seconds
            )
            pair_count = int(pair_count)
            ip_count = int(ip_count)
        except Exception as exc:
            raise RateLimiterUnavailable from exc
        # Per email/IP pair and a broader per-IP ceiling prevent rotating email
        # addresses from bypassing the endpoint-level throttle. Keep the IP burst
        # bounded to reduce concurrent Argon2 memory pressure.
        if pair_count > limit or ip_count > limit * 2:
            raise RateLimitExceeded(window_seconds)

    def _get_client(self):
        if self._client is None:
            try:
                from redis import Redis
            except ImportError as exc:
                raise RateLimiterUnavailable from exc
            self._client = Redis.from_url(
                self.redis_url,
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=True,
            )
        return self._client
