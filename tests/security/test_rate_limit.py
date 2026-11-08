import pytest

from backend.security.rate_limit import (
    AuthRateLimiter,
    RateLimitExceeded,
    RateLimiterUnavailable,
)


class FakeRedis:
    def __init__(self, pair_count: int, ip_count: int):
        self.pair_count = pair_count
        self.ip_count = ip_count
        self.call = None

    def eval(self, *args):
        self.call = args
        return [self.pair_count, self.ip_count]


def test_rate_limiter_hashes_identity_and_uses_atomic_two_key_script():
    redis = FakeRedis(pair_count=2, ip_count=3)
    limiter = AuthRateLimiter("redis://unused")
    limiter._client = redis

    limiter.enforce(
        purpose="login",
        client_ip="192.0.2.10",
        identity="person@example.com",
        limit=5,
        window_seconds=60,
    )

    assert redis.call[1] == 2
    assert "person@example.com" not in str(redis.call)
    assert redis.call[-1] == 60


def test_rate_limiter_rejects_pair_or_ip_over_limit():
    for pair_count, ip_count in ((6, 6), (1, 11)):
        limiter = AuthRateLimiter("redis://unused")
        limiter._client = FakeRedis(pair_count, ip_count)
        with pytest.raises(RateLimitExceeded):
            limiter.enforce(
                purpose="login",
                client_ip="192.0.2.10",
                identity="person@example.com",
                limit=5,
                window_seconds=60,
            )


def test_rate_limiter_fails_closed_when_redis_is_unavailable():
    class BrokenRedis:
        def eval(self, *_args):
            raise OSError("connection refused")

    limiter = AuthRateLimiter("redis://unused")
    limiter._client = BrokenRedis()
    with pytest.raises(RateLimiterUnavailable):
        limiter.enforce(
            purpose="login",
            client_ip="192.0.2.10",
            identity="person@example.com",
            limit=5,
            window_seconds=60,
        )
