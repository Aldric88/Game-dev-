"""Sliding-window rate limiter for AI requests.

Uses Redis sorted sets when REDIS_URL is configured, giving accurate
cross-worker enforcement. Falls back to a process-local in-memory
implementation when Redis is unavailable or not configured (dev / single-worker).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque

from app.core.config import settings

_rl_logger = logging.getLogger(__name__)


class RateLimitResult:
    def __init__(self, allowed: bool, retry_after_seconds: int = 0) -> None:
        self.allowed = allowed
        self.retry_after_seconds = retry_after_seconds


# ── In-memory backend (single-process fallback) ────────────────────────────────

class _InMemoryBackend:
    def __init__(self, max_requests: int) -> None:
        self._max = max_requests
        self._events: dict[str, deque] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> RateLimitResult:
        async with self._lock:
            now = time.monotonic()
            window = self._events[key]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) < self._max:
                window.append(now)
                return RateLimitResult(allowed=True)
            retry_after = int(60 - (now - window[0]))
            return RateLimitResult(allowed=False, retry_after_seconds=max(1, retry_after))


# ── Redis backend ──────────────────────────────────────────────────────────────

class _RedisBackend:
    """Sliding window using a Redis sorted set per user key.

    Each member's score is its Unix timestamp. Members older than 60 s are
    pruned on every check via ZREMRANGEBYSCORE, keeping the set small.
    All operations run in a single pipeline round-trip.
    """

    def __init__(self, redis_url: str, max_requests: int) -> None:
        self._url = redis_url
        self._max = max_requests
        self._client = None
        self._init_lock = asyncio.Lock()

    async def _get_client(self):
        if self._client is None:
            async with self._init_lock:
                if self._client is None:
                    import certifi
                    import redis.asyncio as aioredis
                    extra: dict = {}
                    if self._url.startswith("rediss://"):
                        extra["ssl_ca_certs"] = certifi.where()
                    self._client = aioredis.from_url(
                        self._url,
                        encoding="utf-8",
                        decode_responses=True,
                        socket_connect_timeout=2,
                        **extra,
                    )
        return self._client

    async def check(self, key: str) -> RateLimitResult:
        client = await self._get_client()
        now = time.time()
        window_start = now - 60
        rkey = f"rl:{key}"
        member = str(uuid.uuid4())

        pipe = client.pipeline()
        pipe.zremrangebyscore(rkey, "-inf", window_start)
        pipe.zadd(rkey, {member: now})
        pipe.zcard(rkey)
        pipe.zrange(rkey, 0, 0, withscores=True)   # oldest remaining member
        pipe.expire(rkey, 120)                       # auto-cleanup TTL
        results = await pipe.execute()

        count: int = results[2]
        if count <= self._max:
            return RateLimitResult(allowed=True)

        oldest_score: float = results[3][0][1] if results[3] else now
        retry_after = int(60 - (now - oldest_score))
        return RateLimitResult(allowed=False, retry_after_seconds=max(1, retry_after))


# ── Public facade ──────────────────────────────────────────────────────────────

class SlidingWindowRateLimiter:
    """Rate limiter with automatic Redis / in-memory backend selection."""

    def __init__(self, max_requests_per_minute: int) -> None:
        self.max_requests_per_minute = max_requests_per_minute
        self._backend = self._build_backend()

    def _build_backend(self):
        redis_url = settings.redis_url.strip()
        if redis_url:
            try:
                import redis.asyncio  # noqa: F401
                _rl_logger.info("Rate limiter using Redis backend: %s", redis_url)
                return _RedisBackend(redis_url, self.max_requests_per_minute)
            except ImportError:
                _rl_logger.warning(
                    "redis[asyncio] not installed — falling back to in-memory rate limiter. "
                    "Run: pip install 'redis[asyncio]'"
                )
        else:
            _rl_logger.warning(
                "REDIS_URL not configured — using in-memory rate limiter "
                "(not safe for multi-worker deployments)."
            )
        return _InMemoryBackend(self.max_requests_per_minute)

    async def check(self, user_id: str) -> RateLimitResult:
        try:
            return await self._backend.check(user_id)
        except Exception as exc:
            # Fail open: Redis downtime should not block all users.
            _rl_logger.warning(
                "Rate limiter backend error (%s), allowing request: %s",
                type(exc).__name__,
                exc,
            )
            return RateLimitResult(allowed=True)


ai_rate_limiter = SlidingWindowRateLimiter(
    max_requests_per_minute=settings.ai_max_requests_per_minute
)
