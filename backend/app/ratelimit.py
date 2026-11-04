"""In-process token-bucket rate limiter.

Per-instance only — fine for a single Cloud Run instance or as a first line of defense. For
multi-instance enforcement, back this with Redis (same interface). Pure + clock-injectable so it
unit-tests deterministically.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class RateLimiter:
    def __init__(self, per_minute: int, burst: int) -> None:
        self.refill_per_sec = per_minute / 60.0
        self.capacity = float(burst)
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    def _check(self, key: str, now: float) -> tuple[bool, float]:
        bucket = self._buckets.get(key)
        if bucket is None:
            self._buckets[key] = _Bucket(tokens=self.capacity - 1.0, updated_at=now)
            return True, 0.0
        elapsed = max(0.0, now - bucket.updated_at)
        bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_per_sec)
        bucket.updated_at = now
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True, 0.0
        retry_after = (1.0 - bucket.tokens) / self.refill_per_sec if self.refill_per_sec else 60.0
        return False, retry_after

    async def allow(self, key: str, now: float) -> tuple[bool, float]:
        async with self._lock:
            return self._check(key, now)
