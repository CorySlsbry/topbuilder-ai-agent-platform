"""HTTP middleware: request context + logging + security headers, and rate limiting."""
from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.errors import error_response
from app.logging_config import get_logger
from app.ratelimit import RateLimiter

log = get_logger("http")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "X-XSS-Protection": "0",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, hsts_enabled: bool = False) -> None:
        super().__init__(app)
        self.hsts_enabled = hsts_enabled

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, method=request.method, path=request.url.path
        )
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if self.hsts_enabled:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        log.info(
            "request_completed",
            status=response.status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    # Only liveness probes are exempt — /docs etc. stay throttled (and are dev-gated in main.py).
    EXEMPT = {"/", "/health", "/health/db"}

    def __init__(self, app, limiter: RateLimiter, trusted_proxy_hops: int = 1) -> None:
        super().__init__(app)
        self.limiter = limiter
        # How many RIGHTMOST X-Forwarded-For entries are set by trusted infra (Cloud Run GFE/GLB = 1).
        self.trusted_proxy_hops = max(0, trusted_proxy_hops)

    def _client_key(self, request: Request) -> str:
        # SECURITY: never key the limiter on the CLIENT-MOST (leftmost) X-Forwarded-For entry — a caller
        # can spoof it (`X-Forwarded-For: 1.2.3.4`) to mint unlimited buckets and bypass the limit. The
        # trusted proxy (Cloud Run GFE) APPENDS the real client on the right, so the genuine caller is the
        # entry immediately to the LEFT of the `trusted_proxy_hops` infra entries. Falls back to the peer
        # address when the header is absent (direct/local).
        xff = request.headers.get("x-forwarded-for")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                idx = max(0, len(parts) - 1 - self.trusted_proxy_hops)
                return parts[idx]
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in self.EXEMPT:
            return await call_next(request)
        client = self._client_key(request)
        allowed, retry_after = await self.limiter.allow(client, time.monotonic())
        if not allowed:
            response = error_response(429, "rate_limited", "Too many requests", request)
            response.headers["Retry-After"] = str(int(retry_after) + 1)
            return response
        return await call_next(request)
