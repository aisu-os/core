import asyncio
import time
from collections import deque
from functools import lru_cache
from typing import Protocol

from fastapi import HTTPException, status
from redis import asyncio as redis
from redis.exceptions import RedisError

from aiso_core.config import settings

_RATE_LIMIT_LUA = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
  redis.call("EXPIRE", KEYS[1], ARGV[1])
end
return current
"""


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_seconds: int) -> None: ...


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._requests: dict[str, deque[float]] = {}

    async def hit(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds

        async with self._lock:
            queue = self._requests.get(key)
            if queue is None:
                queue = deque()
                self._requests[key] = queue

            while queue and queue[0] <= cutoff:
                queue.popleft()

            if len(queue) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                )

            queue.append(now)


class RedisRateLimiter:
    def __init__(self, redis_url: str) -> None:
        self._redis = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    async def hit(self, key: str, limit: int, window_seconds: int) -> None:
        try:
            current = await self._redis.eval(_RATE_LIMIT_LUA, 1, key, window_seconds)
        except RedisError as err:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limiter unavailable",
            ) from err

        if int(current) > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )


@lru_cache
def get_rate_limiter() -> RateLimiter:
    backend = settings.rate_limit_backend.lower()
    if backend == "memory":
        return InMemoryRateLimiter()
    if backend == "redis":
        return RedisRateLimiter(settings.rate_limit_redis_url)

    raise ValueError(f"Unknown rate limit backend: {settings.rate_limit_backend}")
