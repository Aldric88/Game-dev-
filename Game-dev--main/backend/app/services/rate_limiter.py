"""Sliding-window rate limiter for AI requests."""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import datetime, timezone

from app.core.config import settings


class RateLimitResult:
    def __init__(self, allowed: bool, retry_after_seconds: int = 0) -> None:
        self.allowed = allowed
        self.retry_after_seconds = retry_after_seconds


class SlidingWindowRateLimiter:
    def __init__(self, max_requests_per_minute: int) -> None:
        self.max_requests_per_minute = max_requests_per_minute
        self._events: dict[str, deque] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, user_id: str) -> RateLimitResult:
        async with self._lock:
            now = datetime.now(timezone.utc)
            window = self._events[user_id]

            # Remove events older than 60 seconds
            while window and (now - window[0]).total_seconds() > 60:
                window.popleft()

            if len(window) < self.max_requests_per_minute:
                window.append(now)
                return RateLimitResult(allowed=True)

            oldest = window[0]
            retry_after = int(60 - (now - oldest).total_seconds())
            return RateLimitResult(allowed=False, retry_after_seconds=max(1, retry_after))


ai_rate_limiter = SlidingWindowRateLimiter(
    max_requests_per_minute=settings.ai_max_requests_per_minute
)
